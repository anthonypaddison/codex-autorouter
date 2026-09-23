#!/usr/bin/env python3
"""Deterministic combinatorial fuzzing for routing invariants."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "route-gpt-5-6-work" / "scripts"))
import router_hook  # noqa: E402


def main() -> int:
    verbs = ["Explain", "Review", "Fix", "Design", "Diagnose", "Extract", "Migrate", "Audit", "Deploy", "Benchmark"]
    objects = [
        "the README", "OAuth handling", "the production database", "a flaky CI test", "500 records",
        "the billing ledger", "the mobile sync flow", "the API", "the Terraform cluster", "the analytics funnel",
    ]
    qualifiers = [
        "", " with exact schema validation", " in parallel", " with rollback", " for a toy blog example",
        " across the monorepo", " with no existing validator", " and targeted tests", " for customer data",
        " with unclear requirements",
    ]
    endings = [".", " safely.", " and summarize evidence.", " without making changes.", " then verify the result."]
    count = 0
    for verb, object_name, qualifier, ending in itertools.product(verbs, objects, qualifiers, endings):
        prompt = f"{verb} {object_name}{qualifier}{ending}"
        first = router_hook.classify_prompt(
            prompt, "gpt-6-luna", "low", enforce_active_root=True,
        )
        second = router_hook.classify_prompt(
            prompt, "gpt-6-luna", "low", enforce_active_root=True,
        )
        assert first == second
        assert first["route"] in router_hook.ROUTES
        plan = first["orchestration"]
        assert plan["max_workers"] <= 3 and plan["max_depth"] == 1
        assert sum(plan["required_agents"].values()) <= plan["max_workers"]
        assert set(plan["required_agents"]) <= set(plan["allowed_agents"])
        assert prompt not in json.dumps(first)

        astra_root = router_hook.classify_prompt(
            prompt, "gpt-6-astra", "medium", enforce_active_root=True,
        )
        assert astra_root["route"] == "current"
        assert astra_root["orchestration"]["mode"] in {"direct", "clarify"}
        assert astra_root["orchestration"]["required_agents"] == {}

        sol_root = router_hook.classify_prompt(
            prompt, "gpt-6-sol", "high", enforce_active_root=True,
        )
        assert sol_root["route"] == "current"
        for role in sol_root["orchestration"]["required_agents"]:
            spec = router_hook.ROUTES[role]
            transition = router_hook.model_policy.classify_transition(
                "gpt-6-sol", "high", spec["model"], spec["effort"],
            )
            assert transition != router_hook.model_policy.TransitionKind.DOWNWARD
        assert not any(role.startswith("gpt6_astra_") for role in first["orchestration"]["required_agents"])
        count += 1
    assert count == 5000

    explicit_efforts = {
        "Use GPT-6 Astra for this task.": "gpt6_astra_medium",
        "Use GPT-6 Astra Medium for this task.": "gpt6_astra_medium",
        "Use GPT-6 Astra High for this task.": "gpt6_astra_high",
        "Use GPT-6 Astra xHigh for this task.": "gpt6_astra_xhigh",
        "Use GPT-6 Astra Max for this task.": "gpt6_astra_max",
    }
    for prompt, route in explicit_efforts.items():
        decision = router_hook.classify_prompt(
            prompt, "gpt-6-luna", "low", enforce_active_root=True,
        )
        assert decision["route"] == route
        assert decision["orchestration"]["required_agents"] == {route: 1}
    for effort in ("Low", "Ultra"):
        decision = router_hook.classify_prompt(
            f"Use GPT-6 Astra {effort} for this task.", "gpt-6-luna", "low", enforce_active_root=True,
        )
        assert decision["route"] == "current"
        assert decision["orchestration"]["mode"] == "clarify"
        assert decision["orchestration"]["required_agents"] == {}
    print(f"routing fuzz passed: {count} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
