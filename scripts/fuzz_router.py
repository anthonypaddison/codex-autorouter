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
        first = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
        second = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
        assert first == second
        assert first["route"] in router_hook.ROUTES
        plan = first["orchestration"]
        assert plan["max_workers"] <= 3 and plan["max_depth"] == 1
        assert sum(plan["required_agents"].values()) <= plan["max_workers"]
        assert set(plan["required_agents"]) <= set(plan["allowed_agents"])
        assert prompt not in json.dumps(first)
        count += 1
    assert count == 5000
    print(f"routing fuzz passed: {count} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
