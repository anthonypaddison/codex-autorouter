#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

import spawn_compat


class SpawnCompatibilityTests(unittest.TestCase):
    def test_builds_supported_direct_model_calls(self) -> None:
        for model, effort in (
            ("gpt-5.6-terra", "medium"),
            ("gpt-5.6-sol", "high"),
        ):
            with self.subTest(model=model, effort=effort):
                arguments = spawn_compat.build_arguments(
                    model=model,
                    effort=effort,
                    task_name="bounded-review",
                    message="Inspect the bounded surface and return evidence.",
                )
                self.assertEqual("none", arguments["fork_turns"])
                self.assertEqual(model, arguments["model"])
                self.assertEqual(effort, arguments["reasoning_effort"])
                self.assertNotIn("agent_type", arguments)
                rendered = spawn_compat.render_call(arguments)
                self.assertEqual(arguments, json.loads(rendered.removeprefix("spawn_agent(").removesuffix(")")))

    def test_rejects_luna_unknown_models_and_invalid_effort(self) -> None:
        for model, effort in (
            ("gpt-5.6-luna", "low"),
            ("gpt-5.6-unknown", "medium"),
            ("gpt-5.6-terra", "ultra"),
        ):
            with self.subTest(model=model, effort=effort), self.assertRaises(ValueError):
                spawn_compat.build_arguments(
                    model=model,
                    effort=effort,
                    task_name="bounded",
                    message="A complete bounded contract.",
                )

    def test_signature_and_fallback_are_explicit(self) -> None:
        self.assertEqual(1, spawn_compat.SCHEMA_VERSION)
        self.assertEqual("direct-model-spawn-v1", spawn_compat.CAPABILITY_SIGNATURE)
        fallback = spawn_compat.fallback_contract("model override rejected")
        self.assertEqual("current", fallback["route"])
        self.assertEqual("DEGRADED", fallback["readiness"])
        self.assertIn("model override rejected", fallback["reason"])


if __name__ == "__main__":
    unittest.main()
