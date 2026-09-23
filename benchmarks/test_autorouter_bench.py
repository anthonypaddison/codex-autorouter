import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("autorouter_bench.py")
SPEC = importlib.util.spec_from_file_location("autorouter_bench", SCRIPT)
assert SPEC and SPEC.loader
bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)


class ArenaTests(unittest.TestCase):
    def test_route_contracts(self):
        self.assertEqual(0, bench.route_audit(strict=True))

    def test_live_case_prompts_select_the_expected_plan(self):
        router = bench._load_router()
        for case in bench.CASES:
            for profile in bench.AUTOROUTER_ARMS:
                with self.subTest(case=case.case_id, profile=profile):
                    decision = router.classify_prompt(
                        case.prompt, "gpt-6-luna", "low", profile, enforce_active_root=True
                    )
                    mode, roles = bench.EXPECTED_PLANS[case.case_id][profile]
                    active_roles = {}
                    for role, count in roles.items():
                        active_role = router._ACTIVE_ROUTE_ALIASES.get(role, role)
                        if active_role != "current":
                            active_roles[active_role] = active_roles.get(active_role, 0) + count
                    roles = active_roles
                    self.assertEqual(mode, decision["orchestration"]["mode"])
                    self.assertEqual(roles, decision["orchestration"]["required_agents"])

    def test_prepare_all_cases_and_graders_start_red(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bench.prepare(root, list(bench.CASES), clean=False)
            for case in bench.CASES:
                workspace = root / "starters" / case.case_id
                self.assertTrue((workspace / "TASK.md").is_file())
                result = subprocess.run(
                    [sys.executable, "benchmark_grader.py"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, result.returncode, case.case_id)
                payload = json.loads(result.stdout.strip().splitlines()[-1])
                self.assertLess(payload["score"], 1.0, case.case_id)

    def test_usage_parser_chooses_aggregate_total(self):
        with tempfile.TemporaryDirectory() as td:
            events = Path(td) / "events.jsonl"
            events.write_text(
                json.dumps({"usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}})
                + "\n"
                + json.dumps({"payload": {"total_token_usage": {"input_tokens": 50, "cached_input_tokens": 20, "output_tokens": 7, "reasoning_output_tokens": 3, "total_tokens": 57}}})
                + "\n",
                encoding="utf-8",
            )
            usage = bench._usage_from_events(events)
            self.assertEqual(57, usage["total_tokens"])
            self.assertEqual("TOKEN ESTIMATE", usage["provenance"])
            self.assertEqual("documented_total_token_usage", usage["aggregation"])

    def test_usage_parser_preserves_partial_observations_without_fake_total(self):
        with tempfile.TemporaryDirectory() as td:
            events = Path(td) / "events.jsonl"
            events.write_text(
                json.dumps({"thread_id": "root", "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}})
                + "\n"
                + json.dumps({"thread_id": "child", "usage": {"input_tokens": 50, "output_tokens": 7, "total_tokens": 57}})
                + "\n",
                encoding="utf-8",
            )
            usage = bench._usage_from_events(events)
            self.assertIsNone(usage["total_tokens"])
            self.assertEqual("TOKEN ESTIMATE", usage["provenance"])
            self.assertEqual("partial_per_thread", usage["aggregation"])
            self.assertEqual(2, len(usage["observations"]))
            self.assertNotIn(57, [usage["total_tokens"]])

    def test_live_run_requires_two_explicit_acknowledgements(self):
        parser = bench.parser()
        args = parser.parse_args(["run", "--case", "locale_batch"])
        self.assertEqual("gpt-6-luna", args.root_model)
        self.assertEqual("low", args.root_effort)
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(2, bench.run(args, Path(td), [bench.CASES[0]]))
        args = parser.parse_args(["run", "--case", "locale_batch", "--execute"])
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(2, bench.run(args, Path(td), [bench.CASES[0]]))

    def test_outsider_review_requires_separate_cost_acknowledgement(self):
        parser = bench.parser()
        args = parser.parse_args(["review", "--case", "locale_batch"])
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(2, bench.review(args, Path(td), [bench.CASES[0]]))
        args = parser.parse_args(["review", "--case", "locale_batch", "--execute"])
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(2, bench.review(args, Path(td), [bench.CASES[0]]))

    def test_arm_order_rotates_to_reduce_order_bias(self):
        self.assertEqual(bench.ARMS, bench._arm_order(1))
        self.assertEqual(bench.ARMS[1:] + bench.ARMS[:1], bench._arm_order(2))
        self.assertEqual(set(bench.ARMS), set(bench._arm_order(7)))

    def test_live_matrix_restores_the_users_original_profile(self):
        args = bench.parser().parse_args([
            "run", "--case", "locale_batch", "--execute", "--trust-reviewed-hooks"
        ])
        profile_calls = []

        def profile(value=None):
            profile_calls.append(value)
            return "balanced" if value is None else value

        fake_result = {
            "case": "locale_batch", "arm": "baseline", "quality": {"passed": 0, "total": 1},
            "routing": {"passed": True}, "elapsed_seconds": 0, "usage": None,
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(bench, "_profile", side_effect=profile), \
                mock.patch.object(bench, "_run_one", return_value=fake_result), \
                mock.patch.object(bench, "_render_report"):
            self.assertEqual(0, bench.run(args, Path(td), [bench.CASES[0]]))
        self.assertEqual([None, "token-saver", "balanced", "max-quality", "balanced"], profile_calls)

    def test_blind_packet_hides_profiles_tokens_and_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bench.prepare(root, [bench.CASES[0]], clean=False)
            results = []
            for arm in bench.ARMS:
                workspace = bench._copy_starter(root, bench.CASES[0], arm, 1)
                (workspace / "normalize_catalogs.py").write_text("print('candidate')\n", encoding="utf-8")
                (workspace.parent / "final.txt").write_text("Route: Luna Low Fast\nToken Saver implementation verified.\n", encoding="utf-8")
                results.append({
                    "case": "locale_batch",
                    "arm": arm,
                    "repetition": 1,
                    "workspace": str(workspace),
                    "usage": {"total_tokens": 999999},
                    "quality": {"passed": 1, "total": 1, "checks": [{"name": "x", "passed": True}]},
                    "elapsed_seconds": 99,
                })
            packet, mapping = bench._blind_packet(bench.CASES[0], 1, results)
            serialized = json.dumps(packet)
            self.assertEqual(set(bench.ARMS), set(mapping.values()))
            for hidden in (*bench.ARMS, "999999", str(root)):
                self.assertNotIn(hidden, serialized)
            self.assertNotIn("Luna", serialized)
            self.assertTrue(packet["blindness_contract"]["token_and_latency_hidden"])

    def test_panel_fold_requires_full_quorum_and_unblinds_after_scoring(self):
        ids = [f"artifact-{index}" for index in range(4)]
        mapping = dict(zip(ids, bench.ARMS))
        packet = {"packet_digest": "abc", "artifacts": [{"artifact_id": value} for value in ids]}
        results = [{"arm": arm, "quality": {}, "usage": {"total_tokens": index + 10}, "elapsed_seconds": 1} for index, arm in enumerate(bench.ARMS)]

        def row(seat, top):
            artifacts = {artifact_id: {"quality_score": 80 + index, "safety_veto": False, "recommended_changes": [f"repair {artifact_id}"]} for index, artifact_id in enumerate(ids)}
            return {"seat": seat, "status": "scored", "review": {"ranking": [top] + [value for value in ids if value != top], "artifacts": artifacts}}

        partial = bench._fold_panel(packet, mapping, [row("glm", ids[1])], results)
        self.assertFalse(partial["official"])
        full = bench._fold_panel(packet, mapping, [row("glm", ids[1]), row("deepseek", ids[1])], results)
        self.assertTrue(full["official"])
        self.assertEqual("token-saver", full["consensus_winner"])
        self.assertEqual(11, full["arms"]["token-saver"]["total_tokens"])

    def test_private_reviewer_pipeline_writes_only_full_quorum_as_official(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bench.prepare(root, [bench.CASES[0]], clean=False)
            results = []
            for index, arm in enumerate(bench.ARMS):
                workspace = bench._copy_starter(root, bench.CASES[0], arm, 1)
                (workspace / "normalize_catalogs.py").write_text(f"print({index})\n", encoding="utf-8")
                (workspace.parent / "final.txt").write_text("Done.\n", encoding="utf-8")
                results.append({
                    "case": "locale_batch", "arm": arm, "repetition": 1, "workspace": str(workspace),
                    "usage": {"total_tokens": 100 + index}, "elapsed_seconds": 1,
                    "quality": {"passed": 1, "total": 1, "checks": []},
                })
            (root / "report.json").write_text(json.dumps({"results": results}), encoding="utf-8")

            def provider(seat, packet, timeout, key_override=None):
                ids = [item["artifact_id"] for item in packet["artifacts"]]
                artifacts = {
                    artifact_id: {
                        "quality_score": 80, "correctness": 80, "completeness": 80,
                        "robustness": 80, "maintainability": 80, "verification": 80,
                        "safety_veto": False, "strengths": [], "weaknesses": [],
                        "recommended_changes": ["Tighten one edge case."],
                    }
                    for artifact_id in ids
                }
                return {"seat": seat.seat, "status": "scored", "review": {"ranking": ids, "artifacts": artifacts}}

            args = bench.parser().parse_args([
                "review", "--output", str(root), "--case", "locale_batch", "--execute",
                "--acknowledge-external-review-cost",
            ])
            with mock.patch.dict(os.environ, {"ZAI_API_KEY": "test", "DEEPSEEK_API_KEY": "test"}), \
                    mock.patch.object(bench, "_provider_review", side_effect=provider):
                self.assertEqual(0, bench.review(args, root, [bench.CASES[0]]))
            report = json.loads((root / "outsider-review.json").read_text(encoding="utf-8"))
            self.assertEqual(1, report["official_panel_count"])
            self.assertTrue(report["panels"][0]["full_quorum"])
            self.assertIn("token-saver", report["profile_summary"])


if __name__ == "__main__":
    unittest.main()
