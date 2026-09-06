#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

import spawn_compat


class SpawnCompatibilityTests(unittest.TestCase):
    def test_observed_contract_requires_every_adapter_field(self) -> None:
        valid = spawn_compat.build_arguments(
            model="gpt-5.6-terra", effort="medium", task_name="bounded", message="Inspect only.",
        )
        validator = getattr(spawn_compat, "validate_arguments", None)
        self.assertTrue(callable(validator), "observed spawn validator is missing")
        self.assertTrue(validator(valid)["spawn_contract_valid"])
        for field in valid:
            with self.subTest(missing=field):
                arguments = {key: value for key, value in valid.items() if key != field}
                result = validator(arguments)
                self.assertFalse(result["spawn_contract_valid"])
                self.assertIn("missing_" + field, result["reasons"])
        for field, value in (
            ("fork_turns", "all"), ("task_name", " \t"), ("message", ""),
            ("model", "gpt-5.6-luna"), ("reasoning_effort", "ultra"),
            ("model", []), ("reasoning_effort", {}), ("message", None),
        ):
            with self.subTest(field=field, value=value):
                result = validator({**valid, field: value})
                self.assertFalse(result["spawn_contract_valid"])
                self.assertIn("invalid_" + field, result["reasons"])
        self.assertTrue(validator({**valid, "host_metadata": {"trace": "opaque"}})["spawn_contract_valid"])
        self.assertFalse(validator({**valid, "service_tier": "fast"})["spawn_contract_valid"])

    def test_nested_calls_are_complete_objects_not_message_text(self) -> None:
        observe = getattr(spawn_compat, "observe_nested_calls", None)
        self.assertTrue(callable(observe), "nested observed-call parser is missing")
        arguments = spawn_compat.build_arguments(
            model="gpt-5.6-sol", effort="high", task_name="bounded", message="Inspect only.",
        )
        source = "text(await tools.multi_agent_v1__spawn_agent(" + json.dumps(arguments) + "));"
        self.assertTrue(observe(source)[0]["spawn_contract_valid"])
        malformed = (
            'const msg="fork_turns: none, task_name: fake"; '
            'await Promise.all([tools.multi_agent_v1__spawn_agent({message:msg, model:"gpt-5.6-terra", reasoning_effort:"medium"}),'
            'tools.multi_agent_v1__spawn_agent({message:msg, model:"gpt-5.6-terra", reasoning_effort:"medium"})]);'
        )
        observations = observe(malformed)
        self.assertEqual(2, len(observations))
        for item in observations:
            self.assertFalse(item["spawn_contract_valid"])
            self.assertIn("missing_fork_turns", item["reasons"])
            self.assertIn("missing_task_name", item["reasons"])
        for source in (
            'text("tools.multi_agent_v1__spawn_agent({model:fake})");',
            '// tools.multi_agent_v1__spawn_agent({model:fake})\ntext("done");',
        ):
            self.assertEqual([], observe(source))

    def test_dynamic_duplicate_and_partial_arguments_never_prove_compliance(self) -> None:
        observe = getattr(spawn_compat, "observe_nested_calls", None)
        self.assertTrue(callable(observe), "nested observed-call parser is missing")
        prefix = 'model:"gpt-5.6-terra",reasoning_effort:"medium",fork_turns:"none",task_name:"x",message:"ok"'
        for body in (prefix + ',...overrides', prefix + ',fork_turns:"all"', prefix + '+suffix',
                     prefix.replace('"ok"', 'dynamicMessage'), prefix + ',[computed]:"none"'):
            with self.subTest(body=body):
                items = observe('await tools.multi_agent_v1__spawn_agent({' + body + '});')
                self.assertTrue(items)
                self.assertFalse(items[0]["spawn_contract_valid"])
        partial = observe('await tools.multi_agent_v1__spawn_agent({' + prefix)
        self.assertFalse(any(item["spawn_contract_valid"] for item in partial))

    def test_nested_parser_rejects_incomplete_comments_and_oversized_input(self) -> None:
        args = spawn_compat.build_arguments(model="gpt-5.6-terra", effort="medium", task_name="bounded", message="Inspect.")
        call = 'tools.multi_agent_v1__spawn_agent(' + json.dumps(args) + ')'
        for source in ('/* never closed ' + call, ' ' * (256 * 1024) + call):
            self.assertFalse(any(item["spawn_contract_valid"] for item in spawn_compat.observe_nested_calls(source)))

    def test_nested_message_with_spawn_code_is_not_a_second_call(self) -> None:
        args = spawn_compat.build_arguments(model="gpt-5.6-terra", effort="medium", task_name="bounded",
                                           message='Example: tools.spawn_agent({model:"gpt-5.6-sol",fork_turns:"all"})')
        observed = spawn_compat.observe_nested_calls('text(await tools.spawn_agent(' + json.dumps(args) + '));')
        self.assertEqual(1, len(observed))
        self.assertTrue(observed[0]["spawn_contract_valid"])

    def test_builds_supported_direct_model_calls(self) -> None:
        for model, effort in (
            ("gpt-5.6-terra", "medium"),
            ("gpt-5.6-sol", "high"),
            ("gpt-6-astra", "medium"),
            ("gpt-6-astra", "high"),
            ("gpt-6-astra", "xhigh"),
            ("gpt-6-astra", "max"),
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
            ("gpt-6-astra", "low"),
            ("gpt-6-astra", "ultra"),
        ):
            with self.subTest(model=model, effort=effort), self.assertRaises(ValueError):
                spawn_compat.build_arguments(
                    model=model,
                    effort=effort,
                    task_name="bounded",
                    message="A complete bounded contract.",
                )

    def test_astra_roles_are_exact_and_malformed_calls_receive_no_credit(self) -> None:
        expected = {
            "medium": "gpt6_astra_medium",
            "high": "gpt6_astra_high",
            "xhigh": "gpt6_astra_xhigh",
            "max": "gpt6_astra_max",
        }
        for effort, role in expected.items():
            with self.subTest(effort=effort):
                arguments = spawn_compat.build_arguments(
                    model="gpt-6-astra",
                    effort=effort,
                    task_name="astra-frontier",
                    message="Complete the bounded frontier task and return structured evidence.",
                )
                self.assertEqual(role, spawn_compat.validate_arguments(arguments)["role"])
                observed = spawn_compat.observe_nested_calls(
                    "await tools.spawn_agent(" + json.dumps(arguments) + ");"
                )
                self.assertEqual(1, len(observed))
                self.assertTrue(observed[0]["spawn_contract_valid"])
                self.assertEqual(role, observed[0]["role"])

        valid = spawn_compat.build_arguments(
            model="gpt-6-astra",
            effort="medium",
            task_name="astra-frontier",
            message="Complete the bounded frontier task.",
        )
        for field, value in (
            ("fork_turns", "all"),
            ("task_name", ""),
            ("message", " "),
            ("service_tier", "priority"),
        ):
            with self.subTest(field=field):
                malformed = {**valid, field: value}
                result = spawn_compat.validate_arguments(malformed)
                self.assertFalse(result["spawn_contract_valid"])

    def test_signature_and_fallback_are_explicit(self) -> None:
        self.assertEqual(1, spawn_compat.SCHEMA_VERSION)
        self.assertEqual("direct-model-spawn-v1", spawn_compat.CAPABILITY_SIGNATURE)
        fallback = spawn_compat.fallback_contract("model override rejected")
        self.assertEqual("current", fallback["route"])
        self.assertEqual("DEGRADED", fallback["readiness"])
        self.assertIn("model override rejected", fallback["reason"])


if __name__ == "__main__":
    unittest.main()
