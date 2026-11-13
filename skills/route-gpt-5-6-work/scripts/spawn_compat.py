#!/usr/bin/env python3
"""Single compatibility boundary for supported direct Codex child spawning."""

from __future__ import annotations

import json
import re
from typing import Any

import model_policy


SCHEMA_VERSION = 1
CAPABILITY_SIGNATURE = "direct-model-spawn-v1"
SUPPORTED_EFFORTS = {
    model_id: frozenset(
        set(policy.explicit_child_efforts)
        | {
        effort
        for profile in model_policy.ROUTE_PROFILES.values()
        if profile.target_model_id == model_id
        for effort in profile.allowed_automatic_efforts
        }
    )
    for model_id, policy in model_policy.ACTIVE_MODELS.items()
    if policy.child_target_allowed
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
    arguments = {
        "fork_turns": "none",
        "task_name": task_name,
        "message": message,
        "model": model,
        "reasoning_effort": effort,
    }
    result = validate_arguments(arguments)
    if not result["spawn_contract_valid"]:
        raise ValueError(", ".join(result["reasons"]))
    return arguments


def build_policy_arguments(
    *, profile_id: str, model: str, effort: str, discovery_state: str,
    root_model: str, root_effort: str | None, task_name: str, message: str,
    requested_model_id: str | None = None, independent_parallel: bool = False,
) -> dict[str, str]:
    """Validate internal policy evidence, then emit only the supported tool fields."""
    if requested_model_id is not None and requested_model_id != model:
        raise ValueError("policy selection denied: policy_unapproved")
    selection = model_policy.select_target(
        profile_id,
        root_model=root_model,
        root_effort=root_effort,
        discovery_state=discovery_state,
        requested_model_id=model,
        requested_effort=effort,
        deep_high=effort == "xhigh",
    )
    satisfied_independent_target = (
        independent_parallel
        and selection.satisfaction == model_policy.RootSatisfaction.SATISFIED
        and selection.target_model_id == model
        and selection.target_effort == effort
    )
    if (
        not selection.approved and not satisfied_independent_target
    ) or selection.target_model_id != model or selection.target_effort != effort:
        raise ValueError(f"policy selection denied: {selection.outcome.value}")
    transition = model_policy.classify_transition(root_model, root_effort, model, effort)
    if transition not in {
        model_policy.TransitionKind.MODEL_ROUTE_UP,
        model_policy.TransitionKind.PROFILE_UP,
    } and not (
        independent_parallel
        and selection.satisfaction == model_policy.RootSatisfaction.SATISFIED
        and transition == model_policy.TransitionKind.NONE
    ):
        raise ValueError("policy selection denied: transition_not_upward")
    return build_arguments(model=model, effort=effort, task_name=task_name, message=message)


def build_explicit_astra_arguments(
    *, effort: str, discovery_state: str, root_model: str,
    task_name: str, message: str,
) -> dict[str, str]:
    """Validate a caller-authorized explicit Astra request without changing the tool schema."""
    astra = model_policy.ACTIVE_MODELS["gpt-6-astra"]
    if (
        effort not in astra.explicit_child_efforts
        or discovery_state != model_policy.DiscoveryState.AVAILABLE.value
        or root_model not in model_policy.ACTIVE_MODELS
        or root_model == "gpt-6-astra"
    ):
        raise ValueError("policy selection denied: explicit_astra_unavailable_or_unapproved")
    return build_arguments(
        model="gpt-6-astra", effort=effort, task_name=task_name, message=message
    )


_UNPROVEN = object()
MAX_SPAWN_SOURCE = 256 * 1024
MAX_SPAWN_TOKENS = 16384


def validate_arguments(arguments: Any) -> dict[str, Any]:
    """Validate the observed call, returning only non-content evidence metadata."""
    if not isinstance(arguments, dict):
        return {"spawn_contract_valid": False, "reasons": ["unproven_arguments"], "role": None}
    reasons = []
    model = arguments.get("model")
    effort = arguments.get("reasoning_effort")
    for field in ("model", "reasoning_effort", "fork_turns", "task_name", "message"):
        value = arguments.get(field)
        if field not in arguments:
            reasons.append("missing_" + field)
        elif value is _UNPROVEN:
            reasons.append("unproven_" + field)
        elif not isinstance(value, str) or not value.strip():
            reasons.append("invalid_" + field)
        elif field == "model" and value not in SUPPORTED_EFFORTS:
            reasons.append("invalid_model")
        elif field == "reasoning_effort" and value not in SUPPORTED_EFFORTS.get(model if isinstance(model, str) else "", ()):
            reasons.append("invalid_reasoning_effort")
        elif field == "fork_turns" and value != "none":
            reasons.append("invalid_fork_turns")
    if "service_tier" in arguments:
        reasons.append("service_tier_override")
    role = role_for(model, effort) if isinstance(model, str) and isinstance(effort, str) else None
    return {
        "spawn_contract_valid": not reasons,
        "reasons": reasons,
        "role": role,
        "model": model if isinstance(model, str) and model in SUPPORTED_EFFORTS else None,
        "effort": effort if role else None,
    }


class _UnprovenSpawn(ValueError):
    pass


def _spawn_tokens(source: str) -> list[tuple[str, str]]:
    """A bounded lexer, not a JavaScript evaluator. Strings/comments are opaque."""
    if len(source) > MAX_SPAWN_SOURCE:
        raise _UnprovenSpawn
    pattern = re.compile(r'''\s+|//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z_$][\w$]*|[0-9]+|[^\w\s]''')
    tokens = []
    end = 0
    for match in pattern.finditer(source):
        if match.start() != end:
            raise _UnprovenSpawn
        end = match.end()
        raw = match.group()
        if raw == "/" and source[match.start():match.start() + 2] == "/*":
            raise _UnprovenSpawn
        if raw.isspace() or raw.startswith(("//", "/*")):
            continue
        if raw[0] in "\"'":
            try:
                if raw[0] == "'":
                    raw = '"' + raw[1:-1].replace('"', '\\"').replace("\\'", "'") + '"'
                tokens.append(("string", json.loads(raw)))
            except (ValueError, RecursionError):
                raise _UnprovenSpawn from None
        elif raw in {'`', '"', "'"}:
            raise _UnprovenSpawn
        else:
            tokens.append(("token", raw))
        if len(tokens) > MAX_SPAWN_TOKENS:
            raise _UnprovenSpawn
    if end != len(source):
        raise _UnprovenSpawn
    return tokens


def _spawn_literal(tokens: list[tuple[str, str]], start: int, depth: int = 0) -> tuple[Any, int]:
    if depth > 8 or start >= len(tokens):
        raise _UnprovenSpawn
    kind, value = tokens[start]
    if kind == "string":
        return value, start + 1
    if value in ("{", "["):
        result: Any = {} if value == "{" else []
        close = "}" if value == "{" else "]"
        pos = start + 1
        while pos < len(tokens) and tokens[pos] != ("token", close):
            if len(result) >= 256:
                raise _UnprovenSpawn
            key = None
            if value == "{":
                key_kind, key = tokens[pos]
                if key_kind != "string" and not re.fullmatch(r"[A-Za-z_$][\w$]*", key):
                    raise _UnprovenSpawn
                if key in result or tokens[pos + 1:pos + 2] != [("token", ":")]:
                    raise _UnprovenSpawn
                pos += 2
            child, pos = _spawn_literal(tokens, pos, depth + 1)
            if value == "{":
                result[key] = child
            else:
                result.append(child)
            if tokens[pos:pos + 1] == [("token", ",")]:
                pos += 1
            elif tokens[pos:pos + 1] != [("token", close)]:
                raise _UnprovenSpawn
        if pos >= len(tokens):
            raise _UnprovenSpawn
        return result, pos + 1
    if value in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[value], start + 1
    if value.isdigit():
        return 0, start + 1  # Numeric metadata is irrelevant to the contract.
    if re.fullmatch(r"[A-Za-z_$][\w$]*", value):
        return _UNPROVEN, start + 1  # Never resolve variables from nearby strings.
    raise _UnprovenSpawn


def observe_nested_calls(source: str) -> list[dict[str, Any]]:
    """Observe complete literal calls only; never execute code or retain messages.

    The index is a lexical call occurrence, NOT a child/result ordering claim.
    Unknown syntax cannot provide positive proof, even if some fields look valid.
    """
    try:
        tokens = _spawn_tokens(source)
    except _UnprovenSpawn:
        return [{**validate_arguments(None), "index": 0}]
    calls = []
    names = {"spawn_agent", "multi_agent_v1__spawn_agent", "collaboration__spawn_agent"}
    for pos, token in enumerate(tokens):
        if token[0] != "token" or token[1] not in names or tokens[pos + 1:pos + 2] != [("token", "(")]:
            continue
        # Accept only the explicit supported tools.<name> receiver; not quoted examples.
        if tokens[max(0, pos - 2):pos] != [("token", "tools"), ("token", ".")]:
            continue
        try:
            arguments, end = _spawn_literal(tokens, pos + 2)
            if tokens[end:end + 1] != [("token", ")")]:
                raise _UnprovenSpawn
            result = validate_arguments(arguments)
        except _UnprovenSpawn:
            result = validate_arguments(None)
        calls.append({**result, "index": len(calls)})
        if len(calls) > 256:
            return [{**validate_arguments(None), "index": 0}]
    return calls


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
    if model in {"gpt-6.1-sol", "gpt-6.1-terra"} and effort in {"medium", "high", "xhigh"}:
        family = model.rsplit("-", 1)[1]
        return f"gpt61_{family}_{'balanced' if effort == 'medium' else effort}"
    return {
        ("gpt-6-sol", "medium"): "gpt6_sol_balanced",
        ("gpt-6-sol", "high"): "gpt6_sol_high",
        ("gpt-6-sol", "xhigh"): "gpt6_sol_xhigh",
        ("gpt-6-astra", "medium"): "gpt6_astra_medium",
        ("gpt-6-astra", "high"): "gpt6_astra_high",
        ("gpt-6-astra", "xhigh"): "gpt6_astra_xhigh",
        ("gpt-6-astra", "max"): "gpt6_astra_max",
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


def current_role_spec(role: str) -> dict[str, str]:
    """Resolve internal roles through the active model/profile registry only."""
    for model in model_policy.ACTIVE_MODELS.values():
        if not model.child_target_allowed:
            continue
        for effort in model.explicit_child_efforts:
            if role_for(model.canonical_id, effort) == role:
                profile = "frontier" if model.canonical_id == "gpt-6-astra" else "balanced" if effort == "medium" else "high"
                return {"model": model.canonical_id, "effort": effort, "profile": profile}
    return {}


def role_from_event(data: dict[str, Any], allowed: list[str],
                    intent: dict[str, Any] | None = None) -> str | None:
    """Prefer exact bound intent; a model alone cannot distinguish profiles."""
    model = str(data.get("model") or "")
    effort = str(data.get("reasoning_effort") or data.get("model_reasoning_effort") or "")
    if intent is not None:
        role = role_for(str(intent.get("model") or ""), str(intent.get("effort") or ""))
        if (
            intent.get("spawn_contract_valid") is not True
            or role != intent.get("role")
            or (model and model != intent.get("model"))
            or (effort and effort != intent.get("effort"))
        ):
            return None
        return role
    direct = role_for(
        model, effort,
    )
    if direct:
        return direct
    if model in model_policy.ACTIVE_MODELS:
        if effort:  # An unsupported explicit effort is not missing evidence.
            return None
        candidates = [role for role in allowed if current_role_spec(role).get("model") == model]
        return candidates[0] if len(candidates) == 1 else None
    candidates = [role for role in allowed if model and _legacy_spec(role)[0] == model]
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
