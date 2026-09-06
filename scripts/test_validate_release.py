from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_marketplace_uses_fork_and_immutable_candidate_ref(self) -> None:
        marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        source = marketplace["plugins"][0]["source"]

        self.assertEqual(source["url"], "https://github.com/anthonypaddison/Codex-Autorouter.git")
        self.assertEqual(source["ref"], "v0.2.0")
        self.assertNotIn(source["ref"].lower(), {"main", "master", "head"})

    def test_manifest_identifies_candidate_without_losing_original_author(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], "0.2.0")
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
            'model = "gpt-5.6-luna"',
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

        for required in ("v0.2.0", "git tag", "archive", "SHA256", "scripts/validate_release.py"):
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


if __name__ == "__main__":
    unittest.main()
