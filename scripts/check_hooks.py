#!/usr/bin/env python3
"""Query Codex app-server for authoritative plugin-hook discovery and trust."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


EXPECTED_EVENTS = {"postToolUse", "userPromptSubmit", "subagentStart", "subagentStop", "stop"}
CHECKER_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_SCHEMA_VERSION = 1
CAPABILITY_SIGNATURE = "direct-model-spawn-v1"
ROOT_OBSERVATION_FILE = "root-observation-v1.json"
CAPABILITY_FILE = "capability-v1.json"


def _send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    process.stdin.flush()


def _wait_for(process: subprocess.Popen[str], request_id: int, timeout: float = 10.0) -> dict[str, Any]:
    assert process.stdout is not None
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"timed out waiting for app-server request {request_id}")
        lines: queue.Queue[str] = queue.Queue(maxsize=1)
        reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty as exc:
            raise RuntimeError(f"timed out waiting for app-server request {request_id}") from exc
        if not line:
            raise RuntimeError("app-server closed before returning hook status")
        message = json.loads(line)
        if message.get("id") == request_id:
            if "error" in message:
                raise RuntimeError(str(message["error"]))
            return message["result"]


def _effective_readiness(config_response: dict[str, Any], requirements_response: dict[str, Any], plugin_prefix: str) -> dict[str, Any]:
    config = config_response.get("config")
    if not isinstance(config, dict):
        raise RuntimeError("app-server returned an invalid config/read shape")
    requirements = requirements_response.get("requirements")
    if requirements is not None and not isinstance(requirements, dict):
        raise RuntimeError("app-server returned an invalid configRequirements/read shape")
    features = config.get("features") if isinstance(config.get("features"), dict) else {}
    agents = config.get("agents") if isinstance(config.get("agents"), dict) else {}
    plugins = config.get("plugins") if isinstance(config.get("plugins"), dict) else {}
    plugin_entry = next(
        (value for key, value in plugins.items() if str(key).startswith(plugin_prefix + "@") and isinstance(value, dict)),
        None,
    )
    managed_only = bool((requirements or {}).get("allowManagedHooksOnly"))
    hooks_enabled = features.get("hooks") is not False
    agents_enabled = agents.get("enabled") is not False
    plugin_enabled = bool(plugin_entry and plugin_entry.get("enabled") is True)
    return {
        "available": plugin_enabled and hooks_enabled and agents_enabled and not managed_only,
        "plugin_enabled": plugin_enabled,
        "hooks_enabled": hooks_enabled,
        "agents_enabled": agents_enabled,
        "managed_hooks_only": managed_only,
        "model": config.get("model"),
        "model_reasoning_effort": config.get("model_reasoning_effort"),
        "service_tier": config.get("service_tier"),
        "source": "app_server_effective_config_and_requirements",
    }


def _skill_binding(skill_entries: list[Any], plugin_prefix: str, checker_root: Path = CHECKER_ROOT) -> tuple[bool, dict[str, Any]]:
    skills = skill_entries[0].get("skills", []) if len(skill_entries) == 1 and isinstance(skill_entries[0], dict) else []
    expected_name = f"{plugin_prefix}:route-gpt-5-6-work"
    matches = [skill for skill in skills if isinstance(skill, dict) and skill.get("name") == expected_name]
    expected_path = (checker_root / "skills" / "route-gpt-5-6-work" / "SKILL.md").resolve()
    actual_path = Path(str(matches[0].get("path"))).resolve() if len(matches) == 1 and matches[0].get("path") else None
    manifest_path = checker_root / ".codex-plugin" / "plugin.json"
    try:
        version = json.loads(manifest_path.read_text(encoding="utf-8")).get("version")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read checker plugin manifest: {exc}") from exc
    errors = skill_entries[0].get("errors", []) if len(skill_entries) == 1 and isinstance(skill_entries[0], dict) else ["unexpected skills/list shape"]
    ready = len(matches) == 1 and matches[0].get("enabled") is True and actual_path == expected_path and not errors
    return ready, {
        "expected_name": expected_name,
        "discovered": len(matches) == 1,
        "enabled": matches[0].get("enabled") if len(matches) == 1 else False,
        "path_matches_checker_build": actual_path == expected_path,
        "version": version,
    }


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__
    if not isinstance(value, dict):
        return None, "invalid_shape"
    return value, None


def _routing_health(effective: dict[str, Any], plugin_version: str, data_root: Path) -> dict[str, Any]:
    """Evaluate saved hook evidence without creating files or paid child work."""
    observation, observation_error = _read_json_object(data_root / ROOT_OBSERVATION_FILE)
    receipt, receipt_error = _read_json_object(data_root / CAPABILITY_FILE)
    config_model = effective.get("model")
    observed_model = observation.get("root_model") if observation else None
    root_model = observed_model if isinstance(observed_model, str) and observed_model else config_model
    root_source = "hook_observation" if isinstance(observed_model, str) and observed_model else "effective_config"
    reasons: list[str] = []

    if not effective.get("available"):
        status = "UNAVAILABLE"
        reasons.append("The supported plugin hook and direct-child routing path is not available in effective configuration.")
    else:
        status = "DEGRADED"
        if observation_error:
            reasons.append(f"Authoritative root observation is unreadable ({observation_error}).")
        if observation is None:
            reasons.append("No authoritative UserPromptSubmit.model observation is available for an actual turn.")
        else:
            if observation.get("schema_version") != CAPABILITY_SCHEMA_VERSION:
                reasons.append("Root observation schema does not match this health checker.")
            if observation.get("plugin_version") != plugin_version:
                reasons.append("Root observation belongs to a different plugin version.")
            if not observation.get("timestamp"):
                reasons.append("Root observation has no timestamp.")

        if not isinstance(root_model, str) or not root_model:
            reasons.append("The effective root model is unknown.")
        elif not root_model.lower().endswith("luna"):
            reasons.append(
                f"Active root is {root_model}, not Luna; credit-saving behaviour will be substantially reduced for that turn."
            )

        if receipt_error:
            reasons.append(f"Capability receipt is unreadable ({receipt_error}).")
        if receipt is None:
            reasons.append("No successful Terra/Sol escalation receipt exists; no automatic paid probe was performed.")
        else:
            if receipt.get("schema_version") != CAPABILITY_SCHEMA_VERSION:
                reasons.append("Capability receipt schema does not match this health checker.")
            if receipt.get("capability_signature") != CAPABILITY_SIGNATURE:
                reasons.append("Capability receipt signature does not match the supported direct-spawn adapter.")
            if receipt.get("plugin_version") != plugin_version:
                reasons.append("Capability receipt belongs to a different plugin version.")
            if receipt.get("observed_child_model") not in {"gpt-5.6-terra", "gpt-5.6-sol"}:
                reasons.append("Capability receipt does not attest a Terra or Sol child.")
            if not receipt.get("effort_intent") or not receipt.get("timestamp"):
                reasons.append("Capability receipt lacks effort intent or timestamp evidence.")

        if observation is not None and receipt is not None:
            current_runtime = observation.get("runtime_version")
            current_build = observation.get("runtime_build")
            receipt_runtime = receipt.get("runtime_version")
            receipt_build = receipt.get("runtime_build")
            if not all(isinstance(value, str) and value for value in (current_runtime, current_build, receipt_runtime, receipt_build)):
                reasons.append("Codex runtime or build identity is unknown, so the capability receipt cannot establish READY.")
            elif current_runtime != receipt_runtime or current_build != receipt_build:
                reasons.append("Codex runtime or build changed after the last successful escalation receipt.")
            current_platform = observation.get("platform")
            receipt_platform = receipt.get("platform")
            if current_platform and receipt_platform and current_platform != receipt_platform:
                reasons.append("Capability receipt platform does not match the current hook observation.")
            current_host = observation.get("host_type")
            receipt_host = receipt.get("host_type")
            if current_host and receipt_host and current_host != receipt_host:
                reasons.append("Capability receipt host type does not match the current hook observation.")

        if not reasons:
            status = "READY"

    return {
        "status": status,
        "ready": status == "READY",
        "root_model": root_model,
        "root_model_source": root_source,
        "config_model": config_model,
        "reasons": reasons,
        "observation_present": observation is not None,
        "capability_receipt_present": receipt is not None,
        "automatic_paid_probe_performed": False,
        "data_root": str(data_root),
    }


def inspect(cwd: Path, plugin_prefix: str) -> dict[str, Any]:
    process = subprocess.Popen(
        ["codex", "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    try:
        _send(process, {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "gpt-5-6-router-hook-check", "version": "0.1"},
                "capabilities": {"experimentalApi": True},
            },
        })
        _wait_for(process, 1)
        _send(process, {"method": "initialized", "params": {}})
        _send(process, {"id": 2, "method": "hooks/list", "params": {"cwds": [str(cwd.resolve())]}})
        response = _wait_for(process, 2)
        _send(process, {"id": 3, "method": "skills/list", "params": {"cwds": [str(cwd.resolve())], "forceReload": True}})
        skills_response = _wait_for(process, 3)
        _send(process, {"id": 4, "method": "config/read", "params": {"cwd": str(cwd.resolve()), "includeLayers": False}})
        config_response = _wait_for(process, 4)
        _send(process, {"id": 5, "method": "configRequirements/read", "params": {}})
        requirements_response = _wait_for(process, 5)
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    entries = response.get("data", [])
    if len(entries) != 1:
        raise RuntimeError("app-server returned an unexpected hooks/list shape")
    entry = entries[0]
    hooks = [
        hook for hook in entry.get("hooks", [])
        if str(hook.get("pluginId") or "").startswith(plugin_prefix + "@")
    ]
    events = {str(hook.get("eventName")) for hook in hooks}
    skill_entries = skills_response.get("data", [])
    skill_ready, skill_summary = _skill_binding(skill_entries, plugin_prefix)
    effective = _effective_readiness(config_response, requirements_response, plugin_prefix)
    supported_path_available = (
        events == EXPECTED_EVENTS
        and len(hooks) == len(EXPECTED_EVENTS)
        and all(hook.get("source") == "plugin" and hook.get("enabled") and hook.get("trustStatus") == "trusted" for hook in hooks)
        and not entry.get("warnings")
        and not entry.get("errors")
        and skill_ready
        and effective["available"]
    )
    effective["available"] = supported_path_available
    data_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    health = _routing_health(effective, str(skill_summary.get("version") or ""), data_home / plugin_prefix)
    return {
        "plugin": plugin_prefix,
        "cwd_checked": bool(entry.get("cwd")),
        "ready": health["ready"],
        "status": health["status"],
        "root_model": health["root_model"],
        "root_model_source": health["root_model_source"],
        "reasons": health["reasons"],
        "readiness_scope": "OBSERVED_ROOT_AND_RUNTIME_BOUND_CAPABILITY",
        "live_delegation_required": health["status"] != "READY",
        "hooks": [
            {
                "event": hook.get("eventName"),
                "enabled": hook.get("enabled"),
                "trust": hook.get("trustStatus"),
                "source": hook.get("source"),
                "plugin_id": hook.get("pluginId"),
            }
            for hook in hooks
        ],
        "skill": skill_summary,
        "legacy_custom_agents": {"required": False, "checked": False},
        "effective": effective,
        "health": health,
        "warnings": entry.get("warnings", []),
        "errors": entry.get("errors", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check GPT-5.6 Router hook discovery and trust")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--plugin", default="gpt-5-6-router")
    args = parser.parse_args()
    try:
        result = inspect(args.cwd, args.plugin)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ready": False, "status": "UNAVAILABLE", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "READY" else (1 if result["status"] == "DEGRADED" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
