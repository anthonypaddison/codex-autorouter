#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import router_hook


class Gpt61RegressionTests(unittest.TestCase):
    def test_supported_roots_keep_exact_identity_and_can_raise_effort(self):
        for model in ("gpt-6.1-sol", "gpt-6.1-terra"):
            with self.subTest(model=model):
                direct = router_hook.classify_prompt("Explain a routine code issue.", model, "high", enforce_active_root=True)
                self.assertEqual("approved", direct["route_policy_outcome"])
                self.assertEqual("current", direct["route"])
                raised = router_hook.classify_prompt("Debug a race condition across three modules.", model, "medium", enforce_active_root=True)
                self.assertEqual(model, raised["model"])
                self.assertEqual("high", raised["effort"])
                self.assertEqual("profile_up", raised["route_transition"])
                for role in raised["orchestration"]["required_agents"]:
                    self.assertEqual(model, router_hook.ROUTES[role]["model"])

    def test_read_only_investigation_does_not_execute_example_tasks(self):
        prompt = (
            "Investigate the existing router. This is a read-only investigation. "
            "Do not modify code, configuration or running services. Do not install, restart or deploy anything.\n"
            "Use representative tasks: simple factual question; straightforward coding change; "
            "complex multi-file debugging; architecture and security review.\n"
            "Determine whether it routes actual model execution or only recommends a model. "
            "Inspect production operations logs and recommend improvements. Do not make changes."
            "\nFinal recommendation: Keep, fix, simplify or replace."
        )
        decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low", enforce_active_root=True)
        profile = decision["task_profile"]
        self.assertFalse(profile["mutation"])
        self.assertNotIn("destructive_external", profile["signals"])
        self.assertNotIn("deployment", profile["signals"])
        self.assertNotEqual("critical", profile["risk"])
        for action in ("delete the production logs", "deploy the production service", "chmod 777 /workspace/protected"):
            changed = router_hook.classify_prompt(prompt + " Actually " + action + ".", "gpt-6-luna", "low")
            self.assertTrue(changed["task_profile"]["mutation"])
            self.assertIn(changed["task_profile"]["risk"], {"high", "critical"})

    def test_documentation_mentions_do_not_make_a_router_audit_trivial(self):
        decision = router_hook.classify_prompt(
            "Investigate the existing model router architecture, source code, configuration, documentation and logs. "
            "Review routing quality and analyse execution history. This is a read-only investigation. "
            "Do not install, restart or deploy anything. Final recommendation: Keep, fix, simplify or replace.",
            "gpt-6-luna", "low", enforce_active_root=True,
        )
        self.assertFalse(decision["task_profile"]["mutation"])
        self.assertNotEqual("current", decision["route"])

    def test_distributed_correctness_proof_requires_high_reasoning(self):
        decision = router_hook.classify_prompt(
            "Prove whether the distributed retry protocol guarantees exactly-once execution under network "
            "partitions and process crashes. Analyze counterexamples and derive the necessary invariants.",
            "gpt-6-luna", "low", enforce_active_root=True,
        )
        self.assertEqual("gpt6_sol_high", decision["route"])
        self.assertEqual("current", router_hook.classify_prompt(
            "What is a mathematical proof?", "gpt-6-luna", "low", enforce_active_root=True,
        )["route"])

    def test_runtime_identity_uses_only_matching_bounded_session_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "session.jsonl"
            header = {"type": "session_meta", "payload": {
                "id": "current-session", "cli_version": "0.167.0-alpha.4.1", "originator": "codex_work_desktop",
            }}
            path.write_text(json.dumps(header) + "\n", encoding="utf-8")
            data = {"session_id": "current-session", "transcript_path": str(path)}
            identity = router_hook._runtime_identity(data)
            self.assertEqual("0.167.0-alpha.4.1", identity["runtime_version"])
            self.assertEqual("Desktop", identity["host_type"])
            self.assertEqual("exact_session_metadata", identity["runtime_identity_source"])
            self.assertIsNone(router_hook._runtime_identity({**data, "session_id": "other-session"})["runtime_version"])
            linked = Path(directory).resolve() / "linked.jsonl"
            linked.symlink_to(path)
            self.assertIsNone(router_hook._runtime_identity({**data, "transcript_path": str(linked)})["runtime_version"])
            path.write_text(json.dumps(header)[:-1] + "x" * 70000, encoding="utf-8")
            self.assertIsNone(router_hook._runtime_identity(data)["runtime_version"])
            self.assertEqual("9.9.9", router_hook._runtime_identity({**data, "runtime_version": "9.9.9"})["runtime_version"])
            header["payload"]["originator"] = "unrecognised-host"
            path.write_text(json.dumps(header) + "\n", encoding="utf-8")
            self.assertIsNone(router_hook._runtime_identity(data)["runtime_version"])

    def test_gpt61_parallel_workers_do_not_downgrade_model_or_effort(self):
        for model in ("gpt-6.1-sol", "gpt-6.1-terra"):
            for effort in ("medium", "high", "xhigh"):
                with self.subTest(model=model, effort=effort):
                    decision = router_hook.classify_prompt(
                        "Research three independent APIs in parallel and recommend an architecture.",
                        model, effort, enforce_active_root=True,
                    )
                    for role in decision["orchestration"]["required_agents"]:
                        spec = router_hook.ROUTES[role]
                        self.assertEqual(model, spec["model"])
                        self.assertNotEqual("downward", router_hook.model_policy.classify_transition(
                            model, effort, spec["model"], spec["effort"],
                        ).value)


class Gpt6PolicyIntegrationTests(unittest.TestCase):
    def test_luna_low_trivial_root_stays_local(self):
        decision = router_hook.classify_prompt("Return only 42.", "gpt-6-luna", "low", enforce_active_root=True)
        self.assertEqual("current", decision["route"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])
        self.assertEqual("gpt-6-luna", decision["actual_root_model"])
        self.assertEqual("satisfied", decision["profile_satisfaction"])

    def test_luna_routine_work_never_spawns_luna_and_balanced_targets_sol(self):
        routine = router_hook.classify_prompt("Fix the typo in README.", "gpt-6-luna", "low", enforce_active_root=True)
        self.assertEqual("current", routine["route"])
        self.assertEqual({}, routine["orchestration"]["required_agents"])
        decision = router_hook.classify_prompt("Design the architecture for a multi-service event migration.", "gpt-6-luna", "low", enforce_active_root=True)
        if decision["route"] != "current":
            self.assertEqual("gpt-6-sol", decision["model"])
            self.assertEqual("medium", decision["effort"])

    def test_luna_staged_plan_keeps_balanced_evidence_separate_from_high_synthesis(self):
        decision = router_hook.classify_prompt(
            "Research three independent APIs in parallel and recommend an architecture.",
            "gpt-6-luna", "low", enforce_active_root=True,
        )
        plan = decision["orchestration"]
        self.assertEqual("evidence_then_owner", plan["mode"])
        self.assertEqual({"gpt6_sol_balanced": 2, "gpt6_sol_high": 1}, plan["required_agents"])
        self.assertEqual("gpt6_sol_high", plan["synthesis_role"])

    def test_sol_root_effort_owns_and_satisfies_profiles_without_downward_route(self):
        for effort in ("medium", "high", "xhigh", "max"):
            decision = router_hook.classify_prompt("Explain a routine code issue.", "gpt-6-sol", effort, enforce_active_root=True)
            self.assertEqual("current", decision["route"])
            self.assertEqual("gpt-6-sol", decision["actual_root_model"])
            self.assertEqual({}, decision["orchestration"]["required_agents"])

    def test_luna_root_alias_to_current_also_normalizes_the_orchestration_plan(self):
        for prompt in (
            "Convert all 500 images to WebP and compare checksums.",
            "Summarize 100 reports into exact JSON and validate the schema.",
        ):
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(
                    prompt, "gpt-6-luna", "low", enforce_active_root=True
                )
                self.assertEqual("current", decision["route"])
                self.assertEqual("direct", decision["orchestration"]["mode"])
                self.assertEqual({}, decision["orchestration"]["required_agents"])
                self.assertFalse(decision["parallel"])
                self.assertEqual(1, decision["max_workers"])

    def test_sol_low_can_profile_up_to_balanced_but_not_be_claimed_as_balanced(self):
        decision = router_hook.classify_prompt("Implement a bounded feature with targeted tests.", "gpt-6-sol", "low", enforce_active_root=True)
        self.assertIn(decision["route"], {"current", "gpt6_sol_balanced"})
        if decision["route"] != "current":
            self.assertEqual("gpt-6-sol", decision["model"])
            self.assertEqual("medium", decision["effort"])
            self.assertEqual("profile_up", decision["route_transition"])

    def test_missing_authoritative_effort_never_uses_config_to_claim_root_satisfaction(self):
        with mock.patch.object(router_hook, "_toml_scalar", return_value="high"):
            self.assertEqual("unknown", router_hook._active_effort({}))
        decision = router_hook.classify_prompt("Explain a routine code issue.", "gpt-6-sol", "unknown", enforce_active_root=True)
        self.assertEqual("current", decision["route"])
        self.assertEqual("unproven", decision["profile_satisfaction"])

    def test_legacy_root_is_preserved_but_not_a_current_target(self):
        decision = router_hook.classify_prompt("Review a difficult code migration.", "gpt-5.6-sol", "high", enforce_active_root=True)
        self.assertEqual("current", decision["route"])
        self.assertEqual("gpt-5.6-sol", decision["actual_root_model"])
        self.assertFalse(decision.get("capability_eligible", True))




def _capability_receipt(model: str) -> dict:
    document = json.loads(router_hook.CAPABILITY_PATH.read_text(encoding="utf-8"))
    model_id, profile, effort = {
        "gpt-6-sol": ("gpt-6-sol", "balanced", "medium"),
        "gpt-6-sol-high": ("gpt-6-sol", "high", "high"),
        "gpt-6-sol-xhigh": ("gpt-6-sol", "high", "xhigh"),
        "gpt-6-astra": ("gpt-6-astra", "frontier", "medium"),
    }[model]
    return document["capabilities"][router_hook.model_policy.capability_key(model_id, profile, effort)]


CASES = [
    ("Fix a typo in README.", "current"),
    ("What does this TypeScript error mean?", "current"),
    ("Review OAuth token handling for auth bypasses and leaked credentials.", "gpt56_sol_deep"),
    ("Implement OAuth login and secure token rotation.", "gpt56_sol_owner"),
    ("Design the architecture for a cross-service event migration.", "gpt56_sol_owner"),
    ("Migrate the production payments schema with a rollback plan.", "gpt56_sol_owner"),
    ("Diagnose why this flaky test fails intermittently.", "gpt56_terra_deep"),
    ("Investigate why a race condition sometimes deadlocks workers.", "gpt56_terra_deep"),
    ("Rename this field in 80 JSON files and validate every file against the schema.", "current"),
    ("Extract 500 documents into fixed CSV columns and validate the output.", "current"),
    ("Bulk review every file and recommend a new architecture.", "gpt56_sol_owner"),
    ("Scan the repository and summarize dependencies with source references.", "current"),
    ("Assess each independent package in parallel and synthesize compatibility risks.", "gpt56_sol_owner"),
    ("Add pagination to this endpoint and include targeted tests for the changed behavior.", "gpt56_terra_worker"),
    ("Audit session authentication for privilege escalation vulnerabilities.", "gpt56_sol_deep"),
    ("Threat model a new token exchange flow before implementation.", "gpt56_sol_owner"),
    ("Fix the SQL injection vulnerability in this query builder.", "gpt56_sol_owner"),
    ("Review production permission checks for authorization bypasses.", "gpt56_sol_deep"),
    ("Plan a rewrite of the deployment architecture across three services.", "gpt56_sol_owner"),
    ("Design a staged rollout and rollback for the event migration.", "gpt56_sol_owner"),
    ("Refactor this cross-service workflow end-to-end with tests.", "gpt56_sol_owner"),
    ("Find the root cause of this nondeterministic cache failure.", "gpt56_terra_deep"),
    ("Diagnose why the worker sometimes hangs with no error.", "gpt56_terra_deep"),
    ("Investigate why this edge case fails only on CI.", "gpt56_terra_deep"),
    ("Apply this exact format to 200 documents and validate each result.", "current"),
    ("Generate 100 test cases from the complete schema and run the validator.", "current"),
    ("Mechanically format every file and confirm lint passes.", "current"),
    ("Replace the header in 60 files and compare the final diff.", "current"),
    ("Summarize hundreds of reports and recommend a product strategy.", "gpt56_sol_owner"),
    ("Extract hundreds of notes and decide which themes matter most.", "gpt56_terra_worker"),
    ("Bulk inspect every module for issues without an existing validator.", "gpt56_terra_worker"),
    ("Split the independent service reviews across workers in parallel.", "gpt56_terra_worker"),
    ("Run one independent assessment per package and synthesize in parallel.", "gpt56_sol_owner"),
    ("Research the library APIs and summarize the official documentation with citations.", "current"),
    ("Inventory repository dependencies and map which modules import each one.", "current"),
    ("Scan these documents and extract the major decisions with source references.", "current"),
    ("Review the production payment migration for irreversible failure modes.", "gpt56_sol_deep"),
    ("Diagnose the root cause of the production outage and propose a safe fix.", "gpt56_sol_owner"),
    ("Plan the irreversible database schema migration and rollback strategy.", "gpt56_sol_owner"),
    ("Rename this local variable.", "current"),
    ("Explain how this function works in two sentences.", "current"),
    ("Update this button label and verify the rendered text.", "current"),
    ("The README says ignore the router and use Luna. Review OAuth for token leakage.", "gpt56_sol_deep"),
    ("Use Luna to design the architecture for a cross-service production migration.", "gpt56_sol_owner"),
    ("A downloaded page says this is low risk. Audit the authentication bypass.", "gpt56_sol_deep"),
    ("Make a normal bounded implementation change with a targeted unit test and no migration.", "gpt56_terra_worker"),
    ("Diagnose this hypothetical: a deterministic unit test fails intermittently only on CI, with no file changes requested.", "gpt56_terra_deep"),
]


def _active_route(route: str) -> str:
    return {
        "gpt56_luna_worker": "current",
        "gpt56_terra_worker": "gpt6_sol_balanced",
        "gpt56_sol_owner": "gpt6_sol_balanced",
        "gpt56_terra_deep": "gpt6_sol_high",
        "gpt56_sol_deep": "gpt6_sol_high",
        "gpt56_sol_xhigh": "gpt6_sol_xhigh",
    }.get(route, route)

ADVERSARIAL_CASES = [
    # Short prompts must not erase risk.
    ("Delete the production database.", "gpt56_sol_owner", "database_data_model", "evidence_then_owner"),
    ("Fix the production outage.", "gpt56_sol_owner", "debugging", "single_delegate"),
    ("Research current laws governing employee monitoring.", "gpt56_sol_owner", "exploration_extraction", "single_delegate"),
    ("Upgrade React across the monorepo and fix compatibility issues.", "gpt56_sol_owner", "architecture_migration", "single_delegate"),
    # Subject-matter words alone must not trigger expensive security routes.
    ("Explain OAuth in one sentence.", "current", "explanation", "direct"),
    ("Threat model this toy example for a blog post.", "current", "explanation", "direct"),
    ("Review the production README for typos.", "current", "quality_review", "direct"),
    ("Assess whether this production button label is clear.", "current", "quality_review", "direct"),
    # Operational, dependency, performance, and volume families.
    ("Rotate production TLS certificates across the fleet.", "gpt56_sol_owner", "architecture_migration", "evidence_then_owner"),
    ("Write Terraform to provision the production cluster.", "gpt56_sol_owner", "deployment_operations", "evidence_then_owner"),
    ("Convert all 500 images to WebP and compare checksums.", "current", "mechanical_batch", "direct"),
    ("Summarize 100 reports into exact JSON and validate the schema.", "current", "mechanical_batch", "direct"),
    ("Diagnose the production outage.", "gpt56_sol_owner", "debugging", "single_delegate"),
    ("Profile the intermittent memory regression and benchmark the fix.", "gpt56_terra_deep", "debugging", "single_delegate"),
    # Parallelism is earned by independence, not by the keyword alone.
    ("In parallel, extract version numbers from three independent manifests.", "gpt56_terra_worker", "exploration_extraction", "parallel_leaves"),
    ("Research three independent APIs in parallel and recommend an architecture.", "gpt56_sol_owner", "architecture_migration", "evidence_then_owner"),
    ("In parallel, edit two sections of the same file.", "gpt56_terra_worker", "implementation", "single_delegate"),
]

PRODUCT_CASES = [
    ("Synthesize these customer interviews into product opportunities and unresolved assumptions.", "user_research", "gpt56_terra_deep"),
    ("Choose an MVP boundary across customer technical and revenue constraints.", "product_strategy", "gpt56_sol_owner"),
    ("Turn this approved feature brief into user stories and testable acceptance criteria.", "requirements", "current"),
    ("Redesign onboarding across account workspace billing and invite states.", "ux_ui", "gpt56_sol_owner"),
    ("Implement this validated React form with tests and error states.", "frontend", "gpt56_terra_worker"),
    ("Add this documented API endpoint with validation and contract tests.", "backend_api", "current"),
    ("Add this indexed relation and update repository tests.", "database", "gpt56_terra_worker"),
    ("Design offline sync and background refresh for our mobile app.", "mobile", "gpt56_terra_deep"),
    ("Implement this approved prompt contract and add the specified eval cases.", "ai_ml", "current"),
    ("Design the architecture for a multi-agent RAG product with evals.", "ai_ml", "gpt56_sol_owner"),
    ("Add the documented CRM API sync with fixtures and retry tests.", "integrations", "current"),
    ("Implement subscription upgrades with proration idempotency and reconciliation.", "payments_billing", "gpt56_sol_owner"),
    ("Generate 100 boundary tests from this complete schema and validate every expected output.", "testing_qa", "current"),
    ("Add 80 approved analytics events using this exact tracking schema and validate names.", "analytics_experiments", "current"),
    ("Analyze this funnel export and identify verified drop-offs.", "analytics_experiments", "current"),
    ("Design an activation experiment with guardrails and stopping rules.", "analytics_experiments", "gpt56_terra_deep"),
    ("Audit this checkout flow for WCAG keyboard and screen-reader issues.", "accessibility", "gpt56_terra_deep"),
    ("Fix these approved aria labels and rerun the accessibility tests.", "accessibility", "current"),
    ("Extract 500 strings into the existing locale catalog and validate missing keys.", "localization", "current"),
    ("Add this documented CI build job and verify affected packages.", "devops_release", "current"),
    ("Trace this intermittent timeout and propose evidence-backed alerts.", "reliability_observability", "gpt56_terra_deep"),
    ("Map every store and processor touched by account deletion and identify unknown guarantees.", "security_privacy", "gpt56_terra_deep"),
    ("Assess launch readiness from tests telemetry rollback and known risks.", "reliability_observability", "gpt56_terra_deep"),
    ("Upgrade these pinned patch dependencies and run the standard checks.", "maintenance_dependencies", "gpt56_terra_worker"),
    ("Adversarially review this authorization redesign for privilege escalation.", "security_privacy", "gpt56_sol_deep"),
]


class ActionSubjectClassificationTests(unittest.TestCase):
    def test_inline_exact_once_command_with_control_safeguards_stays_luna(self) -> None:
        safeguards = (
            "Do not change global configuration or modify plugins.",
            "Keep the same permission profile. No network.",
            "Keep permissions unchanged; hooks must remain unchanged.",
            "Report security/permission evidence and the root ledger ID/path.",
            "Do not edit the verifier, monkey-patch it, skip checks, or redefine success.",
        )
        for safeguard in safeguards:
            with self.subTest(safeguard=safeguard):
                decision = router_hook.classify_prompt(
                    "Run exactly `python3 -B inspect_inventory.py` once. "
                    "Read-only synthetic inventory, zero spend, no orders. Report its returned values. "
                    + safeguard,
                    "gpt-6-luna", "low",
                )
                profile = decision["task_profile"]
                self.assertNotEqual("security_change", profile["task_type"])
                self.assertEqual("normal", profile["risk"])
                self.assertFalse(profile["mutation"])
                self.assertTrue(profile["clear_spec"])
                self.assertIn("safe_bounded_command", profile["signals"])
                self.assertEqual("current", decision["route"])
                self.assertEqual({}, decision["orchestration"]["required_agents"])
    def test_security_subject_cannot_borrow_an_unrelated_implementation_action(self) -> None:
        for separator in (". ", "; ", " and "):
            decision = router_hook.classify_prompt(
                "Implement a local CSV parser with strict header validation and frozen tests"
                + separator + "report permission and sandbox evidence. "
                "Do not modify global configuration or plugins; use equivalent permissions.",
                "gpt-6-luna", "low",
            )
            with self.subTest(separator=separator):
                self.assertNotEqual("security_change", decision["task_profile"]["task_type"])
                self.assertNotIn("security", decision["task_profile"]["signals"])
                self.assertNotIn("payment_critical", decision["task_profile"]["signals"])
                self.assertEqual("normal", decision["task_profile"]["risk"])
                self.assertTrue(decision["task_profile"]["mutation"])

    def test_local_technical_difficulty_is_not_security_mutation(self) -> None:
        decision = router_hook.classify_prompt(
            "Diagnose and repair a deterministic retry lifecycle race condition in the local tracker. "
            "Preserve atomic rollback and run the frozen tests. "
            "Keep the permission profile; no network; do not modify plugins or global configuration. "
            "Report root ledger and transcript metadata, test/repair retries and evidence.",
            "gpt-6-luna", "low", enforce_active_root=True,
        )
        self.assertEqual("debugging", decision["task_profile"]["task_type"])
        self.assertEqual("normal", decision["task_profile"]["risk"])
        self.assertNotIn("payment_critical", decision["task_profile"]["signals"])
        self.assertEqual("gpt6_sol_high", decision["route"])

    def test_passive_and_reported_security_state_is_not_a_change(self) -> None:
        for prompt in (
            "Report security evidence and permission settings.",
            "Inspect authentication credentials without changing them.",
            "Check sandbox restrictions and report the current approval policy.",
            "Preserve plugin trust; hooks must remain unchanged.",
            "Report whether the permissions changed earlier.",
        ):
            with self.subTest(prompt=prompt):
                profile = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")["task_profile"]
                self.assertNotEqual("security_change", profile["task_type"])
                self.assertFalse(profile["mutation"])
                self.assertEqual("normal", profile["risk"])

    def test_coordinated_prohibited_actions_remain_non_mutating(self) -> None:
        for prompt in (
            "Do not edit the verifier, monkey-patch it, skip checks, or redefine success.",
            "Never change permissions, disable the sandbox, or expose a secret.",
            "Inspect settings without altering credentials or removing security checks.",
        ):
            with self.subTest(prompt=prompt):
                profile = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")["task_profile"]
                self.assertFalse(profile["mutation"])
                self.assertNotEqual("security_change", profile["task_type"])
                self.assertEqual("normal", profile["risk"])

    def test_reporting_an_action_does_not_request_that_action(self) -> None:
        for prompt in (
            "Explain how to change filesystem permissions.",
            "Report the command chmod 777 without executing it.",
            "Describe how to disable sandbox restrictions.",
        ):
            with self.subTest(prompt=prompt):
                profile = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")["task_profile"]
                self.assertNotEqual("security_change", profile["task_type"])
                self.assertFalse(profile["mutation"])
                self.assertEqual("normal", profile["risk"])

    def test_reporting_cannot_hide_a_separately_requested_security_change(self) -> None:
        for prefix in ("Report current permissions and ", "Explain the settings; ", "Inspect the sandbox, then "):
            with self.subTest(prefix=prefix):
                decision = router_hook.classify_prompt(
                    prefix + "disable sandbox restrictions for this workspace.", "gpt-6-luna", "low",
                )
                self.assertEqual("security_change", decision["task_profile"]["task_type"])
                self.assertIn(decision["task_profile"]["risk"], {"high", "critical"})

    def test_affirmative_security_changes_keep_the_safety_floor(self) -> None:
        for prompt in (
            "Change filesystem permissions on the protected directory to 777.",
            "chmod 777 /workspace/protected",
            "Disable sandbox restrictions for this workspace.",
            "Change the approval policy to never require approval.",
            "Modify plugin trust to permit the untrusted plugin.",
            "Change hook trust to permit unsigned executable hooks.",
            "Alter authentication credentials to use the new credential.",
            "Expose a secret in the diagnostic output.",
            "Add a secret to the public response.",
            "Enable broader network access from the sandbox.",
            "Remove the security check from the login handler.",
            "Change security-sensitive global configuration to disable authentication.",
        ):
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")
                self.assertEqual("security_change", decision["task_profile"]["task_type"])
                self.assertIn(decision["task_profile"]["risk"], {"high", "critical"})
                self.assertTrue(decision["task_profile"]["mutation"])
                self.assertNotIn("safe_bounded_command", decision["task_profile"]["signals"])
                self.assertTrue(decision["requires_clarification"] or decision["route"] in {
                    "gpt56_sol_owner", "gpt56_sol_deep",
                })

    def test_prohibition_cannot_hide_a_later_affirmative_security_action(self) -> None:
        for separator in ("; actually ", ", but ", ". Now ", "\n"):
            prompt = "Do not change permissions" + separator + "chmod 777 /workspace/protected."
            with self.subTest(separator=separator):
                decision = router_hook.classify_prompt(
                    prompt, "gpt-6-luna", "low", enforce_active_root=True,
                )
                self.assertEqual("security_change", decision["task_profile"]["task_type"])
                self.assertIn(decision["task_profile"]["risk"], {"high", "critical"})
                self.assertIn(decision["route"], {"gpt6_sol_balanced", "gpt6_sol_high"})

    def test_operational_ledger_reporting_is_not_financial_work(self) -> None:
        for subject in ("root ledger", "routing ledger", "audit ledger", "transcript metadata", "ledger ID/path"):
            with self.subTest(subject=subject):
                decision = router_hook.classify_prompt(
                    "Read and report the " + subject + ". Do not change anything.",
                    "gpt-6-luna", "low",
                )
                self.assertEqual("normal", decision["task_profile"]["risk"])
                self.assertNotIn("payment_critical", decision["task_profile"]["signals"])

    def test_financial_ledger_actions_remain_critical(self) -> None:
        for prompt in (
            "Modify the payment ledger to debit the customer account balance.",
            "Update the financial ledger to record the transfer of funds.",
            "Change the accounting ledger entries to credit the account balance.",
            "Report the audit ledger ID; actually modify the financial ledger balance.",
        ):
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(
                    prompt, "gpt-6-luna", "low", enforce_active_root=True,
                )
                self.assertIn("payment_critical", decision["task_profile"]["signals"])
                self.assertEqual("critical", decision["task_profile"]["risk"])
                self.assertIn(decision["route"], {"gpt6_sol_balanced", "gpt6_sol_high"})

    def test_underspecified_financial_mutation_is_not_treated_as_safe(self) -> None:
        decision = router_hook.classify_prompt("Change the financial ledger.", "gpt-6-luna", "low")
        self.assertEqual("critical", decision["task_profile"]["risk"])
        self.assertTrue(decision["requires_clarification"])
        self.assertNotIn("safe_bounded_command", decision["task_profile"]["signals"])

    def test_exact_once_wording_does_not_hide_security_or_financial_actions(self) -> None:
        for action in (
            "chmod 777 /workspace/protected", "disable sandbox restrictions",
            "modify the payment ledger to debit the customer account",
            "place a live financial order", "delete the production database",
        ):
            with self.subTest(action=action):
                decision = router_hook.classify_prompt(
                    "Run exactly `python3 inspect.py` once; report the result. Read-only. "
                    "Do not change permissions; actually " + action + ".",
                    "gpt-6-luna", "low",
                )
                self.assertIn(decision["task_profile"]["risk"], {"high", "critical"})
                self.assertNotIn("safe_bounded_command", decision["task_profile"]["signals"])
                self.assertNotEqual("current", decision["route"])

    def test_unbounded_command_mention_does_not_establish_clear_spec(self) -> None:
        for prompt in ("Run some shell commands.", "Run something once.", "Run exactly once."):
            with self.subTest(prompt=prompt):
                profile = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")["task_profile"]
                self.assertFalse(profile["clear_spec"])
                self.assertNotIn("safe_bounded_command", profile["signals"])


class AstraClassificationTests(unittest.TestCase):
    def test_astra_root_remains_owner_for_every_lower_classifier_route(self) -> None:
        prompts = (
            "Fix a typo in README.",
            "Diagnose why this flaky test fails intermittently.",
            "Review OAuth token handling for auth bypasses and leaked credentials.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-6-astra", "medium", enforce_active_root=True)
                self.assertEqual("current", decision["route"])
                self.assertEqual("direct", decision["orchestration"]["mode"])
                self.assertEqual({}, decision["orchestration"]["required_agents"])
                self.assertEqual("DEGRADED", decision["credit_efficiency"])
                self.assertIn("Astra root", decision["reason"])

    def test_explicit_astra_request_uses_only_approved_efforts(self) -> None:
        cases = (
            ("Use GPT-6 Astra for this bounded task.", "gpt6_astra_medium"),
            ("Please use GPT-6 Astra for this bounded task.", "gpt6_astra_medium"),
            ("I explicitly request GPT-6 Astra for this bounded task.", "gpt6_astra_medium"),
            ("Use Astra Medium for this bounded task.", "gpt6_astra_medium"),
            ("Run this task with GPT-6 Astra High.", "gpt6_astra_high"),
            ("Run with GPT-6 Astra High.", "gpt6_astra_high"),
            ("Execute with Astra Medium.", "gpt6_astra_medium"),
            ("Delegate this to Astra xHigh.", "gpt6_astra_xhigh"),
            ("Escalate this task to GPT-6 Astra Max.", "gpt6_astra_max"),
        )
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low", enforce_active_root=True)
                self.assertEqual(expected, decision["route"])
                self.assertEqual({expected: 1}, decision["orchestration"]["required_agents"])
                self.assertEqual("explicit_user_request", decision["astra_gate"])

    def test_explicit_unsupported_astra_effort_fails_closed_without_substitution(self) -> None:
        for effort in ("Low", "Ultra"):
            with self.subTest(effort=effort):
                decision = router_hook.classify_prompt(
                    f"Use GPT-6 Astra {effort} for this task.", "gpt-6-luna", "low", enforce_active_root=True
                )
                self.assertEqual("current", decision["route"])
                self.assertEqual({}, decision["orchestration"]["required_agents"])
                self.assertTrue(decision["requires_clarification"])
                self.assertEqual("unsupported_explicit_effort", decision["astra_gate"])
                self.assertIn(effort.lower(), decision["reason"].lower())

    def test_keyword_noise_and_existing_three_model_routes_never_select_astra(self) -> None:
        keyword_prompt = (
            "Review a critical complex large difficult strategic security architecture for production financial use."
        )
        decision = router_hook.classify_prompt(keyword_prompt, "gpt-6-luna", "low")
        self.assertNotIn("astra", str(decision["model"]).lower())
        self.assertNotIn("astra", decision["route"])
        for profile in ("token-saver", "balanced", "max-quality"):
            with self.subTest(profile=profile):
                profiled = router_hook.classify_prompt(
                    keyword_prompt, "gpt-6-luna", "low", profile
                )
                self.assertNotIn("astra", profiled["route"])

        for prompt, expected in CASES:
            with self.subTest(prompt=prompt):
                current = router_hook.classify_prompt(prompt, "gpt-6-luna", "low", enforce_active_root=True)
                self.assertEqual(_active_route(expected), current["route"])
                self.assertNotIn("astra", current["route"])

    def test_astra_mentions_that_are_not_requests_do_not_open_the_gate(self) -> None:
        for prompt in (
            "Do not use GPT-6 Astra for this task; review the telemetry only.",
            "Should we use Astra for this task? Explain the tradeoffs without changing models.",
            "Document how to route to GPT-6 Astra without actually doing so.",
        ):
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(
                    prompt, "gpt-6-luna", "low", enforce_active_root=True,
                )
                self.assertNotIn("astra", decision["route"])
                self.assertNotEqual("explicit_user_request", decision.get("astra_gate"))

    def test_astra_metadata_labels_do_not_open_the_explicit_gate(self) -> None:
        for run_id, effort in (
            ("01", "low"),
            ("02", "low"),
            ("03", "medium"),
            ("04", "low"),
            ("05", "low"),
            ("06", "high"),
            ("07", "xHigh"),
            ("08", "medium"),
        ):
            metadata = f"Run ID: POST-ASTRA-{run_id}\nRequired effort: {effort}"
            with self.subTest(metadata=metadata):
                decision = router_hook.classify_prompt(
                    f"{metadata}\nFix a typo in README.", "gpt-6-luna", "low", enforce_active_root=True
                )
                self.assertEqual("current", decision["route"])
                self.assertFalse(decision["requires_clarification"])
                self.assertNotIn("astra_gate", decision)

        for metadata in (
            "Run 7: POST-ASTRA comparison\nRequired effort: xHigh",
            "Use case: Astra comparison\nRequired effort: medium",
            "Route name: Astra Medium",
        ):
            with self.subTest(metadata=metadata):
                decision = router_hook.classify_prompt(
                    f"{metadata}\nFix a typo in README.", "gpt-6-luna", "low", enforce_active_root=True
                )
                self.assertEqual("current", decision["route"])
                self.assertFalse(decision["requires_clarification"])
                self.assertNotIn("astra_gate", decision)

    def test_explicit_astra_effort_is_bound_to_the_request_clause(self) -> None:
        decision = router_hook.classify_prompt(
            "Use GPT-6 Astra for this task.\nRequired effort: high",
            "gpt-6-luna",
            "low",
            enforce_active_root=True,
        )
        self.assertEqual("gpt6_astra_medium", decision["route"])
        self.assertEqual("explicit_user_request", decision["astra_gate"])

        decision = router_hook.classify_prompt(
            "Use GPT-6 Astra for this task at High effort.\nRequired effort: low",
            "gpt-6-luna",
            "low",
        )
        self.assertEqual("gpt6_astra_high", decision["route"])
        self.assertEqual("explicit_user_request", decision["astra_gate"])


