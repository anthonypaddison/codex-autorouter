#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

import spawn_compat


class Gpt61SpawnTests(unittest.TestCase):
    def test_profile_up_uses_exact_model_and_supported_spawn_shape(self):
        for model in ("gpt-6.1-sol", "gpt-6.1-terra"):
            args = spawn_compat.build_policy_arguments(
                profile_id="high", model=model, effort="high", discovery_state="available",
                root_model=model, root_effort="medium", task_name="bounded_review", message="Review the queue race.",
            )
            self.assertEqual(model, args["model"])
            self.assertEqual("none", args["fork_turns"])
            self.assertNotIn("service_tier", args)
            self.assertIsNotNone(spawn_compat.role_for(model, "high"))
            self.assertEqual({"model": model, "effort": "high", "profile": "high"},
                             spawn_compat.current_role_spec(spawn_compat.role_for(model, "high")))
            with self.assertRaises(ValueError):
                spawn_compat.build_policy_arguments(
                    profile_id="high", model="gpt-6-sol", effort="high", discovery_state="available",
                    root_model=model, root_effort="medium", task_name="wrong_model", message="Review.",
                )


class SpawnCompatibilityTests(unittest.TestCase):
    def test_current_model_only_lifecycle_resolves_one_approved_profile(self) -> None:
        for role in ("gpt6_sol_balanced", "gpt6_sol_high", "gpt6_sol_xhigh"):
            with self.subTest(role=role):
                self.assertEqual(role, spawn_compat.role_from_event({"model": "gpt-6-sol"}, [role]))

    def test_model_only_lifecycle_cannot_choose_between_current_profiles(self) -> None:
        self.assertIsNone(spawn_compat.role_from_event(
            {"model": "gpt-6-sol", "agent_type": "default"},
            ["gpt6_sol_balanced", "gpt6_sol_high"],
        ))

    def test_historical_model_observation_cannot_become_active_spawn_support(self) -> None:
        event = {"model": "gpt-5.6-sol", "reasoning_effort": "high", "agent_type": "gpt56_sol_deep"}
        self.assertEqual("gpt56_sol_deep", spawn_compat.role_from_event(event, ["gpt56_sol_deep"]))
        contract = spawn_compat.validate_arguments({
            "model": "gpt-5.6-sol", "reasoning_effort": "high", "fork_turns": "none",
            "task_name": "historical", "message": "Inspect only.",
        })
        self.assertFalse(contract["spawn_contract_valid"])
        self.assertEqual({}, spawn_compat.current_role_spec("gpt56_sol_deep"))

    def test_observed_contract_requires_every_adapter_field(self) -> None:
        valid = spawn_compat.build_arguments(
            model="gpt-6-sol", effort="medium", task_name="bounded", message="Inspect only.",
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
            ("model", "gpt-6-luna"), ("reasoning_effort", "ultra"),
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
            model="gpt-6-sol", effort="high", task_name="bounded", message="Inspect only.",
        )
        source = "text(await tools.multi_agent_v1__spawn_agent(" + json.dumps(arguments) + "));"
        self.assertTrue(observe(source)[0]["spawn_contract_valid"])
        malformed = (
            'const msg="fork_turns: none, task_name: fake"; '
            'await Promise.all([tools.multi_agent_v1__spawn_agent({message:msg, model:"gpt-6-sol", reasoning_effort:"medium"}),'
            'tools.multi_agent_v1__spawn_agent({message:msg, model:"gpt-6-sol", reasoning_effort:"medium"})]);'
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
        prefix = 'model:"gpt-6-sol",reasoning_effort:"medium",fork_turns:"none",task_name:"x",message:"ok"'
        for body in (prefix + ',...overrides', prefix + ',fork_turns:"all"', prefix + '+suffix',
                     prefix.replace('"ok"', 'dynamicMessage'), prefix + ',[computed]:"none"'):
            with self.subTest(body=body):
                items = observe('await tools.multi_agent_v1__spawn_agent({' + body + '});')
                self.assertTrue(items)
                self.assertFalse(items[0]["spawn_contract_valid"])
        partial = observe('await tools.multi_agent_v1__spawn_agent({' + prefix)
        self.assertFalse(any(item["spawn_contract_valid"] for item in partial))

    def test_nested_parser_rejects_incomplete_comments_and_oversized_input(self) -> None:
        args = spawn_compat.build_arguments(model="gpt-6-sol", effort="medium", task_name="bounded", message="Inspect.")
        call = 'tools.multi_agent_v1__spawn_agent(' + json.dumps(args) + ')'
        for source in ('/* never closed ' + call, ' ' * (256 * 1024) + call):
            self.assertFalse(any(item["spawn_contract_valid"] for item in spawn_compat.observe_nested_calls(source)))

    def test_nested_message_with_spawn_code_is_not_a_second_call(self) -> None:
        args = spawn_compat.build_arguments(model="gpt-6-sol", effort="medium", task_name="bounded",
                                           message='Example: tools.spawn_agent({model:"gpt-6-sol",fork_turns:"all"})')
        observed = spawn_compat.observe_nested_calls('text(await tools.spawn_agent(' + json.dumps(args) + '));')
        self.assertEqual(1, len(observed))
        self.assertTrue(observed[0]["spawn_contract_valid"])

    def test_builds_supported_direct_model_calls(self) -> None:
        for model, effort in (
            ("gpt-6-sol", "medium"),
            ("gpt-6-sol", "high"),
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
            ("gpt-6-luna", "low"),
            ("gpt-5.6-sol", "medium"),
            ("gpt-5.6-unknown", "medium"),
            ("gpt-6-sol", "ultra"),
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

    def test_internal_policy_validation_preserves_supported_spawn_schema(self) -> None:
        build = getattr(spawn_compat, "build_policy_arguments", None)
        self.assertTrue(callable(build), "typed policy-selection boundary is missing")
        args = build(
            profile_id="balanced", model="gpt-6-sol", effort="medium",
            discovery_state="available", root_model="gpt-6-luna", root_effort="low",
            task_name="bounded", message="Inspect only.",
        )
        self.assertEqual(
            {"fork_turns", "task_name", "message", "model", "reasoning_effort"},
            set(args),
        )
        with self.assertRaisesRegex(ValueError, "policy selection denied"):
            build(
                profile_id="balanced", model="gpt-6-sol", effort="medium",
                discovery_state="available", root_model="gpt-6-luna", root_effort="low",
                requested_model_id="gpt-5.6-sol", task_name="bounded", message="Inspect.",
            )
        with self.assertRaisesRegex(ValueError, "policy selection denied"):
            build(
                profile_id="high", model="gpt-6-sol", effort="xhigh",
                discovery_state="available", root_model="gpt-6-sol", root_effort=None,
                task_name="bounded", message="Inspect.",
            )

    def test_explicit_independent_council_allows_same_profile_without_allowing_downward_spawns(self) -> None:
        args = spawn_compat.build_policy_arguments(
            profile_id="balanced", model="gpt-6-sol", effort="medium",
            discovery_state="available", root_model="gpt-6-sol", root_effort="medium",
            task_name="independent-advisor", message="Assess the separate bounded question.",
            independent_parallel=True,
        )
        self.assertEqual("gpt-6-sol", args["model"])
        self.assertEqual("medium", args["reasoning_effort"])
        with self.assertRaisesRegex(ValueError, "policy selection denied"):
            spawn_compat.build_policy_arguments(
                profile_id="balanced", model="gpt-6-sol", effort="medium",
                discovery_state="available", root_model="gpt-6-sol", root_effort="high",
                task_name="downward", message="Must not route down.",
                independent_parallel=True,
            )
    def test_explicit_astra_uses_its_separate_effort_policy(self) -> None:
        build = getattr(spawn_compat, "build_explicit_astra_arguments", None)
        self.assertTrue(callable(build), "explicit Astra policy boundary is missing")
        args = build(
            effort="high", discovery_state="available", root_model="gpt-6-luna",
            task_name="frontier", message="Run this bounded explicit request.",
        )
        self.assertEqual("gpt-6-astra", args["model"])
        self.assertEqual("high", args["reasoning_effort"])
        with self.assertRaisesRegex(ValueError, "policy selection denied"):
            build(
                effort="low", discovery_state="available", root_model="gpt-6-luna",
                task_name="frontier", message="Run this bounded request.",
            )


if __name__ == "__main__":
    unittest.main()
