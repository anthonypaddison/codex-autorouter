from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_release

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_documented_installs_match_the_referenced_hook_manifests(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        install = (ROOT / "docs/INSTALL.md").read_text(encoding="utf-8")
        candidate = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        signature = validate_release.hook_signature(candidate)
        published = validate_release.published_hook_signature(archive=True)
        validate_release.validate_hook_docs(readme, install, published, signature)

        for label, before, after in (
            ("published count", "Published `v0.3.0` | 5", "Published `v0.3.0` | 6"),
            ("published guard", "Published `v0.3.0` | 5 | No", "Published `v0.3.0` | 5 | Yes"),
            ("candidate guard", "candidate | 6 | Yes", "candidate | 6 | No"),
        ):
            with self.subTest(label=label):
                bad_install = install.replace(before, after)
                self.assertNotEqual(install, bad_install)
                with self.assertRaisesRegex(AssertionError, "hook documentation"):
                    validate_release.validate_hook_docs(readme, bad_install, published, signature)
        for ref in ("v0.3.0", "v0.4.0-experimental.1"):
            with self.subTest(ref=ref), self.assertRaisesRegex(AssertionError, "install ref"):
                validate_release.validate_hook_docs(
                    readme.replace(f"--ref {ref}", "--ref main"), install, published, signature,
                )

    def test_published_hook_snapshot_must_match_the_git_tag(self) -> None:
        unexpected = json.dumps({"hooks": {
            "PreToolUse": [{"matcher": "collaborationspawn_agent", "hooks": [{"type": "command"}]}],
        }})
        with patch.object(validate_release.subprocess, "check_output", return_value=unexpected):
            with self.assertRaisesRegex(AssertionError, "published hook snapshot"):
                validate_release.published_hook_signature(archive=False)

    def test_checkout_mode_rejects_an_enclosing_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run(["git", "init", "--quiet", temp], check=True)
            extracted = (Path(temp) / "extracted").resolve()
            extracted.mkdir()
            with patch.object(validate_release, "ROOT", extracted):
                with self.assertRaisesRegex(AssertionError, "with --archive"):
                    validate_release.release_paths(archive=False)

    def test_extracted_archive_uses_its_own_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.object(validate_release, "ROOT", Path(temp)):
            (Path(temp) / "README.md").touch()
            self.assertEqual(validate_release.release_paths(archive=True), [Path("README.md")])
            (Path(temp) / ".env").touch()
            with self.assertRaisesRegex(AssertionError, "local-only"):
                validate_release.release_paths(archive=True)

    def test_local_secrets_and_trial_data_cannot_enter_release_inputs(self) -> None:
        for name in (".env", ".env.local", ".all-env", "auth.json", "autorouter-acceptance.json", ".trigger-tree/history.jsonl", "router-state-v2/turn.json"):
            with self.subTest(name=name), self.assertRaisesRegex(AssertionError, "local-only"):
                validate_release.candidate_source_paths({name}, set())
        self.assertEqual([Path(".env.example")], validate_release.candidate_source_paths({".env.example"}, set()))

    def test_ignored_generated_runtime_artifacts_do_not_become_candidate_drift(self) -> None:
        paths = validate_release.candidate_source_paths(
            {"src/keep.py"},
            {"src/new.py", "src/__pycache__/new.cpython-314.pyc", "src/.DS_Store"},
        )
        self.assertEqual({"src/keep.py", "src/new.py"}, {path.as_posix() for path in paths})

    def test_tracked_or_packaged_generated_artifacts_remain_release_failures(self) -> None:
        with self.assertRaisesRegex(AssertionError, "generated artifact"):
            validate_release.candidate_source_paths({"src/__pycache__/tracked.pyc"}, set())
        self.assertEqual(
            {"src/generated.py"},
            {path.as_posix() for path in validate_release.candidate_source_paths(
                {"src/generated.py"}, {"src/__pycache__/generated.pyc"}
            )},
        )

    def test_marketplace_uses_fork_and_immutable_candidate_ref(self) -> None:
        marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        source = marketplace["plugins"][0]["source"]

        self.assertEqual(source["url"], "https://github.com/anthonypaddison/Codex-Autorouter.git")
        self.assertEqual(source["ref"], "v0.4.0-experimental.1")
        self.assertNotIn(source["ref"].lower(), {"main", "master", "head"})

    def test_manifest_identifies_candidate_without_losing_original_author(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], "0.4.0-experimental.1")
        self.assertEqual(manifest["author"]["name"], "Alchemist")
        self.assertEqual(manifest["interface"]["websiteURL"], "https://github.com/anthonypaddison/Codex-Autorouter")

    def test_operator_docs_state_the_cheap_root_and_readiness_contract(self) -> None:
        docs = "\n".join(
            [
                (ROOT / "README.md").read_text(encoding="utf-8"),
                (ROOT / "docs/TROUBLESHOOTING.md").read_text(encoding="utf-8"),
            ]
        )

        for required in (
            'model = "gpt-6-luna"',
            'model_reasoning_effort = "low"',
            "python3 scripts/check_hooks.py",
            "READY",
            "DEGRADED",
            "substantially reduced",
            "UserPromptSubmit.model",
            "Luna Low",
            "Luna Medium",
            "paid probe",
            "legacy",
        ):
            self.assertIn(required, docs)

        self.assertNotIn("routerctl.py activate\n", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_release_procedure_requires_reviewed_tag_archive_and_sha256(self) -> None:
        release = (ROOT / "docs/RELEASING.md").read_text(encoding="utf-8")

        for required in ("v0.3.0", "git tag", "archive", "SHA256", "scripts/validate_release.py"):
            self.assertIn(required, release)

    def test_astra_frontier_policy_is_part_of_the_release_contract(self) -> None:
        skill = (ROOT / "skills/route-gpt-5-6-work/SKILL.md").read_text(encoding="utf-8")
        operator_docs = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in ("README.md", "docs/HOST_ACCEPTANCE.md", "docs/LIMITATIONS.md")
        )
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))

        for required in (
            "GPT-6 Astra",
            "Astra Medium",
            "Low and Ultra are rejected",
            "authoritative attested Sol `ROUTE_UP`",
            "no automatic Astra effort retry",
            "model-keyed",
        ):
            self.assertIn(required, skill + "\n" + operator_docs)
        self.assertIn("gpt-6", manifest["keywords"])

    def test_plugin_surface_uses_the_current_gpt6_routing_policy(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
        prompt_hook = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertIn("GPT-6 Luna or Sol", manifest["interface"]["longDescription"])
        self.assertNotIn("Terra", manifest["interface"]["longDescription"])
        self.assertIn("GPT-6", prompt_hook["statusMessage"])
        self.assertNotIn("GPT-5.6", prompt_hook["statusMessage"])


if __name__ == "__main__":
    unittest.main()
