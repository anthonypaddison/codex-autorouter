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
