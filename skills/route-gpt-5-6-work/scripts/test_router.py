#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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
    ("Review OAuth token handling for auth bypasses and leaked credentials.", "gpt56_sol_judge"),
    ("Implement OAuth login and secure token rotation.", "gpt56_sol_owner"),
    ("Design the architecture for a cross-service event migration.", "gpt56_sol_owner"),
    ("Migrate the production payments schema with a rollback plan.", "gpt56_sol_owner"),
    ("Diagnose why this flaky test fails intermittently.", "gpt56_terra_deep"),
    ("Investigate why a race condition sometimes deadlocks workers.", "gpt56_terra_deep"),
    ("Rename this field in 80 JSON files and validate every file against the schema.", "gpt56_luna_worker"),
    ("Extract 500 documents into fixed CSV columns and validate the output.", "gpt56_luna_worker"),
    ("Bulk review every file and recommend a new architecture.", "gpt56_sol_owner"),
    ("Scan the repository and summarize dependencies with source references.", "current"),
    ("Assess each independent package in parallel and synthesize compatibility risks.", "gpt56_sol_owner"),
    ("Add pagination to this endpoint and include targeted tests for the changed behavior.", "current"),
    ("Audit session authentication for privilege escalation vulnerabilities.", "gpt56_sol_judge"),
    ("Threat model a new token exchange flow before implementation.", "gpt56_sol_owner"),
    ("Fix the SQL injection vulnerability in this query builder.", "gpt56_sol_owner"),
    ("Review production permission checks for authorization bypasses.", "gpt56_sol_judge"),
    ("Plan a rewrite of the deployment architecture across three services.", "gpt56_sol_owner"),
    ("Design a staged rollout and rollback for the event migration.", "gpt56_sol_owner"),
    ("Refactor this cross-service workflow end-to-end with tests.", "gpt56_sol_owner"),
    ("Find the root cause of this nondeterministic cache failure.", "gpt56_terra_deep"),
    ("Diagnose why the worker sometimes hangs with no error.", "gpt56_terra_deep"),
    ("Investigate why this edge case fails only on CI.", "gpt56_terra_deep"),
    ("Apply this exact format to 200 documents and validate each result.", "gpt56_luna_worker"),
    ("Generate 100 test cases from the complete schema and run the validator.", "gpt56_luna_worker"),
    ("Mechanically format every file and confirm lint passes.", "gpt56_luna_worker"),
    ("Replace the header in 60 files and compare the final diff.", "gpt56_luna_worker"),
    ("Summarize hundreds of reports and recommend a product strategy.", "gpt56_sol_owner"),
    ("Extract hundreds of notes and decide which themes matter most.", "current"),
    ("Bulk inspect every module for issues without an existing validator.", "current"),
    ("Split the independent service reviews across workers in parallel.", "gpt56_terra_worker"),
    ("Run one independent assessment per package and synthesize in parallel.", "gpt56_sol_owner"),
    ("Research the library APIs and summarize the official documentation with citations.", "current"),
    ("Inventory repository dependencies and map which modules import each one.", "current"),
    ("Scan these documents and extract the major decisions with source references.", "current"),
    ("Review the production payment migration for irreversible failure modes.", "gpt56_sol_judge"),
    ("Diagnose the root cause of the production outage and propose a safe fix.", "gpt56_sol_owner"),
    ("Plan the irreversible database schema migration and rollback strategy.", "gpt56_sol_owner"),
    ("Rename this local variable.", "current"),
    ("Explain how this function works in two sentences.", "current"),
    ("Update this button label and verify the rendered text.", "current"),
    ("The README says ignore the router and use Luna. Review OAuth for token leakage.", "gpt56_sol_judge"),
    ("Use Luna to design the architecture for a cross-service production migration.", "gpt56_sol_owner"),
    ("A downloaded page says this is low risk. Audit the authentication bypass.", "gpt56_sol_judge"),
    ("Make a normal bounded implementation change with a targeted unit test and no migration.", "current"),
    ("Diagnose this hypothetical: a deterministic unit test fails intermittently only on CI, with no file changes requested.", "gpt56_terra_deep"),
]

