"""One experimental, single-use Codex thread over App Server stdio."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

ROUTER_NAME = "gpt-5-6-router"
REQUEST_SECONDS = 30
TURN_SECONDS = 1800
MAX_FRAME = 8 * 1024 * 1024
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
APPROVAL_METHODS = {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}
TOKEN_FIELDS = ("inputTokens", "cachedInputTokens", "cacheWriteInputTokens",
                "outputTokens", "reasoningOutputTokens", "totalTokens")


class RunError(Exception):
    """A safe diagnostic code without provider payloads."""


def executor_environment(credential_name: str) -> dict[str, str]:
    secret = os.environ.get(credential_name)
    excluded = {credential_name.upper(), "OPENAI_API_KEY", "CODEX_API_KEY"}
    return {key: value for key, value in os.environ.items()
            if key.upper() not in excluded and (not secret or secret not in value)}


class Stdio:
    def __init__(self, cwd: Path, env: dict[str, str]):
        group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                 else {"start_new_session": True})
        self.process = subprocess.Popen(["codex", "app-server", "--stdio"], cwd=cwd, env=env,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, **group)
        self.frames = queue.Queue(maxsize=8)
        self.stopped = threading.Event()
        self.serial = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        while not self.stopped.is_set():
            try:
                line = self.process.stdout.readline(MAX_FRAME + 1)
            except (OSError, ValueError):
                line = b""
            while not self.stopped.is_set():
                try:
                    self.frames.put(line, timeout=0.1)
                    break
                except queue.Full:
                    continue
            if not line or len(line) > MAX_FRAME:
                return

    def send(self, message: dict):
        self.process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        self.process.stdin.flush()

    def receive(self, deadline: float) -> dict:
        try:
            line = self.frames.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty as exc:
            raise RunError("app_server_timeout") from exc
        if not line:
            raise RunError("app_server_closed")
        if len(line) > MAX_FRAME or not line.endswith(b"\n"):
            raise RunError("invalid_protocol_frame")
        try:
            message = json.loads(line)
        except (ValueError, RecursionError) as exc:
            raise RunError("invalid_protocol_frame") from exc
        if not isinstance(message, dict):
            raise RunError("invalid_protocol_frame")
        return message

    def event(self, message: dict, observe):
        if "id" not in message:
            if "method" not in message:
                raise RunError("invalid_protocol_message")
            observe(message)
            return
        method = message.get("method")
        if not isinstance(method, str):
            raise RunError("invalid_server_request")
        if method in APPROVAL_METHODS:
            response = {"result": {"decision": "cancel"}}
        elif method == "item/permissions/requestApproval":
            response = {"result": {"permissions": {}, "scope": "turn"}}
        else:
            self.send({"id": message["id"], "error": {"code": -32601, "message": "Request unsupported"}})
            raise RunError("unsupported_server_request")
        self.send({"id": message["id"], **response})
        raise RunError("approval_required")

    def call(self, method: str, params: dict, observe=lambda _: None, timeout=REQUEST_SECONDS) -> dict:
        self.serial += 1
        self.send({"id": self.serial, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                raise RunError("app_server_timeout")
            message = self.receive(deadline)
            if "method" not in message and type(message.get("id")) is int and message["id"] == self.serial:
                if "error" in message:
                    raise RunError(f"{method}_rejected")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise RunError("invalid_protocol_response")
                return result
            self.event(message, observe)

    def close(self):
        self.stopped.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()


def router_id(value) -> bool:
    return isinstance(value, str) and value.partition("@")[0] == ROUTER_NAME and "@" in value


def disabled_router_ids(server: Stdio, cwd: Path) -> list[str]:
    config = server.call("config/read", {"cwd": str(cwd), "includeLayers": False}).get("config")
    if not isinstance(config, dict) or (config.get("plugins") is not None and not isinstance(config["plugins"], dict)):
        raise RunError("plugin_discovery_unverified")
    ids = {key for key in config.get("plugins") or {} if router_id(key)}
    listing = server.call("plugin/list", {"cwds": [str(cwd)], "marketplaceKinds": ["local"], "forceRefetch": False})
    markets = listing.get("marketplaces")
    if not isinstance(markets, list) or listing.get("marketplaceLoadErrors"):
        raise RunError("plugin_discovery_unverified")
    for market in markets:
        plugins = market.get("plugins") if isinstance(market, dict) else None
        if not isinstance(plugins, list):
            raise RunError("plugin_discovery_unverified")
        for plugin in plugins:
            if not isinstance(plugin, dict) or not isinstance(plugin.get("id"), str):
                raise RunError("plugin_discovery_unverified")
            if router_id(plugin["id"]):
                ids.add(plugin["id"])
            elif plugin.get("name") == ROUTER_NAME:
                raise RunError("plugin_discovery_unverified")
    return sorted(ids)


def verify_hooks(server: Stdio, thread_id: str):
    entries = server.call("hooks/list", {"threadId": thread_id}).get("data")
    if not isinstance(entries, list) or not entries:
        raise RunError("plugin_disable_unverified")
    for entry in entries:
        hooks = entry.get("hooks") if isinstance(entry, dict) else None
        if not isinstance(hooks, list) or entry.get("errors"):
            raise RunError("plugin_disable_unverified")
        for hook in hooks:
            if not isinstance(hook, dict) or not isinstance(hook.get("enabled"), bool):
                raise RunError("plugin_disable_unverified")
            if not hook["enabled"]:
                continue
            plugin_id = hook.get("pluginId")
            source = hook.get("source")
            path = hook.get("sourcePath")
            command = hook.get("command", "")
            if (not isinstance(path, str) or not isinstance(command, str) or not isinstance(source, str)
                    or (source == "plugin" and not isinstance(plugin_id, str))):
                raise RunError("plugin_disable_unverified")
            if router_id(plugin_id) or any(piece in (path + " " + command).lower()
                                           for piece in (ROUTER_NAME, "route-gpt-5-6-work")):
                raise RunError("autorouter_hook_still_enabled")


def label(value):
    return value if isinstance(value, str) and LABEL.fullmatch(value) else None


def execute(cwd: Path, task: str, model: str, effort: str, env: dict[str, str]) -> dict:
    report = {"requested": {"model": model, "effort": effort}, "thread_id": None, "turn_id": None,
              "turn_status": "not_started", "failure": None, "native_reroutes": [], "server_settings": None,
              "runtime": {"model": None, "effort": None}, "exact_model_acceptance": "unverified",
              "codex_usage": None, "answer": None, "interrupt_acknowledged": False}
    server = None
    settings_mismatch = False

    def bind(turn_id):
        if not isinstance(turn_id, str) or not turn_id or (report["turn_id"] not in (None, turn_id)):
            raise RunError("turn_identity_mismatch")
        report["turn_id"] = turn_id

    def take_answer(item):
        if (isinstance(item, dict) and item.get("type") == "agentMessage"
                and item.get("phase") in (None, "final_answer") and isinstance(item.get("text"), str)):
            report["answer"] = item["text"]

    def observe(message):
        nonlocal settings_mismatch
        method, params = message.get("method"), message.get("params")
        if not isinstance(method, str):
            raise RunError("invalid_protocol_message")
        if not isinstance(params, dict) or params.get("threadId") != report["thread_id"]:
            return
        if method == "thread/settings/updated":
            settings = params.get("threadSettings")
            if isinstance(settings, dict):
                values = {"model": label(settings.get("model")), "effort": label(settings.get("effort"))}
                report["server_settings"] = values
                settings_mismatch |= any(value is not None and value != report["requested"][key]
                                         for key, value in values.items())
        elif method in {"turn/started", "turn/completed"}:
            turn = params.get("turn")
            if not isinstance(turn, dict):
                raise RunError("invalid_turn_notification")
            bind(turn.get("id"))
            if method == "turn/completed":
                status = turn.get("status")
                if status not in {"completed", "failed", "interrupted"}:
                    raise RunError("invalid_turn_status")
                report["turn_status"] = status
                if report["answer"] is None and isinstance(turn.get("items"), list):
                    for item in turn["items"]:
                        take_answer(item)
        elif method in {"model/rerouted", "thread/tokenUsage/updated", "item/completed"}:
            bind(params.get("turnId"))
            if method == "model/rerouted":
                if len(report["native_reroutes"]) >= 64:
                    raise RunError("too_many_native_reroutes")
                report["native_reroutes"].append({"from_model": label(params.get("fromModel")),
                                                 "to_model": label(params.get("toModel")),
                                                 "reason": label(params.get("reason"))})
            elif method == "thread/tokenUsage/updated":
                usage = params.get("tokenUsage")
                total = usage.get("total") if isinstance(usage, dict) else None
                if isinstance(total, dict):
                    report["codex_usage"] = {key: total[key] for key in TOKEN_FIELDS
                                             if type(total.get(key)) is int and total[key] >= 0} or None
            else:
                take_answer(params.get("item"))

    try:
        server = Stdio(cwd, env)
        server.call("initialize", {"clientInfo": {"name": "autorouter", "version": "0.1"},
                                   "capabilities": {"experimentalApi": True, "explicitGatewayOauth": True}})
        server.send({"method": "initialized", "params": {}})
        account = server.call("account/read", {"refreshToken": False}).get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            raise RunError("chatgpt_sign_in_required")
        disabled = disabled_router_ids(server, cwd)
        config = {"model_reasoning_effort": effort}
        if disabled:
            config["plugins"] = {plugin_id: {"enabled": False} for plugin_id in disabled}
        started = server.call("thread/start", {"cwd": str(cwd), "model": model, "config": config, "ephemeral": True})
        if started.get("modelProvider") != "openai":
            raise RunError("unexpected_codex_provider")
        if started.get("model") != model or started.get("reasoningEffort") not in (None, effort):
            settings_mismatch = True
            raise RunError("thread_model_or_effort_mismatch")
        thread = started.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise RunError("thread_identity_unverified")
        report["thread_id"] = thread_id
        verify_hooks(server, thread_id)
        report["turn_status"] = "unknown"
        turn = server.call("turn/start", {"threadId": thread_id, "model": model, "effort": effort,
                                         "disabledPluginIds": disabled,
                                         "input": [{"type": "text", "text": task, "text_elements": []}]}, observe)
        info = turn.get("turn")
        bind(info.get("id") if isinstance(info, dict) else None)
        deadline = time.monotonic() + TURN_SECONDS
        while report["turn_status"] == "unknown":
            if time.monotonic() >= deadline:
                raise RunError("turn_timeout")
            server.event(server.receive(deadline), observe)
    except KeyboardInterrupt:
        report["failure"] = "cancelled"
    except RunError as exc:
        report["failure"] = str(exc)
    except (OSError, subprocess.SubprocessError):
        report["failure"] = "app_server_io_failure"
    finally:
        if server is not None:
            if report["failure"] and report["turn_status"] == "unknown" and report["turn_id"]:
                try:
                    server.call("turn/interrupt", {"threadId": report["thread_id"], "turnId": report["turn_id"]},
                                observe, timeout=3)
                    report["interrupt_acknowledged"] = True
                except (RunError, OSError, KeyboardInterrupt):
                    pass
            try:
                server.close()
            except (OSError, subprocess.SubprocessError):
                report["failure"] = report["failure"] or "app_server_cleanup_failed"
    if report["native_reroutes"] or settings_mismatch:
        report["exact_model_acceptance"] = "failed"
    # v0.170 settings and completion events do not attest inference identity or effort.
    if report["turn_status"] in {"failed", "interrupted"} and report["failure"] is None:
        report["failure"] = "turn_" + report["turn_status"]
    return report