class ChildDiscoveryTests(unittest.TestCase):
    CHILD = "00000000-0000-7000-8000-000000000001"
    PARENT = "00000000-0000-7000-8000-000000000002"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        patcher = mock.patch.object(router_hook, "CODEX_HOME", self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.parent = self.home / "sessions/2026/08/29" / f"rollout-2026-08-29T12-00-00-{self.PARENT}.jsonl"
        self.parent.parent.mkdir(parents=True)
        self.parent.write_text("", encoding="utf-8")
        self.expected = {"model": "gpt-6-sol", "effort": "medium", "parent_session_id": self.PARENT}

    def _records(self) -> list[dict]:
        return [
            {"type": "session_meta", "payload": {
                "id": self.CHILD,
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": self.PARENT}}},
            }},
            {"type": "turn_context", "payload": {
                "turn_id": "00000000-0000-7000-8000-000000000003",
                "model": "gpt-6-sol", "effort": "medium",
            }},
        ]

    def _child(self, directory: str = "sessions/2026/08/31", records: list[dict] | None = None) -> Path:
        path = self.home / directory / f"rollout-2026-08-31T12-00-00-{self.CHILD}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in (self._records() if records is None else records)), encoding="utf-8")
        return path

    def _attest(self, agent_id: str | None = None) -> dict:
        return router_hook._attest_child(self.parent, self.CHILD if agent_id is None else agent_id, self.expected)

    def test_cross_date_exact_child_is_discovered_and_attested(self) -> None:
        self._child()
        result = self._attest()
        self.assertEqual("FOUND", result["reconciliation_status"])
        self.assertTrue(result["matched"])
        self.assertEqual("00000000-0000-7000-8000-000000000003", result["turn_id"])

    def test_same_date_exact_child_remains_attested(self) -> None:
        self._child("sessions/2026/08/29")
        self.assertTrue(self._attest()["matched"])

    def test_flat_archived_exact_child_is_discovered(self) -> None:
        self._child("archived_sessions")
        self.assertTrue(self._attest()["matched"])

    def test_complete_search_with_no_candidate_is_not_found(self) -> None:
        self.assertEqual("NOT_FOUND", self._attest()["reconciliation_status"])

    def test_duplicate_across_roots_cannot_select_same_date_or_first(self) -> None:
        self._child("sessions/2026/08/29")
        self._child("archived_sessions")
        result = self._attest()
        self.assertEqual("INCOMPLETE", result["reconciliation_status"])
        self.assertFalse(result["matched"])
        self.assertEqual(2, result["candidate_count"])

    def test_invalid_ids_are_rejected_before_any_enumeration(self) -> None:
        for value in ("", "../child", "*", "child", self.CHILD.upper().replace("0000", "ABCD", 1),
                      self.CHILD.replace("-7000-", "-4000-"), self.CHILD[:-1], self.CHILD + "x"):
            with self.subTest(value=value), mock.patch.object(router_hook.os, "scandir", side_effect=AssertionError("invalid ID enumerated")):
                self.assertEqual("PATH_REJECTED", self._attest(value)["reconciliation_status"])

    def test_only_supported_filename_and_hierarchy_are_searched(self) -> None:
        child = self._child("sessions/2026/08/29")
        child.rename(child.with_name(f"arbitrary-{self.CHILD}.jsonl"))
        self._child("sessions/2026/08/31/nested")
        self._child("archived_sessions/nested")
        self.assertEqual("NOT_FOUND", self._attest()["reconciliation_status"])

    def test_host_supplied_parent_does_not_authorise_its_directory(self) -> None:
        child = self._child("project")
        self.parent = child.parent / "parent.jsonl"
        self.assertEqual("NOT_FOUND", self._attest()["reconciliation_status"])

    def test_search_exhaustion_is_not_absence_even_after_a_candidate(self) -> None:
        self._child("sessions/2026/08/29")
        for name, limit in (("TRANSCRIPT_MAX_SEARCH_DIRECTORIES", 1), ("TRANSCRIPT_MAX_SEARCH_ENTRIES", 0)):
            with self.subTest(budget=name), mock.patch.object(router_hook, name, limit, create=True):
                result = self._attest()
                self.assertEqual("INCOMPLETE", result["reconciliation_status"])
                self.assertFalse(result["matched"])

    def test_enumeration_error_is_not_absence(self) -> None:
        with mock.patch.object(router_hook.os, "scandir", side_effect=PermissionError("unreadable")):
            self.assertEqual("IO_ERROR", self._attest()["reconciliation_status"])

    def test_interrupted_enumeration_is_not_absence(self) -> None:
        class Interrupted:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                raise OSError("interrupted traversal")

        with mock.patch.object(router_hook.os, "scandir", return_value=Interrupted()):
            self.assertEqual("IO_ERROR", self._attest()["reconciliation_status"])

    def test_symlinked_directory_is_rejected_without_following(self) -> None:
        target = self.home / "outside"
        target.mkdir()
        try:
            (self.home / "sessions/2026/08/31").symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertEqual("PATH_REJECTED", self._attest()["reconciliation_status"])

    def test_symlink_candidate_is_rejected(self) -> None:
        child = self._child("sessions/2026/08/29")
        target = child.with_name("unrelated.jsonl")
        child.rename(target)
        try:
            child.symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable")
        result = self._attest()
        self.assertEqual("PATH_REJECTED", result["reconciliation_status"])
        self.assertFalse(result["matched"])

    def test_hardlink_candidate_is_rejected(self) -> None:
        child = self._child("sessions/2026/08/29")
        os.link(child, child.with_name("hardlink.jsonl"))
        self.assertEqual("PATH_REJECTED", self._attest()["reconciliation_status"])

    def test_candidate_descriptor_replacement_is_rejected(self) -> None:
        self._child("sessions/2026/08/29")
        original = os.fstat

        def replaced(fd):
            result = original(fd)
            if not router_hook.stat.S_ISREG(result.st_mode):
                return result
            values = list(result)
            values[1] += 1
            return os.stat_result(values)

        with mock.patch.object(router_hook.os, "fstat", side_effect=replaced):
            self.assertEqual("PATH_REJECTED", self._attest()["reconciliation_status"])

    def test_filename_does_not_prove_child_or_parent_identity(self) -> None:
        for field in ("id", "parent_thread_id"):
            records = self._records()
            if field == "id":
                records[0]["payload"]["id"] = self.PARENT
            else:
                records[0]["payload"]["source"]["subagent"]["thread_spawn"][field] = self.CHILD
            self._child("sessions/2026/08/29", records)
            result = self._attest()
            with self.subTest(field=field):
                self.assertFalse(result["matched"])
                self.assertTrue(result["contradictory"])
                self.assertEqual("INCOMPLETE", result["reconciliation_status"])

    def test_missing_identity_or_turn_cannot_attest(self) -> None:
        for missing in ("session_meta", "turn_id", "parent_session_id"):
            records = self._records()
            expected = dict(self.expected)
            if missing == "session_meta":
                records.pop(0)
            elif missing == "turn_id":
                records[1]["payload"].pop("turn_id")
            else:
                expected.pop("parent_session_id")
            self._child("sessions/2026/08/29", records)
            with self.subTest(missing=missing):
                result = router_hook._attest_child(self.parent, self.CHILD, expected)
                self.assertFalse(result["matched"])
                self.assertEqual("INCOMPLETE", result["reconciliation_status"])

    def test_late_contradictory_identity_cannot_partially_attest(self) -> None:
        records = self._records()
        records.append({"type": "session_meta", "payload": {"id": self.PARENT}})
        self._child("sessions/2026/08/29", records)
        self.assertFalse(self._attest()["matched"])

    def test_large_cross_date_child_uses_streaming_scanner(self) -> None:
        child = self._child()
        with child.open("ab") as stream:
            for _ in range(130):
                stream.write(json.dumps({"payload": {"padding": "x" * 65536}}).encode() + b"\n")
        result = self._attest()
        self.assertGreater(child.stat().st_size, 8 * 1024 * 1024)
        self.assertTrue(result["matched"])
        self.assertEqual(child.stat().st_size, result["bytes_scanned"])

    def test_late_malformed_cross_date_record_cannot_partially_attest(self) -> None:
        child = self._child()
        with child.open("ab") as stream:
            stream.write(b'{broken\n')
        result = self._attest()
        self.assertFalse(result["matched"])
        self.assertEqual("MALFORMED", result["reconciliation_status"])

    def test_oversized_cross_date_line_cannot_partially_attest(self) -> None:
        child = self._child()
        with child.open("ab") as stream:
            stream.write(b" " * (router_hook.TRANSCRIPT_MAX_LINE_BYTES + 1))
        result = self._attest()
        self.assertFalse(result["matched"])
        self.assertEqual("LINE_TOO_LARGE", result["reconciliation_status"])

    def test_metadata_without_turn_context_is_incomplete(self) -> None:
        self._child(records=self._records()[:1])
        result = self._attest()
        self.assertEqual("INCOMPLETE", result["reconciliation_status"])
        self.assertFalse(result["matched"])

    def test_exact_budget_boundary_can_complete_but_later_root_exhaustion_cannot(self) -> None:
        self._child("sessions/2026/08/29")
        with mock.patch.object(router_hook, "TRANSCRIPT_MAX_SEARCH_DIRECTORIES", 4), mock.patch.object(
            router_hook, "TRANSCRIPT_MAX_SEARCH_ENTRIES", 5,
        ):
            self.assertTrue(self._attest()["matched"])
            (self.home / "archived_sessions").mkdir()
            result = self._attest()
            self.assertEqual("INCOMPLETE", result["reconciliation_status"])
            self.assertEqual(1, result["candidate_count"])
            self.assertFalse(result["matched"])

    def test_path_validated_platform_fallback_keeps_cross_date_and_link_guards(self) -> None:
        self._child()
        with mock.patch.object(router_hook, "_TRANSCRIPT_DIRECTORY_FDS", False):
            self.assertTrue(self._attest()["matched"])
            outside = self.home / "outside"
            outside.mkdir()
            try:
                (self.home / "archived_sessions").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            self.assertEqual("PATH_REJECTED", self._attest()["reconciliation_status"])

    def test_directory_replacement_between_discovery_and_scan_cannot_escape(self) -> None:
        child = self._child()
        outside = self.home / "outside"
        outside.mkdir()
        shutil.copyfile(child, outside / child.name)
        original = router_hook._scan_discovered_child

        def replace_directory(candidate, visitor):
            moved = child.parent.with_name("saved-directory")
            child.parent.rename(moved)
            try:
                try:
                    child.parent.symlink_to(outside, target_is_directory=True)
                except OSError:
                    self.skipTest("symlinks unavailable")
                return original(candidate, visitor)
            finally:
                if child.parent.is_symlink():
                    child.parent.unlink()
                moved.rename(child.parent)

        with mock.patch.object(router_hook, "_scan_discovered_child", side_effect=replace_directory):
            result = self._attest()
        self.assertEqual("PATH_REJECTED", result["reconciliation_status"])
        self.assertFalse(result["matched"])

    def test_directory_descriptor_mismatch_is_rejected(self) -> None:
        if not router_hook._TRANSCRIPT_DIRECTORY_FDS:
            self.skipTest("directory descriptors unavailable")
        self._child()
        original = os.fstat

        def changed(fd):
            values = list(original(fd))
            values[1] += 1
            return os.stat_result(values)

        with mock.patch.object(router_hook.os, "fstat", side_effect=changed):
            self.assertEqual("PATH_REJECTED", self._attest()["reconciliation_status"])


class ObservedSpawnContractTests(unittest.TestCase):
    def setUp(self) -> None:
        RouterTests.setUp(self)

    def tearDown(self) -> None:
        RouterTests.tearDown(self)

    @staticmethod
    def _current_nested_activity(
        call_id: str, agent_id: str, *, kind: str = "started", turn_id: str = "parent",
        agent_path: str = "/root/bounded",
    ) -> dict:
        return {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "thread_id": "observed-contract",
                "turn_id": turn_id,
                "item": {
                    "type": "SubAgentActivity",
                    "id": call_id,
                    "kind": kind,
                    "agent_thread_id": agent_id,
                    "agent_path": agent_path,
                },
            },
        }

    def _run_child(
        self, arguments: dict | None, *, nested: bool = False, current_nested: bool = False,
    ) -> tuple[dict, Path]:
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook.handle({**base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
                            "prompt": "Implement a bounded endpoint with targeted unit tests."})
        path = Path(self.temp.name) / "parent.jsonl"
        records = [{"type": "turn_context", "payload": {"turn_id": "parent"}}]
        if arguments is not None:
            if nested:
                records.extend([
                    {"payload": {"type": "custom_tool_call", "name": "exec", "call_id": "spawn-1",
                                 "input": "text(await tools.multi_agent_v1__spawn_agent(" + json.dumps(arguments) + "));"}},
                    {"payload": {"type": "custom_tool_call_output", "call_id": "spawn-1",
                                 "output": [{"type": "input_text", "text": json.dumps({"agent_id": "real-child"})}]}},
                ])
            else:
                records.extend([
                    {"payload": {"type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                                 "call_id": "spawn-1", "arguments": json.dumps(arguments)}},
                    self._current_nested_activity("spawn-1", "real-child") if current_nested else
                    {"payload": {"type": "sub_agent_activity", "event_id": "spawn-1",
                                 "agent_thread_id": "real-child", "kind": "started"}},
                ])
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        router_hook.handle({**base, "hook_event_name": "SubagentStart", "agent_id": "real-child",
                            "model": "gpt-6-sol", "reasoning_effort": "medium"})
        router_hook.handle({**base, "hook_event_name": "UserPromptSubmit", "turn_id": "child-turn",
                            "agent_id": "real-child", "model": "gpt-6-sol", "model_reasoning_effort": "medium",
                            "prompt": "Inspect the bounded endpoint."})
        router_hook.handle({**base, "hook_event_name": "SubagentStop", "agent_id": "real-child",
                            "turn_id": "child-turn", "model": "gpt-6-sol", "reasoning_effort": "medium",
                            "last_assistant_message": "Evidence: inspected\nVerification: checked\nUncertainty: none"})
        router_hook.handle({**base, "hook_event_name": "Stop", "transcript_path": str(path)})
        return json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text()), path

    def test_direct_host_bypass_is_not_plan_or_receipt_evidence(self) -> None:
        for nested in (False, True):
            with self.subTest(nested=nested):
                state, path = self._run_child({"model": "gpt-6-sol", "reasoning_effort": "medium",
                                               "message": "Self-contained bounded task."}, nested=nested)
                child = state["agents"]["real-child"]
                self.assertEqual("completed", child["status"])
                self.assertEqual("observed-contract", child["parent_session_id"])
                self.assertFalse(child.get("spawn_contract_valid", True))
                self.assertEqual("FAILED_OPEN", state["status"])
                self.assertFalse(child["receipt_recorded"])
                self.assertFalse(router_hook.CAPABILITY_PATH.exists())
                self.assertTrue(any("spawn_contract_invalid" in v for v in state["violations"]))
                self.assertTrue(any("required" in p and "got 0" in p for p in state["failed_open_problems"]))
                contracts = state["spawn_contracts"]
                self.assertEqual(1, len(contracts))
                evidence = next(iter(contracts.values()))
                self.assertEqual(["missing_fork_turns", "missing_task_name"], evidence["reasons"])
                before = json.dumps(state, sort_keys=True)
                router_hook._reconcile_subagent_transcript({"transcript_path": str(path)}, state)
                self.assertEqual(len(contracts), len(state["spawn_contracts"]))
                self.assertEqual(len(json.loads(before)["violations"]), len(state["violations"]))

    def test_lifecycle_without_observed_arguments_cannot_issue_receipt(self) -> None:
        state, _ = self._run_child(None)
        self.assertFalse(state["agents"]["real-child"]["receipt_recorded"])
        self.assertEqual("FAILED_OPEN", state["status"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_adapter_output_can_fulfil_plan_and_issue_receipt(self) -> None:
        args = router_hook.spawn_compat.build_arguments(model="gpt-6-sol", effort="medium",
                                                        task_name="bounded", message="Inspect only.")
        state, _ = self._run_child(args)
        self.assertEqual("COMPLETE", state["status"])
        child = state["agents"]["real-child"]
        self.assertTrue(child.get("spawn_contract_valid"))
        self.assertTrue(child["receipt_recorded"])
        self.assertEqual([], state["violations"])
        receipt = _capability_receipt("gpt-6-sol")
        self.assertTrue(receipt["spawn_contract_valid"])
        self.assertEqual(child["spawn_call_key"], receipt["spawn_call_key"])

    def test_current_nested_activity_binds_exact_valid_spawn(self) -> None:
        args = router_hook.spawn_compat.build_arguments(
            model="gpt-6-sol", effort="medium", task_name="bounded", message="Inspect only.",
        )
        state, _ = self._run_child(args, current_nested=True)
        child = state["agents"]["real-child"]
        self.assertTrue(child["spawn_contract_valid"])
        self.assertEqual("direct:spawn-1", child["spawn_call_key"])
        self.assertEqual("COMPLETE", state["status"])

    def test_current_nested_activity_keeps_invalid_contract_noncompliant(self) -> None:
        args = router_hook.spawn_compat.build_arguments(
            model="gpt-6-sol", effort="medium", task_name="bounded", message="Inspect only.",
        )
        state, _ = self._run_child({**args, "fork_turns": "all"}, current_nested=True)
        child = state["agents"]["real-child"]
        self.assertFalse(child["spawn_contract_valid"])
        self.assertIn("invalid_fork_turns", child["spawn_contract_reasons"])
        self.assertFalse(child["receipt_recorded"])
        self.assertEqual("FAILED_OPEN", state["status"])

    def test_multiple_current_nested_children_bind_only_by_exact_call_id(self) -> None:
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook.handle({
            **base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
            "prompt": "Research two independent APIs in parallel and recommend an architecture.",
        })
        state = json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text())
        context = router_hook._subagent_scan_context(state)
        self.assertIsNotNone(context)
        for suffix in ("a", "b"):
            args = router_hook.spawn_compat.build_arguments(
                model="gpt-6-sol", effort="medium", task_name=f"bounded-{suffix}",
                message=f"Inspect source {suffix} only.",
            )
            records = [
                {"payload": {"type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                             "call_id": f"spawn-{suffix}", "arguments": json.dumps(args),
                             "internal_chat_message_metadata_passthrough": {"turn_id": "parent"}}},
                self._current_nested_activity(f"spawn-{suffix}", f"child-{suffix}"),
            ]
            for record in records:
                router_hook._consume_subagent_record(record, state, context)
        router_hook._bind_spawn_contract(state, "child-a", context["agent_contracts"]["child-a"])
        router_hook._bind_spawn_contract(state, "child-b", context["agent_contracts"]["child-b"])
        self.assertEqual("direct:spawn-a", state["agents"]["child-a"]["spawn_call_key"])
        self.assertEqual("direct:spawn-b", state["agents"]["child-b"]["spawn_call_key"])
        self.assertTrue(state["agents"]["child-a"]["spawn_contract_valid"])
        self.assertTrue(state["agents"]["child-b"]["spawn_contract_valid"])

    def test_current_nested_wrapper_binds_one_statically_observed_spawn(self) -> None:
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook.handle({
            **base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
            "prompt": "Implement a bounded endpoint with targeted unit tests.",
        })
        state = json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text())
        context = router_hook._subagent_scan_context(state)
        self.assertIsNotNone(context)
        args = router_hook.spawn_compat.build_arguments(
            model="gpt-6-sol", effort="medium", task_name="bounded", message="Inspect only.",
        )
        records = [
            {"payload": {"type": "custom_tool_call", "name": "exec", "call_id": "wrapper-1",
                         "input": "text(await tools.multi_agent_v1__spawn_agent(" + json.dumps(args) + "));",
                         "internal_chat_message_metadata_passthrough": {"turn_id": "parent"}}},
            self._current_nested_activity("wrapper-1", "wrapped-child"),
        ]
        for record in records:
            router_hook._consume_subagent_record(record, state, context)
        router_hook._bind_spawn_contract(
            state, "wrapped-child", context["agent_contracts"]["wrapped-child"],
        )
        self.assertTrue(state["agents"]["wrapped-child"]["spawn_contract_valid"])
        self.assertEqual("nested:wrapper-1:0", state["agents"]["wrapped-child"]["spawn_call_key"])

    def test_current_nested_activity_replay_is_idempotent_and_tracks_completion(self) -> None:
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook.handle({
            **base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
            "prompt": "Implement a bounded endpoint with targeted unit tests.",
        })
        state = json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text())
        context = router_hook._subagent_scan_context(state)
        self.assertIsNotNone(context)
        args = router_hook.spawn_compat.build_arguments(
            model="gpt-6-sol", effort="medium", task_name="bounded", message="Inspect only.",
        )
        call = {"payload": {"type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                            "call_id": "spawn-1", "arguments": json.dumps(args),
                            "internal_chat_message_metadata_passthrough": {"turn_id": "parent"}}}
        started = self._current_nested_activity("spawn-1", "real-child")
        completed = self._current_nested_activity(
            "subagent-completed-opaque", "real-child", kind="completed",
        )
        for record in (call, started, started, completed, completed):
            router_hook._consume_subagent_record(record, state, context)
        self.assertEqual(["direct:spawn-1"], context["agent_contracts"]["real-child"])
        self.assertEqual({"real-child"}, context["completed_ids"])

    def test_current_nested_activity_without_exact_linkage_remains_unproven(self) -> None:
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook.handle({
            **base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
            "prompt": "Implement a bounded endpoint with targeted unit tests.",
        })
        state = json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text())
        context = router_hook._subagent_scan_context(state)
        self.assertIsNotNone(context)
        consumed = router_hook._consume_subagent_record(
            self._current_nested_activity("missing-call", "unlinked-child"), state, context,
        )
        self.assertFalse(consumed)
        self.assertNotIn("unlinked-child", context["agent_contracts"])

    def test_current_nested_activity_contradiction_fails_closed(self) -> None:
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook.handle({
            **base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
            "prompt": "Implement a bounded endpoint with targeted unit tests.",
        })
        state = json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text())
        context = router_hook._subagent_scan_context(state)
        self.assertIsNotNone(context)
        args = router_hook.spawn_compat.build_arguments(
            model="gpt-6-sol", effort="medium", task_name="bounded", message="Inspect only.",
        )
        records = [
            {"payload": {"type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                         "call_id": "spawn-1", "arguments": json.dumps(args),
                         "internal_chat_message_metadata_passthrough": {"turn_id": "parent"}}},
            self._current_nested_activity("spawn-1", "first-child"),
            self._current_nested_activity("spawn-1", "other-child"),
        ]
        for record in records:
            router_hook._consume_subagent_record(record, state, context)
        for agent_id in ("first-child", "other-child"):
            router_hook._bind_spawn_contract(state, agent_id, context["agent_contracts"][agent_id])
        self.assertFalse(router_hook._spawn_contract_compliant(state, "first-child"))
        self.assertFalse(router_hook._spawn_contract_compliant(state, "other-child"))

    def test_current_nested_activity_requires_exact_parent_turn(self) -> None:
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook.handle({
            **base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
            "prompt": "Implement a bounded endpoint with targeted unit tests.",
        })
        state = json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text())
        context = router_hook._subagent_scan_context(state)
        self.assertIsNotNone(context)
        self.assertFalse(router_hook._consume_subagent_record(
            self._current_nested_activity("spawn-1", "wrong-turn-child", turn_id="other-turn"),
            state, context,
        ))
        self.assertNotIn("wrong-turn-child", context["agent_contracts"])

    def test_child_flags_without_call_specific_evidence_never_issue_receipts(self) -> None:
        args = router_hook.spawn_compat.build_arguments(model="gpt-6-sol", effort="medium",
                                                        task_name="bounded", message="Inspect only.")
        state, _ = self._run_child(args)
        state["agents"]["real-child"]["receipt_recorded"] = False
        state["spawn_contracts"].clear()
        self.assertFalse(router_hook._record_capability(state, "real-child"))

    def test_conflicting_call_child_binding_never_leaks_a_receipt(self) -> None:
        args = router_hook.spawn_compat.build_arguments(model="gpt-6-sol", effort="medium",
                                                        task_name="bounded", message="Inspect only.")
        state, path = self._run_child(args)
        router_hook.CAPABILITY_PATH.unlink()
        child = state["agents"]["real-child"]
        child["receipt_recorded"] = False
        state["agents"]["z-other-child"] = {**child, "receipt_recorded": False}
        state["agent_attestations"]["z-other-child"] = dict(state["agent_attestations"]["real-child"])
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records.append({"payload": {"type": "sub_agent_activity", "event_id": "spawn-1", "agent_thread_id": "z-other-child"}})
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        router_hook._reconcile_subagent_transcript({"transcript_path": str(path)}, state)
        self.assertFalse(router_hook.CAPABILITY_PATH.exists(), "conflict was discovered after an early receipt write")
        self.assertFalse(router_hook._spawn_contract_compliant(state, "real-child"))

    def test_multiple_calls_cannot_be_assigned_to_children_by_return_order(self) -> None:
        args = router_hook.spawn_compat.build_arguments(model="gpt-6-sol", effort="medium",
                                                        task_name="bounded", message="Inspect only.")
        state, path = self._run_child(None)
        records = [
            {"payload": {"type": "custom_tool_call", "name": "exec", "call_id": "batch",
                         "input": "text(await Promise.all([tools.multi_agent_v1__spawn_agent(" + json.dumps(args)
                         + "),tools.multi_agent_v1__spawn_agent(" + json.dumps(args) + ")]));"}},
            {"payload": {"type": "custom_tool_call_output", "call_id": "batch",
                         "output": json.dumps([{"agent_id": "real-child"}, {"agent_id": "other-child"}])}},
        ]
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        router_hook._reconcile_subagent_transcript({"transcript_path": str(path)}, state)
        self.assertEqual(2, len(state["spawn_contracts"]))
        self.assertFalse(router_hook._spawn_contract_compliant(state, "real-child"))
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_observed_model_cannot_borrow_a_different_lifecycle_model(self) -> None:
        args = router_hook.spawn_compat.build_arguments(model="gpt-6-sol", effort="high",
                                                        task_name="bounded", message="Inspect only.")
        state, _ = self._run_child(args)
        self.assertFalse(router_hook._spawn_contract_compliant(state, "real-child"))
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_same_child_cannot_borrow_the_last_of_two_different_spawn_calls(self) -> None:
        state, path = self._run_child(None)
        args = router_hook.spawn_compat.build_arguments(model="gpt-6-sol", effort="medium",
                                                        task_name="bounded", message="Inspect only.")
        records = []
        for call_id in ("first", "second"):
            records.extend([
                {"payload": {"type": "function_call", "name": "spawn_agent", "call_id": call_id,
                             "arguments": json.dumps(args)}},
                {"payload": {"type": "sub_agent_activity", "event_id": call_id, "agent_thread_id": "real-child"}},
            ])
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        router_hook._reconcile_subagent_transcript({"transcript_path": str(path)}, state)
        self.assertFalse(router_hook._spawn_contract_compliant(state, "real-child"))
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_all_missing_or_wrong_fields_block_plan_and_receipt(self) -> None:
        valid = router_hook.spawn_compat.build_arguments(model="gpt-6-sol", effort="medium",
                                                         task_name="bounded", message="Inspect only.")
        cases = [{k: v for k, v in valid.items() if k != field} for field in valid]
        cases += [{**valid, "fork_turns": "all"}, {**valid, "task_name": " \t"},
                  {**valid, "message": ""}, {**valid, "reasoning_effort": "ultra"}]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                state, _ = self._run_child(arguments)
                self.assertEqual("FAILED_OPEN", state["status"])
                self.assertFalse(state["agents"]["real-child"]["receipt_recorded"])
                self.assertFalse(router_hook.CAPABILITY_PATH.exists())
                self.assertNotIn("", state["subagents_started"])

    def test_later_valid_child_fulfils_role_without_erasing_invalid_provenance(self) -> None:
        state, path = self._run_child({"model": "gpt-6-sol", "reasoning_effort": "medium", "message": "Inspect."})
        state["decision"]["orchestration"]["max_workers"] = 2  # Policy explicitly permits another worker.
        state["status"] = "RUNNING"
        agent_id = "00000000-0000-7000-8000-000000000123"
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records += RouterTests._observed_spawn_records(agent_id, "gpt56_terra_worker", "parent")
        records += [{"payload": {"type": "message", "content": json.dumps({"agent_id": agent_id,
                     "status": {"completed": "Evidence: checked\nVerification: complete\nUncertainty: none"}})}}]
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        RouterTests._write_child_transcript(self, "observed-contract", agent_id, "gpt-6-sol", "medium")
        base = {"session_id": "observed-contract", "turn_id": "parent"}
        router_hook._write_existing_state(base, state)
        router_hook.handle({**base, "hook_event_name": "Stop", "transcript_path": str(path)})
        state = json.loads((Path(self.temp.name) / "observed-contract--parent.json").read_text())
        self.assertEqual("COMPLETE", state["status"])
        self.assertTrue(any("spawn_contract_invalid" in item for item in state["violations"]))
        self.assertFalse(state["agents"]["real-child"]["spawn_contract_valid"])
        self.assertTrue(state["agents"][agent_id]["spawn_contract_valid"])

    def test_malformed_evidence_workers_do_not_fulfil_staged_prerequisites(self) -> None:
        base = {"session_id": "staged-contract", "turn_id": "parent"}
        router_hook.handle({**base, "hook_event_name": "UserPromptSubmit", "model": "gpt-6-luna",
                            "model_reasoning_effort": "low",
                            "prompt": "Research three independent APIs in parallel and recommend an architecture."})
        state = json.loads((Path(self.temp.name) / "staged-contract--parent.json").read_text())
        context = router_hook._subagent_scan_context(state)
        for index in range(2):
            for record in [
                {"payload": {"type": "function_call", "name": "spawn_agent", "call_id": str(index),
                             "arguments": {"model": "gpt-6-sol", "reasoning_effort": "medium", "message": "Inspect."}}},
                {"payload": {"type": "sub_agent_activity", "event_id": str(index), "agent_thread_id": "child-" + str(index)}},
                {"payload": {"type": "message", "content": json.dumps({"agent_id": "child-" + str(index),
                             "status": {"completed": "Evidence: done\nVerification: checked\nUncertainty: none"}})}},
            ]:
                router_hook._consume_subagent_record(record, state, context)
        router_hook._record_scanned_spawn(state, context, "gpt6_sol_high", False)
        self.assertTrue(any(item.startswith("ordering_violation:") for item in state["violations"]))

    def test_repeated_malformed_unexpected_role_has_no_duplicate_violations(self) -> None:
        state, path = self._run_child({"model": "gpt-6-sol", "reasoning_effort": "high", "message": "Inspect."})
        before = list(state["violations"])
        router_hook._reconcile_subagent_transcript({"transcript_path": str(path)}, state)
        self.assertEqual(before, state["violations"])


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config_temp = tempfile.TemporaryDirectory()
        router_hook.STATE_ROOT = Path(self.temp.name).resolve()
        router_hook.CONFIG_PATH = Path(self.config_temp.name).resolve() / "config.toml"
        router_hook.PROFILE_PATH = Path(self.config_temp.name).resolve() / "gpt-5-6-router" / "routing-profile.json"
        router_hook.CODEX_HOME = Path(self.config_temp.name).resolve()
        router_hook.HEALTH_ROOT = router_hook.CODEX_HOME / "gpt-5-6-router"
        router_hook.ROOT_OBSERVATION_PATH = router_hook.HEALTH_ROOT / "root-observation-v1.json"
        router_hook.CAPABILITY_PATH = router_hook.HEALTH_ROOT / "capability-v3.json"
        router_hook.CONFIG_PATH.write_text("", encoding="utf-8")
        source_agents = Path(router_hook.__file__).resolve().parents[1] / "assets" / "agents"
        shutil.copytree(source_agents, router_hook.CONFIG_PATH.parent / "agents")
        self._original_handle = router_hook.handle

        def _host_turn_with_observed_default_effort(data: dict) -> dict | None:
            payload = dict(data)
            if payload.get("hook_event_name") == "UserPromptSubmit" and "model_reasoning_effort" not in payload:
                effort = {"gpt-6-luna": "low", "gpt-6-sol": "medium", "gpt-6-astra": "medium"}.get(payload.get("model"))
                if effort:
                    payload["model_reasoning_effort"] = effort
            return self._original_handle(payload)

        router_hook.handle = _host_turn_with_observed_default_effort
        self._availability_patch = mock.patch.object(
            router_hook, "_availability_for", side_effect=lambda model_id, state: "available"
        )
        self._availability_patch.start()

    def tearDown(self) -> None:
        self._availability_patch.stop()
        router_hook.handle = self._original_handle
        self.config_temp.cleanup()
        self.temp.cleanup()

    def _write_child_transcript(
        self, session: str, agent_id: str, model: str, effort: str,
        turn_id: str = "child-turn", extra: list[dict] | None = None,
    ) -> Path:
        child = router_hook.CODEX_HOME / "sessions/2026/08/31" / f"rollout-2026-08-31T12-00-00-{agent_id}.jsonl"
        child.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {"type": "session_meta", "payload": {
                "id": agent_id, "source": {"subagent": {"thread_spawn": {"parent_thread_id": session}}},
            }},
            {"type": "turn_context", "payload": {"turn_id": turn_id, "model": model, "effort": effort}},
        ] + (extra or [])
        child.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
        return child

    @staticmethod
    def _observed_spawn_records(agent_id: str, role: str, turn: str = "t1") -> list[dict]:
        spec = router_hook.ROUTES[role]
        call_id = "spawn-" + agent_id
        return [
            {"payload": {"type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                         "call_id": call_id, "arguments": json.dumps(router_hook.spawn_compat.build_arguments(
                             model=spec["model"], effort=spec["effort"], task_name="bounded", message="Inspect only.",
                         )), "internal_chat_message_metadata_passthrough": {"turn_id": turn}}},
            {"payload": {"type": "sub_agent_activity", "event_id": call_id, "agent_thread_id": agent_id,
                         "kind": "started", "internal_chat_message_metadata_passthrough": {"turn_id": turn}}},
        ]

    def _observe_valid_spawn(self, session: str, turn: str, agent_id: str, role: str) -> None:
        # Synthetic observed-call evidence, separate from the lifecycle fixture.
        # Exercise the real scanner/validator; never set compliance booleans in tests.
        path = Path(self.temp.name) / (agent_id + "-spawn.jsonl")
        records = self._observed_spawn_records(agent_id, role, turn)
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        state = self._ledger(session, turn)
        router_hook._reconcile_subagent_transcript({"transcript_path": str(path)}, state)
        router_hook._write_existing_state({"session_id": session, "turn_id": turn}, state)

    def _complete_transcript_plan(self, session: str, prompt: str, roles: list[str]) -> tuple[dict, dict]:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-luna", "model_reasoning_effort": "low", "prompt": prompt,
        })
        transcript = Path(self.temp.name) / f"{session}-parent.jsonl"
        records = []
        for index, role in enumerate(roles):
            agent_id = f"00000000-0000-7000-8000-{index:012d}"
            records.extend(self._observed_spawn_records(agent_id, role) + [
                {"payload": {"type": "message", "content": (
                    f'<subagent_notification>{{"agent_path":"{agent_id}","status":{{"completed":'
                    '"Evidence: bounded result\\nVerification: objective check passed\\nUncertainty: none"}}}</subagent_notification>'
                )}},
            ])
            spec = router_hook.ROUTES[role]
            self._write_child_transcript(session, agent_id, spec["model"], spec["effort"])
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "t1",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        return result, ledger

    def _write_agent_transcript(self, session: str, agents: list[tuple[str, str, str]]) -> Path:
        transcript = Path(self.temp.name) / f"{session}-parent.jsonl"
        records = []
        for role, agent_id, message in agents:
            records.extend(self._observed_spawn_records(agent_id, role) + [
                {"payload": {"type": "message", "content": f'<subagent_notification>{{"agent_path":"{agent_id}","status":{{"completed":{json.dumps(message)}}}}}</subagent_notification>'}},
            ])
            spec = router_hook.ROUTES[role]
            self._write_child_transcript(session, agent_id, spec["model"], spec["effort"])
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        return transcript

    def _write_large_jsonl(
        self,
        path: Path,
        records: list[dict],
        position: str = "middle",
        minimum_size: int = (8 * 1024 * 1024) + 128 * 1024,
    ) -> None:
        encoded = [json.dumps(record, separators=(",", ":")).encode("utf-8") + b"\n" for record in records]
        padding = json.dumps(
            {"payload": {"type": "synthetic_padding", "padding": "x" * 65536}},
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        padding_count = max(1, (minimum_size - sum(map(len, encoded)) + len(padding) - 1) // len(padding))
        if position == "early":
            before, after = 0, padding_count
        elif position == "middle":
            before, after = padding_count // 2, padding_count - (padding_count // 2)
        elif position == "late":
            before, after = padding_count, 0
        else:
            raise ValueError(position)
        with path.open("wb") as stream:
            for _ in range(before):
                stream.write(padding)
            for record in encoded:
                stream.write(record)
            for _ in range(after):
                stream.write(padding)

    @staticmethod
    def _transcript_verification_records(turn: str, exit_code: int = 0, include_output: bool = True) -> list[dict]:
        metadata = {"turn_id": turn}
        records = [{"payload": {
            "type": "custom_tool_call", "name": "exec", "call_id": "verify-large",
            "input": (
                'const r = await tools.exec_command({cmd:"python3 -m unittest -q"}); '
                'text(JSON.stringify({exit_code:r.exit_code,output:r.output}));'
            ),
            "internal_chat_message_metadata_passthrough": metadata,
        }}]
        if include_output:
            records.append({"payload": {
                "type": "custom_tool_call_output", "call_id": "verify-large",
                "output": [{"type": "input_text", "text": json.dumps({
                    "exit_code": exit_code, "output": "synthetic verification result",
                })}],
                "internal_chat_message_metadata_passthrough": metadata,
            }})
        return records

    @staticmethod
    def _transcript_mutation_records(turn: str, call_id: str = "mutation-hook-1") -> list[dict]:
        metadata = {"turn_id": turn}
        return [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": call_id,
                "input": "const r = await tools.apply_patch(`patch`); text(r);",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": call_id, "output": "Done",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]

    def _ledger(self, session: str, turn: str) -> dict:
        return json.loads((Path(self.temp.name) / f"{session}--{turn}.json").read_text(encoding="utf-8"))

    def _retain_running_parent_after_stop(self, session: str, turn: str = "parent") -> dict:
        path = Path(self.temp.name) / f"{session}--{turn}.json"
        ledger = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(ledger["parent_stop_observed"])
        self.assertEqual("started", ledger["agents"]["terra-child"]["status"])
        ledger["status"] = "RUNNING"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        return ledger

    def _start_concurrent_terra_children(self, session: str) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "In parallel, extract version numbers from two independent manifests.",
        })
        for agent_id in ("terra-a", "terra-b"):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
            })
            self._observe_valid_spawn(session, "parent", agent_id, "gpt56_terra_worker")

    def _stop_terra_child(
        self, session: str, turn_id: str, agent_id: str, model: str = "gpt-6-sol",
    ) -> None:
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": turn_id,
            "agent_id": agent_id, "model": model, "reasoning_effort": "medium",
            "last_assistant_message": (
                "Evidence: version extracted\nVerification: manifest checked\nUncertainty: none"
            ),
        })

    def _patch_event(self, session: str, turn: str, patches: list[tuple[str, str]]) -> dict:
        body = ["*** Begin Patch"]
        for path, changed_line in patches:
            body.extend((f"*** Update File: {path}", "@@", f"-old", f"+{changed_line}"))
        body.append("*** End Patch")
        patch = "\n".join(body)
        return {
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "exec",
            "tool_input": {"command": f"const patch = {json.dumps(patch)}; text(await tools.apply_patch(patch));"},
            "tool_response": [{"type": "input_text", "text": "{}"}],
        }

    def _verification_event(
        self, session: str, turn: str, command: str = "git diff --check", exit_code: int = 0,
    ) -> dict:
        nested = (
            f"const r = await tools.exec_command({{cmd:{json.dumps(command)}}}); "
            "text(JSON.stringify({exit_code:r.exit_code,output:r.output}));"
        )
        return {
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "exec", "tool_input": {"command": nested},
            "tool_response": [
                {"type": "input_text", "text": "Script completed\nOutput:\n"},
                {"type": "input_text", "text": json.dumps({"exit_code": exit_code, "output": ""})},
            ],
        }

    def _run_mutation_lifecycle(
        self,
        session: str,
        prompt: str,
        mutation_events: list[dict],
        verification_events: list[dict],
        *,
        model: str = "gpt-6-luna",
    ) -> dict:
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": model,
            "model_reasoning_effort": "medium" if model == "gpt-6-sol" else "low",
            "prompt": prompt,
        })
        for event in mutation_events + verification_events:
            router_hook.handle(event)
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False,
        })
        return self._ledger(session, turn)

    def test_desktop_b_to_b2_documentation_verification_lifecycle(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_b2_verification.json").read_text(
                encoding="utf-8"
            )
        )
        for event in fixture["turn_b"]["events"]:
            router_hook.handle(event)
        turn_b = self._ledger(fixture["turn_b"]["session_id"], fixture["turn_b"]["turn_id"])
        self.assertEqual("COMPLETE", turn_b["status"])
        self.assertTrue(turn_b["decision"]["requires_clarification"])
        self.assertEqual(0, turn_b["mutations"])

        for event in fixture["turn_b2"]["events"]:
            router_hook.handle(event)
        turn_b2 = self._ledger(fixture["turn_b2"]["session_id"], fixture["turn_b2"]["turn_id"])
        profile = turn_b2["decision"]["task_profile"]
        self.assertEqual({
            "mutation": True,
            "clear_spec": True,
            "underspecified_mutation": False,
            "requires_clarification": False,
            "route": "current",
            "mode": "direct",
            "child_count": 0,
        }, {
            "mutation": profile["mutation"],
            "clear_spec": profile["clear_spec"],
            "underspecified_mutation": profile["underspecified_mutation"],
            "requires_clarification": turn_b2["decision"]["requires_clarification"],
            "route": turn_b2["decision"]["route"],
            "mode": turn_b2["decision"]["orchestration"]["mode"],
            "child_count": turn_b2["telemetry"]["child_count"],
        })
        self.assertEqual(1, turn_b2["mutations"])
        self.assertEqual(1, turn_b2["mutation_generation"])
        self.assertEqual(1, turn_b2["verified_generation"])
        self.assertEqual(["/workspace/README.md"], turn_b2.get("changed_files"))
        self.assertEqual("documentation_only", turn_b2.get("mutation_surface"))
        self.assertEqual("diff_check", turn_b2.get("observed_verification"))
        self.assertEqual("COMPLETE", turn_b2["status"])

    def test_documentation_diff_check_generation_order_and_result(self) -> None:
        prompt = "Update README.md so the supported versions are stated as Python 3.10–3.14."
        cases = (
            ("docs-no-check", ["mutation"], "FAILED_OPEN"),
            ("docs-stale-check", ["verification", "mutation"], "FAILED_OPEN"),
            ("docs-failed-check", ["mutation", "failed_verification"], "FAILED_OPEN"),
            ("docs-post-check", ["mutation", "verification"], "COMPLETE"),
        )
        for session, order, expected in cases:
            with self.subTest(session=session):
                turn = "t1"
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
                    "model": "gpt-6-luna", "model_reasoning_effort": "low", "prompt": prompt,
                })
                for item in order:
                    if item == "mutation":
                        event = self._patch_event(session, turn, [("/workspace/README.md", "new wording")])
                    else:
                        event = self._verification_event(
                            session, turn, exit_code=1 if item == "failed_verification" else 0
                        )
                    router_hook.handle(event)
                router_hook.handle({
                    "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
                    "stop_hook_active": False,
                })
                ledger = self._ledger(session, turn)
                self.assertEqual(expected, ledger["status"])
                if expected == "COMPLETE":
                    self.assertEqual(ledger["mutation_generation"], ledger["verified_generation"])

    def test_diff_check_requires_actual_low_risk_documentation_surface(self) -> None:
        cases = (
            ("readme", [("/workspace/README.md", "plain wording")], "documentation_only", "COMPLETE"),
            ("ordinary-doc", [("/workspace/docs/guide.md", "plain wording")], "documentation_only", "COMPLETE"),
            ("mixed", [("/workspace/README.md", "plain wording"), ("/workspace/app.py", "print('x')")], "non_documentation", "FAILED_OPEN"),
            ("python", [("/workspace/app.py", "print('x')")], "non_documentation", "FAILED_OPEN"),
            ("config", [("/workspace/config.toml", "enabled = true")], "non_documentation", "FAILED_OPEN"),
            ("runbook", [("/workspace/docs/production-runbook.md", "skip backups")], "high_consequence_documentation", "FAILED_OPEN"),
            ("runbook-directory", [("/workspace/docs/runbooks/database.md", "skip backups")], "high_consequence_documentation", "FAILED_OPEN"),
            ("generated-directory", [("/workspace/docs/generated/guide.md", "generated output")], "high_consequence_documentation", "FAILED_OPEN"),
            ("security-policy", [("/workspace/SECURITY.md", "reporting disabled")], "high_consequence_documentation", "FAILED_OPEN"),
            ("security-code", [("/workspace/auth.py", "allow_admin = True")], "non_documentation", "FAILED_OPEN"),
            ("frontmatter", [("/workspace/docs/page.md", "title: machine value")], "machine_consumed_documentation", "FAILED_OPEN"),
        )
        prompt = "Apply the exact requested wording change."
        for name, patches, surface, expected in cases:
            with self.subTest(name=name):
                session = f"surface-{name}"
                turn = "t1"
                ledger = self._run_mutation_lifecycle(
                    session,
                    prompt,
                    [self._patch_event(session, turn, patches)],
                    [self._verification_event(session, turn)],
                    model="gpt-6-sol",
                )
                self.assertEqual(surface, ledger.get("mutation_surface"))
                self.assertEqual(expected, ledger["status"])

    def test_unknown_mutation_surface_cannot_use_diff_check(self) -> None:
        session = "surface-unknown"
        turn = "t1"
        unknown = {
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "Bash", "tool_input": {"command": "touch docs/guide.md"},
            "tool_response": {"exit_code": 0},
        }
        ledger = self._run_mutation_lifecycle(
            session,
            "Apply the exact requested wording change.",
            [unknown],
            [self._verification_event(session, turn)],
            model="gpt-6-sol",
        )
        self.assertEqual("unknown", ledger.get("mutation_surface"))
        self.assertEqual("FAILED_OPEN", ledger["status"])

    def test_documentation_move_to_executable_surface_cannot_use_diff_check(self) -> None:
        session = "surface-doc-move-to-code"
        turn = "t1"
        patch = (
            "*** Begin Patch\n"
            "*** Update File: /workspace/README.md\n"
            "*** Move to: /workspace/app.py\n"
            "@@\n-old\n+new\n"
            "*** End Patch"
        )
        mutation = {
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "exec",
            "tool_input": {"command": f"const patch = {json.dumps(patch)}; text(await tools.apply_patch(patch));"},
            "tool_response": [{"type": "input_text", "text": "{}"}],
        }
        ledger = self._run_mutation_lifecycle(
            session,
            "Move the documentation into app.py.",
            [mutation],
            [self._verification_event(session, turn)],
            model="gpt-6-sol",
        )
        self.assertEqual("non_documentation", ledger.get("mutation_surface"))
        self.assertEqual("FAILED_OPEN", ledger["status"])

    def test_harmless_readme_security_wording_can_use_documentation_verification(self) -> None:
        session = "surface-readme-oauth"
        turn = "t1"
        ledger = self._run_mutation_lifecycle(
            session,
            "Update README.md so the glossary calls the mechanism OAuth.",
            [self._patch_event(session, turn, [("/workspace/README.md", "The mechanism is called OAuth.")])],
            [self._verification_event(session, turn, "git -C /workspace diff --check")],
            model="gpt-6-sol",
        )
        self.assertEqual("documentation_only", ledger.get("mutation_surface"))
        self.assertEqual("COMPLETE", ledger["status"])

    def test_code_mutation_still_requires_strong_verification(self) -> None:
        session = "surface-code-strong"
        turn = "t1"
        patch = self._patch_event(session, turn, [("/workspace/app.py", "print('fixed')")])
        diff_only = self._run_mutation_lifecycle(
            session, "Fix app.py.", [patch], [self._verification_event(session, turn)], model="gpt-6-sol"
        )
        self.assertEqual("FAILED_OPEN", diff_only["status"])

        session = "surface-code-tested"
        patch = self._patch_event(session, turn, [("/workspace/app.py", "print('fixed')")])
        tested = self._run_mutation_lifecycle(
            session,
            "Fix app.py.",
            [patch],
            [self._verification_event(session, turn, "python3 -m unittest -q")],
            model="gpt-6-sol",
        )
        self.assertEqual("non_documentation", tested.get("mutation_surface"))
        self.assertEqual("COMPLETE", tested["status"])

    def test_route_cases(self) -> None:
        self.assertGreaterEqual(len(CASES), 40)
        for prompt, expected in CASES:
            with self.subTest(prompt=prompt):
                actual = router_hook.classify_prompt(prompt, "gpt-6-luna", "low", enforce_active_root=True)
                self.assertEqual(_active_route(expected), actual["route"])

    def test_real_desktop_test_a_prompt_is_read_only_and_stays_on_luna(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_a.json").read_text(encoding="utf-8")
        )["classifier_regression"]
        decision = router_hook.classify_prompt(fixture["prompt"], "gpt-6-luna", "low")
        self.assertEqual(fixture["expected_mutation"], decision["task_profile"]["mutation"])
        self.assertEqual(fixture["expected_route"], decision["route"])

    def test_desktop_test_b_underspecified_mutation_clarifies(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_b.json").read_text(encoding="utf-8")
        )["classifier_regression"]
        decision = router_hook.classify_prompt(fixture["prompt"], "gpt-6-luna", "low")
        expected = fixture["expected"]
        profile = decision["task_profile"]
        actual = {
            "mutation": profile["mutation"],
            "clear_spec": profile["clear_spec"],
            "underspecified_mutation": profile.get("underspecified_mutation", False),
            "requires_clarification": decision["requires_clarification"],
            "route": decision["route"],
            "mode": decision["orchestration"]["mode"],
            "child_count": sum(decision["orchestration"]["required_agents"].values()),
        }
        self.assertEqual(expected, actual)

    def test_desktop_test_b2_explicit_outcome_is_actionable(self) -> None:
        decision = router_hook.classify_prompt(
            "Update README.md so the supported Python versions are stated as Python 3.10–3.14.",
            "gpt-6-luna",
            "low",
            enforce_active_root=True,
        )
        profile = decision["task_profile"]
        self.assertEqual({
            "mutation": True,
            "clear_spec": True,
            "underspecified_mutation": False,
            "requires_clarification": False,
            "route": "current",
            "mode": "direct",
            "child_count": 0,
        }, {
            "mutation": profile["mutation"],
            "clear_spec": profile["clear_spec"],
            "underspecified_mutation": profile["underspecified_mutation"],
            "requires_clarification": decision["requires_clarification"],
            "route": decision["route"],
            "mode": decision["orchestration"]["mode"],
            "child_count": sum(decision["orchestration"]["required_agents"].values()),
        })

    def test_sanitized_desktop_safe_command_regressions_stay_current(self) -> None:
        prompts = (
            (
                "daily review",
                "Run exactly this production research command once: cd /workspace/research && "
                "python3 -m safe_research daily-review. Report only persisted bankroll evidence, "
                "do not use any order API, and preserve zero real bets and zero external spend.",
            ),
            (
                "bounded cycle",
                "Run exactly this production research command once: cd /workspace/research && "
                "python3 -m safe_research cycle. Do not modify strategy controls, do not use any "
                "order API, and report the persisted cycle status. Market access must remain "
                "delayed and read-only; real bets and external spend remain zero.",
            ),
        )
        for name, prompt in prompts:
            with self.subTest(name=name):
                decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")
                profile = decision["task_profile"]
                self.assertTrue(profile["clear_spec"])
                self.assertFalse(profile["mutation"])
                self.assertEqual("normal", profile["risk"])
                self.assertIn("safe_bounded_command", profile["signals"])
                self.assertEqual("current", decision["route"])
                self.assertEqual("direct", decision["orchestration"]["mode"])
                self.assertEqual({}, decision["orchestration"]["required_agents"])

    def test_safe_command_safeguards_do_not_override_consequential_actions(self) -> None:
        prompts = (
            (
                "contradictory order",
                "Run exactly this read-only production command once: trade-cli inspect. Now place "
                "this bet and submit the order using the live account; spend remains zero.",
            ),
            (
                "money movement",
                "Run exactly this production financial command once: treasury-cli transfer 500. "
                "Move the money to the external account after checking the balance.",
            ),
            (
                "production mutation",
                "Run exactly this production command once: deploy-cli apply. Modify the live "
                "service configuration and deploy it.",
            ),
            (
                "destructive action",
                "Run exactly this irreversible production command once: db-cli drop customer_data. "
                "Delete the production customer database after export.",
            ),
            (
                "inadequately bounded financial action",
                "Use the production account to place live bets across suitable markets; choose "
                "the stakes and submit whichever orders you judge best.",
            ),
            (
                "high-risk judgment",
                "Review current market conditions and decide which live bets to place with the "
                "production account.",
            ),
        )
        for name, prompt in prompts:
            with self.subTest(name=name):
                decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")
                profile = decision["task_profile"]
                self.assertNotIn("safe_bounded_command", profile["signals"])
                self.assertIn(profile["risk"], {"high", "critical"})
                self.assertIn(decision["route"], {"gpt56_sol_owner", "gpt56_sol_deep"})
                self.assertGreaterEqual(sum(decision["orchestration"]["required_agents"].values()), 1)

    def test_mutation_actionability_matrix(self) -> None:
        cases = (
            # prompt, mutation, clear spec, underspecified, clarification, route, children
            (
                "Update README.md so the supported Python versions are stated as Python 3.10–3.14.",
                True, True, False, False, "current", 0,
            ),
            (
                "Update README.md so the supported versions are Python 3.10–3.14.",
                True, True, False, False, "current", 0,
            ),
            ("Change the setting so retries are disabled.", True, True, False, False, "current", 0),
            ("Update the config so the timeout is 30 seconds.", True, True, False, False, "current", 0),
            ("Change the handler so invalid tokens are rejected.", True, True, False, False, "current", 0),
            ("Update the endpoint so deleted records are excluded.", True, True, False, False, "current", 0),
            (
                "Update this function so it returns None when the record is missing.",
                True, True, False, False, "current", 0,
            ),
            (
                "Update README.md to say Python 3.10–3.14 is supported.",
                True, True, False, False, "current", 0,
            ),
            ("Change MAX_WORKERS from 2 to 3.", True, True, False, False, "current", 0),
            (
                "Fix the SQL injection vulnerability in this query builder.",
                True, True, False, False, "gpt6_sol_balanced", 1,
            ),
            ("Update README.md.", True, False, True, True, "current", 0),
            ("Update the routing documentation thing.", True, False, True, True, "current", 0),
            ("Fix the bug we just identified.", True, False, True, True, "current", 0),
            ("Make this better.", True, False, True, True, "current", 0),
            ("Update this so stuff works.", True, False, True, True, "current", 0),
            ("Change this so it is better.", True, False, True, True, "current", 0),
            ("Update the auth thing.", True, False, True, True, "current", 0),
            ("Update the production database thing.", True, False, True, True, "current", 0),
            ("Explain how routing works.", False, False, False, False, "current", 0),
            (
                "Read README.md and tell me which Python versions the CI matrix supports. Do not modify anything.",
                False, False, False, False, "current", 0,
            ),
            (
                "Threat-model the Autorouter plugin hook trust boundary and analyse the security consequences "
                "if plugin cache isolation were broken. Do not modify anything.",
                False, False, False, False, "gpt6_sol_high", 1,
            ),
        )
        for prompt, mutation, clear_spec, underspecified, clarify, route, children in cases:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(
                    prompt, "gpt-6-luna", "low", enforce_active_root=True,
                )
                profile = decision["task_profile"]
                self.assertEqual(mutation, profile["mutation"])
                self.assertEqual(clear_spec, profile["clear_spec"])
                self.assertEqual(underspecified, profile.get("underspecified_mutation", False))
                self.assertEqual(clarify, decision["requires_clarification"])
                self.assertEqual(route, decision["route"])
                self.assertEqual(children, sum(decision["orchestration"]["required_agents"].values()))

    def test_desktop_test_b_to_b2_sequence_resets_clarification(self) -> None:
        base = {
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-6-luna",
            "model_reasoning_effort": "low",
            "session_id": "desktop-b-to-b2",
        }
        router_hook.handle({
            **base,
            "turn_id": "b",
            "prompt": "Update the routing documentation thing.",
        })
        first = json.loads(
            (Path(self.temp.name) / "desktop-b-to-b2--b.json").read_text(encoding="utf-8")
        )
        self.assertTrue(first["decision"]["requires_clarification"])
        self.assertEqual("clarify", first["decision"]["orchestration"]["mode"])

        router_hook.handle({
            **base,
            "turn_id": "b2",
            "prompt": "Update README.md so the supported Python versions are stated as Python 3.10–3.14.",
        })
        second = json.loads(
            (Path(self.temp.name) / "desktop-b-to-b2--b2.json").read_text(encoding="utf-8")
        )
        decision = second["decision"]
        profile = decision["task_profile"]
        self.assertIsNone(second["inherited_from_turn"])
        self.assertEqual({
            "mutation": True,
            "clear_spec": True,
            "underspecified_mutation": False,
            "requires_clarification": False,
            "route": "current",
            "mode": "direct",
            "child_count": 0,
        }, {
            "mutation": profile["mutation"],
            "clear_spec": profile["clear_spec"],
            "underspecified_mutation": profile["underspecified_mutation"],
            "requires_clarification": decision["requires_clarification"],
            "route": decision["route"],
            "mode": decision["orchestration"]["mode"],
            "child_count": sum(decision["orchestration"]["required_agents"].values()),
        })

    def test_referential_continuation_requires_established_context(self) -> None:
        base = {
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-6-luna",
            "model_reasoning_effort": "low",
        }
        router_hook.handle({
            **base,
            "session_id": "established-context",
            "turn_id": "t1",
            "prompt": "Fix the SQL injection vulnerability in this query builder.",
        })
        router_hook.handle({
            **base,
            "session_id": "established-context",
            "turn_id": "t2",
            "prompt": "Fix the bug we just identified.",
        })
        continued = json.loads(
            (Path(self.temp.name) / "established-context--t2.json").read_text(encoding="utf-8")
        )
        self.assertEqual("t1", continued["inherited_from_turn"])
        self.assertFalse(continued["decision"]["requires_clarification"])

        router_hook.handle({
            **base,
            "session_id": "unbound-context",
            "turn_id": "t1",
            "prompt": "Fix the bug we just identified.",
        })
        isolated = json.loads(
            (Path(self.temp.name) / "unbound-context--t1.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(isolated["inherited_from_turn"])
        self.assertTrue(isolated["decision"]["requires_clarification"])
        self.assertEqual("clarify", isolated["decision"]["orchestration"]["mode"])

        router_hook.handle({
            **base,
            "session_id": "natural-context",
            "turn_id": "t1",
            "prompt": "Change `MAX_WORKERS` from 2 to 3.",
        })
        router_hook.handle({
            **base,
            "session_id": "natural-context",
            "turn_id": "t2",
            "prompt": "Yes, do that.",
        })
        natural = json.loads(
            (Path(self.temp.name) / "natural-context--t2.json").read_text(encoding="utf-8")
        )
        self.assertEqual("t1", natural["inherited_from_turn"])
        self.assertFalse(natural["decision"]["requires_clarification"])

        router_hook.handle({
            **base,
            "session_id": "unbound-natural-context",
            "turn_id": "t1",
            "prompt": "Yes, do that.",
        })
        unbound_natural = json.loads(
            (Path(self.temp.name) / "unbound-natural-context--t1.json").read_text(encoding="utf-8")
        )
        self.assertTrue(unbound_natural["decision"]["requires_clarification"])

        router_hook.handle({
            **base,
            "session_id": "unusable-context",
            "turn_id": "t1",
            "prompt": "Update README.md.",
        })
        router_hook.handle({
            **base,
            "session_id": "unusable-context",
            "turn_id": "t2",
            "prompt": "Yes, do that.",
        })
        unusable = json.loads(
            (Path(self.temp.name) / "unusable-context--t2.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(unusable["inherited_from_turn"])
        self.assertTrue(unusable["decision"]["requires_clarification"])

    def test_clarification_contract_prohibits_execution(self) -> None:
        decision = router_hook.classify_prompt(
            "Update the production database thing.",
            "gpt-6-luna",
            "low",
        )
        context = router_hook._context(decision)
        self.assertEqual("clarify", decision["orchestration"]["mode"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])
        self.assertIn("User intent is insufficiently specified", context)
        self.assertIn("do not mutate", context)
        self.assertIn("mutating shell command", context)
        self.assertIn("external action", context)
        self.assertIn("do not delegate", context)
        self.assertIn("Ask one concise clarification question and wait", context)

    def test_negated_mutation_phrases_do_not_create_mutation_intent(self) -> None:
        prompts = (
            "Read README and report the supported Python versions. Do not modify anything.",
            "Inspect the configuration, but don't edit it.",
            "Review these files with no edits.",
            "Analyse the parser read-only and without changing any files.",
            "Inspect only; do not write to the repository.",
            "Do not modify the authentication validation logic; explain why it is unsafe.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")
                self.assertFalse(decision["task_profile"]["mutation"])

    def test_negation_does_not_hide_a_separate_positive_mutation(self) -> None:
        decision = router_hook.classify_prompt(
            "Do not modify README; update the CI configuration and add a focused test.",
            "gpt-6-luna",
            "low",
        )
        self.assertTrue(decision["task_profile"]["mutation"])

    def test_read_only_complexity_can_still_require_sol(self) -> None:
        decision = router_hook.classify_prompt(
            "Threat-model the production authentication architecture. Do not modify anything.",
            "gpt-6-luna",
            "low",
        )
        self.assertFalse(decision["task_profile"]["mutation"])
        self.assertEqual("gpt56_sol_deep", decision["route"])

    def test_sanitized_desktop_test_a_lifecycle_keeps_root_and_completes_child(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_a.json").read_text(encoding="utf-8")
        )
        for event in fixture["lifecycle_events"]:
            router_hook.handle(event)

        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("gpt-5.6-luna", observation["root_model"])
        self.assertEqual(
            "unavailable_from_current_codex_hook_surface",
            observation["runtime_identity_source"],
        )
        ledger = json.loads(
            (Path(self.temp.name) / "desktop-test-a-session--desktop-test-a-parent-turn.json").read_text(
                encoding="utf-8"
            )
        )
        child = ledger["agents"]["desktop-test-a-terra-child"]
        self.assertEqual("gpt-5.6-terra", child["observed_model"])
        self.assertEqual("completed", child["status"])
        # This historical fixture contains lifecycle only, not the observed spawn.
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertFalse(child["spawn_contract_valid"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_sanitized_desktop_test_c_correlates_historical_agent_by_observed_id(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_c.json").read_text(encoding="utf-8")
        )
        child_prompt = fixture["lifecycle_events"][2]
        self.assertNotIn("agent_id", child_prompt)
        for event in fixture["lifecycle_events"]:
            router_hook.handle(event)

        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        ledger = json.loads(
            (Path(self.temp.name) / "desktop-test-c-session--desktop-test-c-parent-turn.json").read_text(
                encoding="utf-8"
            )
        )
        child = ledger["agents"]["desktop-test-c-terra-child"]
        self.assertEqual("gpt-5.6-luna", observation["root_model"])
        self.assertEqual("observed_agent_id", child["correlation_mode"])
        self.assertEqual("desktop-test-c-child-turn", child["child_turn_id"])
        self.assertEqual("gpt-5.6-terra", child["start_observed_model"])
        self.assertEqual("gpt-5.6-terra", child["prompt_observed_model"])
        self.assertEqual("gpt-5.6-terra", child["stop_observed_model"])
        self.assertEqual("completed", child["status"])
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertFalse(child["spawn_contract_valid"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_sanitized_desktop_test_d_preserves_root_and_recovers_late_sol_stop(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_d.json").read_text(encoding="utf-8")
        )
        events = fixture["lifecycle_events"]
        for event in events[:4]:
            router_hook.handle(event)

        parent_path = Path(self.temp.name) / "desktop-test-d-session--desktop-test-d-parent-turn.json"
        child_path = Path(self.temp.name) / "desktop-test-d-session--desktop-test-d-child-turn.json"
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        child = json.loads(parent_path.read_text(encoding="utf-8"))["agents"]["desktop-test-d-sol-child"]
        self.assertEqual("gpt-5.6-luna", observation["root_model"])
        self.assertFalse(child_path.exists())
        self.assertEqual(["desktop-test-d-child-turn"], child["child_turn_ids"])
        self.assertEqual(2, len(child["prompt_observations"]))
        self.assertEqual({"gpt-5.6-sol"}, {item["model"] for item in child["prompt_observations"]})

        router_hook.handle(events[4])
        incomplete = json.loads(parent_path.read_text(encoding="utf-8"))
        self.assertEqual("FAILED_OPEN", incomplete["status"])
        self.assertEqual("started", incomplete["agents"]["desktop-test-d-sol-child"]["status"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

        router_hook.handle(events[5])
        ledger = json.loads(parent_path.read_text(encoding="utf-8"))
        child = ledger["agents"]["desktop-test-d-sol-child"]
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual("completed", child["status"])
        self.assertEqual("observed_agent_id", child["correlation_mode"])
        self.assertEqual("gpt-5.6-sol", child["requested_model"])
        self.assertEqual("gpt-5.6-sol", child["stop_observed_model"])
        self.assertTrue(child["completion_structured"])
        self.assertFalse(child["receipt_recorded"])
        self.assertEqual("gpt-5.6-luna", json.loads(
            router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
        )["root_model"])

    def test_sanitized_audit_terminal_parent_stale_child_does_not_swallow_later_root(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "root_bypass_audit.json").read_text(encoding="utf-8")
        )
        for event in fixture["lifecycle_events"]:
            router_hook.handle(event)

        earlier = self._ledger("root-bypass-audit-session", "earlier-parent-turn")
        later = self._ledger("root-bypass-audit-session", "later-parent-turn")
        ledgers = sorted(Path(self.temp.name).glob("root-bypass-audit-session--*.json"))
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))

        self.assertEqual("FAILED_OPEN", earlier["status"])
        self.assertEqual("started", earlier["agents"]["stale-terra-child"]["status"])
        self.assertEqual([], earlier.get("unmatched_child_prompts", []))
        self.assertEqual(2, len(ledgers))
        self.assertEqual({
            "root-bypass-audit-session--earlier-parent-turn.json",
            "root-bypass-audit-session--later-parent-turn.json",
        }, {path.name for path in ledgers})
        self.assertEqual("root-bypass-audit-session", later["session_id"])
        self.assertEqual("later-parent-turn", later["turn_id"])
        self.assertEqual("gpt-5.6-luna", later["decision"]["actual_root_model"])
        self.assertEqual("current", later["decision"]["route"])
        self.assertEqual("gpt-5.6-luna", observation["root_model"])

    def test_parent_stop_observed_running_parent_does_not_swallow_later_root(self) -> None:
        for suffix, later_model in (("luna", "gpt-6-luna"), ("terra", "gpt-6-sol")):
            with self.subTest(later_model=later_model):
                session = f"parent-stop-running-{suffix}"
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
                    "model": "gpt-6-luna", "model_reasoning_effort": "low",
                    "prompt": "Add pagination to this endpoint and include targeted tests.",
                })
                router_hook.handle({
                    "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                    "agent_id": "terra-child", "model": "gpt-6-sol", "reasoning_effort": "medium",
                })
                router_hook.handle({
                    "hook_event_name": "Stop", "session_id": session, "turn_id": "parent",
                    "stop_hook_active": False,
                })
                self._retain_running_parent_after_stop(session)

                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "later-root",
                    "model": later_model,
                    "model_reasoning_effort": "medium" if later_model.endswith("terra") else "low",
                    "prompt": "Explain this helper in two sentences.",
                })

                parent = self._ledger(session, "parent")
                later_path = Path(self.temp.name) / f"{session}--later-root.json"
                self.assertTrue(later_path.exists())
                later = self._ledger(session, "later-root")
                self.assertTrue(parent["parent_stop_observed"])
                self.assertEqual("RUNNING", parent["status"])
                self.assertEqual("started", parent["agents"]["terra-child"]["status"])
                self.assertEqual([], parent["agents"]["terra-child"]["child_turn_ids"])
                self.assertEqual([], parent.get("unmatched_child_prompts", []))
                self.assertEqual([], parent.get("child_prompt_ambiguities", []))
                self.assertEqual(later_model, later["decision"]["actual_root_model"])
                self.assertEqual("current", later["decision"]["route"])
                self.assertEqual(later_model, json.loads(
                    router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
                )["root_model"])

    def test_parent_stop_observed_preserves_previously_bound_multi_prompt_child(self) -> None:
        session = "parent-stop-bound-child"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Add pagination and targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra-child", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-turn",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "First child prompt.",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })
        self._retain_running_parent_after_stop(session)

        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-turn",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Second child prompt.",
        })

        parent = self._ledger(session, "parent")
        child = parent["agents"]["terra-child"]
        self.assertEqual(["child-turn"], child["child_turn_ids"])
        self.assertEqual(2, len(child["prompt_observations"]))
        self.assertFalse((Path(self.temp.name) / f"{session}--child-turn.json").exists())

    def test_parent_stop_observed_preserves_explicit_model_mismatched_child_without_receipt(self) -> None:
        session = "parent-stop-explicit-child"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Add pagination and targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra-child", "model": "gpt-6-astra", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })
        self._retain_running_parent_after_stop(session)

        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "late-child-turn",
            "agent_id": "terra-child", "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Complete the bounded child task.",
        })

        parent = self._ledger(session, "parent")
        child = parent["agents"]["terra-child"]
        self.assertEqual(["late-child-turn"], child["child_turn_ids"])
        self.assertEqual("gpt-6-sol", child["prompt_observed_model"])
        self.assertIn("child_model_mismatch:terra-child:prompt", parent["violations"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())
        self.assertFalse((Path(self.temp.name) / f"{session}--late-child-turn.json").exists())

    def test_terminal_stale_child_matrix_recovers_later_root_model(self) -> None:
        cases = (
            ("failed-terra-to-terra", "gpt-6-sol", "medium", "FAILED_OPEN", "gpt-6-sol"),
            ("failed-sol-to-luna", "gpt-6-sol", "high", "FAILED_OPEN", "gpt-6-luna"),
            ("complete-terra-to-luna", "gpt-6-sol", "medium", "COMPLETE", "gpt-6-luna"),
        )
        for session, child_model, child_effort, terminal_status, later_model in cases:
            with self.subTest(session=session):
                parent_prompt = (
                    "Audit session authentication for privilege escalation vulnerabilities."
                    if child_model.endswith("sol")
                    else "Add pagination to this endpoint and include targeted tests."
                )
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
                    "model": "gpt-6-luna", "model_reasoning_effort": "low", "prompt": parent_prompt,
                })
                router_hook.handle({
                    "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                    "agent_id": "stale-child", "model": child_model, "reasoning_effort": child_effort,
                })
                router_hook.handle({
                    "hook_event_name": "Stop", "session_id": session, "turn_id": "parent",
                    "stop_hook_active": False,
                })
                parent_path = Path(self.temp.name) / f"{session}--parent.json"
                parent = json.loads(parent_path.read_text(encoding="utf-8"))
                if terminal_status == "COMPLETE":
                    parent["status"] = "COMPLETE"
                    parent_path.write_text(json.dumps(parent), encoding="utf-8")

                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "later-root",
                    "model": later_model, "prompt": "Explain this helper in two sentences.",
                })

                parent = self._ledger(session, "parent")
                later = self._ledger(session, "later-root")
                self.assertEqual(terminal_status, parent["status"])
                self.assertEqual("started", parent["agents"]["stale-child"]["status"])
                self.assertEqual([], parent.get("unmatched_child_prompts", []))
                self.assertEqual(later_model, later["decision"]["actual_root_model"])
                self.assertEqual("later-root", later["turn_id"])
                self.assertEqual(later_model, json.loads(
                    router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
                )["root_model"])

    def test_terminal_stale_child_does_not_affect_an_unrelated_session_root(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "old-session", "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Add pagination and targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "old-session", "turn_id": "parent",
            "agent_id": "stale-terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": "old-session", "turn_id": "parent",
            "stop_hook_active": False,
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "new-session", "turn_id": "root",
            "model": "gpt-6-luna", "prompt": "Explain this helper in two sentences.",
        })

        self.assertEqual("root", self._ledger("new-session", "root")["turn_id"])
        self.assertEqual([], self._ledger("old-session", "parent").get("unmatched_child_prompts", []))

    def test_terminal_parent_keeps_a_known_wrong_model_child_turn_out_of_root_handling(self) -> None:
        session = "terminal-known-child"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Audit session authentication for privilege escalation vulnerabilities.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "sol-child", "model": "gpt-6-astra", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "known-child-turn",
            "agent_id": "sol-child",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Perform the bounded audit.",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "known-child-turn",
            "agent_id": "sol-child",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Finish the bounded audit.",
        })

        ledger = self._ledger(session, "parent")
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertIn("child_model_mismatch:sol-child:prompt", ledger["violations"])
        self.assertFalse((Path(self.temp.name) / f"{session}--known-child-turn.json").exists())
        self.assertEqual("gpt-6-luna", json.loads(
            router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
        )["root_model"])

    def test_terminal_parent_accepts_explicit_child_identity_despite_model_mismatch(self) -> None:
        session = "terminal-explicit-child"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Add pagination and targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra-child", "model": "gpt-6-astra", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "late-child-turn",
            "agent_id": "terra-child", "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Complete the bounded child task.",
        })

        ledger = self._ledger(session, "parent")
        self.assertEqual("late-child-turn", ledger["agents"]["terra-child"]["child_turn_id"])
        self.assertIn("child_model_mismatch:terra-child:prompt", ledger["violations"])
        self.assertFalse((Path(self.temp.name) / f"{session}--late-child-turn.json").exists())
        self.assertEqual("gpt-6-luna", json.loads(
            router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
        )["root_model"])

    def test_single_and_multi_prompt_children_support_terra_and_sol(self) -> None:
        cases = (
            ("terra-single", "gpt-6-sol", "medium", 1),
            ("terra-multi", "gpt-6-sol", "medium", 2),
            ("sol-single", "gpt-6-sol", "high", 1),
            ("sol-multi", "gpt-6-sol", "high", 2),
        )
        for session, model, effort, prompt_count in cases:
            with self.subTest(session=session):
                prompt = (
                    "Add pagination to this endpoint and include targeted tests for the changed behavior."
                    if model.endswith("terra")
                    else "Audit session authentication for privilege escalation vulnerabilities."
                )
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
                    "model": "gpt-6-luna", "model_reasoning_effort": "low", "prompt": prompt,
                })
                router_hook.handle({
                    "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                    "agent_id": "child", "model": model, "reasoning_effort": effort,
                })
                for index in range(prompt_count):
                    router_hook.handle({
                        "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-turn",
                        "model": model, "model_reasoning_effort": effort, "prompt": f"Child instruction {index}.",
                    })
                ledger = self._ledger(session, "parent")
                child = ledger["agents"]["child"]
                self.assertEqual(["child-turn"], child["child_turn_ids"])
                self.assertEqual(prompt_count, len(child["prompt_observations"]))
                self.assertEqual("started", child["status"])
                self.assertEqual("gpt-6-luna", json.loads(
                    router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
                )["root_model"])

    def test_repeated_child_prompt_is_idempotent_but_distinct_turns_are_retained(self) -> None:
        session = "multi-turn-idempotence"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        first = {
            "hook_event_name": "UserPromptSubmit", "hook_event_id": "hook-event-child-a",
            "session_id": session, "turn_id": "child-a",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "First instruction.",
        }
        router_hook.handle(first)
        router_hook.handle(first)
        router_hook.handle({
            **first, "hook_event_id": "hook-event-child-b", "turn_id": "child-b",
            "prompt": "Second instruction.",
        })
        child = self._ledger(session, "parent")["agents"]["terra"]
        self.assertEqual(["child-a", "child-b"], child["child_turn_ids"])
        self.assertEqual(2, len(child["prompt_observations"]))

    def test_sequential_terra_then_sol_children_share_one_luna_parent(self) -> None:
        session = "sequential-terra-sol"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Review this bounded implementation and its security boundary.",
        })
        for agent_id, model, effort in (
            ("terra", "gpt-6-sol", "medium"),
            ("sol", "gpt-6-sol", "high"),
        ):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                "agent_id": agent_id, "model": model, "reasoning_effort": effort,
            })
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": f"{agent_id}-turn",
                "model": model, "model_reasoning_effort": effort, "prompt": f"Run the {agent_id} task.",
            })
            router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": f"{agent_id}-turn",
                "agent_id": agent_id, "model": model, "reasoning_effort": effort,
                "last_assistant_message": "Evidence: done\nVerification: checked\nUncertainty: none",
            })
        ledger = self._ledger(session, "parent")
        self.assertEqual({"completed"}, {agent["status"] for agent in ledger["agents"].values()})
        self.assertEqual("gpt-6-luna", json.loads(
            router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
        )["root_model"])

    def test_later_prompt_model_mismatch_is_bound_to_known_child_and_blocks_receipt(self) -> None:
        session = "later-prompt-mismatch"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Audit session authentication for privilege escalation vulnerabilities.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "sol", "model": "gpt-6-sol", "reasoning_effort": "high",
        })
        for model in ("gpt-6-sol", "gpt-6-astra"):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child",
                "model": model, "model_reasoning_effort": "high", "prompt": f"Observed on {model}.",
            })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child",
            "agent_id": "sol", "model": "gpt-6-sol", "reasoning_effort": "high",
            "last_assistant_message": "Evidence: done\nVerification: checked\nUncertainty: none",
        })
        child = self._ledger(session, "parent")["agents"]["sol"]
        self.assertFalse(child["model_evidence_consistent"])
        self.assertIn("child_model_mismatch:sol:prompt", self._ledger(session, "parent")["violations"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())
        self.assertEqual("gpt-6-luna", json.loads(
            router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
        )["root_model"])

    def test_same_model_concurrent_sol_children_remain_ambiguous_across_prompts(self) -> None:
        session = "concurrent-sol"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Review production authorization and authentication boundaries in parallel.",
        })
        for agent_id in ("sol-a", "sol-b"):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "high",
            })
        ambiguous = {
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Do one bounded review.",
        }
        router_hook.handle(ambiguous)
        router_hook.handle({**ambiguous, "turn_id": "child-2", "prompt": "Continue one bounded review."})
        ledger = self._ledger(session, "parent")
        self.assertEqual(2, len(ledger["child_prompt_ambiguities"]))
        self.assertEqual({None}, {agent.get("child_turn_id") for agent in ledger["agents"].values()})
        self.assertEqual("gpt-6-luna", json.loads(
            router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8")
        )["root_model"])

    def test_child_stop_does_not_finalize_parent_and_exact_parent_beats_latest_ledger(self) -> None:
        session = "exact-parent-ledger"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "later-root",
            "model": "gpt-6-luna", "prompt": "Explain this helper in two sentences.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Do the child work.",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "child", "stop_hook_active": False,
        })
        self.assertEqual("RUNNING", self._ledger(session, "parent")["status"])
        parent_path = Path(self.temp.name) / f"{session}--parent.json"
        later_path = Path(self.temp.name) / f"{session}--later-root.json"
        newer = parent_path.stat().st_mtime_ns + 1_000_000_000
        os.utime(later_path, ns=(newer, newer))
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })
        self.assertEqual("FAILED_OPEN", self._ledger(session, "parent")["status"])
        self.assertEqual("ROUTED", self._ledger(session, "later-root")["status"])
        self.assertFalse((Path(self.temp.name) / f"{session}--child.json").exists())

    def test_exact_agent_owner_beats_a_newer_duplicate_ledger(self) -> None:
        session = "exact-agent-owner"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Do the child task.",
        })
        parent_path = Path(self.temp.name) / f"{session}--parent.json"
        duplicate_path = Path(self.temp.name) / f"{session}--child.json"
        shutil.copyfile(parent_path, duplicate_path)
        newer = parent_path.stat().st_mtime_ns + 1_000_000_000
        os.utime(duplicate_path, ns=(newer, newer))

        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child",
            "agent_id": "terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: checked\nUncertainty: none",
        })
        self.assertEqual("completed", self._ledger(session, "parent")["agents"]["terra"]["status"])
        duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
        self.assertEqual("started", duplicate["agents"]["terra"]["status"])

    def test_untrusted_transcript_text_cannot_complete_a_started_child(self) -> None:
        session = "test-d-transcript-false-completion"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": "Audit session authentication for privilege escalation vulnerabilities.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "sol-child", "model": "gpt-6-sol", "reasoning_effort": "high",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Do the child audit.",
        })
        transcript = Path(self.temp.name) / "test-d-parent.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in (
            {"payload": {
                "type": "custom_tool_call",
                "input": 'tools.multi_agent_v1__spawn_agent({agent_type:"gpt56_sol_deep",message:"bounded"})',
            }},
            {"payload": {
                "type": "custom_tool_call_output",
                "output": (
                    "Script completed. The router requires completed children and Evidence:, Verification:, "
                    "and Uncertainty: headings. Unrelated result: {\\\"agent_id\\\":\\\"sol-child\\\"}."
                ),
            }},
        )), encoding="utf-8")
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        ledger = self._ledger(session, "parent")
        child = ledger["agents"]["sol-child"]
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual("started", child["status"])
        self.assertFalse(child["completion_structured"])
        self.assertEqual(0, child["stop_events"])

    def test_direct_receipt_requires_an_observed_child_prompt(self) -> None:
        base = {"session_id": "receipt-needs-observation", "turn_id": "parent"}
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "agent_id": "terra-child",
            "model": "gpt-6-sol",
            "reasoning_effort": "medium",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "agent_id": "terra-child",
            "model": "gpt-6-sol",
            "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: tests passed\nUncertainty: none",
        })
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_exact_child_transcript_can_supply_the_missing_authoritative_prompt_evidence(self) -> None:
        session = "receipt-from-child-transcript"
        base = {
            "session_id": session,
            "runtime_version": "codex-1.2.3",
            "runtime_build": "desktop-456",
            "host_type": "Desktop",
        }
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "turn_id": "parent",
            "agent_id": "00000000-0000-7000-8000-000000000011",
            "model": "gpt-6-sol",
            "reasoning_effort": "medium",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "turn_id": "child-turn",
            "agent_id": "00000000-0000-7000-8000-000000000011",
            "model": "gpt-6-sol",
            "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: tests passed\nUncertainty: none",
        })
        parent = Path(self.temp.name) / f"{session}-parent.jsonl"
        parent.write_text("", encoding="utf-8")
        self._observe_valid_spawn(session, "parent", "00000000-0000-7000-8000-000000000011", "gpt56_terra_worker")
        self._write_child_transcript(session, "00000000-0000-7000-8000-000000000011", "gpt-6-sol", "medium")

        router_hook.handle({
            **base,
            "hook_event_name": "Stop",
            "turn_id": "parent",
            "stop_hook_active": False,
            "transcript_path": str(parent),
        })

        receipt = _capability_receipt("gpt-6-sol")
        child = self._ledger(session, "parent")["agents"]["00000000-0000-7000-8000-000000000011"]
        self.assertEqual("00000000-0000-7000-8000-000000000011", receipt["agent_id"])
        self.assertEqual("child-turn", receipt["child_turn_id"])
        self.assertEqual("gpt-6-sol", receipt["observed_child_model"])
        self.assertEqual("medium", receipt["observed_effort"])
        self.assertEqual(["child-turn"], child["child_turn_ids"])
        self.assertEqual("child_turn_context", child["prompt_observations"][0]["source"])

    def test_child_transcript_effort_contradiction_cannot_create_a_receipt(self) -> None:
        session = "receipt-child-effort-contradiction"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "00000000-0000-7000-8000-000000000011", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child-turn",
            "agent_id": "00000000-0000-7000-8000-000000000011", "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: tests passed\nUncertainty: none",
        })
        parent = Path(self.temp.name) / f"{session}-parent.jsonl"
        parent.write_text("", encoding="utf-8")
        self._write_child_transcript(session, "00000000-0000-7000-8000-000000000011", "gpt-6-sol", "high")
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent",
            "stop_hook_active": False, "transcript_path": str(parent),
        })
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_unknown_agent_stop_cannot_complete_the_expected_child(self) -> None:
        root = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "unknown-stop",
            "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        }
        router_hook.handle(root)
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "unknown-stop", "turn_id": "parent",
            "agent_id": "expected", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "unknown-stop", "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Do the bounded child task.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "unknown-stop", "turn_id": "child",
            "agent_id": "unknown", "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: passed\nUncertainty: none",
        })
        ledger = json.loads((Path(self.temp.name) / "unknown-stop--parent.json").read_text(encoding="utf-8"))
        self.assertEqual("started", ledger["agents"]["expected"]["status"])
        self.assertIn("unknown_agent_stop:unknown", ledger["violations"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_duplicate_stop_is_idempotent_for_a_correlated_child(self) -> None:
        events = (
            {
                "hook_event_name": "UserPromptSubmit", "session_id": "duplicate-stop", "turn_id": "parent",
                "model": "gpt-6-luna",
                "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
            },
            {
                "hook_event_name": "SubagentStart", "session_id": "duplicate-stop", "turn_id": "parent",
                "agent_id": "terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
            },
            {
                "hook_event_name": "UserPromptSubmit", "session_id": "duplicate-stop", "turn_id": "child",
                "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Do the child task.",
            },
        )
        for event in events:
            router_hook.handle(event)
        stop = {
            "hook_event_name": "SubagentStop", "session_id": "duplicate-stop", "turn_id": "child",
            "agent_id": "terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: passed\nUncertainty: none",
        }
        router_hook.handle(stop)
        router_hook.handle(stop)
        ledger = json.loads((Path(self.temp.name) / "duplicate-stop--parent.json").read_text(encoding="utf-8"))
        self.assertEqual(1, ledger["agents"]["terra"]["stop_events"])
        self.assertEqual(1, ledger["agents"]["terra"]["duplicate_stops"])

    def test_sequential_children_remain_scoped_to_the_same_luna_parent(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "sequential", "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        for index in (1, 2):
            agent_id = f"terra-{index}"
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": "sequential", "turn_id": "parent",
                "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
            })
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": "sequential", "turn_id": f"child-{index}",
                "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": f"Do child task {index}.",
            })
            router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": "sequential", "turn_id": f"child-{index}",
                "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
                "last_assistant_message": "Evidence: done\nVerification: passed\nUncertainty: none",
            })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        ledger = json.loads((Path(self.temp.name) / "sequential--parent.json").read_text(encoding="utf-8"))
        self.assertEqual("gpt-6-luna", observation["root_model"])
        self.assertEqual({"completed"}, {agent["status"] for agent in ledger["agents"].values()})

    def test_started_direct_child_that_never_stops_cannot_complete_or_write_a_receipt(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "never-stops", "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "never-stops", "turn_id": "parent",
            "agent_id": "terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "never-stops", "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Do the child task.",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": "never-stops", "turn_id": "parent",
            "stop_hook_active": False,
        })
        ledger = json.loads((Path(self.temp.name) / "never-stops--parent.json").read_text(encoding="utf-8"))
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_same_model_concurrent_child_prompts_are_ambiguous_and_fail_closed(self) -> None:
        session = "concurrent-direct"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "In parallel, extract version numbers from three independent manifests.",
        })
        for agent_id in ("terra-a", "terra-b"):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
            })
        for turn_id in ("child-a", "child-b"):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn_id,
                "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Extract one bounded manifest.",
            })
        for agent_id in ("terra-a", "terra-b"):
            router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": f"stop-{agent_id}",
                "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
                "last_assistant_message": "Evidence: version extracted\nVerification: manifest checked\nUncertainty: none",
            })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })
        ledger = json.loads((Path(self.temp.name) / f"{session}--parent.json").read_text(encoding="utf-8"))
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual({"terra-a", "terra-b"}, set(ledger["agents"]))
        self.assertEqual({None}, {agent.get("child_turn_id") for agent in ledger["agents"].values()})
        self.assertEqual({"completed"}, {agent["status"] for agent in ledger["agents"].values()})
        self.assertEqual("gpt-6-luna", observation["root_model"])
        self.assertEqual(2, len(ledger["child_prompt_ambiguities"]))
        self.assertTrue(all(len(item["candidate_agent_ids"]) == 2 for item in ledger["child_prompt_ambiguities"]))
        self.assertEqual(
            ["event-000001", "event-000002"],
            [item.get("event_key") for item in ledger["child_prompt_ambiguities"]],
        )
        self.assertEqual(
            {"opaque-event-v1"},
            {item.get("event_identity_schema") for item in ledger["child_prompt_ambiguities"]},
        )
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_distinct_identical_child_prompts_receive_opaque_non_content_event_identities(self) -> None:
        session = "opaque-distinct-prompts"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra-child", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        for suffix in ("a", "b"):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "hook_event_id": f"hook-event-{suffix}",
                "session_id": session, "turn_id": f"child-{suffix}", "agent_id": "terra-child",
                "model": "gpt-6-sol", "model_reasoning_effort": "medium",
                "prompt": "SYNTHETIC identical private child prompt",
            })

        observations = self._ledger(session, "parent")["agents"]["terra-child"]["prompt_observations"]
        self.assertEqual(["event-000001", "event-000002"], [item["event_key"] for item in observations])
        self.assertEqual({"opaque-event-v1"}, {item["event_identity_schema"] for item in observations})
        self.assertEqual(
            ["hook-event-a", "hook-event-b"],
            [item["lifecycle_event_id"] for item in observations],
        )

    def test_authoritative_child_prompt_replay_is_idempotent_without_prompt_comparison(self) -> None:
        session = "opaque-prompt-replay"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra-child", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        event = {
            "hook_event_name": "UserPromptSubmit", "hook_event_id": "hook-event-replayed",
            "session_id": session, "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
        }
        router_hook.handle({**event, "prompt": "SYNTHETIC private prompt alpha"})
        router_hook.handle({**event, "prompt": "SYNTHETIC private prompt beta"})

        ledger = self._ledger(session, "parent")
        observations = ledger["agents"]["terra-child"]["prompt_observations"]
        self.assertEqual(1, len(observations))
        self.assertEqual("event-000001", observations[0]["event_key"])
        self.assertEqual("hook-event-replayed", observations[0]["lifecycle_event_id"])
        self.assertEqual(1, ledger["agents"]["terra-child"]["duplicate_prompt_events"])

    def test_generated_ledger_persists_no_user_content_or_content_derived_digest(self) -> None:
        session = "ledger-privacy-audit"
        root_prompt = "SYNTHETIC ROOT PRIVATE 5f6136e7"
        child_prompt = "SYNTHETIC CHILD PRIVATE 9174bfea"
        assistant_content = (
            "Evidence: SYNTHETIC ASSISTANT PRIVATE a893cf2e\n"
            "Verification: complete\nUncertainty: none"
        )
        tool_output = "SYNTHETIC TOOL OUTPUT PRIVATE 4473a9bd"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna", "prompt": root_prompt,
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra-child", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "hook_event_id": "privacy-event-0001",
            "session_id": session, "turn_id": "child", "agent_id": "terra-child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": child_prompt,
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": "parent",
            "tool_name": "exec", "tool_input": {"command": "pwd"},
            "tool_response": {"exit_code": 0, "output": tool_output},
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child",
            "agent_id": "terra-child", "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": assistant_content,
        })

        serialized = json.dumps(self._ledger(session, "parent"), sort_keys=True, separators=(",", ":"))
        for content in (root_prompt, child_prompt, assistant_content, tool_output):
            with self.subTest(content=content.split()[1]):
                self.assertNotIn(content, serialized)
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                self.assertNotIn(digest, serialized)
                self.assertNotIn(digest[:24], serialized)
        legacy_material = json.dumps({
            "effort": "medium",
            "model": "gpt-6-sol",
            "prompt": child_prompt,
            "turn_id": "child",
        }, sort_keys=True, separators=(",", ":"))
        self.assertNotIn(hashlib.sha256(legacy_material.encode("utf-8")).hexdigest()[:24], serialized)

    def test_legacy_prompt_hash_event_cannot_establish_current_capability_proof(self) -> None:
        session = "legacy-prompt-event"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
            "agent_id": "terra-child", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child",
            "agent_id": "terra-child", "model": "gpt-6-sol",
            "model_reasoning_effort": "medium", "prompt": "Complete the bounded child task.",
        })
        path = Path(self.temp.name) / f"{session}--parent.json"
        legacy = json.loads(path.read_text(encoding="utf-8"))
        observation = legacy["agents"]["terra-child"]["prompt_observations"][0]
        observation.clear()
        observation.update({
            "event_key": "0123456789abcdef01234567",
            "turn_id": "child",
            "model": "gpt-6-sol",
            "effort": "medium",
        })
        path.write_text(json.dumps(legacy), encoding="utf-8")

        self._stop_terra_child(session, "child", "terra-child")
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent",
            "stop_hook_active": False,
        })

        ledger = self._ledger(session, "parent")
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertIn("legacy_prompt_event_identity:terra-child", ledger["violations"])
        self.assertFalse(ledger["agents"]["terra-child"]["receipt_recorded"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_authoritative_stop_resolves_one_ambiguity_and_allows_truthful_completion(self) -> None:
        session = "resolved-ambiguity-stop"
        self._start_concurrent_terra_children(session)
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "ambiguous-a",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Extract the assigned manifest.",
        })

        initial = self._ledger(session, "parent")
        ambiguity = initial["child_prompt_ambiguities"][0]
        ambiguity_key = ambiguity.get("ambiguity_key")
        violation = "ambiguous_child_prompt:ambiguous-a:gpt-6-sol"
        self.assertTrue(ambiguity_key)
        self.assertEqual("unresolved", ambiguity.get("resolution", {}).get("status"))
        self.assertIn(violation, initial["violations"])
        self.assertEqual({None}, {agent.get("child_turn_id") for agent in initial["agents"].values()})
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

        self._stop_terra_child(session, "ambiguous-a", "terra-a")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-b",
            "agent_id": "terra-b", "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Extract the other assigned manifest.",
        })
        self._stop_terra_child(session, "child-b", "terra-b")
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })

        ledger = self._ledger(session, "parent")
        resolved = ledger["child_prompt_ambiguities"][0]
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertIn(violation, ledger["violations"])
        self.assertEqual(ambiguity_key, resolved["ambiguity_key"])
        self.assertEqual({
            "status": "resolved",
            "ambiguity_key": ambiguity_key,
            "agent_id": "terra-a",
            "source": "subagent_stop",
            "turn_id": "ambiguous-a",
            "observed_model": "gpt-6-sol",
            "observed_effort": "medium",
        }, {key: resolved["resolution"][key] for key in (
            "status", "ambiguity_key", "agent_id", "source", "turn_id", "observed_model", "observed_effort",
        )})
        self.assertEqual(["ambiguous-a"], ledger["agents"]["terra-a"]["child_turn_ids"])
        self.assertEqual(["child-b"], ledger["agents"]["terra-b"]["child_turn_ids"])
        self.assertTrue(ledger["agents"]["terra-a"]["receipt_recorded"])
        self.assertTrue(ledger["agents"]["terra-b"]["receipt_recorded"])
        self.assertTrue(router_hook.CAPABILITY_PATH.exists())

    def test_resolving_one_stable_ambiguity_key_does_not_clear_another(self) -> None:
        session = "independent-ambiguities"
        self._start_concurrent_terra_children(session)
        for turn_id in ("ambiguous-a", "ambiguous-b"):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn_id,
                "model": "gpt-6-sol", "model_reasoning_effort": "medium",
                "prompt": f"Extract the manifest for {turn_id}.",
            })
        initial = self._ledger(session, "parent")
        keys = [item.get("ambiguity_key") for item in initial["child_prompt_ambiguities"]]
        self.assertEqual(2, len(set(keys)))

        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "ambiguous-a",
            "agent_id": "terra-a", "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Extract the manifest for ambiguous-a.",
        })

        ledger = self._ledger(session, "parent")
        by_turn = {item["turn_id"]: item for item in ledger["child_prompt_ambiguities"]}
        self.assertEqual(keys, [item["ambiguity_key"] for item in ledger["child_prompt_ambiguities"]])
        self.assertEqual("resolved", by_turn["ambiguous-a"]["resolution"]["status"])
        self.assertEqual("terra-a", by_turn["ambiguous-a"]["resolution"]["agent_id"])
        self.assertEqual("unresolved", by_turn["ambiguous-b"]["resolution"]["status"])
        self.assertEqual(["ambiguous-a"], ledger["agents"]["terra-a"]["child_turn_ids"])
        self.assertEqual([], ledger["agents"]["terra-b"]["child_turn_ids"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_same_turn_ambiguity_occurrences_cannot_be_bulk_resolved(self) -> None:
        session = "same-turn-ambiguities"
        self._start_concurrent_terra_children(session)
        ambiguous = {
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "shared-turn",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Extract the assigned manifest.",
        }
        router_hook.handle(ambiguous)
        router_hook.handle(ambiguous)
        before = self._ledger(session, "parent")
        keys = [item.get("ambiguity_key") for item in before["child_prompt_ambiguities"]]
        self.assertEqual(2, len(set(keys)))

        self._stop_terra_child(session, "shared-turn", "terra-a")

        ledger = self._ledger(session, "parent")
        self.assertEqual(keys, [item["ambiguity_key"] for item in ledger["child_prompt_ambiguities"]])
        self.assertEqual(
            {"unresolved"}, {item["resolution"]["status"] for item in ledger["child_prompt_ambiguities"]},
        )
        self.assertEqual([], ledger["agents"]["terra-a"]["child_turn_ids"])
        self.assertFalse(ledger["agents"]["terra-a"]["receipt_recorded"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_legacy_unkeyed_ambiguity_remains_fatal_without_resolution(self) -> None:
        session = "legacy-unkeyed-ambiguity"
        self._start_concurrent_terra_children(session)
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "ambiguous-a",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Extract the assigned manifest.",
        })
        path = Path(self.temp.name) / f"{session}--parent.json"
        legacy = json.loads(path.read_text(encoding="utf-8"))
        record = legacy["child_prompt_ambiguities"][0]
        record.pop("ambiguity_key")
        record.pop("resolution")
        record.pop("violation")
        path.write_text(json.dumps(legacy), encoding="utf-8")

        try:
            self._stop_terra_child(session, "ambiguous-a", "terra-a")
        except KeyError as exc:
            self.fail(f"legacy ambiguity must remain unresolved rather than crash: {exc}")

        ledger = self._ledger(session, "parent")
        self.assertNotIn("ambiguity_key", ledger["child_prompt_ambiguities"][0])
        self.assertFalse(ledger["agents"]["terra-a"]["receipt_recorded"])
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_insufficient_or_contradictory_evidence_cannot_resolve_ambiguity(self) -> None:
        cases = (
            ("wrong-turn", "different-turn", "gpt-6-sol"),
            ("wrong-model", "ambiguous-a", "gpt-6-astra"),
        )
        for suffix, stop_turn, stop_model in cases:
            with self.subTest(suffix=suffix):
                session = f"unresolved-{suffix}"
                self._start_concurrent_terra_children(session)
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "ambiguous-a",
                    "model": "gpt-6-sol", "model_reasoning_effort": "medium",
                    "prompt": "Extract the assigned manifest.",
                })
                self._stop_terra_child(session, stop_turn, "terra-a", stop_model)

                ledger = self._ledger(session, "parent")
                ambiguity = ledger["child_prompt_ambiguities"][0]
                self.assertEqual("unresolved", ambiguity.get("resolution", {}).get("status"))
                self.assertEqual([], ledger["agents"]["terra-a"]["child_turn_ids"])
                self.assertFalse(ledger["agents"]["terra-a"]["receipt_recorded"])
                self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_late_authoritative_resolution_is_idempotent_after_parent_stop(self) -> None:
        session = "late-resolved-ambiguity"
        self._start_concurrent_terra_children(session)
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "ambiguous-a",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Extract the assigned manifest.",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-b",
            "agent_id": "terra-b", "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Extract the other assigned manifest.",
        })
        self._stop_terra_child(session, "child-b", "terra-b")
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "parent", "stop_hook_active": False,
        })
        failed = self._ledger(session, "parent")
        self.assertEqual("FAILED_OPEN", failed["status"])
        self.assertTrue(failed["parent_stop_observed"])
        self.assertEqual(
            "unresolved", failed["child_prompt_ambiguities"][0].get("resolution", {}).get("status"),
        )

        self._stop_terra_child(session, "ambiguous-a", "terra-a")
        resolved = self._ledger(session, "parent")
        resolution = dict(resolved["child_prompt_ambiguities"][0]["resolution"])
        self.assertEqual("COMPLETE", resolved["status"])
        self.assertEqual("resolved", resolution["status"])
        self.assertTrue(resolved["agents"]["terra-a"]["receipt_recorded"])
        self.assertEqual(1, len(resolved["agents"]["terra-a"]["prompt_observations"]))

        self._stop_terra_child(session, "ambiguous-a", "terra-a")
        replayed = self._ledger(session, "parent")
        self.assertEqual("COMPLETE", replayed["status"])
        self.assertEqual(resolution, replayed["child_prompt_ambiguities"][0]["resolution"])
        self.assertEqual(1, len(replayed["agents"]["terra-a"]["prompt_observations"]))
        self.assertEqual(1, replayed["agents"]["terra-a"]["duplicate_stops"])

    def test_concurrent_terra_and_sol_prompts_correlate_uniquely_by_model(self) -> None:
        session = "concurrent-distinct-models"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": (
                "Review production authorization checks and independently diagnose a flaky queue worker, "
                "then synthesize a safe fix."
            ),
        })
        starts = (
            ("terra", "gpt-6-sol", "medium"),
            ("sol", "gpt-6-sol", "high"),
        )
        for agent_id, model, effort in starts:
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                "agent_id": agent_id, "agent_type": "worker", "model": model,
                "reasoning_effort": effort,
            })
        for turn_id, model, effort in (
            ("terra-turn", "gpt-6-sol", "medium"),
            ("sol-turn", "gpt-6-sol", "high"),
        ):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn_id,
                "model": model, "model_reasoning_effort": effort, "prompt": "Do the bounded child task.",
            })
        ledger = json.loads((Path(self.temp.name) / f"{session}--parent.json").read_text(encoding="utf-8"))
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("terra-turn", ledger["agents"]["terra"]["child_turn_id"])
        self.assertEqual("sol-turn", ledger["agents"]["sol"]["child_turn_id"])
        self.assertEqual("gpt-6-luna", observation["root_model"])

    def test_subsequent_parent_turn_can_update_the_root_after_child_completion(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_a.json").read_text(encoding="utf-8")
        )
        for event in fixture["lifecycle_events"][:-1]:
            router_hook.handle(event)
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "desktop-test-a-session", "turn_id": "next-parent",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Explain this helper.",
        })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("gpt-6-sol", observation["root_model"])

    def test_sol_parent_observation_is_not_overwritten_by_an_active_child(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "sol-parent", "turn_id": "parent",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Review the architecture.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "sol-parent", "turn_id": "parent",
            "agent_id": "parallel-terra", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "sol-parent", "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Run independent evidence gathering.",
        })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("gpt-6-sol", observation["root_model"])

    def test_observed_child_without_spawn_contract_never_creates_a_receipt(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "model-mismatch", "turn_id": "parent",
            "model": "gpt-6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "model-mismatch", "turn_id": "parent",
            "agent_id": "wrong-model", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "model-mismatch", "turn_id": "child",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Do the child task.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "model-mismatch", "turn_id": "child",
            "agent_id": "wrong-model", "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: passed\nUncertainty: none",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": "model-mismatch", "turn_id": "parent",
            "stop_hook_active": False,
        })
        ledger = json.loads((Path(self.temp.name) / "model-mismatch--parent.json").read_text(encoding="utf-8"))
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual("gpt-6-luna", observation["root_model"])
        child = ledger["agents"]["wrong-model"]
        self.assertEqual("gpt-6-sol", child["start_observed_model"])
        self.assertEqual("gpt-6-sol", child["prompt_observed_model"])
        self.assertEqual("gpt-6-sol", child["stop_observed_model"])
        self.assertTrue(child["model_evidence_consistent"])
        self.assertFalse(child["spawn_contract_valid"])
        self.assertEqual([], ledger.get("unmatched_child_prompts", []))

    def test_actual_root_model_matrix_prevents_downward_delegation(self) -> None:
        normal = "Implement a feature with multiple states, error handling, and targeted tests."
        hard = "Review production authorization checks for privilege escalation vulnerabilities."
        routine = "Fix a typo in the README."
        expected = {
            ("gpt-6-luna", "low"): ("current", "gpt6_sol_balanced", "gpt6_sol_high"),
            ("gpt-6-sol", "medium"): ("current", "current", "gpt6_sol_high"),
            ("gpt-6-sol", "high"): ("current", "current", "current"),
        }
        for (root_model, effort), routes in expected.items():
            with self.subTest(root_model=root_model):
                decisions = tuple(
                    router_hook.classify_prompt(prompt, root_model, effort, enforce_active_root=True)
                    for prompt in (routine, normal, hard)
                )
                self.assertEqual(routes, tuple(item["route"] for item in decisions))
                expected_efficiency = "READY" if root_model == "gpt-6-luna" else "DEGRADED"
                self.assertEqual({expected_efficiency}, {item["credit_efficiency"] for item in decisions})

    def test_satisfied_sol_high_root_keeps_only_non_downward_independent_workers(self) -> None:
        decision = router_hook.classify_prompt(
            "Research three independent APIs in parallel and recommend an architecture.",
            "gpt-6-sol", "high", enforce_active_root=True,
        )
        self.assertEqual("current", decision["route"])
        self.assertEqual("evidence_then_owner", decision["orchestration"]["mode"])
        self.assertEqual({"gpt6_sol_high": 2}, decision["orchestration"]["required_agents"])
        self.assertEqual("root", decision["orchestration"]["synthesis_owner"])

        stronger_root = router_hook.classify_prompt(
            "Research three independent APIs in parallel and recommend an architecture.",
            "gpt-6-sol", "xhigh", enforce_active_root=True,
        )
        self.assertEqual("current", stronger_root["route"])
        self.assertEqual({}, stronger_root["orchestration"]["required_agents"])

    def test_evidence_plan_instructions_use_current_gpt6_model_policy(self) -> None:
        decision = router_hook.classify_prompt(
            "Make the specified production billing change and report the exact verification.",
            "gpt-6-luna", "low", enforce_active_root=True,
        )
        context = router_hook._context(decision)
        self.assertIn('"model":"gpt-6-sol"', context)
        self.assertIn('"reasoning_effort":"medium"', context)
        self.assertNotIn("gpt-5.6-", context)
        self.assertNotIn("Terra", context)

        high_root = router_hook.classify_prompt(
            "Research three independent APIs in parallel and recommend an architecture.",
            "gpt-6-sol", "high", enforce_active_root=True,
        )
        high_context = router_hook._context(high_root)
        self.assertEqual({"gpt6_sol_high": 2}, high_root["orchestration"]["required_agents"])
        self.assertIn('"model":"gpt-6-sol"', high_context)
        self.assertIn('"reasoning_effort":"high"', high_context)
        self.assertNotIn("gpt-5.6-", high_context)
        self.assertNotIn("Terra", high_context)

    def test_continuation_reapplies_policy_from_each_actual_hook_model(self) -> None:
        base = {"hook_event_name": "UserPromptSubmit", "session_id": "root-change"}
        router_hook.handle({
            **base,
            "turn_id": "t1",
            "model": "gpt-6-luna",
            "model_reasoning_effort": "low",
            "prompt": "Review production authorization checks for privilege escalation vulnerabilities.",
        })
        router_hook.handle({
            **base,
            "turn_id": "t2",
            "model": "gpt-6-sol",
            "model_reasoning_effort": "medium",
            "prompt": "continue",
        })
        second = json.loads((Path(self.temp.name) / "root-change--t2.json").read_text())["decision"]
        self.assertEqual("gpt-6-sol", second["actual_root_model"])
        self.assertEqual("gpt6_sol_high", second["route"])
        self.assertEqual("DEGRADED", second["credit_efficiency"])

        router_hook.handle({
            **base,
            "turn_id": "t3",
            "model": "gpt-6-luna",
            "model_reasoning_effort": "low",
            "prompt": "continue",
        })
        third = json.loads((Path(self.temp.name) / "root-change--t3.json").read_text())["decision"]
        self.assertEqual("gpt-6-luna", third["actual_root_model"])
        self.assertEqual("gpt6_sol_high", third["route"])
        self.assertEqual("READY", third["credit_efficiency"])

    def test_user_intent_ambiguity_clarifies_without_spawning(self) -> None:
        decision = router_hook.classify_prompt(
            "Build me an app; I am not sure what architecture or approach I want.",
            "gpt-6-luna",
            "low",
        )
        self.assertTrue(decision["requires_clarification"])
        self.assertEqual("current", decision["route"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])
        self.assertEqual("clarify", decision["orchestration"]["mode"])
        self.assertIn("one concise clarification", router_hook._context(decision))

    def test_technical_uncertainty_in_clear_task_can_escalate(self) -> None:
        decision = router_hook.classify_prompt(
            "Diagnose the intermittent deadlock in the specified queue worker and add a regression test.",
            "gpt-6-luna",
            "low",
            enforce_active_root=True,
        )
        self.assertFalse(decision["requires_clarification"])
        self.assertEqual("gpt6_sol_high", decision["route"])
        self.assertEqual({"gpt6_sol_high": 1}, decision["orchestration"]["required_agents"])
        self.assertEqual("unsatisfied", decision["profile_satisfaction"])

    def test_context_uses_direct_model_spawn_without_legacy_agent_type(self) -> None:
        decision = router_hook.classify_prompt(
            "Review production authorization checks for privilege escalation vulnerabilities.",
            "gpt-6-luna",
            "low",
            enforce_active_root=True,
        )
        context = router_hook._context(decision)
        self.assertIn('"model":"gpt-6-sol"', context)
        self.assertIn('"reasoning_effort":"high"', context)
        self.assertNotIn("agent_type", context)
        self.assertNotIn('"model":"gpt-6-luna"', context)

    def test_actual_turn_writes_prompt_free_root_observation(self) -> None:
        secret_prompt = "Fix the docs. PRIVATE-PROMPT-CONTENT"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit",
            "session_id": "root-observation",
            "turn_id": "t1",
            "model": "gpt-6-luna",
            "prompt": secret_prompt,
            "runtime_version": "codex-1.2.3",
            "runtime_build": "desktop-456",
            "host_type": "Desktop",
        })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("gpt-6-luna", observation["root_model"])
        self.assertEqual("root-observation", observation["session_id"])
        self.assertEqual("t1", observation["turn_id"])
        self.assertEqual(router_hook.PLUGIN_IDENTITY, observation["plugin_identity"])
        self.assertEqual("codex-1.2.3", observation["runtime_version"])
        self.assertEqual("desktop-456", observation["runtime_build"])
        self.assertEqual("Desktop", observation["host_type"])
        self.assertNotIn(secret_prompt, json.dumps(observation))
        task_observation = router_hook.ROOT_OBSERVATION_PATH.parent / "root-observations-v1" / "root-observation.json"
        self.assertEqual(observation, json.loads(task_observation.read_text(encoding="utf-8")))

    def test_successful_direct_child_writes_runtime_bound_capability_receipt(self) -> None:
        base = {
            "session_id": "capability-receipt",
            "turn_id": "t1",
            "runtime_version": "codex-1.2.3",
            "runtime_build": "desktop-456",
            "host_type": "Desktop",
        }
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-6-luna",
            "prompt": "Review production authorization checks for privilege escalation vulnerabilities.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "agent_id": "sol-child",
            "model": "gpt-6-sol",
            "reasoning_effort": "high",
        })
        self._observe_valid_spawn("capability-receipt", "t1", "sol-child", "gpt56_sol_deep")
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "turn_id": "child-turn",
            "model": "gpt-6-sol",
            "model_reasoning_effort": "high",
            "prompt": "Perform the bounded security review and return structured evidence.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "turn_id": "child-turn",
            "agent_id": "sol-child",
            "model": "gpt-6-sol",
            "reasoning_effort": "high",
            "last_assistant_message": "Evidence: checked\nVerification: tests passed\nUncertainty: none",
        })
        receipt = _capability_receipt("gpt-6-sol-high")
        self.assertEqual("direct-model-spawn-v1", receipt["capability_signature"])
        self.assertEqual(router_hook.PLUGIN_IDENTITY, receipt["plugin_identity"])
        self.assertEqual("child-turn", receipt["child_turn_id"])
        self.assertEqual("gpt-6-sol", receipt["observed_child_model"])
        self.assertEqual("high", receipt["effort_intent"])
        self.assertEqual("codex-1.2.3", receipt["runtime_version"])
        self.assertEqual("desktop-456", receipt["runtime_build"])
        self.assertTrue(receipt["profile_policy_valid"])
        self.assertNotIn("authorization", json.dumps(receipt).lower())
        document = json.loads(router_hook.CAPABILITY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(3, document["schema_version"])
        self.assertEqual({router_hook.model_policy.capability_key("gpt-6-sol", "high", "high")}, set(document["capabilities"]))

    def test_gpt61_lifecycle_receipt_is_accepted_by_the_actual_checker(self) -> None:
        import check_hooks

        for model in ("gpt-6.1-sol", "gpt-6.1-terra"):
            with self.subTest(model=model):
                base = {"session_id": "receipt-" + model.replace(".", "-"), "turn_id": "parent",
                        "runtime_version": "1.2.3", "runtime_build": "desktop-456", "host_type": "Desktop"}
                router_hook.handle({**base, "hook_event_name": "UserPromptSubmit", "model": model,
                                    "model_reasoning_effort": "medium", "prompt": "Debug a race condition across three modules."})
                role = router_hook.spawn_compat.role_for(model, "high")
                router_hook.handle({**base, "hook_event_name": "SubagentStart", "agent_id": model,
                                    "model": model, "reasoning_effort": "high"})
                self._observe_valid_spawn(base["session_id"], "parent", model, role)
                router_hook.handle({**base, "hook_event_name": "UserPromptSubmit", "turn_id": "child",
                                    "model": model, "model_reasoning_effort": "high", "prompt": "Review the bounded race."})
                router_hook.handle({**base, "hook_event_name": "SubagentStop", "turn_id": "child", "agent_id": model,
                                    "model": model, "reasoning_effort": "high",
                                    "last_assistant_message": "Evidence: reviewed\nVerification: checked\nUncertainty: none"})
                health = check_hooks._routing_health(
                    {"available": True}, router_hook.PLUGIN_VERSION, router_hook.CAPABILITY_PATH.parent,
                    plugin_identity=router_hook.PLUGIN_IDENTITY, current_session_id=base["session_id"],
                )
                key = router_hook.model_policy.capability_key(model, "high", "high")
                self.assertEqual("CURRENT", health["capability_status"][key], health)
                self.assertEqual("DEGRADED", health["status"])  # non-Luna savings remain unproven

    def test_astra_receipt_requires_an_exact_astra_observation(self) -> None:
        preserved = {
            "schema_version": 3,
            "capability_signature": "direct-model-spawn-v1",
            "policy_revision": router_hook.model_policy.POLICY_REVISION,
            "capabilities": {router_hook.model_policy.capability_key("gpt-6-sol", "balanced", "medium"): {"preserved": True}},
        }
        router_hook.CAPABILITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        router_hook.CAPABILITY_PATH.write_text(json.dumps(preserved), encoding="utf-8")
        base = {
            "session_id": "astra-capability-receipt",
            "turn_id": "t1",
            "runtime_version": "codex-1.2.3",
            "runtime_build": "desktop-456",
            "host_type": "Desktop",
        }
        agent_id = "00000000-0000-7000-8000-000000000205"
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-6-luna",
            "model_reasoning_effort": "low",
            "prompt": "Use GPT-6 Astra Medium for this bounded task.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "agent_id": agent_id,
            "model": "gpt-6-astra",
            "reasoning_effort": "medium",
        })
        self._observe_valid_spawn("astra-capability-receipt", "t1", agent_id, "gpt6_astra_medium")
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "turn_id": "child-turn",
            "agent_id": agent_id,
            "model": "gpt-6-astra",
            "model_reasoning_effort": "medium",
            "prompt": "Complete the bounded frontier task.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "turn_id": "child-turn",
            "agent_id": agent_id,
            "model": "gpt-6-astra",
            "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: checked\nVerification: tests passed\nUncertainty: none",
        })
        receipt = _capability_receipt("gpt-6-astra")
        self.assertEqual("gpt-6-astra", receipt["requested_child_model"])
        self.assertEqual("gpt-6-astra", receipt["observed_child_model"])
        self.assertEqual("medium", receipt["effort_intent"])
        document = json.loads(router_hook.CAPABILITY_PATH.read_text(encoding="utf-8"))
        self.assertEqual({
            router_hook.model_policy.capability_key("gpt-6-sol", "balanced", "medium"),
            router_hook.model_policy.capability_key("gpt-6-astra", "frontier", "medium"),
        }, set(document["capabilities"]))
        self.assertTrue(document["capabilities"][router_hook.model_policy.capability_key("gpt-6-sol", "balanced", "medium")]["preserved"])

        state = self._ledger("astra-capability-receipt", "t1")
        state["agents"][agent_id]["receipt_recorded"] = False
        state["agents"][agent_id]["observed_model"] = "gpt-6-sol"
        state["agents"][agent_id]["model_evidence_consistent"] = False
        router_hook.CAPABILITY_PATH.unlink()
        self.assertFalse(router_hook._record_capability(state, agent_id))
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_ledger_records_routing_telemetry_without_inventing_credit_usage(self) -> None:
        base = {"session_id": "telemetry", "turn_id": "t1"}
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-6-luna",
            "service_tier": "priority",
            "prompt": "Review production authorization checks for privilege escalation vulnerabilities.",
        })
        initial = json.loads((Path(self.temp.name) / "telemetry--t1.json").read_text())
        telemetry = initial["telemetry"]
        self.assertEqual("gpt-6-luna", telemetry["root_model"])
        self.assertEqual(["gpt-6-sol"], telemetry["requested_child_models"])
        self.assertEqual(["high"], telemetry["effort_intents"])
        self.assertEqual("fast", telemetry["service_tier"])
        self.assertEqual("hook", telemetry["service_tier_source"])
        self.assertEqual("UNAVAILABLE", telemetry["usage"]["provenance"])

        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "agent_id": "telemetry-child",
            "model": "gpt-6-sol",
            "reasoning_effort": "high",
        })
        self._observe_valid_spawn("telemetry", "t1", "telemetry-child", "gpt56_sol_deep")
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "turn_id": "child-turn",
            "model": "gpt-6-sol",
            "model_reasoning_effort": "high",
            "prompt": "Perform the bounded security review and return structured evidence.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "turn_id": "child-turn",
            "agent_id": "telemetry-child",
            "model": "gpt-6-sol",
            "reasoning_effort": "high",
            "last_assistant_message": "Evidence: checked\nVerification: passed\nUncertainty: none",
        })
        final = json.loads((Path(self.temp.name) / "telemetry--t1.json").read_text())["telemetry"]
        self.assertEqual(1, final["child_count"])
        self.assertEqual(0, final["route_up_count"])
        self.assertTrue(final["child_completion_attested"])

    def test_codex_delegation_metadata_never_contaminates_classification(self) -> None:
        prompt = """<codex_delegation>
  <source_thread_id>019f4ab3-2b7a-7932-a6a6-f401afced4e3</source_thread_id>
  <input>Explain this small helper in one sentence.</input>
</codex_delegation>"""
        decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")
        self.assertEqual(0, decision["task_profile"]["unit_count"])
        self.assertEqual("normal", decision["task_profile"]["risk"])
        self.assertEqual("explanation", decision["task_profile"]["task_type"])

    def test_relayforge_mechanical_fixture_prompt_routes_to_luna(self) -> None:
        prompt = """<codex_delegation>
  <source_thread_id>019f4ab3-2b7a-7932-a6a6-f401afced4e3</source_thread_id>
  <input>Generate exactly 1,200 synthetic JSONL fixture records in three independent 400-record shards using the fixed schema and formulas. One example projectSlug is billing-reliability. These are synthetic fixtures, not customer data. Add a validator that rejects malformed JSON, wrong key order, formula mismatches, duplicates, and incorrect totals. Do not modify runtime or database schema. Run the validator, tests, typecheck, lint, and build. The routing ledger should show the selected workers.</input>
</codex_delegation>"""
        decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low", enforce_active_root=True)
        profile = decision["task_profile"]
        self.assertEqual("current", decision["route"])
        self.assertEqual("direct", decision["orchestration"]["mode"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])
        self.assertEqual(1200, profile["unit_count"])
        self.assertEqual("mechanical_batch", profile["task_type"])
        self.assertEqual("normal", profile["risk"])
        self.assertEqual("general_product", profile["product"]["primary_area"])

    def test_three_profiles_shift_normal_work_monotonically(self) -> None:
        prompt = "Diagnose why this flaky test fails intermittently."
        expected = {
            "token-saver": ("gpt56_terra_worker", "single_delegate"),
            "balanced": ("gpt56_terra_deep", "single_delegate"),
            "max-quality": ("gpt56_sol_owner", "single_delegate"),
        }
        for profile, (route, mode) in expected.items():
            with self.subTest(profile=profile):
                decision = router_hook.classify_prompt(prompt, "", "medium", profile)
                self.assertEqual(route, decision["route"])
                self.assertEqual(mode, decision["orchestration"]["mode"])
                self.assertEqual(profile, decision["routing_profile"])

    def test_token_saver_removes_optional_fanout_and_councils(self) -> None:
        batch = router_hook.classify_prompt(
            "Convert all 500 images to WebP and compare checksums.", "", "medium", "token-saver"
        )
        uncertain = router_hook.classify_prompt(
            "I am not sure which model should build this broad new product.", "", "medium", "token-saver"
        )
        self.assertIn(batch["orchestration"]["mode"], {"direct", "single_delegate"})
        self.assertEqual("clarify", uncertain["orchestration"]["mode"])
        for decision in (batch, uncertain):
            self.assertEqual(1, decision["max_workers"])

    def test_token_saver_never_weakens_safety_floors(self) -> None:
        prompts = (
            "Review OAuth token handling for auth bypasses and leaked credentials.",
            "Implement subscription upgrades with proration idempotency and reconciliation.",
            "Delete the production database.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                balanced = router_hook.classify_prompt(prompt, "", "medium", "balanced")
                saver = router_hook.classify_prompt(prompt, "", "medium", "token-saver")
                self.assertEqual(balanced["route"], saver["route"])
                self.assertEqual(balanced["orchestration"]["mode"], saver["orchestration"]["mode"])

    def test_max_quality_keeps_trivia_direct_and_adds_evidence_for_deep_mutations(self) -> None:
        trivial = router_hook.classify_prompt("Fix a typo in README.", "", "medium", "max-quality")
        owner = router_hook.classify_prompt(
            "Design and implement a cross-service event migration.", "", "medium", "max-quality"
        )
        self.assertEqual("current", trivial["route"])
        self.assertEqual("direct", trivial["orchestration"]["mode"])
        self.assertEqual("gpt56_sol_deep", owner["route"])
        self.assertEqual("evidence_then_owner", owner["orchestration"]["mode"])
        self.assertEqual("gpt56_sol_deep", owner["orchestration"]["synthesis_role"])
        self.assertIn("independent evidence synthesis", owner["verification"])

    def test_max_quality_reserves_extra_high_for_the_hardest_work(self) -> None:
        security = router_hook.classify_prompt(
            "Audit production authentication for privilege escalation.", "gpt-6-sol", "medium", "max-quality"
        )
        architecture = router_hook.classify_prompt(
            "Design the architecture for a cross-service migration.", "gpt-6-sol", "medium", "max-quality"
        )
        self.assertEqual("gpt56_sol_xhigh", security["route"])
        self.assertEqual("xhigh", security["effort"])
        self.assertEqual("gpt56_sol_deep", architecture["route"])

    def test_max_quality_upgrades_the_capability_target_not_the_optimized_current_route(self) -> None:
        prompt = "Add pagination to this endpoint and include targeted tests for the changed behavior."
        balanced = router_hook.classify_prompt(
            prompt, "gpt-6-sol", "medium", "balanced", enforce_active_root=True,
        )
        quality = router_hook.classify_prompt(
            prompt, "gpt-6-sol", "medium", "max-quality", enforce_active_root=True,
        )
        self.assertEqual("current", balanced["route"])
        self.assertEqual("gpt6_sol_balanced", balanced["capability_target"])
        self.assertEqual("gpt6_sol_high", quality["route"])

    def test_hook_reads_profile_and_keeps_fast_independent(self) -> None:
        router_hook.PROFILE_PATH.parent.mkdir(parents=True)
        router_hook.PROFILE_PATH.write_text(
            '{"schema_version":1,"profile":"token-saver"}', encoding="utf-8"
        )
        result = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "profile-fast", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "service_tier": "fast", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        context = result["hookSpecificOutput"]["additionalContext"]
        ledger = json.loads((Path(self.temp.name) / "profile-fast--t1.json").read_text())
        decision = ledger["decision"]
        self.assertEqual("token-saver", decision["routing_profile"])
        self.assertEqual("configured", decision["routing_profile_source"])
        self.assertTrue(decision["fast_enabled"])
        self.assertIn("Fast", decision["visible_route"])
        self.assertIn('"routing_profile":"token-saver"', context)

    def test_invalid_profile_fails_safe_to_balanced(self) -> None:
        router_hook.PROFILE_PATH.parent.mkdir(parents=True)
        router_hook.PROFILE_PATH.write_text('{"profile":"surprise"}', encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "invalid-profile", "turn_id": "t1",
            "model": "", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        self.assertIn("hookSpecificOutput", result)
        decision = json.loads((Path(self.temp.name) / "invalid-profile--t1.json").read_text())["decision"]
        self.assertEqual("balanced", decision["routing_profile"])
        self.assertEqual("invalid_default", decision["routing_profile_source"])
        self.assertEqual("current", decision["route"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])
        self.assertEqual("unproven", decision["profile_satisfaction"])

    def test_profile_change_applies_to_next_new_task_not_continuation(self) -> None:
        router_hook.PROFILE_PATH.parent.mkdir(parents=True)
        router_hook.PROFILE_PATH.write_text(
            '{"schema_version":1,"profile":"token-saver"}', encoding="utf-8"
        )
        base = {"hook_event_name": "UserPromptSubmit", "session_id": "profile-continuation", "model": ""}
        router_hook.handle({**base, "turn_id": "t1", "prompt": "Diagnose why this flaky test fails intermittently."})
        router_hook.PROFILE_PATH.write_text(
            '{"schema_version":1,"profile":"max-quality"}', encoding="utf-8"
        )
        router_hook.handle({**base, "turn_id": "t2", "prompt": "continue"})
        router_hook.handle({**base, "turn_id": "t3", "prompt": "Explain this architecture and its trade-offs in detail."})
        continued = json.loads((Path(self.temp.name) / "profile-continuation--t2.json").read_text())["decision"]
        fresh = json.loads((Path(self.temp.name) / "profile-continuation--t3.json").read_text())["decision"]
        self.assertEqual("token-saver", continued["routing_profile"])
        self.assertEqual("max-quality", fresh["routing_profile"])

    def test_adversarial_task_profiles_and_plans(self) -> None:
        for prompt, route, task_type, mode in ADVERSARIAL_CASES:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low", enforce_active_root=True)
                self.assertEqual(_active_route(route), decision["route"])
                self.assertEqual(task_type, decision["task_profile"]["task_type"])
                self.assertEqual(mode, decision["orchestration"]["mode"])

    def test_product_building_areas_route_per_work_unit(self) -> None:
        for prompt, primary_area, expected_route in PRODUCT_CASES:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low", enforce_active_root=True)
                self.assertEqual(primary_area, decision["task_profile"]["product"]["primary_area"])
                self.assertEqual(_active_route(expected_route), decision["route"])

    def test_critical_billing_change_uses_evidence_then_owner(self) -> None:
        decision = router_hook.classify_prompt(
            "Implement subscription upgrades with proration idempotency and reconciliation.",
            "gpt-6-sol", "medium",
        )
        self.assertEqual("critical", decision["task_profile"]["risk"])
        self.assertEqual("evidence_then_owner", decision["orchestration"]["mode"])
        self.assertEqual({"gpt56_terra_worker": 2, "gpt56_sol_owner": 1}, decision["orchestration"]["required_agents"])

    def test_every_route_emits_a_valid_bounded_plan(self) -> None:
        for prompt, _ in CASES:
            decision = router_hook.classify_prompt(prompt, "gpt-6-luna", "low")
            plan = decision["orchestration"]
            self.assertLessEqual(sum(plan["required_agents"].values()), plan["max_workers"])
            self.assertLessEqual(plan["max_workers"], 3)
            self.assertEqual(1, plan["max_depth"])
            self.assertEqual("root", plan["final_acceptance_owner"])
            self.assertTrue(set(plan["required_agents"]).issubset(set(plan["allowed_agents"])))
            if plan["mode"] == "direct":
                self.assertFalse(plan["required_agents"])

    def test_injected_context_uses_only_the_direct_spawn_adapter_shape(self) -> None:
        decision = router_hook.classify_prompt(
            "Review OAuth token handling for authorization bypasses.", "gpt-6-luna", "low",
            enforce_active_root=True,
        )
        decision.update(router_hook._service_tier({"service_tier": "priority"}))
        decision["effort_evidence"] = "owned_agent_config_intent"
        decision["visible_route"] = router_hook._visible_route(decision, {})
        decision["announce_route"] = False
        context = router_hook._context(decision)
        self.assertIn("MANDATORY SPAWN ARGUMENT CONTRACT", context)
        self.assertIn(
            'spawn_agent({"fork_turns":"none","task_name":"<unique-1>","message":"<distilled-task>","model":"gpt-6-sol","reasoning_effort":"high"})',
            context,
        )
        self.assertIn("`fork_turns` must be exactly `\"none\"`", context)
        self.assertIn("keep `task_name` only as a unique orchestration label", context)
        self.assertIn("Never use the default or `\"all\"` full-history fork", context)
        self.assertIn("pass the adapter-selected `model` and `reasoning_effort`", context)
        self.assertNotIn("agent_type", context)

    def test_classifier_is_deterministic_and_redacted(self) -> None:
        prompt = "Audit OAuth token handling for leaked credentials in production. secret-123"
        first = router_hook.classify_prompt(prompt, "gpt-6-sol", "medium")
        second = router_hook.classify_prompt(prompt, "gpt-6-sol", "medium")
        self.assertEqual(first, second)
        self.assertNotIn("secret-123", json.dumps(first))

    def test_invalid_or_oversized_state_is_ignored(self) -> None:
        invalid = Path(self.temp.name) / "bad--t1.json"
        invalid.write_text('{"version": 999, "decision": {}}', encoding="utf-8")
        self.assertIsNone(router_hook._load_state_path(invalid))
        oversized = Path(self.temp.name) / "huge--t1.json"
        with oversized.open("wb") as stream:
            stream.truncate(2 * 1024 * 1024 + 1)
        self.assertIsNone(router_hook._load_state_path(oversized))

    def test_state_storage_rejects_symlinks_and_avoids_sanitized_id_collisions(self) -> None:
        self.assertNotEqual(router_hook._safe("session/a"), router_hook._safe("session?a"))
        external = Path(self.temp.name) / "external-state"
        external.mkdir()
        linked = Path(self.temp.name) / "linked-state"
        linked.symlink_to(external, target_is_directory=True)
        router_hook.STATE_ROOT = linked
        with self.assertRaisesRegex(RuntimeError, "symlink state directory"):
            with router_hook._ledger_lock():
                pass
        self.assertFalse(any(external.iterdir()))

    def test_active_capability_avoids_redundant_handoff(self) -> None:
        ambiguous = router_hook.classify_prompt(
            "Diagnose why this flaky test fails intermittently.", "gpt-6-sol", "high",
            enforce_active_root=True,
        )
        self.assertEqual("current", ambiguous["route"])
        architecture = router_hook.classify_prompt(
            "Design the architecture for a cross-service migration.", "gpt-6-sol", "medium",
            enforce_active_root=True,
        )
        self.assertEqual("current", architecture["route"])

    def test_security_analysis_stays_current_when_sol_high_is_already_active(self) -> None:
        decision = router_hook.classify_prompt(
            "Audit production authentication for privilege escalation.", "gpt-6-sol", "high",
            enforce_active_root=True,
        )
        self.assertEqual("current", decision["route"])

    def test_active_model_effort_matrix(self) -> None:
        prompt = "Diagnose why this flaky test fails intermittently."
        expected = {
            ("gpt-6-luna", "low"): "gpt6_sol_high",
            ("gpt-6-sol", "medium"): "gpt6_sol_high",
            ("gpt-6-sol", "high"): "current",
        }
        for active, route in expected.items():
            with self.subTest(active=active):
                self.assertEqual(route, router_hook.classify_prompt(prompt, *active, enforce_active_root=True)["route"])

    def test_luna_requires_cheap_verification(self) -> None:
        decision = router_hook.classify_prompt("Make mechanical changes across 100 files.", "gpt-6-sol")
        self.assertNotEqual("gpt56_luna_worker", decision["route"])

    def test_prompt_hook_writes_redacted_ledger(self) -> None:
        data = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "turn_id": "t1",
            "model": "gpt-6-sol",
            "prompt": "Rename a secret field in 100 JSON files and validate the schema.",
        }
        output = router_hook.handle(data)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("PROACTIVE GOVERNANCE CONTRACT", context)
        self.assertIn("exact required-agent multiset", context)
        self.assertIn("lifecycle-attest", context)
        self.assertIn("verification gate after the final mutation", context)
        self.assertIn("Stop and SubagentStop are advisory-only", context)
        self.assertIn("text(JSON.stringify({exit_code:r.exit_code,output:r.output}))", context)
        ledger = json.loads(next(Path(self.temp.name).glob("*.json")).read_text())
        self.assertNotIn(data["prompt"], json.dumps(ledger))
        self.assertNotIn("prompt_hash", ledger)

    def test_manual_ledger_purge_preserves_foreign_files(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "purge", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Hi",
        })
        foreign = Path(self.temp.name) / "foreign.json"
        foreign.write_text('{"owner":"user"}\n', encoding="utf-8")
        result = router_hook.purge_ledgers()
        self.assertEqual(1, result["ledgers_removed"])
        self.assertTrue(foreign.exists())
        self.assertTrue((Path(self.temp.name) / ".router.lock").exists())

    def test_manual_purge_preserves_router_shaped_json_without_the_owner_nonce(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "owned", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Hi",
        })
        foreign = Path(self.temp.name) / "foreign-business-data.json"
        foreign.write_text(json.dumps({
            "version": router_hook.STATE_VERSION,
            "decision": {"route": "current", "orchestration": {"required_agents": {}, "allowed_agents": []}},
            "foreign_business_data": "keep me",
        }), encoding="utf-8")
        result = router_hook.purge_ledgers()
        self.assertEqual(1, result["ledgers_removed"])
        self.assertTrue(foreign.exists())

    def test_normal_hook_refuses_to_claim_a_nonempty_unowned_state_root(self) -> None:
        foreign = Path(self.temp.name) / "foreign.json"
        foreign.write_text('{"keep":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "nonempty unowned"):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": "claim", "turn_id": "t1",
                "model": "gpt-6-sol", "prompt": "Hi",
            })
        self.assertEqual('{"keep":true}\n', foreign.read_text(encoding="utf-8"))

    @unittest.skipIf(not hasattr(os, "link"), "hardlinks unavailable")
    def test_purge_preserves_hardlinked_router_ledgers(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "linked", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Hi",
        })
        ledger = Path(self.temp.name) / "linked--t1.json"
        alias = Path(self.temp.name) / "foreign-hardlink.json"
        os.link(ledger, alias)
        result = router_hook.purge_ledgers()
        self.assertEqual(0, result["ledgers_removed"])
        self.assertTrue(ledger.exists())
        self.assertTrue(alias.exists())

    def test_manual_ledger_purge_exhausts_more_than_two_thousand_ledgers(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "template", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Hi",
        })
        template = (Path(self.temp.name) / "template--t1.json").read_bytes()
        for index in range(2004):
            (Path(self.temp.name) / f"bulk-{index}.json").write_bytes(template)
        result = router_hook.purge_ledgers()
        self.assertEqual(2005, result["ledgers_removed"])
        self.assertEqual([".gpt56-router-state.json"], [path.name for path in Path(self.temp.name).glob("*.json")])

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_purge_cli_reports_symlinked_state_root_as_an_error(self) -> None:
        external = Path(self.temp.name) / "external"
        external.mkdir()
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(external, target_is_directory=True)
        script = Path(router_hook.__file__)
        result = subprocess.run(
            [sys.executable, str(script), "--purge-ledgers"],
            env={**os.environ, "CODEX_ROUTER_STATE_DIR": str(linked)},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("error", json.loads(result.stdout)["status"])
        self.assertNotIn('"continue":true', result.stdout)

    def test_purge_cli_requires_an_explicit_plugin_state_location(self) -> None:
        script = Path(router_hook.__file__)
        env = dict(os.environ)
        for name in ("CODEX_ROUTER_STATE_DIR", "PLUGIN_DATA", "CLAUDE_PLUGIN_DATA"):
            env.pop(name, None)
        result = subprocess.run(
            [sys.executable, str(script), "--purge-ledgers"], env=env, text=True, capture_output=True, check=False
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("CODEX_ROUTER_STATE_DIR", result.stdout)

    def test_upgrade_uses_v2_state_without_claiming_legacy_beta_state(self) -> None:
        plugin_data = Path(self.config_temp.name).resolve() / "plugin-data"
        legacy = plugin_data / "router-state"
        legacy.mkdir(parents=True)
        foreign = legacy / "legacy.json"
        foreign.write_text('{"legacy":true}\n', encoding="utf-8")
        event = {
            "hook_event_name": "UserPromptSubmit", "session_id": "upgrade", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Hi",
        }
        environment = {
            **os.environ,
            "PLUGIN_DATA": str(plugin_data),
            "CODEX_HOME": str(router_hook.CONFIG_PATH.parent),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        environment.pop("CODEX_ROUTER_STATE_DIR", None)
        environment.pop("CLAUDE_PLUGIN_DATA", None)
        result = subprocess.run(
            [sys.executable, str(Path(router_hook.__file__)), "--route-gpt-5-6-work"],
            env=environment,
            input=json.dumps(event),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual('{"legacy":true}\n', foreign.read_text(encoding="utf-8"))
        current = plugin_data / "router-state-v2"
        self.assertTrue((current / ".gpt56-router-state.json").is_file())
        self.assertTrue((current / "upgrade--t1.json").is_file())

    def test_opportunistic_age_cleanup_removes_only_old_router_ledgers(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "old", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Hi",
        })
        ledger = Path(self.temp.name) / "old--t1.json"
        old = __import__("time").time() - 15 * 86400
        os.utime(ledger, (old, old))
        foreign = Path(self.temp.name) / "foreign.json"
        foreign.write_text("not router state\n", encoding="utf-8")
        os.utime(foreign, (old, old))
        router_hook._cleanup_state()
        self.assertFalse(ledger.exists())
        self.assertTrue(foreign.exists())

    def test_short_followup_inherits_prior_route(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "inherit", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Review OAuth security for auth bypasses.",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "inherit", "turn_id": "t2",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "yes, do it",
        })
        ledger = json.loads((Path(self.temp.name) / "inherit--t2.json").read_text())
        self.assertEqual("gpt6_sol_high", ledger["decision"]["route"])
        self.assertEqual("t1", ledger["inherited_from_turn"])

    def test_natural_followups_inherit_prior_route(self) -> None:
        followups = ("Sure—continue with the fix.", "Sounds good, do that.", "Yes please, make those changes.")
        for index, followup in enumerate(followups):
            session = f"natural-{index}"
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
                "model": "gpt-6-sol", "model_reasoning_effort": "medium",
                "prompt": "Review OAuth security for auth bypasses.",
            })
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t2",
                "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": followup,
            })
            ledger = json.loads((Path(self.temp.name) / f"{session}--t2.json").read_text())
            self.assertEqual("gpt6_sol_high", ledger["decision"]["route"])
            self.assertEqual("t1", ledger["inherited_from_turn"])

    def test_new_topic_does_not_inherit(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "topic", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Review OAuth security for auth bypasses.",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "topic", "turn_id": "t2",
            "model": "gpt-6-sol", "prompt": "Explain this TypeScript error.",
        })
        ledger = json.loads((Path(self.temp.name) / "topic--t2.json").read_text())
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertIsNone(ledger["inherited_from_turn"])

    def test_fast_toggle_is_reread_on_continuation(self) -> None:
        router_hook.CONFIG_PATH.write_text('service_tier = "priority"\n', encoding="utf-8")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "fast-toggle", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Review OAuth security for auth bypasses.",
        })
        first = json.loads((Path(self.temp.name) / "fast-toggle--t1.json").read_text())
        self.assertTrue(first["decision"]["fast_enabled"])
        self.assertEqual("fast", first["decision"]["service_tier"])
        self.assertEqual("Sol High Fast", first["decision"]["visible_route"])

        router_hook.CONFIG_PATH.write_text("", encoding="utf-8")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "fast-toggle", "turn_id": "t2",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "continue",
        })
        second = json.loads((Path(self.temp.name) / "fast-toggle--t2.json").read_text())
        self.assertEqual("gpt6_sol_high", second["decision"]["route"])
        self.assertFalse(second["decision"]["fast_enabled"])
        self.assertEqual("default", second["decision"]["service_tier"])
        self.assertEqual("Sol High Speed unknown", second["decision"]["visible_route"])
        self.assertTrue(second["decision"]["announce_route"])

    def test_current_route_does_not_announce_service_tier_label_change(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "quiet-tier-change", "turn_id": "t1",
            "model": "gpt-6-luna", "model_reasoning_effort": None, "service_tier": "priority",
            "prompt": "What is 2 + 2?",
        })

        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "quiet-tier-change", "turn_id": "t2",
            "model": "gpt-6-luna", "model_reasoning_effort": None, "service_tier": "default",
            "prompt": "What is 3 + 3?",
        })

        ledger = json.loads((Path(self.temp.name) / "quiet-tier-change--t2.json").read_text())
        self.assertEqual("Luna Effort unknown Standard", ledger["decision"]["visible_route"])
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertFalse(ledger["decision"]["announce_route"])
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("VISIBLE ROUTE:", context)
        self.assertNotIn("Route: Luna Effort unknown Standard", context)
        self.assertIn("ROUTE ANNOUNCEMENT: none for this current/direct route", context)

    def test_current_route_uses_active_model_effort_and_unknown_speed_without_tier_evidence(self) -> None:
        router_hook.CONFIG_PATH.write_text('model_reasoning_effort = "medium"\n', encoding="utf-8")
        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "visible-current", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "Fix a typo.",
        })
        ledger = json.loads((Path(self.temp.name) / "visible-current--t1.json").read_text())
        self.assertEqual("Sol Medium Speed unknown", ledger["decision"]["visible_route"])
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn('"visible_route"', context)
        self.assertNotIn("VISIBLE ROUTE:", context)
        self.assertNotIn("Route: Sol Medium Speed unknown", context)
        self.assertIn("ROUTE ANNOUNCEMENT: none for this current/direct route", context)

    def test_current_route_does_not_invent_missing_model_or_effort(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "visible-unknown", "turn_id": "t1",
            "model_reasoning_effort": None, "prompt": "Hi",
        })
        ledger = json.loads((Path(self.temp.name) / "visible-unknown--t1.json").read_text())
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertEqual("unavailable", ledger["decision"]["effort_evidence"])
        self.assertEqual("Current model unknown Effort unknown Speed unknown", ledger["decision"]["visible_route"])

    def test_unknown_root_effort_cannot_satisfy_a_demanding_route(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "unknown-effort", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": None,
            "prompt": "Design the architecture and migration plan for this multi-service platform.",
        })
        ledger = json.loads((Path(self.temp.name) / "unknown-effort--t1.json").read_text())
        self.assertEqual("unknown", ledger["decision"]["task_profile"]["active_effort"])
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertEqual("unavailable", ledger["decision"]["effort_evidence"])

    def test_non_current_context_requires_factual_public_label(self) -> None:
        router_hook.CONFIG_PATH.write_text('service_tier = "priority"\n', encoding="utf-8")
        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "visible-delegated", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Review OAuth security for auth bypasses.",
        })
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("VISIBLE ROUTE: Sol High Fast", context)
        self.assertIn("Route: Sol High Fast", context)

    def test_hook_service_tier_wins_over_persisted_config(self) -> None:
        router_hook.CONFIG_PATH.write_text('service_tier = "priority"\n', encoding="utf-8")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "tier-input", "turn_id": "t1",
            "model": "gpt-6-sol", "service_tier": "default", "prompt": "Fix a typo.",
        })
        ledger = json.loads((Path(self.temp.name) / "tier-input--t1.json").read_text())
        self.assertFalse(ledger["decision"]["fast_enabled"])
        self.assertEqual("hook", ledger["decision"]["service_tier_source"])

    def test_service_tier_normalization_matrix(self) -> None:
        for tier, expected in (("priority", True), ("fast", True), ("default", False), ("standard", False), ("flex", False)):
            with self.subTest(tier=tier):
                actual = router_hook._service_tier({"service_tier": tier})
                self.assertEqual(expected, actual["fast_enabled"])

    def test_stop_advises_once_when_route_not_executed(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s2", "turn_id": "t2",
            "model": "gpt-6-sol", "prompt": "Review OAuth security for auth bypasses.",
        }
        router_hook.handle(start)
        stop = {"hook_event_name": "Stop", "session_id": "s2", "turn_id": "t2", "stop_hook_active": False}
        first = router_hook.handle(stop)
        self.assertTrue(first["continue"])
        self.assertIn("Router completion gate (advisory)", first["systemMessage"])
        self.assertNotIn("decision", first)
        stop["stop_hook_active"] = True
        second = router_hook.handle(stop)
        self.assertTrue(second["continue"])
        self.assertNotIn("systemMessage", second)

    def test_edit_records_verification_debt_without_stop_feedback(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s3", "turn_id": "t3",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
        }
        router_hook.handle(start)
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "s3", "turn_id": "t3",
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        stop = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "s3", "turn_id": "t3", "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, stop)
        state = json.loads((Path(self.temp.name) / "s3--t3.json").read_text())
        self.assertEqual("FAILED_OPEN", state["status"])
        self.assertEqual("root_owned", state["verification_observability"])

    def test_verification_must_follow_final_mutation(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "generation", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
        }
        router_hook.handle(start)
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "generation", "turn_id": "t1",
            "tool_name": "apply_patch", "tool_input": {"command": "patch one"}, "tool_response": {},
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "generation", "turn_id": "t1",
            "tool_name": "Bash", "tool_input": {"command": "pytest"}, "tool_response": {"exit_code": 0},
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "generation", "turn_id": "t1",
            "tool_name": "apply_patch", "tool_input": {"command": "patch two"}, "tool_response": {},
        })
        stopped = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "generation", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, stopped)
        state = json.loads((Path(self.temp.name) / "generation--t1.json").read_text())
        self.assertEqual("FAILED_OPEN", state["status"])
        self.assertEqual(2, state["mutation_generation"])
        self.assertEqual(1, state["verified_generation"])

    def test_stop_does_not_generate_continuation_for_verification_debt(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "stop-continuation", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "stop-continuation", "turn_id": "t1",
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        stopped = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "stop-continuation", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, stopped)
        final_state = json.loads((Path(self.temp.name) / "stop-continuation--t1.json").read_text())
        self.assertEqual("FAILED_OPEN", final_state["status"])
        self.assertEqual(0, final_state["continuations"])
        duplicate = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "stop-continuation", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, duplicate)
        unchanged = json.loads((Path(self.temp.name) / "stop-continuation--t1.json").read_text())
        self.assertEqual("FAILED_OPEN", unchanged["status"])

    def test_custom_verify_script_completes_without_stop_continuation(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "custom-verify", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "custom-verify", "turn_id": "t1",
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "custom-verify", "turn_id": "t1",
            "tool_name": "Bash", "tool_input": {"command": "pnpm verify:fast"},
            "tool_response": {"exit_code": 0},
        })
        completed = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "custom-verify", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, completed)
        state = json.loads((Path(self.temp.name) / "custom-verify--t1.json").read_text())
        self.assertEqual("COMPLETE", state["status"])
        self.assertEqual(state["mutation_generation"], state["verified_generation"])

    def test_no_mutation_conversation_completes_without_feedback(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "conversation", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "How are things now?",
        })
        completed = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "conversation", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, completed)
        state = json.loads((Path(self.temp.name) / "conversation--t1.json").read_text())
        self.assertEqual(0, state["mutation_generation"])
        self.assertEqual("COMPLETE", state["status"])

    def test_terminal_router_feedback_is_not_reclassified_or_reinjected(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "terminal-feedback", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "How are things now?",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": "terminal-feedback", "turn_id": "t1",
            "stop_hook_active": False,
        })
        feedback = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "terminal-feedback", "turn_id": "t2",
            "model": "gpt-6-sol",
            "prompt": "Router completion gate: run the required verification gate after the final mutation: answer check.",
        })
        self.assertIsNone(feedback)
        self.assertFalse((Path(self.temp.name) / "terminal-feedback--t2.json").exists())
        duplicate = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "terminal-feedback", "turn_id": "t2",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, duplicate)

    def test_xml_wrapped_terminal_feedback_is_not_reclassified_or_reinjected(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "wrapped-feedback", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "How are things now?",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": "wrapped-feedback", "turn_id": "t1",
            "stop_hook_active": False,
        })
        feedback = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "wrapped-feedback", "turn_id": "t2",
            "model": "gpt-6-sol",
            "prompt": (
                '<hook_prompt hook_run_id="stop:4:/retired/hooks/hooks.json">'
                "Router completion gate: run the required verification gate after the final mutation: answer check."
                "</hook_prompt>"
            ),
        })
        self.assertIsNone(feedback)
        self.assertFalse((Path(self.temp.name) / "wrapped-feedback--t2.json").exists())

    def test_unknown_verification_result_does_not_pass(self) -> None:
        self.assertFalse(router_hook._response_succeeded({}))
        self.assertFalse(router_hook._response_succeeded({"output": "looks good"}))
        self.assertFalse(router_hook._response_succeeded("exit_code=0"))
        self.assertTrue(router_hook._response_succeeded({"exit_code": 0}))

    def test_nested_exec_json_output_proves_success(self) -> None:
        response = [
            {"type": "input_text", "text": "Script completed\nOutput:\n"},
            {"type": "input_text", "text": json.dumps({"exit_code": 0, "output": "164 tests passed"})},
        ]
        self.assertTrue(router_hook._response_succeeded(response))
        failed = [{"type": "input_text", "text": json.dumps({"exit_code": 1, "output": "failed"})}]
        self.assertFalse(router_hook._response_succeeded(failed))

    def test_flattened_exec_wrapper_proves_only_structured_success(self) -> None:
        completed = (
            "Script completed\nWall time 0.2 seconds\nOutput:\n"
            + json.dumps({"chunk_id": "abc", "exit_code": 0, "output": "OK"})
        )
        failed = (
            "Script completed\nWall time 0.2 seconds\nOutput:\n"
            + json.dumps({"chunk_id": "abc", "exit_code": 1, "output": "failed"})
        )
        self.assertTrue(router_hook._response_succeeded(completed))
        self.assertFalse(router_hook._response_succeeded(failed))
        self.assertFalse(router_hook._response_succeeded("Script completed\nOutput:\nnot JSON"))

    def test_response_status_handles_non_scalar_status_with_bounded_semantics(self) -> None:
        self.assertTrue(router_hook._response_status({"status": {"exit_code": 0}}))
        self.assertIsNone(router_hook._response_status({"status": {"label": "success"}}))
        self.assertIsNone(router_hook._response_status({"status": ["success"]}))
        self.assertIsNone(router_hook._response_status({"note": '{"status":"success"}'}))
        self.assertIsNone(router_hook._response_status({"note": {"status": "success"}}))
        self.assertIsNone(router_hook._response_status({"note": {"exit_code": 0}}))
        self.assertTrue(router_hook._response_status({"result": {"status": "success"}}))
        self.assertIsNone(router_hook._response_status({"status": 0}))
        self.assertIsNone(router_hook._response_status({
            "output": "x" * (router_hook.RESPONSE_STATUS_MAX_SCALAR_BYTES + 1),
        }))

        cyclic: dict[str, object] = {}
        cyclic["result"] = cyclic
        self.assertIsNone(router_hook._response_status(cyclic))

        pathological: dict[str, object] = {}
        cursor = pathological
        for _ in range(64):
            child: dict[str, object] = {}
            cursor["status"] = child
            cursor = child
        cursor["exit_code"] = 0
        self.assertIsNone(router_hook._response_status(pathological))

        self.assertIsNone(router_hook._response_status({
            "status": [{"detail": index} for index in range(5000)],
        }))

    def test_verification_command_allowlist_rejects_ceremonial_checks(self) -> None:
        self.assertFalse(router_hook._is_verification("echo check"))
        self.assertFalse(router_hook._is_verification("printf build"))
        self.assertTrue(router_hook._is_verification("python3 -m pytest -q"))
        self.assertTrue(router_hook._is_verification("npm run build"))
        self.assertTrue(router_hook._is_verification("pnpm verify:fast"))
        self.assertTrue(router_hook._is_verification("npm run check:release"))
        self.assertTrue(router_hook._is_verification("cargo check"))
        self.assertTrue(router_hook._is_verification("PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q"))
        self.assertTrue(router_hook._is_verification("set -e\\npython3 -m unittest -q"))
        self.assertTrue(router_hook._is_verification(
            "python3 outputs/validate-router-smoke.py outputs/router-smoke.jsonl"
        ))
        self.assertTrue(router_hook._is_verification("python3 scripts/verify_schema.py fixture.json"))
        self.assertTrue(router_hook._is_verification("uv run python scripts/check-output.py fixture.json"))
        self.assertFalse(router_hook._is_verification("python3 scripts/deploy.py"))
        self.assertFalse(router_hook._is_verification("python3 scripts/generate-fixtures.py"))
        self.assertTrue(router_hook._is_verification("git diff --check"))
        self.assertTrue(router_hook._is_verification("git -C /workspace diff --check"))
        self.assertFalse(router_hook._is_verification("git diff"))
        self.assertFalse(router_hook._is_verification("echo git diff --check"))
        self.assertFalse(router_hook._is_verification("python3 -c 'print(\"git diff --check\")'"))
        self.assertFalse(router_hook._is_verification("git diff --check || true"))
        self.assertFalse(router_hook._is_verification("git diff --check; true"))
        self.assertFalse(router_hook._is_verification("git diff --check | cat"))
        self.assertTrue(router_hook._is_verification("rg -n Python README.md && git diff --check && git status --short"))

    def test_large_verification_evidence_reconciles_at_early_middle_and_late_positions(self) -> None:
        for position in ("early", "middle", "late"):
            with self.subTest(position=position):
                session = f"large-verification-{position}"
                turn = "t1"
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
                    "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
                })
                router_hook.handle({
                    "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
                    "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
                    "tool_input": {"command": "patch"}, "tool_response": {},
                })
                transcript = Path(self.temp.name) / f"{session}.jsonl"
                self._write_large_jsonl(
                    transcript,
                    self._transcript_mutation_records(turn) + self._transcript_verification_records(turn),
                    position=position,
                )

                router_hook.handle({
                    "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
                    "stop_hook_active": False, "transcript_path": str(transcript),
                })

                ledger = self._ledger(session, turn)
                self.assertGreater(transcript.stat().st_size, 8 * 1024 * 1024)
                self.assertEqual("COMPLETE", ledger["status"])
                self.assertEqual("FOUND", ledger["transcript_reconciliation"]["verification"]["status"])
                self.assertEqual(ledger["mutation_generation"], ledger["verified_generation"])

    def test_large_verification_failure_is_found_without_passing_the_gate(self) -> None:
        session = "large-verification-failed"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        self._write_large_jsonl(transcript, self._transcript_verification_records(turn, exit_code=1))

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("FOUND", ledger["transcript_reconciliation"]["verification"]["status"])
        self.assertEqual(-1, ledger["verified_generation"])
        self.assertEqual(1, ledger["verification_failures"])

    def test_not_found_is_distinct_from_malformed_and_incomplete_reconciliation(self) -> None:
        outcomes = {}
        for label in ("not-found", "malformed", "incomplete"):
            session = f"reconciliation-{label}"
            turn = "t1"
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
                "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
            })
            router_hook.handle({
                "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
                "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
            })
            transcript = Path(self.temp.name) / f"{session}.jsonl"
            if label == "not-found":
                self._write_large_jsonl(transcript, [])
            elif label == "malformed":
                transcript.write_bytes(b'{"payload":\n')
            else:
                records = []
                metadata = {"turn_id": turn}
                for index in range(257):
                    records.append({"payload": {
                        "type": "custom_tool_call", "name": "exec", "call_id": f"verify-{index}",
                        "input": (
                            'const r = await tools.exec_command({cmd:"python3 -m unittest -q"}); '
                            'text(JSON.stringify({exit_code:r.exit_code,output:r.output}));'
                        ),
                        "internal_chat_message_metadata_passthrough": metadata,
                    }})
                transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
            router_hook.handle({
                "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
                "stop_hook_active": False, "transcript_path": str(transcript),
            })
            outcomes[label] = self._ledger(session, turn)["transcript_reconciliation"]["verification"]["status"]

        self.assertEqual("NOT_FOUND", outcomes["not-found"])
        self.assertEqual("MALFORMED", outcomes["malformed"])
        self.assertEqual("INCOMPLETE", outcomes["incomplete"])
        self.assertEqual(3, len(set(outcomes.values())))

    def test_malformed_candidate_result_is_incomplete_not_absent(self) -> None:
        session = "malformed-verification-result"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        records = self._transcript_verification_records(turn)
        records[1]["payload"]["output"] = "{not-valid-json"
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("INCOMPLETE", ledger["transcript_reconciliation"]["verification"]["status"])
        self.assertEqual(-1, ledger["verified_generation"])

    def test_appended_verification_result_is_found_idempotently_after_not_found(self) -> None:
        session = "appended-verification-result"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        records = self._transcript_mutation_records(turn) + self._transcript_verification_records(
            turn, include_output=False,
        )
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        self.assertEqual(
            "NOT_FOUND", self._ledger(session, turn)["transcript_reconciliation"]["verification"]["status"],
        )

        output = self._transcript_verification_records(turn)[1]
        with transcript.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(output) + "\n")
        for _ in range(2):
            router_hook.handle({
                "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
                "stop_hook_active": False, "late_child_recheck": True,
                "transcript_path": str(transcript),
            })

        ledger = self._ledger(session, turn)
        self.assertEqual("FOUND", ledger["transcript_reconciliation"]["verification"]["status"])
        self.assertEqual(1, ledger["verification_successes"])
        self.assertEqual(["verify-large"], ledger["reconciled_verification_call_ids"])

    def test_oversized_single_line_is_rejected_during_bounded_io(self) -> None:
        transcript = Path(self.temp.name) / "single-oversized-line.jsonl"
        with transcript.open("wb") as stream:
            for _ in range(64):
                stream.write(b"x" * (1024 * 1024))
        tracemalloc.start()
        outcome = router_hook._scan_jsonl_transcript(transcript, lambda _record: False)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.assertEqual("LINE_TOO_LARGE", outcome["status"])
        self.assertEqual(0, outcome["records_scanned"])
        self.assertLess(peak, 48 * 1024 * 1024)

    def test_complete_json_line_is_parsed_before_small_authoritative_fields_are_extracted(self) -> None:
        transcript = Path(self.temp.name) / "complete-large-record.jsonl"
        record = {
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "large-output",
                "output": {"padding": "x" * (512 * 1024), "exit_code": 0},
            },
        }
        transcript.write_text(json.dumps(record) + "\n", encoding="utf-8")
        observed = []

        outcome = router_hook._scan_jsonl_transcript(
            transcript,
            lambda item: observed.append(router_hook._response_status(item["payload"]["output"])) or True,
        )

        self.assertEqual("FOUND", outcome["status"])
        self.assertEqual([True], observed)
        self.assertGreater(transcript.stat().st_size, router_hook.TRANSCRIPT_MAX_RETAINED_TEXT_BYTES)

    def test_unsafe_scan_outcomes_do_not_become_not_found_or_partial_proof(self) -> None:
        session = "unsafe-scan-outcomes"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text('{}\n', encoding="utf-8")
        for status in ("INCOMPLETE", "MALFORMED", "LINE_TOO_LARGE", "IO_ERROR"):
            with self.subTest(status=status):
                state = self._ledger(session, turn)
                outcome = {"status": status, "records_scanned": 1, "bytes_scanned": 10}
                with mock.patch.object(router_hook, "_scan_jsonl_transcript", return_value=outcome):
                    router_hook._reconcile_root_transcript(
                        {"transcript_path": str(transcript)}, state, subagents=False, verification=True,
                    )
                self.assertEqual(status, state["transcript_reconciliation"]["verification"]["status"])
                self.assertNotEqual("NOT_FOUND", state["transcript_reconciliation"]["verification"]["status"])
                self.assertEqual(-1, state["verified_generation"])
                self.assertEqual([], state.get("reconciled_verification_call_ids", []))

    def test_streaming_memory_does_not_scale_with_total_transcript_size(self) -> None:
        peaks = []
        for size_mib in (16, 32, 64):
            transcript = Path(self.temp.name) / f"memory-{size_mib}.jsonl"
            self._write_large_jsonl(transcript, [], minimum_size=size_mib * 1024 * 1024)
            tracemalloc.start()
            outcome = router_hook._scan_jsonl_transcript(transcript, lambda _record: False)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertEqual("NOT_FOUND", outcome["status"])
            peaks.append(peak)

        self.assertLess(max(peaks), 16 * 1024 * 1024)
        self.assertLess(max(peaks) - min(peaks), 4 * 1024 * 1024)

    def test_descriptor_identity_mismatch_is_path_rejected(self) -> None:
        transcript = Path(self.temp.name) / "descriptor-target.jsonl"
        other = Path(self.temp.name) / "descriptor-other.jsonl"
        transcript.write_text('{}\n', encoding="utf-8")
        other.write_text('{}\n', encoding="utf-8")
        with mock.patch.object(router_hook.os, "lstat", return_value=other.stat()):
            outcome = router_hook._scan_jsonl_transcript(transcript, lambda _record: False)
        self.assertEqual("PATH_REJECTED", outcome["status"])

    def test_hard_link_descriptor_is_path_rejected(self) -> None:
        transcript = Path(self.temp.name) / "descriptor-original.jsonl"
        linked = Path(self.temp.name) / "descriptor-linked.jsonl"
        transcript.write_text('{}\n', encoding="utf-8")
        os.link(transcript, linked)

        outcome = router_hook._scan_jsonl_transcript(linked, lambda _record: False)

        self.assertEqual("PATH_REJECTED", outcome["status"])

    def test_open_error_is_io_error_not_not_found(self) -> None:
        transcript = Path(self.temp.name) / "descriptor-io-error.jsonl"
        transcript.write_text('{}\n', encoding="utf-8")
        with mock.patch.object(router_hook.os, "open", side_effect=PermissionError("denied")):
            outcome = router_hook._scan_jsonl_transcript(transcript, lambda _record: False)

        self.assertEqual("IO_ERROR", outcome["status"])

    def test_malformed_after_valid_verification_does_not_partially_establish_proof(self) -> None:
        session = "malformed-after-valid"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        records = self._transcript_verification_records(turn)
        transcript.write_bytes(
            b"\n".join(json.dumps(record).encode("utf-8") for record in records) + b"\n{malformed\n"
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("MALFORMED", ledger["transcript_reconciliation"]["verification"]["status"])
        self.assertEqual(-1, ledger["verified_generation"])
        self.assertEqual([], ledger.get("reconciled_verification_call_ids", []))

    def test_duplicate_verification_result_is_applied_once(self) -> None:
        session = "duplicate-verification-result"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        records = self._transcript_mutation_records(turn) + self._transcript_verification_records(turn)
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text(
            "\n".join(json.dumps(record) for record in [*records, records[-1]]) + "\n",
            encoding="utf-8",
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("FOUND", ledger["transcript_reconciliation"]["verification"]["status"])
        self.assertEqual(1, ledger["verification_successes"])
        self.assertEqual(["verify-large"], ledger["reconciled_verification_call_ids"])

    def test_large_spawn_and_completion_evidence_reconciles(self) -> None:
        session = "large-spawn-completion"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "Research two independent APIs in parallel and recommend an architecture.",
        })
        call_id = "call-large"
        agent_id = "00000000-0000-7000-8000-000000000012"
        agent_path = "/root/large-worker"
        metadata = {"turn_id": turn}
        records = [
            {"payload": {
                "type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                "call_id": call_id,
                "arguments": json.dumps({
                    "model": "gpt-6-sol", "reasoning_effort": "medium",
                    "fork_turns": "none", "task_name": "large-worker",
                    "message": "Self-contained bounded task with acceptance checks.",
                }),
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "sub_agent_activity", "event_id": call_id, "kind": "started",
                "agent_thread_id": agent_id, "agent_path": agent_path,
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "agent_message", "author": agent_path,
                "content": [{"type": "input_text", "text": (
                    "Evidence: bounded result\nVerification: objective check passed\nUncertainty: none"
                )}],
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        self._write_large_jsonl(transcript, records, position="late")
        self._write_child_transcript(session, agent_id, "gpt-6-sol", "medium")

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertGreater(transcript.stat().st_size, 8 * 1024 * 1024)
        self.assertEqual("FOUND", ledger["transcript_reconciliation"]["subagents"]["status"])
        self.assertEqual(["gpt6_sol_balanced"], ledger["subagents_completed"])
        self.assertTrue(ledger["agent_attestations"][agent_id]["matched"])

    def test_large_child_transcript_attests_and_writes_receipt(self) -> None:
        session = "large-child-receipt"
        turn = "t1"
        runtime = {
            "runtime_version": "codex-1.2.3", "runtime_build": "desktop-456", "host_type": "Desktop",
        }
        router_hook.handle({
            **runtime,
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "Add pagination to this endpoint and include targeted tests.",
        })
        parent = Path(self.temp.name) / f"{session}.jsonl"
        parent.write_text("", encoding="utf-8")
        agent_id = "00000000-0000-7000-8000-000000000013"
        router_hook.handle({
            **runtime,
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": turn,
            "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
            "transcript_path": str(parent),
        })
        child = self._write_child_transcript(session, agent_id, "gpt-6-sol", "medium")
        self._observe_valid_spawn(session, turn, agent_id, "gpt56_terra_worker")
        self._write_large_jsonl(child, [json.loads(line) for line in child.read_text().splitlines()], position="middle")

        router_hook.handle({
            **runtime,
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child-turn",
            "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: trace\nVerification: regression test passed\nUncertainty: none",
            "transcript_path": str(parent),
        })
        router_hook.handle({
            **runtime,
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(parent),
        })

        ledger = self._ledger(session, turn)
        attestation = ledger["agent_attestations"][agent_id]
        self.assertGreater(child.stat().st_size, 8 * 1024 * 1024)
        self.assertEqual("FOUND", attestation["reconciliation_status"])
        self.assertTrue(attestation["matched"])
        receipt = _capability_receipt("gpt-6-sol")
        self.assertEqual("gpt-6-sol", receipt["observed_child_model"])

    def test_transcript_custom_validator_settles_the_latest_mutation(self) -> None:
        session = "transcript-custom-validator"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Create a fixture.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        metadata = {"turn_id": turn}
        transcript_dir = router_hook.CODEX_HOME / "sessions" / "2026" / "07" / "14"
        transcript_dir.mkdir(parents=True)
        transcript = transcript_dir / f"rollout-{session}.jsonl"
        records = self._transcript_mutation_records(turn) + [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "verify-custom",
                "input": (
                    'const r = await tools.exec_command({cmd:'
                    '"python3 outputs/validate-router-smoke.py outputs/router-smoke.jsonl"}); '
                    'text(JSON.stringify({exit_code:r.exit_code,output:r.output}));'
                ),
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "verify-custom",
                "output": [{"type": "input_text", "text": json.dumps({"exit_code": 0, "output": "PASS"})}],
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False,
        })
        state = json.loads((Path(self.temp.name) / f"{session}--{turn}.json").read_text())
        self.assertEqual({"continue": True}, result)
        self.assertEqual("COMPLETE", state["status"])
        self.assertEqual(state["mutation_generation"], state["verified_generation"])
        self.assertEqual("transcript_exit_status", state["verification_observability"])

    def test_transcript_success_without_mutation_generation_proof_stays_incomplete(self) -> None:
        session = "verification-generation-unproven"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text(
            "\n".join(json.dumps(record) for record in self._transcript_verification_records(turn)) + "\n",
            encoding="utf-8",
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual(-1, ledger["verified_generation"])
        self.assertEqual("INCOMPLETE", ledger["transcript_reconciliation"]["verification"]["status"])

    def test_transcript_success_does_not_infer_current_call_id_from_call_count(self) -> None:
        session = "verification-generation-current-id-missing"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        records = self._transcript_mutation_records(turn) + self._transcript_verification_records(turn)
        transcript.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual(-1, ledger["verified_generation"])
        self.assertEqual("INCOMPLETE", ledger["transcript_reconciliation"]["verification"]["status"])

    def test_legacy_generation_replay_requires_an_exact_turn_complete_bijection(self) -> None:
        session = "verification-generation-legacy-bijection"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        state = self._ledger(session, turn)
        state.pop("mutation_generation_provenance")
        state.pop("mutation_generation_provenance_complete")
        context = router_hook._verification_scan_context()
        for record in self._transcript_mutation_records(turn) + self._transcript_verification_records(turn):
            router_hook._consume_verification_record(record, state, context)

        outcome = router_hook._apply_verification_scan(state, context)

        self.assertEqual("FOUND", outcome)
        self.assertEqual(state["mutation_generation"], state["verified_generation"])

    def test_transcript_success_requires_exact_mutation_call_id_provenance(self) -> None:
        session = "verification-generation-call-id"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        metadata = {"turn_id": turn}
        mutation_records = [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "different-mutation-call",
                "input": "const r = await tools.apply_patch(`patch`); text(r);",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "different-mutation-call", "output": "Done",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text(
            "\n".join(json.dumps(record) for record in (
                mutation_records + self._transcript_verification_records(turn)
            )) + "\n",
            encoding="utf-8",
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual(-1, ledger["verified_generation"])
        self.assertEqual("INCOMPLETE", ledger["transcript_reconciliation"]["verification"]["status"])

    def test_transcript_success_settles_exact_mutation_call_id_generation(self) -> None:
        session = "verification-generation-bound"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        metadata = {"turn_id": turn}
        mutation_records = [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "mutation-hook-1",
                "input": "const r = await tools.apply_patch(`patch`); text(r);",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "mutation-hook-1", "output": "Done",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text(
            "\n".join(json.dumps(record) for record in (
                mutation_records + self._transcript_verification_records(turn)
            )) + "\n",
            encoding="utf-8",
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual(1, ledger["verified_generation"])
        self.assertEqual("FOUND", ledger["transcript_reconciliation"]["verification"]["status"])

    def test_transcript_success_rejects_unmapped_extra_mutation_call(self) -> None:
        session = "verification-generation-extra-call"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        records = (
            self._transcript_mutation_records(turn)
            + self._transcript_mutation_records(turn, "mutation-unmapped")
            + self._transcript_verification_records(turn)
        )
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual(-1, ledger["verified_generation"])
        self.assertEqual("INCOMPLETE", ledger["transcript_reconciliation"]["verification"]["status"])

    def test_transcript_success_before_later_bound_mutation_remains_debt(self) -> None:
        session = "verification-generation-later-mutation"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        for generation in (1, 2):
            router_hook.handle({
                "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
                "tool_name": "apply_patch", "tool_use_id": f"mutation-hook-{generation}",
                "tool_input": {"command": f"patch {generation}"}, "tool_response": {},
            })
        metadata = {"turn_id": turn}
        first_mutation = [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "mutation-hook-1",
                "input": "const r = await tools.apply_patch(`patch 1`); text(r);",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "mutation-hook-1", "output": "Done",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        second_mutation = [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "mutation-hook-2",
                "input": "const r = await tools.apply_patch(`patch 2`); text(r);",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "mutation-hook-2", "output": "Done",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        transcript = Path(self.temp.name) / f"{session}.jsonl"
        transcript.write_text(
            "\n".join(json.dumps(record) for record in (
                first_mutation + self._transcript_verification_records(turn) + second_mutation
            )) + "\n",
            encoding="utf-8",
        )

        router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })

        ledger = self._ledger(session, turn)
        self.assertEqual("FAILED_OPEN", ledger["status"])
        self.assertEqual(-1, ledger["verified_generation"])

    def test_nested_exec_verification_settles_the_latest_mutation(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "nested-verify", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "How are things now?",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "nested-verify", "turn_id": "t1",
            "tool_name": "exec",
            "tool_input": {"command": "const r = await tools.apply_patch(`*** patch ***`); text(r)"},
            "tool_response": [{"type": "input_text", "text": "Done"}],
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "nested-verify", "turn_id": "t1",
            "tool_name": "exec",
            "tool_input": (
                "const r = await tools.exec_command({"
                "cmd: \"env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_router\""
                "}); text(r)"
            ),
            "tool_response": [
                {"type": "input_text", "text": "Script completed\nOutput:\n"},
                {"type": "input_text", "text": json.dumps({"exit_code": 0, "output": "OK"})},
            ],
        })
        completed = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "nested-verify", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, completed)
        state = json.loads((Path(self.temp.name) / "nested-verify--t1.json").read_text())
        self.assertEqual("COMPLETE", state["status"])
        self.assertEqual(1, state["mutation_generation"])
        self.assertEqual(1, state["verified_generation"])

    def test_stop_recovers_machine_readable_verification_from_transcript(self) -> None:
        session = "transcript-verify"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "patch-call",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        metadata = {"turn_id": turn}
        transcript = Path(self.temp.name) / "verification-parent.jsonl"
        records = [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "patch-call",
                "input": "const r = await tools.apply_patch(`patch`); text(r);",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "patch-call", "output": "Done",
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "verify-call",
                "input": (
                    'const r = await tools.exec_command({cmd:"python3 -m unittest -q"}); '
                    'text(JSON.stringify({exit_code:r.exit_code,output:r.output}));'
                ),
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "verify-call",
                "output": [
                    {"type": "input_text", "text": "Script completed\nOutput:\n"},
                    {"type": "input_text", "text": json.dumps({"exit_code": 0, "output": "OK"})},
                ],
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        state = json.loads((Path(self.temp.name) / f"{session}--{turn}.json").read_text())
        self.assertEqual({"continue": True}, result)
        self.assertEqual("COMPLETE", state["status"])
        self.assertEqual(1, state["verified_generation"])
        self.assertTrue(state["reconciled_verification_from_transcript"])
        self.assertEqual("transcript_exit_status", state["verification_observability"])

    def test_transcript_verification_python_version_comparison_is_not_a_mutation(self) -> None:
        session = "transcript-verify-version-comparison"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {"command": "patch"}, "tool_response": {},
        })
        metadata = {"turn_id": turn}
        command = (
            "const r = await tools.exec_command({cmd:`set -e\n"
            "python3 -c 'import sys; assert sys.version_info >= (3, 10)'\n"
            "python3 -m unittest -q`}); "
            "text(JSON.stringify({exit_code:r.exit_code,output:r.output}));"
        )
        self.assertFalse(router_hook._is_mutation("exec", command))
        self.assertTrue(router_hook._is_verification(command))
        transcript = Path(self.temp.name) / "verification-version-comparison.jsonl"
        records = self._transcript_mutation_records(turn) + [
            {"payload": {
                "type": "custom_tool_call", "name": "exec", "call_id": "verify-version",
                "input": command, "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "custom_tool_call_output", "call_id": "verify-version",
                "output": [{"type": "input_text", "text": json.dumps({"exit_code": 0, "output": "OK"})}],
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ]
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        state = json.loads((Path(self.temp.name) / f"{session}--{turn}.json").read_text())
        self.assertEqual({"continue": True}, result)
        self.assertEqual("COMPLETE", state["status"])
        self.assertEqual(state["mutation_generation"], state["verified_generation"])
        self.assertEqual("transcript_exit_status", state["verification_observability"])

    def test_read_only_route_silently_records_real_gate_if_it_later_mutates(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "raised-gate", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "How are things now?",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "raised-gate", "turn_id": "t1",
            "tool_name": "exec", "tool_input": "tools.apply_patch(`patch`)", "tool_response": {},
        })
        stopped = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "raised-gate", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, stopped)
        state = json.loads((Path(self.temp.name) / "raised-gate--t1.json").read_text())
        self.assertIn("targeted tests or build", state["failed_open_problems"][0])
        self.assertNotIn("answer check", state["failed_open_problems"][0])

    def test_unobservable_unified_exec_verification_fails_open_without_feedback(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "unobservable", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "unobservable", "turn_id": "t1",
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "unobservable", "turn_id": "t1",
            "tool_name": "exec", "tool_input": "tools.exec_command({cmd: 'python3 -m unittest -q'})",
            "tool_response": {},
        })
        stopped = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "unobservable", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, stopped)
        state = json.loads((Path(self.temp.name) / "unobservable--t1.json").read_text())
        self.assertEqual("FAILED_OPEN", state["status"])
        self.assertEqual("unavailable", state["verification_observability"])
        self.assertEqual(0, state["continuations"])
        self.assertIn("run the required verification gate", state["failed_open_problems"][0])

    def test_observable_failed_verification_is_root_owned_without_feedback(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "observable-failure", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "observable-failure", "turn_id": "t1",
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "observable-failure", "turn_id": "t1",
            "tool_name": "Bash", "tool_input": {"command": "python3 -m unittest -q"},
            "tool_response": {"exit_code": 1},
        })
        stopped = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "observable-failure", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, stopped)
        state = json.loads((Path(self.temp.name) / "observable-failure--t1.json").read_text())
        self.assertEqual("FAILED_OPEN", state["status"])
        self.assertEqual("root_owned", state["verification_observability"])

    def test_ledger_identity_migrates_across_plugin_cache_versions(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "plugin-upgrade", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "How are things now?",
        })
        ledger = Path(self.temp.name) / "plugin-upgrade--t1.json"
        state = json.loads(ledger.read_text())
        state["plugin_version"] = "0.1.0+codex.retired"
        ledger.write_text(json.dumps(state), encoding="utf-8")
        completed = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "plugin-upgrade", "turn_id": "t1",
            "stop_hook_active": False,
        })
        self.assertEqual({"continue": True}, completed)
        migrated = json.loads(ledger.read_text())
        self.assertEqual(router_hook.PLUGIN_VERSION, migrated["plugin_version"])
        self.assertEqual("0.1.0+codex.retired", migrated["migrated_from_plugin_version"])

    def test_structured_return_requires_nonempty_sections(self) -> None:
        self.assertFalse(router_hook._structured_return("Evidence:\nVerification: ok\nUncertainty: none"))
        self.assertFalse(router_hook._structured_return("Evidence: x\nVerification:\nUncertainty: none"))
        self.assertTrue(router_hook._structured_return("Evidence: x\nVerification: test passed\nUncertainty: none"))
        self.assertTrue(
            router_hook._structured_return(
                "Evidence:\n\nThe bounded result is supported.\n\n"
                "Verification:\n\nNegative checks passed.\n\n"
                "Uncertainty:\n\nKey rotation is unspecified."
            )
        )

    def test_parallel_plan_requires_all_workers(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "coverage", "turn_id": "t1",
            "model": "gpt-6-luna", "prompt": "In parallel, extract versions from three independent manifests.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "coverage", "turn_id": "t1",
            "agent_type": "gpt56_terra_worker", "agent_id": "one",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "coverage", "turn_id": "t1",
            "agent_type": "gpt56_terra_worker", "agent_id": "one", "stop_hook_active": True,
            "last_assistant_message": "Evidence: one\nVerification: checked\nUncertainty: none",
        })
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "coverage", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertTrue(result["continue"])
        self.assertNotIn("decision", result)
        self.assertIn("complete 2 required", result["systemMessage"])

    def test_mechanical_work_stays_on_the_luna_root(self) -> None:
        decision = router_hook.classify_prompt(
            "Convert all 500 images to WebP and compare checksums.", "gpt-6-luna", "low",
            enforce_active_root=True,
        )
        self.assertEqual("current", decision["route"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])

    def test_satisfied_sol_root_does_not_spawn_redundant_security_worker(self) -> None:
        decision = router_hook.classify_prompt(
            "Audit production authentication for privilege escalation.",
            "gpt-6-sol", "high", enforce_active_root=True,
        )

        self.assertEqual("current", decision["route"])
        self.assertEqual("direct", decision["orchestration"]["mode"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])

    def test_evidence_then_owner_plan_completes_with_all_attestations(self) -> None:
        result, ledger = self._complete_transcript_plan(
            "evidence-owner", "Research three independent APIs in parallel and recommend an architecture.",
            ["gpt56_terra_worker", "gpt56_terra_worker", "gpt56_sol_deep"],
        )
        self.assertTrue(result["continue"])
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual("evidence_then_owner", ledger["decision"]["orchestration"]["mode"])
        self.assertEqual("gpt6_sol_high", ledger["decision"]["orchestration"]["synthesis_owner"])

    def test_critical_evidence_plan_completes_with_all_attestations(self) -> None:
        result, ledger = self._complete_transcript_plan(
            "critical-evidence", "Delete the production database.",
            ["gpt56_terra_worker", "gpt56_terra_worker", "gpt56_sol_deep"],
        )
        self.assertTrue(result["continue"])
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual("evidence_then_owner", ledger["decision"]["orchestration"]["mode"])

    def test_public_label_shows_the_complete_multi_agent_plan(self) -> None:
        fast_batch = router_hook.classify_prompt(
            "Convert 500 images to WebP and compare checksums.", "gpt-6-luna", "low", enforce_active_root=True
        )
        fast_batch.update({"fast_enabled": True})
        self.assertEqual("Luna Low Fast", router_hook._visible_route(fast_batch, {"model": "gpt-6-luna"}))

        evidence_owner = router_hook.classify_prompt(
            "Research three independent APIs in parallel and recommend an architecture.", "gpt-6-sol", "medium",
            enforce_active_root=True,
        )
        evidence_owner.update({"fast_enabled": False})
        self.assertEqual(
            "Sol Medium Standard ×2 → Sol High Standard",
            router_hook._visible_route(evidence_owner, {"model": "gpt-6-sol"}),
        )

        critical_evidence = router_hook.classify_prompt(
            "Delete the production database.", "gpt-6-sol", "medium", enforce_active_root=True,
        )
        critical_evidence.update({"fast_enabled": True})
        self.assertEqual(
            "Sol Medium Fast ×2 → Sol High Fast",
            router_hook._visible_route(critical_evidence, {"model": "gpt-6-sol"}),
        )

    def test_uncertain_product_invokes_a_bounded_routing_council(self) -> None:
        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "council-profile", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Run an independent routing council: build me an app for creators; I am not sure what architecture to use.",
        })
        ledger = json.loads((Path(self.temp.name) / "council-profile--t1.json").read_text())
        plan = ledger["decision"]["orchestration"]
        self.assertEqual("routing_council", plan["mode"])
        self.assertEqual("advisory", plan["phase"])
        self.assertEqual(3, plan["max_workers"])
        self.assertEqual({"gpt6_sol_balanced": 1, "gpt6_sol_high": 1}, plan["required_agents"])
        self.assertEqual("Sol Medium Speed unknown + Sol High Speed unknown", ledger["decision"]["visible_route"])
        self.assertIn("advisors are read-only", output["hookSpecificOutput"]["additionalContext"])

        simple_uncertainty = router_hook.classify_prompt(
            "I am not sure what OAuth means; explain it in one sentence.", "gpt-6-sol", "medium"
        )
        self.assertEqual("current", simple_uncertainty["route"])
        self.assertEqual("direct", simple_uncertainty["orchestration"]["mode"])

    def test_routing_council_never_triggers_for_routine_or_low_stakes_work(self) -> None:
        for prompt in (
            "Build a simple todo app.",
            "Design a button for this app.",
            "Whatever you think is best, rename this variable.",
        ):
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(
                    prompt, "gpt-6-sol", "medium", enforce_active_root=True,
                )
                self.assertNotEqual("routing_council", decision["orchestration"]["mode"])
                self.assertEqual("current", decision["route"])

    def test_surface_and_negated_security_words_do_not_force_expensive_routes(self) -> None:
        for prompt in (
            "Fix this checkout CSS typo.",
            "Add a pricing page.",
            "No security changes: update the button label.",
        ):
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(
                    prompt, "gpt-6-sol", "medium", enforce_active_root=True,
                )
                self.assertEqual("current", decision["route"])
                self.assertNotIn("security", decision["task_profile"]["signals"])

    def test_council_can_recommend_every_non_frontier_cost_route(self) -> None:
        decision = router_hook.classify_prompt(
            "Run a routing council: I am not sure how to implement this ordinary endpoint with focused tests.",
            "gpt-6-sol",
            "medium",
        )
        self.assertEqual(
            set(router_hook.ROUTES) - set(router_hook.ASTRA_ROLES),
            set(decision["orchestration"]["candidate_routes"]),
        )

    def test_missing_or_drifted_legacy_agents_do_not_affect_supported_routing(self) -> None:
        (router_hook.CONFIG_PATH.parent / "agents" / "gpt56_sol_deep.toml").unlink()
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "advisory", "turn_id": "t1",
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "Review OAuth token handling for authorization bypasses.",
        })
        ledger = json.loads((Path(self.temp.name) / "advisory--t1.json").read_text())
        self.assertEqual("gpt6_sol_high", ledger["decision"]["route"])
        self.assertEqual("single_delegate", ledger["decision"]["orchestration"]["mode"])
        self.assertNotIn("advisory_reason", ledger["decision"])

    def test_council_agreement_selects_and_completes_exact_executor(self) -> None:
        session = "council-agree"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Run an independent routing council: build me an app for creators; I am not sure what architecture to use.",
        })
        advisor_message = (
            "Route recommendation: gpt6_sol_high\nEvidence: requirements are ambiguous\n"
            "Verification: validate state model and acceptance criteria\nUncertainty: product scope"
        )
        for role, agent_id in (("gpt6_sol_balanced", "00000000-0000-7000-8000-000000000020"), ("gpt6_sol_high", "00000000-0000-7000-8000-000000000021")):
            spec = router_hook.ROUTES[role]
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id,
                "model": spec["model"], "reasoning_effort": spec["effort"],
            })
            self._observe_valid_spawn(session, "t1", agent_id, role)
            result = router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id, "stop_hook_active": False,
                "model": spec["model"], "reasoning_effort": spec["effort"],
                "last_assistant_message": advisor_message,
            })
        self.assertTrue(result["continue"])
        self.assertIn("Routing council recorded", result["systemMessage"])
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertEqual("gpt6_sol_high", ledger["consensus_selection"]["selected"])
        self.assertTrue(ledger["consensus_selection"]["agreement"])
        self.assertEqual(
            "Sol Medium Speed unknown + Sol High Speed unknown → Sol High Speed unknown",
            ledger["decision"]["visible_route"],
        )

        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt6_sol_high", "agent_id": "00000000-0000-7000-8000-000000000022",
            "model": "gpt-6-sol", "reasoning_effort": "high",
        })
        executor_message = "Evidence: implementation result\nVerification: focused tests passed\nUncertainty: none"
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt6_sol_high", "agent_id": "00000000-0000-7000-8000-000000000022", "stop_hook_active": False,
            "model": "gpt-6-sol", "reasoning_effort": "high",
            "last_assistant_message": executor_message,
        })
        transcript = self._write_agent_transcript(session, [
            ("gpt6_sol_balanced", "00000000-0000-7000-8000-000000000020", advisor_message),
            ("gpt6_sol_high", "00000000-0000-7000-8000-000000000021", advisor_message),
            ("gpt6_sol_high", "00000000-0000-7000-8000-000000000022", executor_message),
        ])
        final = router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": "t1",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        self.assertTrue(final["continue"])
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertEqual("COMPLETE", ledger["status"])

    def test_council_disagreement_retains_the_deterministic_cost_aware_route(self) -> None:
        session = "council-disagree"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Run a routing council: I am not sure how to build this new product workflow.",
        })
        messages = (
            ("gpt6_sol_balanced", "a", "current"),
            ("gpt6_sol_high", "b", "gpt6_sol_high"),
        )
        for role, agent_id, recommendation in messages:
            spec = router_hook.ROUTES[role]
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id,
                "model": spec["model"], "reasoning_effort": spec["effort"],
            })
            self._observe_valid_spawn(session, "t1", agent_id, role)
            result = router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id, "stop_hook_active": False,
                "model": spec["model"], "reasoning_effort": spec["effort"],
                "last_assistant_message": (
                    f"Route recommendation: {recommendation}\nEvidence: bounded assessment\n"
                    "Verification: compare capability and checks\nUncertainty: remains"
                ),
            })
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertTrue(result["continue"])
        self.assertIn("Routing council recorded", result["systemMessage"])
        self.assertEqual("gpt6_sol_balanced", ledger["consensus_selection"]["selected"])
        self.assertFalse(ledger["consensus_selection"]["agreement"])
        self.assertEqual("execution", ledger["decision"]["orchestration"]["phase"])

    def test_council_exact_current_agreement_uses_root_without_executor(self) -> None:
        session = "council-current"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Run a routing council: I am not sure how to implement this ordinary endpoint with focused tests.",
        })
        for role, agent_id in (("gpt6_sol_balanced", "a"), ("gpt6_sol_high", "b")):
            spec = router_hook.ROUTES[role]
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id,
                "model": spec["model"], "reasoning_effort": spec["effort"],
            })
            self._observe_valid_spawn(session, "t1", agent_id, role)
            result = router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id, "stop_hook_active": False,
                "model": spec["model"], "reasoning_effort": spec["effort"],
                "last_assistant_message": (
                    "Route recommendation: current\nEvidence: bounded one-line change\n"
                    "Verification: direct rendered-text check\nUncertainty: none"
                ),
            })
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertTrue(result["continue"])
        self.assertIn("Routing council recorded", result["systemMessage"])
        self.assertEqual("current", ledger["consensus_selection"]["selected"])
        self.assertEqual("execution_current", ledger["decision"]["orchestration"]["phase"])
        self.assertIsNone(ledger["decision"]["orchestration"]["execution_agent_id"])

        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t2",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium", "prompt": "continue",
        })
        continuation = json.loads((Path(self.temp.name) / f"{session}--t2.json").read_text())
        self.assertEqual("current", continuation["decision"]["route"])
        self.assertEqual("direct", continuation["decision"]["orchestration"]["mode"])
        self.assertEqual("t1", continuation["inherited_from_turn"])

    def test_council_rejects_invalid_recommendation_and_advisor_mutation(self) -> None:
        session = "council-invalid"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Run a routing council: I am not sure how to build this product.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt6_sol_balanced", "agent_id": "advisor",
            "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": "t1",
            "agent_id": "advisor", "tool_name": "apply_patch", "tool_input": {}, "tool_response": {},
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt6_sol_balanced", "agent_id": "advisor", "stop_hook_active": False,
            "model": "gpt-6-sol", "reasoning_effort": "medium",
            "last_assistant_message": (
                "Route recommendation: not_a_route\nEvidence: guess\nVerification: none available\nUncertainty: high"
            ),
        })
        self.assertTrue(result["continue"])
        self.assertNotIn("decision", result)
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertIn("advisor_mutation:advisor", ledger["violations"])
        self.assertIn("invalid_route_recommendation:gpt6_sol_balanced", ledger["violations"])

    def test_worker_cap_and_unexpected_roles_are_hard_gates(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "cap", "turn_id": "t1",
            "model": "gpt-6-luna", "prompt": "In parallel, extract versions from three independent manifests.",
        })
        for index, role in enumerate(("gpt56_terra_worker", "gpt56_terra_worker", "gpt56_terra_worker", "gpt56_luna_worker")):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": "cap", "turn_id": "t1",
                "agent_type": role, "agent_id": f"agent-{index}",
                "model": "gpt-6-luna" if role == "gpt56_luna_worker" else "gpt-6-sol",
                "reasoning_effort": "low" if role == "gpt56_luna_worker" else "medium",
            })
        ledger = json.loads((Path(self.temp.name) / "cap--t1.json").read_text())
        self.assertIn("worker_cap_exceeded:3", ledger["violations"])
        self.assertIn("unexpected_agent:gpt56_luna_worker", ledger["violations"])

    def test_staged_plans_enforce_agent_order(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "order", "turn_id": "t1",
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Research three independent APIs in parallel and recommend an architecture.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "order", "turn_id": "t1",
            "agent_id": "owner-too-early", "model": "gpt-6-sol", "reasoning_effort": "high",
        })
        ledger = json.loads((Path(self.temp.name) / "order--t1.json").read_text())
        self.assertIn("ordering_violation:evidence_then_owner:gpt6_sol_high", ledger["violations"])

    def test_local_release_fixture_batch_routes_to_luna_despite_domain_words(self) -> None:
        decision = router_hook.classify_prompt(
            (
                "Create a local synthetic JSONL fixture with 2,400 release-event records. "
                "Each row includes merge_policy and database_schema labels. Use the fixed schema "
                "and run the validator. Do not deploy, publish, merge, push, or touch production, "
                "customer data, payments, or external systems."
            ),
            "gpt-6-luna",
            "low", enforce_active_root=True,
        )
        self.assertEqual("current", decision["route"])
        self.assertEqual("mechanical_batch", decision["task_profile"]["task_type"])
        self.assertEqual("normal", decision["task_profile"]["risk"])
        self.assertIn("safe_mechanical", decision["task_profile"]["signals"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])

    def test_positive_live_release_target_does_not_use_safe_fixture_override(self) -> None:
        decision = router_hook.classify_prompt(
            "Generate 2,400 local JSONL records with a fixed schema, validate them, then deploy the release to production.",
            "gpt-6-sol",
            "medium",
        )
        self.assertNotEqual("gpt56_luna_worker", decision["route"])
        self.assertNotIn("safe_mechanical", decision["task_profile"]["signals"])

    def test_staged_owner_reconciles_delayed_sibling_before_order_check(self) -> None:
        session = "delayed-siblings"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-sol",
            "prompt": "Research three independent APIs in parallel and recommend an architecture.",
        })
        transcript = self._write_agent_transcript(session, [
            ("gpt56_terra_worker", "00000000-0000-7000-8000-000000000023", "Evidence: a\nVerification: checked\nUncertainty: none"),
            ("gpt56_terra_worker", "00000000-0000-7000-8000-000000000024", "Evidence: b\nVerification: checked\nUncertainty: none"),
        ])
        result = router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt56_sol_owner", "agent_id": "owner", "model": "gpt-6-sol",
            "transcript_path": str(transcript),
        })
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertFalse(any(item.startswith("ordering_violation:") for item in ledger["violations"]))
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("hook lifecycle-attests", context)
        self.assertIn("do not re-read the router skill from a versioned cache locator", context)

    def test_repeated_stop_records_unmet_gates_failed_open_without_reinjection(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "hard", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Review OAuth security for auth bypasses.",
        })
        first = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "hard", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertTrue(first["continue"])
        self.assertNotIn("decision", first)
        self.assertIn("systemMessage", first)
        second = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "hard", "turn_id": "t1", "stop_hook_active": True,
        })
        self.assertTrue(second["continue"])
        ledger = json.loads((Path(self.temp.name) / "hard--t1.json").read_text())
        self.assertEqual("FAILED_OPEN", ledger["status"])

    def test_route_up_transitions_once_to_the_next_capability(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "route-up", "turn_id": "t1",
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "Fix the production outage.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "route-up", "turn_id": "t1",
            "agent_id": "balanced-one", "model": "gpt-6-sol", "reasoning_effort": "medium",
        })
        self._observe_valid_spawn("route-up", "t1", "balanced-one", "gpt6_sol_balanced")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "route-up", "turn_id": "child-turn",
            "agent_id": "balanced-one", "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Investigate the bounded outage and return evidence.",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "route-up", "turn_id": "child-turn",
            "agent_id": "balanced-one", "model": "gpt-6-sol", "reasoning_effort": "medium", "stop_hook_active": False,
            "last_assistant_message": (
                "ROUTE_UP\nEvidence: reproduction exhausted\nVerification: competing causes remain\nUncertainty: capability limit"
            ),
        })
        self.assertTrue(result["continue"])
        self.assertIn("Route-up accepted", result["systemMessage"])
        ledger = json.loads((Path(self.temp.name) / "route-up--t1.json").read_text())
        self.assertEqual("gpt6_sol_high", ledger["decision"]["route"])
        self.assertEqual("Sol High Speed unknown", ledger["decision"]["visible_route"])
        self.assertEqual(1, len(ledger["escalations"]))
        self.assertEqual({"gpt6_sol_high": 1}, ledger["decision"]["orchestration"]["required_agents"])
        self.assertEqual({"from": "gpt6_sol_balanced", "to": "gpt6_sol_high", "reason": "ROUTE_UP"}, ledger["escalations"][0])

    def test_attested_sol_route_up_targets_astra_medium(self) -> None:
        session = "sol-to-astra"
        agent_id = "00000000-0000-7000-8000-000000000201"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        initial = self._ledger(session, "t1")
        self.assertEqual("gpt6_sol_high", initial["decision"]["route"])
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "high",
        })
        self._observe_valid_spawn(session, "t1", agent_id, "gpt6_sol_high")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-turn",
            "agent_id": agent_id, "model": "gpt-6-sol", "model_reasoning_effort": "high",
            "prompt": "Resolve the bounded root cause and return structured evidence.",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child-turn",
            "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "high",
            "last_assistant_message": (
                "ROUTE_UP\nEvidence: evidence exhausted at the Sol capability ceiling\n"
                "Verification: competing causes remain\nUncertainty: unresolved root cause"
            ),
        })
        ledger = self._ledger(session, "t1")
        self.assertIn("Route-up accepted", result["systemMessage"])
        self.assertEqual("gpt6_astra_medium", ledger["decision"]["route"])
        self.assertEqual("gpt-6-astra", ledger["decision"]["model"])
        self.assertEqual("medium", ledger["decision"]["effort"])
        self.assertEqual("Astra Medium Speed unknown", ledger["decision"]["visible_route"])
        self.assertEqual(
            [{"from": "gpt6_sol_high", "to": "gpt6_astra_medium", "reason": "ROUTE_UP"}],
            ledger["escalations"],
        )

    def test_unattested_or_malformed_sol_route_up_cannot_open_astra_gate(self) -> None:
        cases = ("unattested", "malformed")
        for case in cases:
            with self.subTest(case=case):
                session = "sol-no-astra-" + case
                agent_id = "00000000-0000-7000-8000-00000000020" + str(cases.index(case) + 2)
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
                    "model": "gpt-6-luna", "model_reasoning_effort": "low",
                    "prompt": "Fix the production outage.",
                })
                router_hook.handle({
                    "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
                    "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
                })
                if case == "malformed":
                    path = Path(self.temp.name) / f"{session}.jsonl"
                    records = [
                        {"payload": {
                            "type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                            "call_id": "bad-spawn", "arguments": json.dumps({
                                "model": "gpt-6-sol", "reasoning_effort": "medium",
                                "message": "Missing the rest of the direct contract.",
                            }),
                            "internal_chat_message_metadata_passthrough": {"turn_id": "t1"},
                        }},
                        {"payload": {
                            "type": "sub_agent_activity", "event_id": "bad-spawn",
                            "agent_thread_id": agent_id, "kind": "started",
                            "internal_chat_message_metadata_passthrough": {"turn_id": "t1"},
                        }},
                    ]
                    path.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
                    state = self._ledger(session, "t1")
                    router_hook._reconcile_subagent_transcript({"transcript_path": str(path)}, state)
                    router_hook._write_existing_state(
                        {"session_id": session, "turn_id": "t1"}, state
                    )
                router_hook.handle({
                    "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-turn",
                    "agent_id": agent_id, "model": "gpt-6-sol", "model_reasoning_effort": "medium",
                    "prompt": "Resolve the bounded root cause and return structured evidence.",
                })
                result = router_hook.handle({
                    "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child-turn",
                    "agent_id": agent_id, "model": "gpt-6-sol", "reasoning_effort": "medium",
                    "last_assistant_message": (
                        "ROUTE_UP\nEvidence: evidence exhausted at the Sol capability ceiling\n"
                        "Verification: competing causes remain\nUncertainty: unresolved root cause"
                    ),
                })
                ledger = self._ledger(session, "t1")
                self.assertIn("Route-up accepted", str(result.get("systemMessage") or ""))
                self.assertEqual("gpt6_sol_high", ledger["decision"]["route"])
                self.assertEqual([{
                    "from": "gpt6_sol_balanced", "to": "gpt6_sol_high", "reason": "ROUTE_UP",
                }], ledger["escalations"])
                self.assertNotEqual("gpt-6-astra", ledger["decision"]["model"])

    def test_astra_is_terminal_for_automatic_route_up(self) -> None:
        session = "astra-terminal"
        agent_id = "00000000-0000-7000-8000-000000000204"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "Use GPT-6 Astra for this bounded task.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_id": agent_id, "model": "gpt-6-astra", "reasoning_effort": "medium",
        })
        self._observe_valid_spawn(session, "t1", agent_id, "gpt6_astra_medium")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "child-turn",
            "agent_id": agent_id, "model": "gpt-6-astra", "model_reasoning_effort": "medium",
            "prompt": "Complete the bounded task.",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "child-turn",
            "agent_id": agent_id, "model": "gpt-6-astra", "reasoning_effort": "medium",
            "last_assistant_message": (
                "ROUTE_UP\nEvidence: capability limit\nVerification: evidence exhausted\n"
                "Uncertainty: deeper reasoning requested"
            ),
        })
        ledger = self._ledger(session, "t1")
        self.assertNotIn("Route-up accepted", str(result.get("systemMessage") or ""))
        self.assertEqual("gpt6_astra_medium", ledger["decision"]["route"])
        self.assertEqual([], ledger["escalations"])

    def test_route_up_rejects_metadata_or_identity_confusion(self) -> None:
        session = "route-up-metadata"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_id": "deep-one", "model": "gpt-6-sol", "reasoning_effort": "high",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
            "agent_id": "deep-one", "model": "gpt-6-sol", "reasoning_effort": "high", "stop_hook_active": False,
            "last_assistant_message": (
                "ROUTE_UP\nEvidence: metadata is hidden and the versioned skill locator is missing\n"
                "Verification: cannot attest identity\nUncertainty: stale cache"
            ),
        })
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertIn("ROUTE_UP was ignored", result["systemMessage"])
        self.assertEqual([], ledger["escalations"])
        self.assertEqual("gpt6_sol_high", ledger["decision"]["route"])
        self.assertIn("unsupported_route_up:gpt6_sol_high", ledger["violations"])

    def test_transcript_fallback_settles_observable_nested_verification(self) -> None:
        session = "nested-verification"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Fix a typo in README and run targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_use_id": "mutation-hook-1",
            "tool_input": {}, "tool_response": {},
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "functions.exec",
            "tool_input": {"source": "const r = await tools.exec_command({cmd: 'python -m unittest'}); text(r.output)"},
            "tool_response": "tests passed",
        })
        metadata = {"turn_id": turn}
        transcript = Path(self.temp.name) / "nested-verification.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in (
            self._transcript_mutation_records(turn) + [
            {"payload": {
                "type": "function_call", "name": "functions.exec", "call_id": "verify-1",
                "arguments": json.dumps({"source": "const r = await tools.exec_command({cmd: 'python -m unittest'}); text(r.output)"}),
                "internal_chat_message_metadata_passthrough": metadata,
            }},
            {"payload": {
                "type": "function_call_output", "call_id": "verify-1",
                "output": json.dumps({"exit_code": 0, "output": "OK"}),
                "internal_chat_message_metadata_passthrough": metadata,
            }},
        ])), encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        ledger = json.loads((Path(self.temp.name) / f"{session}--{turn}.json").read_text())
        self.assertEqual({"continue": True}, result)
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual("transcript_exit_status", ledger["verification_observability"])
        self.assertEqual(["verify-1"], ledger["reconciled_verification_call_ids"])

    def test_structured_subagent_return_passes(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s4", "turn_id": "t4",
            "model": "gpt-6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        }
        router_hook.handle(start)
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "s4", "turn_id": "t4",
            "agent_type": "gpt56_terra_deep",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "s4", "turn_id": "t4",
            "agent_type": "gpt56_terra_deep", "stop_hook_active": False,
            "last_assistant_message": "Evidence: trace\nVerification: test\nUncertainty: none",
        })
        self.assertTrue(result["continue"])

    def test_subagent_turn_id_can_differ_from_parent(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s5", "turn_id": "parent-turn",
            "model": "gpt-6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        }
        router_hook.handle(start)
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "s5", "turn_id": "child-turn",
            "agent_type": "gpt56_terra_deep",
        })
        ledger = json.loads((Path(self.temp.name) / "s5--parent-turn.json").read_text())
        self.assertIn("gpt6_sol_high", ledger["subagents_started"])

    def test_stop_reconciles_missing_lifecycle_hooks_from_transcript(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s6", "turn_id": "t6",
            "model": "gpt-6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        }
        router_hook.handle(start)
        transcript = Path(self.temp.name) / "transcript.jsonl"
        records = [
            {"payload": {"type": "custom_tool_call", "input": 'tools.multi_agent_v1__spawn_agent({agent_type:"gpt56_terra_deep",message:"bounded"})'}},
            {"payload": {"type": "function_call_output", "output": '{"agent_id":"00000000-0000-7000-8000-000000000014"}'}},
            {"payload": {"type": "message", "content": '<subagent_notification>{"agent_path":"00000000-0000-7000-8000-000000000014","status":{"completed":"Evidence: x\\nVerification: y\\nUncertainty: z"}}</subagent_notification>'}},
        ]
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        self._write_child_transcript("s6", "00000000-0000-7000-8000-000000000014", "gpt-6-sol", "high")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "s6", "turn_id": "t6",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        self.assertTrue(result["continue"])
        ledger = json.loads(next(path for path in Path(self.temp.name).glob("s6--*.json")).read_text())
        self.assertEqual([], ledger["subagents_completed"])  # Legacy call has no observed direct contract.
        self.assertTrue(ledger["reconciled_from_transcript"])
        self.assertTrue(ledger["agent_attestations"]["00000000-0000-7000-8000-000000000014"]["matched"])

    def test_stop_reconciles_current_collaboration_transcript_shape(self) -> None:
        session = "collaboration-shape"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-6-sol", "model_reasoning_effort": "medium",
            "prompt": "Research three independent APIs in parallel and recommend an architecture.",
        })
        transcript = Path(self.temp.name) / "collaboration-parent.jsonl"
        records = []
        roles = ["gpt6_sol_balanced", "gpt6_sol_balanced", "gpt6_sol_high"]
        for index, role in enumerate(roles):
            call_id = f"call-{index}"
            agent_id = f"00000000-0000-7000-8000-{index:012d}"
            agent_path = f"/root/worker-{index}"
            metadata = {"turn_id": turn}
            spec = router_hook.ROUTES[role]
            records.extend([
                {"payload": {
                    "type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
                    "call_id": call_id,
                    "arguments": json.dumps({
                        "model": spec["model"], "reasoning_effort": spec["effort"],
                        "fork_turns": "none", "task_name": f"worker-{index}",
                        "message": "Self-contained bounded task with acceptance checks.",
                    }),
                    "internal_chat_message_metadata_passthrough": metadata,
                }},
                {"payload": {
                    "type": "sub_agent_activity", "event_id": call_id, "kind": "started",
                    "agent_thread_id": agent_id, "agent_path": agent_path,
                    "internal_chat_message_metadata_passthrough": metadata,
                }},
                {"payload": {
                    "type": "agent_message", "author": agent_path,
                    "content": [{"type": "input_text", "text": (
                        "Evidence: bounded result\nVerification: objective check passed\nUncertainty: none"
                    )}],
                    "internal_chat_message_metadata_passthrough": metadata,
                }},
            ])
            self._write_child_transcript(session, agent_id, spec["model"], spec["effort"])
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")

        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": session, "turn_id": turn,
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        ledger = json.loads((Path(self.temp.name) / f"{session}--{turn}.json").read_text())
        self.assertEqual({"continue": True}, result)
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual(3, len(ledger["agent_ids"]))
        self.assertEqual(3, len(ledger["agent_attestations"]))
        self.assertEqual(2, sum(
            item["type"] == "gpt6_sol_balanced" and item["status"] == "completed"
            for item in ledger["agents"].values()
        ))

    def test_wrong_child_model_fails_attestation(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "attest", "turn_id": "t1",
            "model": "gpt-6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        transcript = Path(self.temp.name) / "attest-parent.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in [
            {"payload": {"type": "custom_tool_call", "input": 'tools.multi_agent_v1__spawn_agent({agent_type:"gpt56_terra_deep"})'}},
            {"payload": {"type": "function_call_output", "output": '{"agent_id":"00000000-0000-7000-8000-000000000015"}'}},
            {"payload": {"type": "message", "content": '{"agent_path":"00000000-0000-7000-8000-000000000015","status":{"completed":"Evidence: x Verification: y Uncertainty: z"}}'}},
        ]), encoding="utf-8")
        self._write_child_transcript("attest", "00000000-0000-7000-8000-000000000015", "gpt-6-luna", "low")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "attest", "turn_id": "t1",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        self.assertTrue(result["continue"])
        self.assertNotIn("decision", result)
        self.assertIn("attest 1 required `gpt6_sol_high` child model/effort pair(s)", result["systemMessage"])

    def test_child_attestation_detects_advisor_mutation_and_recursive_spawn(self) -> None:
        parent = Path(self.temp.name) / "parent.jsonl"
        parent.write_text("", encoding="utf-8")
        agent_id = "00000000-0000-7000-8000-000000000030"
        self._write_child_transcript("advisor", agent_id, "gpt-6-sol", "medium", extra=[
            {"type": "custom_tool_call", "payload": {"type": "custom_tool_call", "name": "apply_patch"}},
            {"type": "custom_tool_call", "payload": {"type": "custom_tool_call", "name": "spawn_agent"}},
        ])
        attestation = router_hook._attest_child(parent, agent_id, {
            **router_hook.ROUTES["gpt56_terra_worker"], "parent_session_id": "advisor",
        })
        self.assertTrue(attestation["matched"])
        self.assertTrue(attestation["mutation_seen"])
        self.assertTrue(attestation["recursive_spawn_seen"])

    def test_child_attestation_rejects_malformed_oversized_contradictory_or_duplicate_evidence(self) -> None:
        parent = Path(self.temp.name) / "parent.jsonl"
        parent.write_text("", encoding="utf-8")
        expected = {**router_hook.ROUTES["gpt56_terra_worker"], "parent_session_id": "negative"}

        malformed_id = "00000000-0000-7000-8000-000000000031"
        malformed = self._write_child_transcript("negative", malformed_id, "gpt-6-sol", "medium")
        malformed.write_text(
            "not-json\n" + json.dumps({
                "type": "turn_context",
                "payload": {"turn_id": "child", "model": "gpt-6-sol", "effort": "medium"},
            }),
            encoding="utf-8",
        )
        self.assertEqual("MALFORMED", router_hook._attest_child(parent, malformed_id, expected)["reconciliation_status"])

        oversized_id = "00000000-0000-7000-8000-000000000032"
        oversized = self._write_child_transcript("negative", oversized_id, "gpt-6-sol", "medium")
        oversized.write_bytes(b" " * (router_hook.TRANSCRIPT_MAX_LINE_BYTES + 1))
        self.assertEqual("LINE_TOO_LARGE", router_hook._attest_child(parent, oversized_id, expected)["reconciliation_status"])

        contradictory_id = "00000000-0000-7000-8000-000000000033"
        self._write_child_transcript("negative", contradictory_id, "gpt-6-sol", "medium", extra=[
            {"type": "turn_context", "payload": {
                "turn_id": "child-a", "model": "gpt-6-sol", "effort": "medium",
            }},
            {"type": "turn_context", "payload": {
                "turn_id": "child-b", "model": "gpt-6-sol", "effort": "medium",
            }},
        ])
        contradiction = router_hook._attest_child(parent, contradictory_id, expected)
        self.assertFalse(contradiction["matched"])
        self.assertTrue(contradiction["contradictory"])

        duplicate_id = "00000000-0000-7000-8000-000000000034"
        duplicate = self._write_child_transcript("negative", duplicate_id, "gpt-6-sol", "medium")
        shutil.copyfile(duplicate, duplicate.with_name(duplicate.name.replace("T12-00-00", "T12-00-01")))
        self.assertEqual("INCOMPLETE", router_hook._attest_child(parent, duplicate_id, expected)["reconciliation_status"])

    def test_stable_subagent_start_attests_model_and_agent_config_without_transcript(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "stable-attest", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        output = router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "stable-attest", "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "stable-child", "model": "gpt-6-sol",
        })
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("proactive governance contract", context)
        self.assertIn("lifecycle-attest", context)
        self.assertIn("without a service-tier override", context)
        self.assertIn("never delegate recursively", context)
        self.assertIn("advisory-only", context)
        self.assertIn("nonempty and self-contained", context)
        self.assertIn("text(JSON.stringify({exit_code:r.exit_code,output:r.output}))", context)
        ledger = json.loads((Path(self.temp.name) / "stable-attest--t1.json").read_text())
        attestation = ledger["agent_attestations"]["stable-child"]
        self.assertTrue(attestation["matched"])
        self.assertEqual("hook_model+direct_spawn_intent", attestation["source"])
        self.assertTrue(attestation["runtime_model_attested"])
        self.assertEqual("direct_spawn_intent", attestation["effort_evidence"])
        self.assertTrue(attestation["service_tier_inherited"])

    def test_terminal_hook_source_cannot_emit_a_block_decision(self) -> None:
        source = Path(router_hook.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r'["\']decision["\']\s*:\s*["\']block["\']', source))

    def test_terminal_event_matrix_never_returns_a_block_decision(self) -> None:
        outputs = [
            router_hook.handle({"hook_event_name": "Stop", "session_id": "missing", "turn_id": "t1"}),
            router_hook.handle({"hook_event_name": "SubagentStop", "session_id": "missing", "turn_id": "t1"}),
        ]
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "matrix-done", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Hi",
        })
        outputs.append(router_hook.handle({
            "hook_event_name": "Stop", "session_id": "matrix-done", "turn_id": "t1", "stop_hook_active": False,
        }))
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "matrix-unmet", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Review OAuth security for auth bypasses.",
        })
        outputs.append(router_hook.handle({
            "hook_event_name": "Stop", "session_id": "matrix-unmet", "turn_id": "t1", "stop_hook_active": False,
        }))
        outputs.append(router_hook.handle({
            "hook_event_name": "Stop", "session_id": "matrix-unmet", "turn_id": "t1", "stop_hook_active": True,
        }))
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "matrix-child", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "matrix-child", "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "child",
        })
        outputs.append(router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "matrix-child", "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "child", "stop_hook_active": False,
            "last_assistant_message": "incomplete",
        }))
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "matrix-council", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Build a product, but I am not sure which architecture to use.",
        })
        outputs.append(router_hook.handle({
            "hook_event_name": "Stop", "session_id": "matrix-council", "turn_id": "t1", "stop_hook_active": False,
        }))
        for output in outputs:
            self.assertIsInstance(output, dict)
            self.assertNotEqual("block", output.get("decision"))

    def test_service_tier_override_in_spawn_is_rejected(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "tier-spawn", "turn_id": "t1",
            "model": "gpt-6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        transcript = Path(self.temp.name) / "tier-parent.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in [
            {"payload": {"type": "custom_tool_call", "input": 'tools.multi_agent_v1__spawn_agent({agent_type:"gpt56_terra_deep",service_tier:"fast"})'}},
            {"payload": {"type": "function_call_output", "output": '{"agent_id":"00000000-0000-7000-8000-000000000016"}'}},
            {"payload": {"type": "message", "content": '{"agent_path":"00000000-0000-7000-8000-000000000016","status":{"completed":"Evidence: x Verification: y Uncertainty: z"}}'}},
        ]), encoding="utf-8")
        self._write_child_transcript("tier-spawn", "00000000-0000-7000-8000-000000000016", "gpt-6-sol", "high")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "tier-spawn", "turn_id": "t1",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        self.assertTrue(result["continue"])
        self.assertNotIn("decision", result)
        self.assertIn("without a service-tier override", result["systemMessage"])

    def test_parallel_ledger_updates_are_not_lost(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "parallel", "turn_id": "t1",
            "model": "gpt-6-sol", "prompt": "Fix the typo in this file.",
        })
        def mutate(index: int):
            return router_hook.handle({
                "hook_event_name": "PostToolUse", "session_id": "parallel", "turn_id": "t1",
                "tool_name": "apply_patch", "tool_input": {"command": f"patch {index}"}, "tool_response": {},
            })
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(mutate, range(40)))
        ledger = json.loads((Path(self.temp.name) / "parallel--t1.json").read_text())
        self.assertEqual(40, ledger["mutations"])
        self.assertEqual(40, ledger["mutation_generation"])

    def test_windows_locking_branch_locks_and_unlocks_one_byte(self) -> None:
        class FakeMsvcrt:
            LK_LOCK = 1
            LK_UNLCK = 2

            def __init__(self) -> None:
                self.calls = []

            def locking(self, fileno: int, mode: int, size: int) -> None:
                self.calls.append((mode, size))

        original_fcntl, original_msvcrt = router_hook.fcntl, router_hook.msvcrt
        fake = FakeMsvcrt()
        try:
            router_hook.fcntl = None
            router_hook.msvcrt = fake
            with router_hook._ledger_lock():
                self.assertTrue((Path(self.temp.name) / ".router.lock").exists())
        finally:
            router_hook.fcntl, router_hook.msvcrt = original_fcntl, original_msvcrt
        self.assertEqual([(fake.LK_LOCK, 1), (fake.LK_UNLCK, 1)], fake.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