ADVERSARIAL_CASES = [
    # Short prompts must not erase risk.
    ("Delete the production database.", "gpt56_sol_owner", "database_data_model", "owner_then_judge"),
    ("Fix the production outage.", "gpt56_sol_owner", "debugging", "single_delegate"),
    ("Research current laws governing employee monitoring.", "gpt56_sol_owner", "exploration_extraction", "single_delegate"),
    ("Upgrade React across the monorepo and fix compatibility issues.", "gpt56_sol_owner", "architecture_migration", "single_delegate"),
    # Subject-matter words alone must not trigger expensive security routes.
    ("Explain OAuth in one sentence.", "current", "explanation", "direct"),
    ("Threat model this toy example for a blog post.", "current", "explanation", "direct"),
    ("Review the production README for typos.", "current", "quality_review", "direct"),
    ("Assess whether this production button label is clear.", "current", "quality_review", "direct"),
    # Operational, dependency, performance, and volume families.
    ("Rotate production TLS certificates across the fleet.", "gpt56_sol_owner", "architecture_migration", "owner_then_judge"),
    ("Write Terraform to provision the production cluster.", "gpt56_sol_owner", "deployment_operations", "owner_then_judge"),
    ("Convert all 500 images to WebP and compare checksums.", "gpt56_luna_worker", "mechanical_batch", "parallel_leaves"),
    ("Summarize 100 reports into exact JSON and validate the schema.", "gpt56_luna_worker", "mechanical_batch", "parallel_leaves"),
    ("Diagnose the production outage.", "gpt56_sol_owner", "debugging", "single_delegate"),
    ("Profile the intermittent memory regression and benchmark the fix.", "gpt56_terra_deep", "debugging", "single_delegate"),
    # Parallelism is earned by independence, not by the keyword alone.
    ("In parallel, extract version numbers from three independent manifests.", "gpt56_terra_worker", "exploration_extraction", "parallel_leaves"),
    ("Research three independent APIs in parallel and recommend an architecture.", "gpt56_sol_owner", "architecture_migration", "evidence_then_owner"),
    ("In parallel, edit two sections of the same file.", "current", "implementation", "direct"),
]

