#!/usr/bin/env python3
"""Single compatibility boundary for supported direct Codex child spawning."""

from __future__ import annotations

import json
import re
from typing import Any


SCHEMA_VERSION = 1
CAPABILITY_SIGNATURE = "direct-model-spawn-v1"
SUPPORTED_EFFORTS = {
    "gpt-5.6-terra": frozenset({"medium", "high"}),
    "gpt-5.6-sol": frozenset({"medium", "high", "xhigh"}),
}
LEGACY_ROLES = frozenset({
    "gpt56_luna_worker",
    "gpt56_terra_worker",
    "gpt56_terra_deep",
    "gpt56_sol_owner",
    "gpt56_sol_deep",
    "gpt56_sol_xhigh",
})


def build_arguments(*, model: str, effort: str, task_name: str, message: str) -> dict[str, str]:
    """Build the only supported spawn shape or fail closed to the caller."""
    allowed = SUPPORTED_EFFORTS.get(model)
    if allowed is None:
        raise ValueError(f"unsupported direct child model: {model or '<empty>'}")
    if effort not in allowed:
        raise ValueError(f"unsupported effort {effort or '<empty>'} for {model}")
    if not task_name.strip() or not message.strip():
        raise ValueError("task_name and message must be nonempty")
    return {
        "fork_turns": "none",
        "task_name": task_name,
        "message": message,
        "model": model,
        "reasoning_effort": effort,
    }


def render_call(arguments: dict[str, str]) -> str:
    """Render a deterministic literal call for the trusted routing envelope."""
    return "spawn_agent(" + json.dumps(arguments, separators=(",", ":")) + ")"


def fallback_contract(reason: str) -> dict[str, Any]:
    """Describe the required fail-open behaviour without claiming escalation."""
    return {
        "schema_version": SCHEMA_VERSION,
        "capability_signature": CAPABILITY_SIGNATURE,
        "route": "current",
        "readiness": "DEGRADED",
        "escalation_observed": False,
        "reason": f"direct child selection unavailable: {reason}",
    }


def role_for(model: str, effort: str) -> str | None:
    """Map an observed direct-spawn model/effort intent back to a router role."""
    return {
        ("gpt-5.6-terra", "medium"): "gpt56_terra_worker",
        ("gpt-5.6-terra", "high"): "gpt56_terra_deep",
        ("gpt-5.6-sol", "medium"): "gpt56_sol_owner",
        ("gpt-5.6-sol", "high"): "gpt56_sol_deep",
        ("gpt-5.6-sol", "xhigh"): "gpt56_sol_xhigh",
    }.get((model, effort))


def role_from_arguments(arguments: dict[str, Any]) -> str | None:
    """Resolve current direct arguments, with an explicit legacy-fixture fallback."""
    direct = role_for(
        str(arguments.get("model") or ""),
        str(arguments.get("reasoning_effort") or ""),
    )
    if direct:
        return direct
    legacy = str(arguments.get("agent_type") or "")
    return legacy if legacy in LEGACY_ROLES else None


def role_from_event(data: dict[str, Any], allowed: list[str]) -> str | None:
    direct = role_for(
        str(data.get("model") or ""),
        str(data.get("reasoning_effort") or data.get("model_reasoning_effort") or ""),
    )
    if direct:
        return direct
    model = str(data.get("model") or "")
    candidates = [role for role in allowed if _legacy_spec(role)[0] == model]
    if len(candidates) == 1:
        return candidates[0]
    legacy = str(data.get("agent_type") or "")
    return legacy if legacy in LEGACY_ROLES else None


def role_from_text(text: str) -> str | None:
    """Resolve transcript call text without leaking parsing into the router."""
    model = re.search(r"\bmodel\s*:\s*[\\\"']*([A-Za-z0-9_.-]+)", text)
    effort = re.search(r"\breasoning_effort\s*:\s*[\\\"']*([A-Za-z0-9_-]+)", text)
    if model and effort:
        direct = role_for(model.group(1), effort.group(1))
        if direct:
            return direct
    legacy = re.search(r"\bagent_type\s*:\s*[\\\"']*([A-Za-z0-9_-]+)", text)
    return legacy.group(1) if legacy and legacy.group(1) in LEGACY_ROLES else None


def _legacy_spec(role: str) -> tuple[str, str]:
    return {
        "gpt56_luna_worker": ("gpt-5.6-luna", "low"),
        "gpt56_terra_worker": ("gpt-5.6-terra", "medium"),
        "gpt56_terra_deep": ("gpt-5.6-terra", "high"),
        "gpt56_sol_owner": ("gpt-5.6-sol", "medium"),
        "gpt56_sol_deep": ("gpt-5.6-sol", "high"),
        "gpt56_sol_xhigh": ("gpt-5.6-sol", "xhigh"),
    }.get(role, ("", ""))
