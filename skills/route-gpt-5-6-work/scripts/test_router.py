#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import router_hook


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
        router_hook.CAPABILITY_PATH = router_hook.HEALTH_ROOT / "capability-v1.json"
        router_hook.CONFIG_PATH.write_text("", encoding="utf-8")
        source_agents = Path(router_hook.__file__).resolve().parents[1] / "assets" / "agents"
        shutil.copytree(source_agents, router_hook.CONFIG_PATH.parent / "agents")

    def tearDown(self) -> None:
        self.config_temp.cleanup()
        self.temp.cleanup()

    def _complete_transcript_plan(self, session: str, prompt: str, roles: list[str]) -> tuple[dict, dict]:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": prompt,
        })
        transcript = Path(self.temp.name) / f"{session}-parent.jsonl"
        records = []
        for index, role in enumerate(roles):
            agent_id = f"{session}-{index}"
            records.extend([
                {"payload": {"type": "custom_tool_call", "input": f'tools.multi_agent_v1__spawn_agent({{agent_type:"{role}",message:"unit-{index}"}})'}},
                {"payload": {"type": "function_call_output", "output": json.dumps({"agent_id": agent_id})}},
                {"payload": {"type": "message", "content": (
                    f'<subagent_notification>{{"agent_path":"{agent_id}","status":{{"completed":'
                    '"Evidence: bounded result\\nVerification: objective check passed\\nUncertainty: none"}}}</subagent_notification>'
                )}},
            ])
            spec = router_hook.ROUTES[role]
            (Path(self.temp.name) / f"rollout-{agent_id}.jsonl").write_text(json.dumps({
                "type": "turn_context", "payload": {"model": spec["model"], "effort": spec["effort"]}
            }), encoding="utf-8")
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
            records.extend([
                {"payload": {"type": "custom_tool_call", "input": f'tools.multi_agent_v1__spawn_agent({{agent_type:"{role}",message:"bounded"}})'}},
                {"payload": {"type": "function_call_output", "output": json.dumps({"agent_id": agent_id})}},
                {"payload": {"type": "message", "content": f'<subagent_notification>{{"agent_path":"{agent_id}","status":{{"completed":{json.dumps(message)}}}}}</subagent_notification>'}},
            ])
            spec = router_hook.ROUTES[role]
            (Path(self.temp.name) / f"rollout-{agent_id}.jsonl").write_text(json.dumps({
                "type": "turn_context", "payload": {"model": spec["model"], "effort": spec["effort"]}
            }), encoding="utf-8")
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        return transcript

    def _ledger(self, session: str, turn: str) -> dict:
        return json.loads((Path(self.temp.name) / f"{session}--{turn}.json").read_text(encoding="utf-8"))

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
        model: str = "gpt-5.6-luna",
    ) -> dict:
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": model, "model_reasoning_effort": "low", "prompt": prompt,
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
                    "model": "gpt-5.6-luna", "model_reasoning_effort": "low", "prompt": prompt,
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
                    model="gpt-5.6-sol",
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
            model="gpt-5.6-sol",
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
            model="gpt-5.6-sol",
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
            model="gpt-5.6-sol",
        )
        self.assertEqual("documentation_only", ledger.get("mutation_surface"))
        self.assertEqual("COMPLETE", ledger["status"])

    def test_code_mutation_still_requires_strong_verification(self) -> None:
        session = "surface-code-strong"
        turn = "t1"
        patch = self._patch_event(session, turn, [("/workspace/app.py", "print('fixed')")])
        diff_only = self._run_mutation_lifecycle(
            session, "Fix app.py.", [patch], [self._verification_event(session, turn)], model="gpt-5.6-sol"
        )
        self.assertEqual("FAILED_OPEN", diff_only["status"])

        session = "surface-code-tested"
        patch = self._patch_event(session, turn, [("/workspace/app.py", "print('fixed')")])
        tested = self._run_mutation_lifecycle(
            session,
            "Fix app.py.",
            [patch],
            [self._verification_event(session, turn, "python3 -m unittest -q")],
            model="gpt-5.6-sol",
        )
        self.assertEqual("non_documentation", tested.get("mutation_surface"))
        self.assertEqual("COMPLETE", tested["status"])

    def test_route_cases(self) -> None:
        self.assertGreaterEqual(len(CASES), 40)
        for prompt, expected in CASES:
            with self.subTest(prompt=prompt):
                actual = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
                self.assertEqual(expected, actual["route"])

    def test_real_desktop_test_a_prompt_is_read_only_and_stays_on_luna(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_a.json").read_text(encoding="utf-8")
        )["classifier_regression"]
        decision = router_hook.classify_prompt(fixture["prompt"], "gpt-5.6-luna", "low")
        self.assertEqual(fixture["expected_mutation"], decision["task_profile"]["mutation"])
        self.assertEqual(fixture["expected_route"], decision["route"])

    def test_desktop_test_b_underspecified_mutation_clarifies(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_b.json").read_text(encoding="utf-8")
        )["classifier_regression"]
        decision = router_hook.classify_prompt(fixture["prompt"], "gpt-5.6-luna", "low")
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
            "gpt-5.6-luna",
            "low",
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
                True, True, False, False, "gpt56_sol_owner", 1,
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
                False, False, False, False, "gpt56_terra_deep", 1,
            ),
        )
        for prompt, mutation, clear_spec, underspecified, clarify, route, children in cases:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
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
            "model": "gpt-5.6-luna",
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
            "model": "gpt-5.6-luna",
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
            "gpt-5.6-luna",
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
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
                self.assertFalse(decision["task_profile"]["mutation"])

    def test_negation_does_not_hide_a_separate_positive_mutation(self) -> None:
        decision = router_hook.classify_prompt(
            "Do not modify README; update the CI configuration and add a focused test.",
            "gpt-5.6-luna",
            "low",
        )
        self.assertTrue(decision["task_profile"]["mutation"])

    def test_read_only_complexity_can_still_require_sol(self) -> None:
        decision = router_hook.classify_prompt(
            "Threat-model the production authentication architecture. Do not modify anything.",
            "gpt-5.6-luna",
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
        self.assertEqual("COMPLETE", ledger["status"])
        receipt = json.loads(router_hook.CAPABILITY_PATH.read_text(encoding="utf-8"))
        self.assertEqual("desktop-test-a-terra-child", receipt["agent_id"])
        self.assertEqual("gpt-5.6-terra", receipt["observed_child_model"])
        self.assertEqual(
            "unavailable_from_current_codex_hook_surface",
            receipt["runtime_identity_source"],
        )

    def test_sanitized_desktop_test_c_correlates_standard_agent_type_as_direct(self) -> None:
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
        self.assertEqual("direct_agent_id", child["correlation_mode"])
        self.assertEqual("desktop-test-c-child-turn", child["child_turn_id"])
        self.assertEqual("gpt-5.6-terra", child["start_observed_model"])
        self.assertEqual("gpt-5.6-terra", child["prompt_observed_model"])
        self.assertEqual("gpt-5.6-terra", child["stop_observed_model"])
        self.assertEqual("completed", child["status"])
        self.assertEqual("COMPLETE", ledger["status"])
        receipt = json.loads(router_hook.CAPABILITY_PATH.read_text(encoding="utf-8"))
        self.assertEqual("desktop-test-c-terra-child", receipt["agent_id"])
        self.assertEqual("gpt-5.6-terra", receipt["observed_child_model"])

    def test_direct_receipt_requires_an_observed_child_prompt(self) -> None:
        base = {"session_id": "receipt-needs-observation", "turn_id": "parent"}
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-5.6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "agent_id": "terra-child",
            "model": "gpt-5.6-terra",
            "reasoning_effort": "medium",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "agent_id": "terra-child",
            "model": "gpt-5.6-terra",
            "reasoning_effort": "medium",
            "last_assistant_message": "Evidence: done\nVerification: tests passed\nUncertainty: none",
        })
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_unknown_agent_stop_cannot_complete_the_expected_child(self) -> None:
        root = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "unknown-stop",
            "turn_id": "parent",
            "model": "gpt-5.6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        }
        router_hook.handle(root)
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "unknown-stop", "turn_id": "parent",
            "agent_id": "expected", "model": "gpt-5.6-terra", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "unknown-stop", "turn_id": "child",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Do the bounded child task.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "unknown-stop", "turn_id": "child",
            "agent_id": "unknown", "model": "gpt-5.6-terra", "reasoning_effort": "medium",
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
                "model": "gpt-5.6-luna",
                "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
            },
            {
                "hook_event_name": "SubagentStart", "session_id": "duplicate-stop", "turn_id": "parent",
                "agent_id": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "medium",
            },
            {
                "hook_event_name": "UserPromptSubmit", "session_id": "duplicate-stop", "turn_id": "child",
                "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Do the child task.",
            },
        )
        for event in events:
            router_hook.handle(event)
        stop = {
            "hook_event_name": "SubagentStop", "session_id": "duplicate-stop", "turn_id": "child",
            "agent_id": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "medium",
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
            "model": "gpt-5.6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        for index in (1, 2):
            agent_id = f"terra-{index}"
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": "sequential", "turn_id": "parent",
                "agent_id": agent_id, "model": "gpt-5.6-terra", "reasoning_effort": "medium",
            })
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": "sequential", "turn_id": f"child-{index}",
                "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": f"Do child task {index}.",
            })
            router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": "sequential", "turn_id": f"child-{index}",
                "agent_id": agent_id, "model": "gpt-5.6-terra", "reasoning_effort": "medium",
                "last_assistant_message": "Evidence: done\nVerification: passed\nUncertainty: none",
            })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        ledger = json.loads((Path(self.temp.name) / "sequential--parent.json").read_text(encoding="utf-8"))
        self.assertEqual("gpt-5.6-luna", observation["root_model"])
        self.assertEqual({"completed"}, {agent["status"] for agent in ledger["agents"].values()})

    def test_started_direct_child_that_never_stops_cannot_complete_or_write_a_receipt(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "never-stops", "turn_id": "parent",
            "model": "gpt-5.6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "never-stops", "turn_id": "parent",
            "agent_id": "terra", "model": "gpt-5.6-terra", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "never-stops", "turn_id": "child",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Do the child task.",
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
            "model": "gpt-5.6-luna",
            "prompt": "In parallel, extract version numbers from three independent manifests.",
        })
        for agent_id in ("terra-a", "terra-b"):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                "agent_id": agent_id, "model": "gpt-5.6-terra", "reasoning_effort": "medium",
            })
        for turn_id in ("child-a", "child-b"):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn_id,
                "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Extract one bounded manifest.",
            })
        for agent_id in ("terra-a", "terra-b"):
            router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": f"stop-{agent_id}",
                "agent_id": agent_id, "model": "gpt-5.6-terra", "reasoning_effort": "medium",
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
        self.assertEqual("gpt-5.6-luna", observation["root_model"])
        self.assertEqual(2, len(ledger["child_prompt_ambiguities"]))
        self.assertTrue(all(len(item["candidate_agent_ids"]) == 2 for item in ledger["child_prompt_ambiguities"]))
        self.assertFalse(router_hook.CAPABILITY_PATH.exists())

    def test_concurrent_terra_and_sol_prompts_correlate_uniquely_by_model(self) -> None:
        session = "concurrent-distinct-models"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "parent",
            "model": "gpt-5.6-luna",
            "prompt": (
                "Review production authorization checks and independently diagnose a flaky queue worker, "
                "then synthesize a safe fix."
            ),
        })
        starts = (
            ("terra", "gpt-5.6-terra", "medium"),
            ("sol", "gpt-5.6-sol", "high"),
        )
        for agent_id, model, effort in starts:
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "parent",
                "agent_id": agent_id, "agent_type": "worker", "model": model,
                "reasoning_effort": effort,
            })
        for turn_id, model, effort in (
            ("terra-turn", "gpt-5.6-terra", "medium"),
            ("sol-turn", "gpt-5.6-sol", "high"),
        ):
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn_id,
                "model": model, "model_reasoning_effort": effort, "prompt": "Do the bounded child task.",
            })
        ledger = json.loads((Path(self.temp.name) / f"{session}--parent.json").read_text(encoding="utf-8"))
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("terra-turn", ledger["agents"]["terra"]["child_turn_id"])
        self.assertEqual("sol-turn", ledger["agents"]["sol"]["child_turn_id"])
        self.assertEqual("gpt-5.6-luna", observation["root_model"])

    def test_subsequent_parent_turn_can_update_the_root_after_child_completion(self) -> None:
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "desktop_test_a.json").read_text(encoding="utf-8")
        )
        for event in fixture["lifecycle_events"][:-1]:
            router_hook.handle(event)
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "desktop-test-a-session", "turn_id": "next-parent",
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Explain this helper.",
        })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("gpt-5.6-sol", observation["root_model"])

    def test_sol_parent_observation_is_not_overwritten_by_an_active_child(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "sol-parent", "turn_id": "parent",
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Review the architecture.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "sol-parent", "turn_id": "parent",
            "agent_id": "parallel-terra", "model": "gpt-5.6-terra", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "sol-parent", "turn_id": "child",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Run independent evidence gathering.",
        })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("gpt-5.6-sol", observation["root_model"])

    def test_unexpected_direct_child_model_never_creates_a_receipt(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "model-mismatch", "turn_id": "parent",
            "model": "gpt-5.6-luna",
            "prompt": "Add pagination to this endpoint and include targeted tests for the changed behavior.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "model-mismatch", "turn_id": "parent",
            "agent_id": "wrong-model", "model": "gpt-5.6-terra", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "model-mismatch", "turn_id": "child",
            "model": "gpt-5.6-sol", "model_reasoning_effort": "medium", "prompt": "Do the child task.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "model-mismatch", "turn_id": "child",
            "agent_id": "wrong-model", "model": "gpt-5.6-sol", "reasoning_effort": "medium",
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
        self.assertEqual("gpt-5.6-luna", observation["root_model"])
        child = ledger["agents"]["wrong-model"]
        self.assertEqual("gpt-5.6-terra", child["start_observed_model"])
        self.assertIsNone(child["prompt_observed_model"])
        self.assertEqual("gpt-5.6-sol", child["stop_observed_model"])
        self.assertFalse(child["model_evidence_consistent"])

    def test_actual_root_model_matrix_prevents_downward_delegation(self) -> None:
        normal = "Implement a feature with multiple states, error handling, and targeted tests."
        hard = "Review production authorization checks for privilege escalation vulnerabilities."
        routine = "Fix a typo in the README."
        expected = {
            "gpt-5.6-luna": ("current", "gpt56_terra_worker", "gpt56_sol_deep"),
            "gpt-5.6-terra": ("current", "current", "gpt56_sol_deep"),
            "gpt-5.6-sol": ("current", "current", "current"),
        }
        for root_model, routes in expected.items():
            with self.subTest(root_model=root_model):
                decisions = tuple(
                    router_hook.classify_prompt(prompt, root_model, "low" if "luna" in root_model else "medium")
                    for prompt in (routine, normal, hard)
                )
                self.assertEqual(routes, tuple(item["route"] for item in decisions))
                expected_efficiency = "READY" if root_model == "gpt-5.6-luna" else "DEGRADED"
                self.assertEqual({expected_efficiency}, {item["credit_efficiency"] for item in decisions})

    def test_continuation_reapplies_policy_from_each_actual_hook_model(self) -> None:
        base = {"hook_event_name": "UserPromptSubmit", "session_id": "root-change"}
        router_hook.handle({
            **base,
            "turn_id": "t1",
            "model": "gpt-5.6-luna",
            "prompt": "Review production authorization checks for privilege escalation vulnerabilities.",
        })
        router_hook.handle({
            **base,
            "turn_id": "t2",
            "model": "gpt-5.6-sol",
            "prompt": "continue",
        })
        second = json.loads((Path(self.temp.name) / "root-change--t2.json").read_text())["decision"]
        self.assertEqual("gpt-5.6-sol", second["actual_root_model"])
        self.assertEqual("current", second["route"])
        self.assertEqual("DEGRADED", second["credit_efficiency"])

        router_hook.handle({
            **base,
            "turn_id": "t3",
            "model": "gpt-5.6-luna",
            "prompt": "continue",
        })
        third = json.loads((Path(self.temp.name) / "root-change--t3.json").read_text())["decision"]
        self.assertEqual("gpt-5.6-luna", third["actual_root_model"])
        self.assertEqual("gpt56_sol_deep", third["route"])
        self.assertEqual("READY", third["credit_efficiency"])

    def test_user_intent_ambiguity_clarifies_without_spawning(self) -> None:
        decision = router_hook.classify_prompt(
            "Build me an app; I am not sure what architecture or approach I want.",
            "gpt-5.6-luna",
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
            "gpt-5.6-luna",
            "low",
        )
        self.assertFalse(decision["requires_clarification"])
        self.assertEqual("gpt56_terra_deep", decision["route"])

    def test_context_uses_direct_model_spawn_without_legacy_agent_type(self) -> None:
        decision = router_hook.classify_prompt(
            "Review production authorization checks for privilege escalation vulnerabilities.",
            "gpt-5.6-luna",
            "low",
        )
        context = router_hook._context(decision)
        self.assertIn('"model":"gpt-5.6-sol"', context)
        self.assertIn('"reasoning_effort":"high"', context)
        self.assertNotIn("agent_type", context)
        self.assertNotIn('"model":"gpt-5.6-luna"', context)

    def test_actual_turn_writes_prompt_free_root_observation(self) -> None:
        secret_prompt = "Fix the docs. PRIVATE-PROMPT-CONTENT"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit",
            "session_id": "root-observation",
            "turn_id": "t1",
            "model": "gpt-5.6-luna",
            "prompt": secret_prompt,
            "runtime_version": "codex-1.2.3",
            "runtime_build": "desktop-456",
            "host_type": "Desktop",
        })
        observation = json.loads(router_hook.ROOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual("gpt-5.6-luna", observation["root_model"])
        self.assertEqual("codex-1.2.3", observation["runtime_version"])
        self.assertEqual("desktop-456", observation["runtime_build"])
        self.assertEqual("Desktop", observation["host_type"])
        self.assertNotIn(secret_prompt, json.dumps(observation))

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
            "model": "gpt-5.6-luna",
            "prompt": "Review production authorization checks for privilege escalation vulnerabilities.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "agent_id": "sol-child",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "turn_id": "child-turn",
            "model": "gpt-5.6-sol",
            "model_reasoning_effort": "high",
            "prompt": "Perform the bounded security review and return structured evidence.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "turn_id": "child-turn",
            "agent_id": "sol-child",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "last_assistant_message": "Evidence: checked\nVerification: tests passed\nUncertainty: none",
        })
        receipt = json.loads(router_hook.CAPABILITY_PATH.read_text(encoding="utf-8"))
        self.assertEqual("direct-model-spawn-v1", receipt["capability_signature"])
        self.assertEqual("gpt-5.6-sol", receipt["observed_child_model"])
        self.assertEqual("high", receipt["effort_intent"])
        self.assertEqual("codex-1.2.3", receipt["runtime_version"])
        self.assertEqual("desktop-456", receipt["runtime_build"])
        self.assertNotIn("authorization", json.dumps(receipt).lower())

    def test_ledger_records_routing_telemetry_without_inventing_credit_usage(self) -> None:
        base = {"session_id": "telemetry", "turn_id": "t1"}
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-5.6-luna",
            "service_tier": "priority",
            "prompt": "Review production authorization checks for privilege escalation vulnerabilities.",
        })
        initial = json.loads((Path(self.temp.name) / "telemetry--t1.json").read_text())
        telemetry = initial["telemetry"]
        self.assertEqual("gpt-5.6-luna", telemetry["root_model"])
        self.assertEqual(["gpt-5.6-sol"], telemetry["requested_child_models"])
        self.assertEqual(["high"], telemetry["effort_intents"])
        self.assertEqual("fast", telemetry["service_tier"])
        self.assertEqual("hook", telemetry["service_tier_source"])
        self.assertEqual("UNAVAILABLE", telemetry["usage"]["provenance"])

        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStart",
            "agent_id": "telemetry-child",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "UserPromptSubmit",
            "turn_id": "child-turn",
            "model": "gpt-5.6-sol",
            "model_reasoning_effort": "high",
            "prompt": "Perform the bounded security review and return structured evidence.",
        })
        router_hook.handle({
            **base,
            "hook_event_name": "SubagentStop",
            "turn_id": "child-turn",
            "agent_id": "telemetry-child",
            "model": "gpt-5.6-sol",
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
        decision = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
        self.assertEqual(0, decision["task_profile"]["unit_count"])
        self.assertEqual("normal", decision["task_profile"]["risk"])
        self.assertEqual("explanation", decision["task_profile"]["task_type"])

    def test_relayforge_mechanical_fixture_prompt_routes_to_luna(self) -> None:
        prompt = """<codex_delegation>
  <source_thread_id>019f4ab3-2b7a-7932-a6a6-f401afced4e3</source_thread_id>
  <input>Generate exactly 1,200 synthetic JSONL fixture records in three independent 400-record shards using the fixed schema and formulas. One example projectSlug is billing-reliability. These are synthetic fixtures, not customer data. Add a validator that rejects malformed JSON, wrong key order, formula mismatches, duplicates, and incorrect totals. Do not modify runtime or database schema. Run the validator, tests, typecheck, lint, and build. The routing ledger should show the selected workers.</input>
</codex_delegation>"""
        decision = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
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
            "Audit production authentication for privilege escalation.", "gpt-5.6-terra", "medium", "max-quality"
        )
        architecture = router_hook.classify_prompt(
            "Design the architecture for a cross-service migration.", "gpt-5.6-terra", "medium", "max-quality"
        )
        self.assertEqual("gpt56_sol_xhigh", security["route"])
        self.assertEqual("xhigh", security["effort"])
        self.assertEqual("gpt56_sol_deep", architecture["route"])

    def test_max_quality_upgrades_the_capability_target_not_the_optimized_current_route(self) -> None:
        prompt = "Add pagination to this endpoint and include targeted tests for the changed behavior."
        balanced = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium", "balanced")
        quality = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium", "max-quality")
        self.assertEqual("current", balanced["route"])
        self.assertEqual("gpt56_terra_worker", balanced["capability_target"])
        self.assertEqual("current", quality["route"])

    def test_hook_reads_profile_and_keeps_fast_independent(self) -> None:
        router_hook.PROFILE_PATH.parent.mkdir(parents=True)
        router_hook.PROFILE_PATH.write_text(
            '{"schema_version":1,"profile":"token-saver"}', encoding="utf-8"
        )
        result = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "profile-fast", "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
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
        self.assertEqual("gpt56_terra_deep", decision["route"])

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
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
                self.assertEqual(route, decision["route"])
                self.assertEqual(task_type, decision["task_profile"]["task_type"])
                self.assertEqual(mode, decision["orchestration"]["mode"])

    def test_product_building_areas_route_per_work_unit(self) -> None:
        for prompt, primary_area, expected_route in PRODUCT_CASES:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
                self.assertEqual(primary_area, decision["task_profile"]["product"]["primary_area"])
                self.assertEqual(expected_route, decision["route"])

    def test_critical_billing_change_uses_evidence_then_owner(self) -> None:
        decision = router_hook.classify_prompt(
            "Implement subscription upgrades with proration idempotency and reconciliation.",
            "gpt-5.6-terra", "medium",
        )
        self.assertEqual("critical", decision["task_profile"]["risk"])
        self.assertEqual("evidence_then_owner", decision["orchestration"]["mode"])
        self.assertEqual({"gpt56_terra_worker": 2, "gpt56_sol_owner": 1}, decision["orchestration"]["required_agents"])

    def test_every_route_emits_a_valid_bounded_plan(self) -> None:
        for prompt, _ in CASES:
            decision = router_hook.classify_prompt(prompt, "gpt-5.6-luna", "low")
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
            "Review OAuth token handling for authorization bypasses.", "gpt-5.6-luna", "low"
        )
        decision.update(router_hook._service_tier({"service_tier": "priority"}))
        decision["effort_evidence"] = "owned_agent_config_intent"
        decision["visible_route"] = router_hook._visible_route(decision, {})
        decision["announce_route"] = False
        context = router_hook._context(decision)
        self.assertIn("MANDATORY SPAWN ARGUMENT CONTRACT", context)
        self.assertIn(
            'spawn_agent({"fork_turns":"none","task_name":"<unique-1>","message":"<distilled-task>","model":"gpt-5.6-sol","reasoning_effort":"high"})',
            context,
        )
        self.assertIn("`fork_turns` must be exactly `\"none\"`", context)
        self.assertIn("keep `task_name` only as a unique orchestration label", context)
        self.assertIn("Never use the default or `\"all\"` full-history fork", context)
        self.assertIn("pass the adapter-selected `model` and `reasoning_effort`", context)
        self.assertNotIn("agent_type", context)

    def test_classifier_is_deterministic_and_redacted(self) -> None:
        prompt = "Audit OAuth token handling for leaked credentials in production. secret-123"
        first = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
        second = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
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
            "Diagnose why this flaky test fails intermittently.", "gpt-5.6-terra", "high"
        )
        self.assertEqual("current", ambiguous["route"])
        architecture = router_hook.classify_prompt(
            "Design the architecture for a cross-service migration.", "gpt-5.6-sol", "medium"
        )
        self.assertEqual("current", architecture["route"])

    def test_security_analysis_stays_current_when_sol_high_is_already_active(self) -> None:
        decision = router_hook.classify_prompt(
            "Audit production authentication for privilege escalation.", "gpt-5.6-sol", "high"
        )
        self.assertEqual("current", decision["route"])

    def test_active_model_effort_matrix(self) -> None:
        prompt = "Diagnose why this flaky test fails intermittently."
        expected = {
            ("gpt-5.6-luna", "low"): "gpt56_terra_deep",
            ("gpt-5.6-terra", "medium"): "current",
            ("gpt-5.6-terra", "high"): "current",
            ("gpt-5.6-sol", "medium"): "current",
            ("gpt-5.6-sol", "high"): "current",
        }
        for active, route in expected.items():
            with self.subTest(active=active):
                self.assertEqual(route, router_hook.classify_prompt(prompt, *active)["route"])

    def test_luna_requires_cheap_verification(self) -> None:
        decision = router_hook.classify_prompt("Make mechanical changes across 100 files.", "gpt-5.6-terra")
        self.assertNotEqual("gpt56_luna_worker", decision["route"])

    def test_prompt_hook_writes_redacted_ledger(self) -> None:
        data = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "turn_id": "t1",
            "model": "gpt-5.6-terra",
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
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Hi",
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
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Hi",
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
                "model": "gpt-5.6-terra", "prompt": "Hi",
            })
        self.assertEqual('{"keep":true}\n', foreign.read_text(encoding="utf-8"))

    @unittest.skipIf(not hasattr(os, "link"), "hardlinks unavailable")
    def test_purge_preserves_hardlinked_router_ledgers(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "linked", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Hi",
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
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Hi",
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
            "model": "gpt-5.6-terra", "prompt": "Hi",
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
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "Hi",
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
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "inherit", "turn_id": "t2",
            "model": "gpt-5.6-terra", "prompt": "yes, do it",
        })
        ledger = json.loads((Path(self.temp.name) / "inherit--t2.json").read_text())
        self.assertEqual("gpt56_sol_deep", ledger["decision"]["route"])
        self.assertEqual("t1", ledger["inherited_from_turn"])

    def test_natural_followups_inherit_prior_route(self) -> None:
        followups = ("Sure—continue with the fix.", "Sounds good, do that.", "Yes please, make those changes.")
        for index, followup in enumerate(followups):
            session = f"natural-{index}"
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
                "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
            })
            router_hook.handle({
                "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t2",
                "model": "gpt-5.6-terra", "prompt": followup,
            })
            ledger = json.loads((Path(self.temp.name) / f"{session}--t2.json").read_text())
            self.assertEqual("gpt56_sol_deep", ledger["decision"]["route"])
            self.assertEqual("t1", ledger["inherited_from_turn"])

    def test_new_topic_does_not_inherit(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "topic", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
        })
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "topic", "turn_id": "t2",
            "model": "gpt-5.6-terra", "prompt": "Explain this TypeScript error.",
        })
        ledger = json.loads((Path(self.temp.name) / "topic--t2.json").read_text())
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertIsNone(ledger["inherited_from_turn"])

    def test_fast_toggle_is_reread_on_continuation(self) -> None:
        router_hook.CONFIG_PATH.write_text('service_tier = "priority"\n', encoding="utf-8")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "fast-toggle", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
        })
        first = json.loads((Path(self.temp.name) / "fast-toggle--t1.json").read_text())
        self.assertTrue(first["decision"]["fast_enabled"])
        self.assertEqual("fast", first["decision"]["service_tier"])
        self.assertEqual("Sol High Fast", first["decision"]["visible_route"])

        router_hook.CONFIG_PATH.write_text("", encoding="utf-8")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "fast-toggle", "turn_id": "t2",
            "model": "gpt-5.6-terra", "prompt": "continue",
        })
        second = json.loads((Path(self.temp.name) / "fast-toggle--t2.json").read_text())
        self.assertEqual("gpt56_sol_deep", second["decision"]["route"])
        self.assertFalse(second["decision"]["fast_enabled"])
        self.assertEqual("default", second["decision"]["service_tier"])
        self.assertEqual("Sol High Speed unknown", second["decision"]["visible_route"])
        self.assertTrue(second["decision"]["announce_route"])

    def test_current_route_uses_active_model_effort_and_unknown_speed_without_tier_evidence(self) -> None:
        router_hook.CONFIG_PATH.write_text('model_reasoning_effort = "medium"\n', encoding="utf-8")
        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "visible-current", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Fix a typo.",
        })
        ledger = json.loads((Path(self.temp.name) / "visible-current--t1.json").read_text())
        self.assertEqual("Terra Medium Speed unknown", ledger["decision"]["visible_route"])
        self.assertNotIn("Route: Terra Medium Speed unknown", output["hookSpecificOutput"]["additionalContext"])

    def test_current_route_does_not_invent_missing_model_or_effort(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "visible-unknown", "turn_id": "t1",
            "prompt": "Hi",
        })
        ledger = json.loads((Path(self.temp.name) / "visible-unknown--t1.json").read_text())
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertEqual("default_assumed", ledger["decision"]["effort_evidence"])
        self.assertEqual("Current model unknown Effort unknown Speed unknown", ledger["decision"]["visible_route"])

    def test_unknown_root_effort_cannot_satisfy_a_demanding_route(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "unknown-effort", "turn_id": "t1",
            "model": "gpt-5.6-sol", "prompt": "Design the architecture and migration plan for this multi-service platform.",
        })
        ledger = json.loads((Path(self.temp.name) / "unknown-effort--t1.json").read_text())
        self.assertEqual("unknown", ledger["decision"]["task_profile"]["active_effort"])
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertEqual("default_assumed", ledger["decision"]["effort_evidence"])

    def test_non_current_context_requires_factual_public_label(self) -> None:
        router_hook.CONFIG_PATH.write_text('service_tier = "priority"\n', encoding="utf-8")
        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "visible-delegated", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
        })
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("VISIBLE ROUTE: Sol High Fast", context)
        self.assertIn("Route: Sol High Fast", context)

    def test_hook_service_tier_wins_over_persisted_config(self) -> None:
        router_hook.CONFIG_PATH.write_text('service_tier = "priority"\n', encoding="utf-8")
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "tier-input", "turn_id": "t1",
            "model": "gpt-5.6-terra", "service_tier": "default", "prompt": "Fix a typo.",
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
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo in this file.",
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
            "model": "gpt-5.6-terra", "prompt": "How are things now?",
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
            "model": "gpt-5.6-terra", "prompt": "How are things now?",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": "terminal-feedback", "turn_id": "t1",
            "stop_hook_active": False,
        })
        feedback = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "terminal-feedback", "turn_id": "t2",
            "model": "gpt-5.6-terra",
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
            "model": "gpt-5.6-terra", "prompt": "How are things now?",
        })
        router_hook.handle({
            "hook_event_name": "Stop", "session_id": "wrapped-feedback", "turn_id": "t1",
            "stop_hook_active": False,
        })
        feedback = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "wrapped-feedback", "turn_id": "t2",
            "model": "gpt-5.6-terra",
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

    def test_transcript_custom_validator_settles_the_latest_mutation(self) -> None:
        session = "transcript-custom-validator"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Create a fixture.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        metadata = {"turn_id": turn}
        transcript_dir = router_hook.CODEX_HOME / "sessions" / "2026" / "07" / "14"
        transcript_dir.mkdir(parents=True)
        transcript = transcript_dir / f"rollout-{session}.jsonl"
        records = [
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

    def test_nested_exec_verification_settles_the_latest_mutation(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "nested-verify", "turn_id": "t1",
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "How are things now?",
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
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
        records = [
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "How are things now?",
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
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
            "model": "gpt-5.6-sol", "model_reasoning_effort": "high", "prompt": "Fix the typo.",
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
            "model": "gpt-5.6-terra", "prompt": "How are things now?",
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
            "model": "gpt-5.6-luna", "prompt": "In parallel, extract versions from three independent manifests.",
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
            "Convert all 500 images to WebP and compare checksums.", "gpt-5.6-luna", "low"
        )
        self.assertEqual("current", decision["route"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])

    def test_evidence_then_owner_plan_completes_with_all_attestations(self) -> None:
        result, ledger = self._complete_transcript_plan(
            "evidence-owner", "Research three independent APIs in parallel and recommend an architecture.",
            ["gpt56_terra_worker", "gpt56_terra_worker", "gpt56_sol_owner"],
        )
        self.assertTrue(result["continue"])
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual("evidence_then_owner", ledger["decision"]["orchestration"]["mode"])
        self.assertEqual("gpt56_sol_owner", ledger["decision"]["orchestration"]["synthesis_owner"])

    def test_critical_evidence_plan_completes_with_all_attestations(self) -> None:
        result, ledger = self._complete_transcript_plan(
            "critical-evidence", "Delete the production database.",
            ["gpt56_terra_worker", "gpt56_terra_worker", "gpt56_sol_owner"],
        )
        self.assertTrue(result["continue"])
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual("evidence_then_owner", ledger["decision"]["orchestration"]["mode"])

    def test_public_label_shows_the_complete_multi_agent_plan(self) -> None:
        fast_batch = router_hook.classify_prompt(
            "Convert 500 images to WebP and compare checksums.", "gpt-5.6-luna", "low"
        )
        fast_batch.update({"fast_enabled": True})
        self.assertEqual("Luna Low Fast", router_hook._visible_route(fast_batch, {"model": "gpt-5.6-luna"}))

        evidence_owner = router_hook.classify_prompt(
            "Research three independent APIs in parallel and recommend an architecture.", "gpt-5.6-terra", "medium"
        )
        evidence_owner.update({"fast_enabled": False})
        self.assertEqual(
            "Terra Medium Standard ×2 → Sol Medium Standard",
            router_hook._visible_route(evidence_owner, {"model": "gpt-5.6-terra"}),
        )

        critical_evidence = router_hook.classify_prompt("Delete the production database.", "gpt-5.6-terra", "medium")
        critical_evidence.update({"fast_enabled": True})
        self.assertEqual(
            "Terra Medium Fast ×2 → Sol Medium Fast",
            router_hook._visible_route(critical_evidence, {"model": "gpt-5.6-terra"}),
        )

    def test_uncertain_product_invokes_a_bounded_routing_council(self) -> None:
        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "council-profile", "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "Run an independent routing council: build me an app for creators; I am not sure what architecture to use.",
        })
        ledger = json.loads((Path(self.temp.name) / "council-profile--t1.json").read_text())
        plan = ledger["decision"]["orchestration"]
        self.assertEqual("routing_council", plan["mode"])
        self.assertEqual("advisory", plan["phase"])
        self.assertEqual(3, plan["max_workers"])
        self.assertEqual({"gpt56_terra_worker": 1, "gpt56_terra_deep": 1}, plan["required_agents"])
        self.assertEqual("Terra Medium Speed unknown + Terra High Speed unknown", ledger["decision"]["visible_route"])
        self.assertIn("advisors are read-only", output["hookSpecificOutput"]["additionalContext"])

        simple_uncertainty = router_hook.classify_prompt(
            "I am not sure what OAuth means; explain it in one sentence.", "gpt-5.6-terra", "medium"
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
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
                self.assertNotEqual("routing_council", decision["orchestration"]["mode"])
                self.assertEqual("current", decision["route"])

    def test_surface_and_negated_security_words_do_not_force_expensive_routes(self) -> None:
        for prompt in (
            "Fix this checkout CSS typo.",
            "Add a pricing page.",
            "No security changes: update the button label.",
        ):
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
                self.assertEqual("current", decision["route"])
                self.assertNotIn("security", decision["task_profile"]["signals"])

    def test_council_can_recommend_every_supported_cost_route(self) -> None:
        decision = router_hook.classify_prompt(
            "Run a routing council: I am not sure how to implement this ordinary endpoint with focused tests.",
            "gpt-5.6-terra",
            "medium",
        )
        self.assertEqual(set(router_hook.ROUTES), set(decision["orchestration"]["candidate_routes"]))

    def test_missing_or_drifted_legacy_agents_do_not_affect_supported_routing(self) -> None:
        (router_hook.CONFIG_PATH.parent / "agents" / "gpt56_sol_deep.toml").unlink()
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "advisory", "turn_id": "t1",
            "model": "gpt-5.6-luna", "model_reasoning_effort": "low",
            "prompt": "Review OAuth token handling for authorization bypasses.",
        })
        ledger = json.loads((Path(self.temp.name) / "advisory--t1.json").read_text())
        self.assertEqual("gpt56_sol_deep", ledger["decision"]["route"])
        self.assertEqual("single_delegate", ledger["decision"]["orchestration"]["mode"])
        self.assertNotIn("advisory_reason", ledger["decision"])

    def test_council_agreement_selects_and_completes_exact_executor(self) -> None:
        session = "council-agree"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "Run an independent routing council: build me an app for creators; I am not sure what architecture to use.",
        })
        advisor_message = (
            "Route recommendation: gpt56_terra_deep\nEvidence: requirements are ambiguous\n"
            "Verification: validate state model and acceptance criteria\nUncertainty: product scope"
        )
        for role, agent_id in (("gpt56_terra_worker", "cost"), ("gpt56_terra_deep", "risk")):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id,
            })
            result = router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id, "stop_hook_active": False,
                "last_assistant_message": advisor_message,
            })
        self.assertTrue(result["continue"])
        self.assertIn("Routing council recorded", result["systemMessage"])
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertEqual("gpt56_terra_deep", ledger["consensus_selection"]["selected"])
        self.assertTrue(ledger["consensus_selection"]["agreement"])
        self.assertEqual(
            "Terra Medium Speed unknown + Terra High Speed unknown → Terra High Speed unknown",
            ledger["decision"]["visible_route"],
        )

        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "executor",
        })
        executor_message = "Evidence: implementation result\nVerification: focused tests passed\nUncertainty: none"
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "executor", "stop_hook_active": False,
            "last_assistant_message": executor_message,
        })
        transcript = self._write_agent_transcript(session, [
            ("gpt56_terra_worker", "cost", advisor_message),
            ("gpt56_terra_deep", "risk", advisor_message),
            ("gpt56_terra_deep", "executor", executor_message),
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
            "model": "gpt-5.6-terra", "prompt": "Run a routing council: I am not sure how to build this new product workflow.",
        })
        messages = (
            ("gpt56_terra_worker", "a", "current"),
            ("gpt56_terra_deep", "b", "gpt56_terra_deep"),
        )
        for role, agent_id, recommendation in messages:
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id,
            })
            result = router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id, "stop_hook_active": False,
                "last_assistant_message": (
                    f"Route recommendation: {recommendation}\nEvidence: bounded assessment\n"
                    "Verification: compare capability and checks\nUncertainty: remains"
                ),
            })
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertTrue(result["continue"])
        self.assertIn("Routing council recorded", result["systemMessage"])
        self.assertEqual("gpt56_terra_worker", ledger["consensus_selection"]["selected"])
        self.assertFalse(ledger["consensus_selection"]["agreement"])
        self.assertEqual("execution", ledger["decision"]["orchestration"]["phase"])

    def test_council_exact_current_agreement_uses_root_without_executor(self) -> None:
        session = "council-current"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "Run a routing council: I am not sure how to implement this ordinary endpoint with focused tests.",
        })
        for role, agent_id in (("gpt56_terra_worker", "a"), ("gpt56_terra_deep", "b")):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id,
            })
            result = router_hook.handle({
                "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
                "agent_type": role, "agent_id": agent_id, "stop_hook_active": False,
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
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium", "prompt": "continue",
        })
        continuation = json.loads((Path(self.temp.name) / f"{session}--t2.json").read_text())
        self.assertEqual("current", continuation["decision"]["route"])
        self.assertEqual("direct", continuation["decision"]["orchestration"]["mode"])
        self.assertEqual("t1", continuation["inherited_from_turn"])

    def test_council_rejects_invalid_recommendation_and_advisor_mutation(self) -> None:
        session = "council-invalid"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Run a routing council: I am not sure how to build this product.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt56_terra_worker", "agent_id": "advisor",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": "t1",
            "agent_id": "advisor", "tool_name": "apply_patch", "tool_input": {}, "tool_response": {},
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt56_terra_worker", "agent_id": "advisor", "stop_hook_active": False,
            "last_assistant_message": (
                "Route recommendation: not_a_route\nEvidence: guess\nVerification: none available\nUncertainty: high"
            ),
        })
        self.assertTrue(result["continue"])
        self.assertNotIn("decision", result)
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertIn("advisor_mutation:advisor", ledger["violations"])
        self.assertIn("invalid_route_recommendation:gpt56_terra_worker", ledger["violations"])

    def test_worker_cap_and_unexpected_roles_are_hard_gates(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "cap", "turn_id": "t1",
            "model": "gpt-5.6-luna", "prompt": "In parallel, extract versions from three independent manifests.",
        })
        for index, role in enumerate(("gpt56_terra_worker", "gpt56_terra_worker", "gpt56_terra_worker", "gpt56_luna_worker")):
            router_hook.handle({
                "hook_event_name": "SubagentStart", "session_id": "cap", "turn_id": "t1",
                "agent_type": role, "agent_id": f"agent-{index}",
            })
        ledger = json.loads((Path(self.temp.name) / "cap--t1.json").read_text())
        self.assertIn("worker_cap_exceeded:3", ledger["violations"])
        self.assertIn("unexpected_agent:gpt56_luna_worker", ledger["violations"])

    def test_staged_plans_enforce_agent_order(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "order", "turn_id": "t1",
            "model": "gpt-5.6-terra",
            "prompt": "Research three independent APIs in parallel and recommend an architecture.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "order", "turn_id": "t1",
            "agent_type": "gpt56_sol_owner", "agent_id": "owner-too-early",
        })
        ledger = json.loads((Path(self.temp.name) / "order--t1.json").read_text())
        self.assertIn("ordering_violation:evidence_then_owner:gpt56_sol_owner", ledger["violations"])

    def test_local_release_fixture_batch_routes_to_luna_despite_domain_words(self) -> None:
        decision = router_hook.classify_prompt(
            (
                "Create a local synthetic JSONL fixture with 2,400 release-event records. "
                "Each row includes merge_policy and database_schema labels. Use the fixed schema "
                "and run the validator. Do not deploy, publish, merge, push, or touch production, "
                "customer data, payments, or external systems."
            ),
            "gpt-5.6-luna",
            "low",
        )
        self.assertEqual("current", decision["route"])
        self.assertEqual("mechanical_batch", decision["task_profile"]["task_type"])
        self.assertEqual("normal", decision["task_profile"]["risk"])
        self.assertIn("safe_mechanical", decision["task_profile"]["signals"])
        self.assertEqual({}, decision["orchestration"]["required_agents"])

    def test_positive_live_release_target_does_not_use_safe_fixture_override(self) -> None:
        decision = router_hook.classify_prompt(
            "Generate 2,400 local JSONL records with a fixed schema, validate them, then deploy the release to production.",
            "gpt-5.6-terra",
            "medium",
        )
        self.assertNotEqual("gpt56_luna_worker", decision["route"])
        self.assertNotIn("safe_mechanical", decision["task_profile"]["signals"])

    def test_staged_owner_reconciles_delayed_sibling_before_order_check(self) -> None:
        session = "delayed-siblings"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-5.6-terra",
            "prompt": "Research three independent APIs in parallel and recommend an architecture.",
        })
        transcript = self._write_agent_transcript(session, [
            ("gpt56_terra_worker", "worker-a", "Evidence: a\nVerification: checked\nUncertainty: none"),
            ("gpt56_terra_worker", "worker-b", "Evidence: b\nVerification: checked\nUncertainty: none"),
        ])
        result = router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_type": "gpt56_sol_owner", "agent_id": "owner", "model": "gpt-5.6-sol",
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
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
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
            "model": "gpt-5.6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "route-up", "turn_id": "t1",
            "agent_id": "deep-one", "model": "gpt-5.6-terra", "reasoning_effort": "high",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "route-up", "turn_id": "t1",
            "agent_id": "deep-one", "model": "gpt-5.6-terra", "reasoning_effort": "high", "stop_hook_active": False,
            "last_assistant_message": (
                "ROUTE_UP\nEvidence: reproduction exhausted\nVerification: competing causes remain\nUncertainty: capability limit"
            ),
        })
        self.assertTrue(result["continue"])
        self.assertIn("Route-up accepted", result["systemMessage"])
        ledger = json.loads((Path(self.temp.name) / "route-up--t1.json").read_text())
        self.assertEqual("gpt56_sol_owner", ledger["decision"]["route"])
        self.assertEqual("Sol Medium Speed unknown", ledger["decision"]["visible_route"])
        self.assertEqual(1, len(ledger["escalations"]))
        self.assertEqual({"gpt56_sol_owner": 1}, ledger["decision"]["orchestration"]["required_agents"])
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "route-up", "turn_id": "t1",
            "agent_id": "owner-two", "model": "gpt-5.6-sol", "reasoning_effort": "medium",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "route-up", "turn_id": "t1",
            "agent_id": "owner-two", "model": "gpt-5.6-sol", "reasoning_effort": "medium", "stop_hook_active": False,
            "last_assistant_message": "Evidence: cause isolated\nVerification: regression check passed\nUncertainty: none",
        })
        final = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "route-up", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertTrue(final["continue"])
        ledger = json.loads((Path(self.temp.name) / "route-up--t1.json").read_text())
        self.assertNotIn("worker_cap_exceeded:1", ledger["violations"])
        self.assertEqual("COMPLETE", ledger["status"])

    def test_route_up_rejects_metadata_or_identity_confusion(self) -> None:
        session = "route-up-metadata"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-5.6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": session, "turn_id": "t1",
            "agent_id": "deep-one", "model": "gpt-5.6-terra", "reasoning_effort": "high",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": session, "turn_id": "t1",
            "agent_id": "deep-one", "model": "gpt-5.6-terra", "reasoning_effort": "high", "stop_hook_active": False,
            "last_assistant_message": (
                "ROUTE_UP\nEvidence: metadata is hidden and the versioned skill locator is missing\n"
                "Verification: cannot attest identity\nUncertainty: stale cache"
            ),
        })
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertIn("ROUTE_UP was ignored", result["systemMessage"])
        self.assertEqual([], ledger["escalations"])
        self.assertEqual("gpt56_terra_deep", ledger["decision"]["route"])
        self.assertIn("unsupported_route_up:gpt56_terra_deep", ledger["violations"])

    def test_transcript_fallback_settles_observable_nested_verification(self) -> None:
        session = "nested-verification"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "Fix a typo in README and run targeted tests.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "apply_patch", "tool_input": {}, "tool_response": {},
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": session, "turn_id": turn,
            "tool_name": "functions.exec",
            "tool_input": {"source": "const r = await tools.exec_command({cmd: 'python -m unittest'}); text(r.output)"},
            "tool_response": "tests passed",
        })
        metadata = {"turn_id": turn}
        transcript = Path(self.temp.name) / "nested-verification.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in [
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
        ]), encoding="utf-8")
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
            "model": "gpt-5.6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
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
            "model": "gpt-5.6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        }
        router_hook.handle(start)
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "s5", "turn_id": "child-turn",
            "agent_type": "gpt56_terra_deep",
        })
        ledger = json.loads((Path(self.temp.name) / "s5--parent-turn.json").read_text())
        self.assertIn("gpt56_terra_deep", ledger["subagents_started"])

    def test_stop_reconciles_missing_lifecycle_hooks_from_transcript(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s6", "turn_id": "t6",
            "model": "gpt-5.6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        }
        router_hook.handle(start)
        transcript = Path(self.temp.name) / "transcript.jsonl"
        records = [
            {"payload": {"type": "custom_tool_call", "input": 'tools.multi_agent_v1__spawn_agent({agent_type:"gpt56_terra_deep",message:"bounded"})'}},
            {"payload": {"type": "function_call_output", "output": '{"agent_id":"agent-123"}'}},
            {"payload": {"type": "message", "content": '<subagent_notification>{"agent_path":"agent-123","status":{"completed":"Evidence: x\\nVerification: y\\nUncertainty: z"}}</subagent_notification>'}},
        ]
        transcript.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
        child = Path(self.temp.name) / "rollout-agent-123.jsonl"
        child.write_text(json.dumps({
            "type": "turn_context", "payload": {"model": "gpt-5.6-terra", "effort": "high"}
        }), encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "s6", "turn_id": "t6",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        self.assertTrue(result["continue"])
        ledger = json.loads(next(path for path in Path(self.temp.name).glob("s6--*.json")).read_text())
        self.assertEqual(["gpt56_terra_deep"], ledger["subagents_completed"])
        self.assertTrue(ledger["reconciled_from_transcript"])
        self.assertTrue(ledger["agent_attestations"]["agent-123"]["matched"])

    def test_stop_reconciles_current_collaboration_transcript_shape(self) -> None:
        session = "collaboration-shape"
        turn = "t1"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": turn,
            "model": "gpt-5.6-terra",
            "prompt": "Research three independent APIs in parallel and recommend an architecture.",
        })
        transcript = Path(self.temp.name) / "collaboration-parent.jsonl"
        records = []
        roles = ["gpt56_terra_worker", "gpt56_terra_worker", "gpt56_sol_owner"]
        for index, role in enumerate(roles):
            call_id = f"call-{index}"
            agent_id = f"019f-child-{index}"
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
            (Path(self.temp.name) / f"rollout-{agent_id}.jsonl").write_text(json.dumps({
                "type": "turn_context", "payload": {"model": spec["model"], "effort": spec["effort"]}
            }), encoding="utf-8")
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
            item["type"] == "gpt56_terra_worker" and item["status"] == "completed"
            for item in ledger["agents"].values()
        ))

    def test_wrong_child_model_fails_attestation(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "attest", "turn_id": "t1",
            "model": "gpt-5.6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        transcript = Path(self.temp.name) / "attest-parent.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in [
            {"payload": {"type": "custom_tool_call", "input": 'tools.multi_agent_v1__spawn_agent({agent_type:"gpt56_terra_deep"})'}},
            {"payload": {"type": "function_call_output", "output": '{"agent_id":"agent-wrong"}'}},
            {"payload": {"type": "message", "content": '{"agent_path":"agent-wrong","status":{"completed":"Evidence: x Verification: y Uncertainty: z"}}'}},
        ]), encoding="utf-8")
        (Path(self.temp.name) / "rollout-agent-wrong.jsonl").write_text(json.dumps({
            "type": "turn_context", "payload": {"model": "gpt-5.6-luna", "effort": "low"}
        }), encoding="utf-8")
        result = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "attest", "turn_id": "t1",
            "stop_hook_active": False, "transcript_path": str(transcript),
        })
        self.assertTrue(result["continue"])
        self.assertNotIn("decision", result)
        self.assertIn("attest the child model", result["systemMessage"])

    def test_child_attestation_detects_advisor_mutation_and_recursive_spawn(self) -> None:
        parent = Path(self.temp.name) / "parent.jsonl"
        parent.write_text("", encoding="utf-8")
        child = Path(self.temp.name) / "rollout-advisor-proof.jsonl"
        child.write_text("\n".join(json.dumps(item) for item in [
            {"type": "turn_context", "payload": {"model": "gpt-5.6-terra", "effort": "medium"}},
            {"type": "custom_tool_call", "payload": {"type": "custom_tool_call", "name": "apply_patch"}},
            {"type": "custom_tool_call", "payload": {"type": "custom_tool_call", "name": "spawn_agent"}},
        ]), encoding="utf-8")
        attestation = router_hook._attest_child(parent, "advisor-proof", router_hook.ROUTES["gpt56_terra_worker"])
        self.assertTrue(attestation["matched"])
        self.assertTrue(attestation["mutation_seen"])
        self.assertTrue(attestation["recursive_spawn_seen"])

    def test_stable_subagent_start_attests_model_and_agent_config_without_transcript(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "stable-attest", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        output = router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "stable-attest", "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "stable-child", "model": "gpt-5.6-terra",
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
            "model": "gpt-5.6-terra", "prompt": "Hi",
        })
        outputs.append(router_hook.handle({
            "hook_event_name": "Stop", "session_id": "matrix-done", "turn_id": "t1", "stop_hook_active": False,
        }))
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "matrix-unmet", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
        })
        outputs.append(router_hook.handle({
            "hook_event_name": "Stop", "session_id": "matrix-unmet", "turn_id": "t1", "stop_hook_active": False,
        }))
        outputs.append(router_hook.handle({
            "hook_event_name": "Stop", "session_id": "matrix-unmet", "turn_id": "t1", "stop_hook_active": True,
        }))
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "matrix-child", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
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
            "model": "gpt-5.6-terra", "prompt": "Build a product, but I am not sure which architecture to use.",
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
            "model": "gpt-5.6-luna", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        transcript = Path(self.temp.name) / "tier-parent.jsonl"
        transcript.write_text("\n".join(json.dumps(item) for item in [
            {"payload": {"type": "custom_tool_call", "input": 'tools.multi_agent_v1__spawn_agent({agent_type:"gpt56_terra_deep",service_tier:"fast"})'}},
            {"payload": {"type": "function_call_output", "output": '{"agent_id":"agent-tier"}'}},
            {"payload": {"type": "message", "content": '{"agent_path":"agent-tier","status":{"completed":"Evidence: x Verification: y Uncertainty: z"}}'}},
        ]), encoding="utf-8")
        (Path(self.temp.name) / "rollout-agent-tier.jsonl").write_text(json.dumps({
            "type": "turn_context", "payload": {"model": "gpt-5.6-terra", "effort": "high"}
        }), encoding="utf-8")
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
            "model": "gpt-5.6-terra", "prompt": "Fix the typo in this file.",
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