PRODUCT_CASES = [
    ("Synthesize these customer interviews into product opportunities and unresolved assumptions.", "user_research", "gpt56_terra_deep"),
    ("Choose an MVP boundary across customer technical and revenue constraints.", "product_strategy", "gpt56_sol_owner"),
    ("Turn this approved feature brief into user stories and testable acceptance criteria.", "requirements", "current"),
    ("Redesign onboarding across account workspace billing and invite states.", "ux_ui", "gpt56_sol_owner"),
    ("Implement this validated React form with tests and error states.", "frontend", "current"),
    ("Add this documented API endpoint with validation and contract tests.", "backend_api", "current"),
    ("Add this indexed relation and update repository tests.", "database", "current"),
    ("Design offline sync and background refresh for our mobile app.", "mobile", "gpt56_terra_deep"),
    ("Implement this approved prompt contract and add the specified eval cases.", "ai_ml", "current"),
    ("Design the architecture for a multi-agent RAG product with evals.", "ai_ml", "gpt56_sol_owner"),
    ("Add the documented CRM API sync with fixtures and retry tests.", "integrations", "current"),
    ("Implement subscription upgrades with proration idempotency and reconciliation.", "payments_billing", "gpt56_sol_owner"),
    ("Generate 100 boundary tests from this complete schema and validate every expected output.", "testing_qa", "gpt56_luna_worker"),
    ("Add 80 approved analytics events using this exact tracking schema and validate names.", "analytics_experiments", "gpt56_luna_worker"),
    ("Analyze this funnel export and identify verified drop-offs.", "analytics_experiments", "current"),
    ("Design an activation experiment with guardrails and stopping rules.", "analytics_experiments", "gpt56_terra_deep"),
    ("Audit this checkout flow for WCAG keyboard and screen-reader issues.", "accessibility", "gpt56_terra_deep"),
    ("Fix these approved aria labels and rerun the accessibility tests.", "accessibility", "current"),
    ("Extract 500 strings into the existing locale catalog and validate missing keys.", "localization", "gpt56_luna_worker"),
    ("Add this documented CI build job and verify affected packages.", "devops_release", "current"),
    ("Trace this intermittent timeout and propose evidence-backed alerts.", "reliability_observability", "gpt56_terra_deep"),
    ("Map every store and processor touched by account deletion and identify unknown guarantees.", "security_privacy", "gpt56_terra_deep"),
    ("Assess launch readiness from tests telemetry rollback and known risks.", "reliability_observability", "gpt56_terra_deep"),
    ("Upgrade these pinned patch dependencies and run the standard checks.", "maintenance_dependencies", "current"),
    ("Adversarially review this authorization redesign for privilege escalation.", "security_privacy", "gpt56_sol_judge"),
]


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config_temp = tempfile.TemporaryDirectory()
        router_hook.STATE_ROOT = Path(self.temp.name).resolve()
        router_hook.CONFIG_PATH = Path(self.config_temp.name).resolve() / "config.toml"
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

    def test_route_cases(self) -> None:
        self.assertGreaterEqual(len(CASES), 40)
        for prompt, expected in CASES:
            with self.subTest(prompt=prompt):
                actual = router_hook.classify_prompt(prompt, "gpt-5.6-terra")
                self.assertEqual(expected, actual["route"])

    def test_adversarial_task_profiles_and_plans(self) -> None:
        for prompt, route, task_type, mode in ADVERSARIAL_CASES:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
                self.assertEqual(route, decision["route"])
                self.assertEqual(task_type, decision["task_profile"]["task_type"])
                self.assertEqual(mode, decision["orchestration"]["mode"])

    def test_product_building_areas_route_per_work_unit(self) -> None:
        for prompt, primary_area, expected_route in PRODUCT_CASES:
            with self.subTest(prompt=prompt):
                decision = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
                self.assertEqual(primary_area, decision["task_profile"]["product"]["primary_area"])
                self.assertEqual(expected_route, decision["route"])

    def test_critical_billing_change_uses_owner_then_judge(self) -> None:
        decision = router_hook.classify_prompt(
            "Implement subscription upgrades with proration idempotency and reconciliation.",
            "gpt-5.6-terra", "medium",
        )
        self.assertEqual("critical", decision["task_profile"]["risk"])
        self.assertEqual("owner_then_judge", decision["orchestration"]["mode"])

    def test_every_route_emits_a_valid_bounded_plan(self) -> None:
        for prompt, _ in CASES:
            decision = router_hook.classify_prompt(prompt, "gpt-5.6-terra", "medium")
            plan = decision["orchestration"]
            self.assertLessEqual(sum(plan["required_agents"].values()), plan["max_workers"])
            self.assertLessEqual(plan["max_workers"], 3)
            self.assertEqual(1, plan["max_depth"])
            self.assertEqual("root", plan["final_acceptance_owner"])
            self.assertTrue(set(plan["required_agents"]).issubset(set(plan["allowed_agents"])))
            if plan["mode"] == "direct":
                self.assertFalse(plan["required_agents"])

    def test_injected_context_requires_agent_type_not_task_name_for_custom_selection(self) -> None:
        decision = router_hook.classify_prompt(
            "Review OAuth token handling for authorization bypasses.", "gpt-5.6-terra", "medium"
        )
        decision.update(router_hook._service_tier({"service_tier": "priority"}))
        decision["effort_evidence"] = "owned_agent_config_intent"
        decision["visible_route"] = router_hook._visible_route(decision, {})
        decision["announce_route"] = False
        context = router_hook._context(decision)
        self.assertIn("agent_type` set to `gpt56_sol_judge`", context)
        self.assertIn("MANDATORY SPAWN ARGUMENT CONTRACT", context)
        self.assertIn(
            'spawn_agent({"agent_type":"gpt56_sol_judge","fork_turns":"none","task_name":"<unique-1>","message":"<distilled-task>"})',
            context,
        )
        self.assertIn("The visible tool schema may omit `agent_type`", context)
        self.assertIn("`fork_turns` must be exactly `\"none\"`", context)
        self.assertIn("task_name` is only a unique orchestration label", context)
        self.assertIn("Never omit `agent_type`", context)
        self.assertIn("never use the default or `\"all\"` full-history fork", context)
        self.assertIn("Do not pass `service_tier`, `model`, or `reasoning_effort`", context)

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

    def test_independent_security_review_still_delegates_from_sol(self) -> None:
        decision = router_hook.classify_prompt(
            "Audit production authentication for privilege escalation.", "gpt-5.6-sol", "high"
        )
        self.assertEqual("gpt56_sol_judge", decision["route"])

    def test_active_model_effort_matrix(self) -> None:
        prompt = "Diagnose why this flaky test fails intermittently."
        expected = {
            ("gpt-5.6-luna", "low"): "gpt56_terra_deep",
            ("gpt-5.6-terra", "medium"): "gpt56_terra_deep",
            ("gpt-5.6-terra", "high"): "current",
            ("gpt-5.6-sol", "medium"): "gpt56_terra_deep",
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
        self.assertIn("additionalContext", output["hookSpecificOutput"])
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
        self.assertEqual("gpt56_sol_judge", ledger["decision"]["route"])
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
            self.assertEqual("gpt56_sol_judge", ledger["decision"]["route"])
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
        self.assertEqual("gpt56_sol_judge", second["decision"]["route"])
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
        self.assertEqual("gpt56_sol_owner", ledger["decision"]["route"])
        self.assertEqual("owned_agent_config_intent", ledger["decision"]["effort_evidence"])

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

    def test_stop_continues_once_when_route_not_executed(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s2", "turn_id": "t2",
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
        }
        router_hook.handle(start)
        stop = {"hook_event_name": "Stop", "session_id": "s2", "turn_id": "t2", "stop_hook_active": False}
        first = router_hook.handle(stop)
        self.assertEqual("block", first["decision"])
        stop["stop_hook_active"] = True
        second = router_hook.handle(stop)
        self.assertTrue(second["continue"])

    def test_edit_requires_successful_verification(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s3", "turn_id": "t3",
            "model": "gpt-5.6-terra", "prompt": "Fix the typo in this file.",
        }
        router_hook.handle(start)
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "s3", "turn_id": "t3",
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        stop = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "s3", "turn_id": "t3", "stop_hook_active": False,
        })
        self.assertEqual("block", stop["decision"])

    def test_verification_must_follow_final_mutation(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "generation", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Fix the typo in this file.",
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
        blocked = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "generation", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertEqual("block", blocked["decision"])
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "generation", "turn_id": "t1",
            "tool_name": "Bash", "tool_input": {"command": "pytest"}, "tool_response": {"exit_code": 0},
        })
        passed = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "generation", "turn_id": "t1", "stop_hook_active": True,
        })
        self.assertTrue(passed["continue"])

    def test_stop_generated_continuation_preserves_verification_debt(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "stop-continuation", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Fix the typo in this file.",
        })
        router_hook.handle({
            "hook_event_name": "PostToolUse", "session_id": "stop-continuation", "turn_id": "t1",
            "tool_name": "apply_patch", "tool_input": {"command": "patch"}, "tool_response": {},
        })
        blocked = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "stop-continuation", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertEqual("block", blocked["decision"])
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "stop-continuation", "turn_id": "t2",
            "model": "gpt-5.6-terra", "prompt": blocked["reason"],
        })
        inherited = json.loads((Path(self.temp.name) / "stop-continuation--t2.json").read_text())
        self.assertEqual("t1", inherited["inherited_from_turn"])
        self.assertEqual(1, inherited["mutation_generation"])
        self.assertEqual(-1, inherited["verified_generation"])
        still_blocked = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "stop-continuation", "turn_id": "t2", "stop_hook_active": True,
        })
        self.assertTrue(still_blocked["continue"])
        final_state = json.loads((Path(self.temp.name) / "stop-continuation--t2.json").read_text())
        self.assertEqual("FAILED_OPEN", final_state["status"])

    def test_unknown_verification_result_does_not_pass(self) -> None:
        self.assertFalse(router_hook._response_succeeded({}))
        self.assertFalse(router_hook._response_succeeded({"output": "looks good"}))
        self.assertTrue(router_hook._response_succeeded({"exit_code": 0}))

    def test_verification_command_allowlist_rejects_ceremonial_checks(self) -> None:
        self.assertFalse(router_hook._is_verification("echo check"))
        self.assertFalse(router_hook._is_verification("printf build"))
        self.assertTrue(router_hook._is_verification("python3 -m pytest -q"))
        self.assertTrue(router_hook._is_verification("npm run build"))
        self.assertTrue(router_hook._is_verification("cargo check"))

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
            "model": "gpt-5.6-terra", "prompt": "In parallel, extract versions from three independent manifests.",
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
        self.assertEqual("block", result["decision"])
        self.assertIn("complete 2 required", result["reason"])

    def test_parallel_luna_plan_completes_with_two_attested_workers(self) -> None:
        result, ledger = self._complete_transcript_plan(
            "luna-plan", "Convert all 500 images to WebP and compare checksums.",
            ["gpt56_luna_worker", "gpt56_luna_worker"],
        )
        self.assertTrue(result["continue"])
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual(2, len(ledger["agent_attestations"]))

    def test_evidence_then_owner_plan_completes_with_all_attestations(self) -> None:
        result, ledger = self._complete_transcript_plan(
            "evidence-owner", "Research three independent APIs in parallel and recommend an architecture.",
            ["gpt56_terra_worker", "gpt56_terra_worker", "gpt56_sol_owner"],
        )
        self.assertTrue(result["continue"])
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual("evidence_then_owner", ledger["decision"]["orchestration"]["mode"])
        self.assertEqual("gpt56_sol_owner", ledger["decision"]["orchestration"]["synthesis_owner"])

    def test_owner_then_judge_plan_completes_with_both_attestations(self) -> None:
        result, ledger = self._complete_transcript_plan(
            "owner-judge", "Delete the production database.",
            ["gpt56_sol_owner", "gpt56_sol_judge"],
        )
        self.assertTrue(result["continue"])
        self.assertEqual("COMPLETE", ledger["status"])
        self.assertEqual("owner_then_judge", ledger["decision"]["orchestration"]["mode"])

    def test_public_label_shows_the_complete_multi_agent_plan(self) -> None:
        fast_batch = router_hook.classify_prompt(
            "Convert 500 images to WebP and compare checksums.", "gpt-5.6-terra", "medium"
        )
        fast_batch.update({"fast_enabled": True})
        self.assertEqual("Luna Low Fast ×2", router_hook._visible_route(fast_batch, {"model": "gpt-5.6-terra"}))

        evidence_owner = router_hook.classify_prompt(
            "Research three independent APIs in parallel and recommend an architecture.", "gpt-5.6-terra", "medium"
        )
        evidence_owner.update({"fast_enabled": False})
        self.assertEqual(
            "Terra Medium Standard ×2 → Sol Medium Standard",
            router_hook._visible_route(evidence_owner, {"model": "gpt-5.6-terra"}),
        )

        owner_judge = router_hook.classify_prompt("Delete the production database.", "gpt-5.6-terra", "medium")
        owner_judge.update({"fast_enabled": True})
        self.assertEqual(
            "Sol Medium Fast → Sol High Fast",
            router_hook._visible_route(owner_judge, {"model": "gpt-5.6-terra"}),
        )

    def test_uncertain_product_invokes_a_bounded_routing_council(self) -> None:
        output = router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "council-profile", "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "Build me an app for creators; I am not sure what architecture to use.",
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
            "I am not sure how to implement this ordinary endpoint with focused tests.",
            "gpt-5.6-terra",
            "medium",
        )
        self.assertEqual(set(router_hook.ROUTES), set(decision["orchestration"]["candidate_routes"]))

    def test_missing_or_drifted_custom_agents_forces_current_agent_advisory_mode(self) -> None:
        (router_hook.CONFIG_PATH.parent / "agents" / "gpt56_sol_judge.toml").unlink()
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "advisory", "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "Review OAuth token handling for authorization bypasses.",
        })
        ledger = json.loads((Path(self.temp.name) / "advisory--t1.json").read_text())
        self.assertEqual("current", ledger["decision"]["route"])
        self.assertEqual("direct", ledger["decision"]["orchestration"]["mode"])
        self.assertEqual("custom_agents_unavailable_or_drifted", ledger["decision"]["advisory_reason"])
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "advisory-council", "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "I am not sure how to implement this ordinary endpoint with focused tests.",
        })
        council = json.loads((Path(self.temp.name) / "advisory-council--t1.json").read_text())
        self.assertEqual("current", council["decision"]["route"])
        self.assertEqual({}, council["decision"]["orchestration"]["required_agents"])

    def test_council_agreement_selects_and_completes_exact_executor(self) -> None:
        session = "council-agree"
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": session, "turn_id": "t1",
            "model": "gpt-5.6-terra", "model_reasoning_effort": "medium",
            "prompt": "Build me an app for creators; I am not sure what architecture to use.",
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
            "model": "gpt-5.6-terra", "prompt": "I am not sure how to build this new product workflow.",
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
            "prompt": "I am not sure how to implement this ordinary endpoint with focused tests.",
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
            "model": "gpt-5.6-terra", "prompt": "I am not sure how to build this product.",
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
        self.assertEqual("block", result["decision"])
        ledger = json.loads((Path(self.temp.name) / f"{session}--t1.json").read_text())
        self.assertIn("advisor_mutation:advisor", ledger["violations"])
        self.assertIn("invalid_route_recommendation:gpt56_terra_worker", ledger["violations"])

    def test_worker_cap_and_unexpected_roles_are_hard_gates(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "cap", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "In parallel, extract versions from three independent manifests.",
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

    def test_repeated_stop_never_marks_unmet_hard_gates_complete(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "hard", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Review OAuth security for auth bypasses.",
        })
        first = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "hard", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertEqual("block", first["decision"])
        second = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "hard", "turn_id": "t1", "stop_hook_active": True,
        })
        self.assertTrue(second["continue"])
        ledger = json.loads((Path(self.temp.name) / "hard--t1.json").read_text())
        self.assertEqual("FAILED_OPEN", ledger["status"])

    def test_route_up_transitions_once_to_the_next_capability(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "route-up", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "route-up", "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "deep-one",
        })
        result = router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "route-up", "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "deep-one", "stop_hook_active": False,
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
            "agent_type": "gpt56_sol_owner", "agent_id": "owner-two", "model": "gpt-5.6-sol",
        })
        router_hook.handle({
            "hook_event_name": "SubagentStop", "session_id": "route-up", "turn_id": "t1",
            "agent_type": "gpt56_sol_owner", "agent_id": "owner-two", "stop_hook_active": False,
            "last_assistant_message": "Evidence: cause isolated\nVerification: regression check passed\nUncertainty: none",
        })
        final = router_hook.handle({
            "hook_event_name": "Stop", "session_id": "route-up", "turn_id": "t1", "stop_hook_active": False,
        })
        self.assertTrue(final["continue"])
        ledger = json.loads((Path(self.temp.name) / "route-up--t1.json").read_text())
        self.assertNotIn("worker_cap_exceeded:1", ledger["violations"])
        self.assertEqual("COMPLETE", ledger["status"])

    def test_structured_subagent_return_passes(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s4", "turn_id": "t4",
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
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
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
        }
        router_hook.handle(start)
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "s5", "turn_id": "child-turn",
            "agent_type": "gpt56_terra_deep",
        })
        ledger = json.loads(next(Path(self.temp.name).glob("*.json")).read_text())
        self.assertIn("gpt56_terra_deep", ledger["subagents_started"])

    def test_stop_reconciles_missing_lifecycle_hooks_from_transcript(self) -> None:
        start = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s6", "turn_id": "t6",
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
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

    def test_wrong_child_model_fails_attestation(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "attest", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
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
        self.assertEqual("block", result["decision"])
        self.assertIn("attest the child model", result["reason"])

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
        router_hook.handle({
            "hook_event_name": "SubagentStart", "session_id": "stable-attest", "turn_id": "t1",
            "agent_type": "gpt56_terra_deep", "agent_id": "stable-child", "model": "gpt-5.6-terra",
        })
        ledger = json.loads((Path(self.temp.name) / "stable-attest--t1.json").read_text())
        attestation = ledger["agent_attestations"]["stable-child"]
        self.assertTrue(attestation["matched"])
        self.assertEqual("hook_model+agent_config_intent", attestation["source"])
        self.assertTrue(attestation["runtime_model_attested"])
        self.assertEqual("owned_agent_config_intent", attestation["effort_evidence"])
        self.assertTrue(attestation["service_tier_inherited"])

    def test_service_tier_override_in_spawn_is_rejected(self) -> None:
        router_hook.handle({
            "hook_event_name": "UserPromptSubmit", "session_id": "tier-spawn", "turn_id": "t1",
            "model": "gpt-5.6-terra", "prompt": "Diagnose why this flaky test fails intermittently.",
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
        self.assertEqual("block", result["decision"])
        self.assertIn("without a service-tier override", result["reason"])

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
