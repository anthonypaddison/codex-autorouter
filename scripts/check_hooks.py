#!/usr/bin/env python3
"""Query Codex app-server for authoritative plugin-hook discovery and trust."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


EXPECTED_EVENTS = {"postToolUse", "userPromptSubmit", "subagentStart", "subagentStop", "stop"}
CHECKER_ROOT = Path(__file__).resolve().parents[1]


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
    multi_agent_enabled = features.get("multi_agent") is not False
    child_depth_enabled = agents.get("max_depth") != 0
    plugin_enabled = bool(plugin_entry and plugin_entry.get("enabled") is True)
    return {
        "ready": plugin_enabled and hooks_enabled and multi_agent_enabled and child_depth_enabled and not managed_only,
        "plugin_enabled": plugin_enabled,
        "hooks_enabled": hooks_enabled,
        "multi_agent_enabled": multi_agent_enabled,
        "child_depth_enabled": child_depth_enabled,
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


def _local_agent_readiness(checker_root: Path = CHECKER_ROOT) -> tuple[bool, dict[str, Any]]:
    controller = checker_root / "skills" / "route-gpt-5-6-work" / "scripts" / "routerctl.py"
    try:
        result = subprocess.run(
            [sys.executable, str(controller), "status"],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        payload = json.loads(result.stdout) if result.stdout else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return False, {"ready": False, "error": type(exc).__name__}
    ready = (
        result.returncode == 0
        and payload.get("mode") == "ADVISORY"
        and payload.get("runtime_surface") == "PLUGIN_LAYOUT_UNATTESTED"
        and payload.get("local_agent_ready") is True
        and payload.get("agents_active") is True
        and payload.get("activation_update_required") is False
        and not payload.get("agent_conflicts")
        and not payload.get("original_backup_conflicts")
    )
    return ready, {
        "ready": ready,
        "agents_active": payload.get("agents_active") is True,
        "local_agent_ready": payload.get("local_agent_ready") is True,
        "activation_update_required": payload.get("activation_update_required"),
        "runtime_surface": payload.get("runtime_surface"),
        "diagnostic_scope": payload.get("diagnostic_scope"),
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
    local_agents_ready, local_agents = _local_agent_readiness()
    effective = _effective_readiness(config_response, requirements_response, plugin_prefix)
    ready = (
        events == EXPECTED_EVENTS
        and len(hooks) == len(EXPECTED_EVENTS)
        and all(hook.get("source") == "plugin" and hook.get("enabled") and hook.get("trustStatus") == "trusted" for hook in hooks)
        and not entry.get("warnings")
        and not entry.get("errors")
        and skill_ready
        and local_agents_ready
        and effective["ready"]
    )
    return {
        "plugin": plugin_prefix,
        "cwd_checked": bool(entry.get("cwd")),
        "ready": ready,
        "readiness_scope": "STATIC_INSTALLATION_ONLY",
        "live_delegation_required": True,
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
        "local_agents": local_agents,
        "effective": effective,
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
        print(json.dumps({"ready": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
