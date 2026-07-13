#!/usr/bin/env python3
from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock

import check_hooks


class EffectiveReadinessTests(unittest.TestCase):
    def test_local_agent_readiness_requires_active_current_agents_from_this_build(self) -> None:
        payload = {
            "mode": "ADVISORY",
            "runtime_surface": "PLUGIN_LAYOUT_UNATTESTED",
            "local_agent_ready": True,
            "agents_active": True,
            "activation_update_required": False,
            "agent_conflicts": [],
            "original_backup_conflicts": [],
            "diagnostic_scope": "LOCAL_FILES_ONLY",
        }
        completed = __import__("subprocess").CompletedProcess([], 0, json.dumps(payload), "")
        with mock.patch.object(check_hooks.subprocess, "run", return_value=completed):
            ready, summary = check_hooks._local_agent_readiness(Path("/candidate"))
        self.assertTrue(ready)
        self.assertTrue(summary["local_agent_ready"])

    def test_local_agent_readiness_rejects_missing_or_stale_activation(self) -> None:
        for payload in (
            {"mode": "ADVISORY", "runtime_surface": "PLUGIN_LAYOUT_UNATTESTED", "local_agent_ready": False, "agents_active": False},
            {"mode": "ADVISORY", "runtime_surface": "PLUGIN_LAYOUT_UNATTESTED", "local_agent_ready": True, "agents_active": True, "activation_update_required": True},
            {"mode": "ADVISORY", "runtime_surface": "STANDALONE_ADVISORY", "local_agent_ready": True, "agents_active": True, "activation_update_required": False},
        ):
            with self.subTest(payload=payload):
                completed = __import__("subprocess").CompletedProcess([], 0, json.dumps(payload), "")
                with mock.patch.object(check_hooks.subprocess, "run", return_value=completed):
                    ready, _ = check_hooks._local_agent_readiness(Path("/candidate"))
                self.assertFalse(ready)

    def test_ready_uses_effective_app_server_values(self) -> None:
        result = check_hooks._effective_readiness(
            {"config": {"model": "gpt-5.6-sol", "model_reasoning_effort": "high", "service_tier": "priority", "plugins": {"gpt-5-6-router@personal": {"enabled": True}}}},
            {"requirements": None},
            "gpt-5-6-router",
        )
        self.assertTrue(result["ready"])
        self.assertEqual("app_server_effective_config_and_requirements", result["source"])

    def test_managed_hooks_only_blocks_effective_readiness(self) -> None:
        result = check_hooks._effective_readiness(
            {"config": {"plugins": {"gpt-5-6-router@personal": {"enabled": True}}}},
            {"requirements": {"allowManagedHooksOnly": True}},
            "gpt-5-6-router",
        )
        self.assertFalse(result["ready"])
        self.assertTrue(result["managed_hooks_only"])

    def test_disabled_features_or_depth_block_effective_readiness(self) -> None:
        result = check_hooks._effective_readiness(
            {"config": {"features": {"hooks": False, "multi_agent": False}, "agents": {"max_depth": 0}, "plugins": {"gpt-5-6-router@personal": {"enabled": True}}}},
            {"requirements": None},
            "gpt-5-6-router",
        )
        self.assertFalse(result["ready"])
        self.assertFalse(result["hooks_enabled"])
        self.assertFalse(result["multi_agent_enabled"])
        self.assertFalse(result["child_depth_enabled"])

    def test_skill_binding_requires_the_checker_build(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".codex-plugin").mkdir()
            (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")
            expected = root / "skills" / "route-gpt-5-6-work" / "SKILL.md"
            expected.parent.mkdir(parents=True)
            expected.write_text("---\nname: route-gpt-5-6-work\n---\n", encoding="utf-8")
            ready, summary = check_hooks._skill_binding(
                [{"skills": [{"name": "gpt-5-6-router:route-gpt-5-6-work", "enabled": True, "path": str(expected)}], "errors": []}],
                "gpt-5-6-router",
                root,
            )
            self.assertTrue(ready)
            self.assertTrue(summary["path_matches_checker_build"])
            self.assertEqual("1.2.3", summary["version"])

    def test_skill_binding_rejects_an_older_or_different_cache(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "current"
            other = Path(raw) / "old" / "skills" / "route-gpt-5-6-work" / "SKILL.md"
            (root / ".codex-plugin").mkdir(parents=True)
            (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"version": "2.0.0"}), encoding="utf-8")
            other.parent.mkdir(parents=True)
            other.write_text("old", encoding="utf-8")
            ready, summary = check_hooks._skill_binding(
                [{"skills": [{"name": "gpt-5-6-router:route-gpt-5-6-work", "enabled": True, "path": str(other)}], "errors": []}],
                "gpt-5-6-router",
                root,
            )
            self.assertFalse(ready)
            self.assertFalse(summary["path_matches_checker_build"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
