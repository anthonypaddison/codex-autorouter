#!/usr/bin/env python3
"""Query Codex app-server for authoritative plugin-hook discovery and trust."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
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
ROOT_OBSERVATIONS_DIRECTORY = "root-observations-v1"
CAPABILITY_FILE = "capability-v1.json"
CAPABILITY_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
PLUGIN_IDENTITY_FILES = (
    ".codex-plugin/plugin.json",
    "hooks/hooks.json",
    "scripts/check_hooks.py",
    "scripts/hook_launcher.py",
    "skills/route-gpt-5-6-work/SKILL.md",
    "skills/route-gpt-5-6-work/scripts/router_hook.py",
    "skills/route-gpt-5-6-work/scripts/spawn_compat.py",
)


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


def _plugin_identity(root: Path = CHECKER_ROOT) -> str | None:
    digest = hashlib.sha256()
    try:
        for relative in PLUGIN_IDENTITY_FILES:
            path = root / relative
            if path.is_symlink() or not path.is_file():
                return None
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    except OSError:
        return None
    return f"sha256:{digest.hexdigest()}"


def _task_observation_path(data_root: Path, session_id: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", session_id):
        return None
    return data_root / ROOT_OBSERVATIONS_DIRECTORY / f"{session_id}.json"


def _timestamp(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _routing_health(
    effective: dict[str, Any],
    plugin_version: str,
    data_root: Path,
    *,
    plugin_identity: str | None = None,
    current_session_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate saved hook evidence without creating files or paid child work."""
    global_observation, global_observation_error = _read_json_object(data_root / ROOT_OBSERVATION_FILE)
    session_id = str(
        current_session_id
        or os.environ.get("CODEX_SESSION_ID")
        or os.environ.get("CODEX_THREAD_ID")
        or ""
    )
    observation: dict[str, Any] | None = None
    observation_error: str | None = None
    if session_id:
        task_path = _task_observation_path(data_root, session_id)
        if task_path is None:
            observation_error = "invalid_session_identity"
        else:
            observation, observation_error = _read_json_object(task_path)
        if observation is None and observation_error is None and global_observation is not None:
            if str(global_observation.get("session_id") or "") == session_id:
                observation = global_observation
                observation_error = global_observation_error
    else:
        observation = global_observation
        observation_error = global_observation_error
    receipt, receipt_error = _read_json_object(data_root / CAPABILITY_FILE)
    current_plugin_identity = plugin_identity or _plugin_identity()
    config_model = effective.get("model")
    observed_model = observation.get("root_model") if observation and session_id else None
    root_model = observed_model if isinstance(observed_model, str) and observed_model else config_model
    root_source = "hook_observation" if isinstance(observed_model, str) and observed_model else "effective_config"
    reasons: list[str] = []
    current_task_root_state = "UNKNOWN"
    historical_escalation_state = "NO ESCALATION RECEIPT"
    current_runtime_capability_state = "NO_EVIDENCE"
    observation_compatible = observation is not None

    receipt_child_model = receipt.get("observed_child_model") if receipt else None
    if receipt is not None and receipt_child_model in {"gpt-5.6-terra", "gpt-5.6-sol"} and _timestamp(receipt.get("timestamp")) is not None:
        historical_escalation_state = "ESCALATION PREVIOUSLY OBSERVED"

    if not effective.get("available"):
        status = "UNAVAILABLE"
        reasons.append("The supported plugin hook and direct-child routing path is not available in effective configuration.")
    else:
        status = "DEGRADED"
        if not session_id:
            reasons.append("Authoritative current task context is unavailable; a global root summary cannot establish task readiness.")
        if observation_error:
            reasons.append(f"Authoritative root observation is unreadable ({observation_error}).")
        if observation is None:
            reasons.append("No authoritative UserPromptSubmit.model observation is available for the current task.")
        else:
            if observation.get("schema_version") != CAPABILITY_SCHEMA_VERSION:
                reasons.append("Root observation schema does not match this health checker.")
                observation_compatible = False
            if observation.get("plugin_version") != plugin_version:
                reasons.append("Root observation belongs to a different plugin version.")
                observation_compatible = False
            if not current_plugin_identity or observation.get("plugin_identity") != current_plugin_identity:
                reasons.append("Root observation belongs to a different or unidentifiable plugin candidate.")
                observation_compatible = False
            if session_id and observation.get("session_id") != session_id:
                reasons.append("Root observation belongs to a different task.")
                observation_compatible = False
            if not observation.get("turn_id"):
                reasons.append("Root observation has no authoritative turn identity.")
                observation_compatible = False
            if _timestamp(observation.get("timestamp")) is None:
                reasons.append("Root observation has no timestamp.")
                observation_compatible = False

        if not isinstance(root_model, str) or not root_model:
            reasons.append("The effective root model is unknown.")
        elif not root_model.lower().endswith("luna"):
            if observation is not None and session_id:
                current_task_root_state = "DEGRADED_NON_LUNA"
                reasons.append(
                    f"Active root is {root_model}, not Luna; credit-saving behaviour will be substantially reduced for that turn."
                )
            else:
                reasons.append(
                    f"The supporting configuration reports {root_model}, not Luna, but cannot establish the current task's active root."
                )
        elif observation is not None and session_id:
            current_task_root_state = "CHEAP_ROOT"

        if receipt_error:
            reasons.append(f"Capability receipt is unreadable ({receipt_error}).")
        if receipt is None:
            reasons.append("No successful Terra/Sol escalation receipt exists; no automatic paid probe was performed.")
        else:
            receipt_compatible = observation_compatible
            if receipt.get("schema_version") != CAPABILITY_SCHEMA_VERSION:
                reasons.append("Capability receipt schema does not match this health checker.")
                receipt_compatible = False
            if receipt.get("capability_signature") != CAPABILITY_SIGNATURE:
                reasons.append("Capability receipt signature does not match the supported direct-spawn adapter.")
                receipt_compatible = False
            if receipt.get("plugin_version") != plugin_version:
                reasons.append("Capability receipt belongs to a different plugin version.")
                receipt_compatible = False
            if not current_plugin_identity or receipt.get("plugin_identity") != current_plugin_identity:
                reasons.append("Capability receipt belongs to a different or unidentifiable plugin candidate.")
                receipt_compatible = False
            if receipt.get("observed_child_model") not in {"gpt-5.6-terra", "gpt-5.6-sol"}:
                reasons.append("Capability receipt does not attest a Terra or Sol child.")
                receipt_compatible = False
            receipt_timestamp = _timestamp(receipt.get("timestamp"))
            if not receipt.get("effort_intent") or receipt_timestamp is None:
                reasons.append("Capability receipt lacks effort intent or timestamp evidence.")
                receipt_compatible = False
            else:
                receipt_age = int(time.time()) - receipt_timestamp
                if receipt_age > CAPABILITY_MAX_AGE_SECONDS:
                    reasons.append("Capability receipt is stale and cannot establish present runtime compatibility.")
                    current_runtime_capability_state = "STALE"
                    receipt_compatible = False
                elif receipt_age < -300:
                    reasons.append("Capability receipt timestamp is in the future and cannot establish present compatibility.")
                    receipt_compatible = False

            current_versioned = {
                field: observation.get(field)
                for field in ("runtime_version", "runtime_build")
                if observation is not None and isinstance(observation.get(field), str) and observation.get(field)
            }
            if not current_versioned:
                reasons.append("Runtime identity unavailable; capability compatibility unproven.")
                if current_runtime_capability_state != "STALE":
                    current_runtime_capability_state = "UNPROVEN"
                receipt_compatible = False
            else:
                for field, label in (
                    ("runtime_version", "Codex runtime version"),
                    ("runtime_build", "Codex runtime build"),
                ):
                    current_value = current_versioned.get(field)
                    if current_value:
                        receipt_value = receipt.get(field)
                        if not isinstance(receipt_value, str) or not receipt_value:
                            reasons.append(f"{label} is currently observable but was not bound by the capability receipt.")
                            receipt_compatible = False
                        elif current_value != receipt_value:
                            reasons.append(f"{label} changed after the last successful escalation receipt.")
                            receipt_compatible = False

            if observation is not None:
                for field, label in (("host_type", "Codex host type"), ("platform", "Current platform")):
                    current_value = observation.get(field)
                    if isinstance(current_value, str) and current_value:
                        receipt_value = receipt.get(field)
                        if not isinstance(receipt_value, str) or not receipt_value:
                            reasons.append(f"{label} was not bound by the capability receipt.")
                            receipt_compatible = False
                        elif current_value != receipt_value:
                            reasons.append(f"Capability receipt {field.replace('_', ' ')} does not match the current hook observation.")
                            receipt_compatible = False

            if receipt_compatible:
                current_runtime_capability_state = "CURRENT RUNTIME ESCALATION CAPABLE"
            elif current_runtime_capability_state not in {"STALE", "UNPROVEN"}:
                current_runtime_capability_state = "INCOMPATIBLE"

        if not reasons:
            status = "READY"

    identity_values = (
        observation.get("runtime_version") if observation else None,
        observation.get("runtime_build") if observation else None,
    )
    observable_identity_count = sum(isinstance(value, str) and bool(value) for value in identity_values)
    runtime_identity = (
        "unavailable from current Codex hook surface"
        if observable_identity_count == 0
        else "partially observable from current Codex hook surface"
        if observable_identity_count < len(identity_values)
        else "observable from current Codex hook surface"
    )

    return {
        "status": status,
        "ready": status == "READY",
        "root_model": root_model,
        "root_model_source": root_source,
        "config_model": config_model,
        "reasons": reasons,
        "current_session_id": session_id or None,
        "observation_session_id": observation.get("session_id") if observation else None,
        "observation_turn_id": observation.get("turn_id") if observation else None,
        "plugin_identity": current_plugin_identity,
        "current_task_root_state": current_task_root_state,
        "historical_escalation_state": historical_escalation_state,
        "current_runtime_capability_state": current_runtime_capability_state,
        "observation_present": observation is not None,
        "capability_receipt_present": receipt is not None,
        "runtime_identity": runtime_identity,
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
    health = _routing_health(
        effective,
        str(skill_summary.get("version") or ""),
        data_home / plugin_prefix,
        plugin_identity=_plugin_identity(),
        current_session_id=os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_THREAD_ID"),
    )
    return {
        "plugin": plugin_prefix,
        "cwd_checked": bool(entry.get("cwd")),
        "ready": health["ready"],
        "status": health["status"],
        "root_model": health["root_model"],
        "root_model_source": health["root_model_source"],
        "reasons": health["reasons"],
        "readiness_scope": "CURRENT_TASK_ROOT_AND_VERSIONED_RUNTIME_CAPABILITY",
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
