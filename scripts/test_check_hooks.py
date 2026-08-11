#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import check_hooks
import hook_launcher


PLUGIN_VERSION = "1.2.3"


def _effective(*, model: str = "gpt-5.6-luna", agents_enabled: bool = True) -> dict[str, object]:
    return check_hooks._effective_readiness(
        {
            "config": {
                "model": model,
                "agents": {"enabled": agents_enabled},
                "plugins": {"gpt-5-6-router@personal": {"enabled": True}},
            }
        },
        {"requirements": None},
        "gpt-5-6-router",
    )


def _write_evidence(root: Path, *, root_model: str = "gpt-5.6-luna", runtime_version: str | None = "0.88.0", runtime_build: str | None = "desktop-88", receipt_version: str | None = None, receipt_build: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    observation = {
        "schema_version": 1,
        "plugin_version": PLUGIN_VERSION,
        "root_model": root_model,
        "runtime_version": runtime_version,
        "runtime_build": runtime_build,
        "host_type": "Desktop",
        "platform": "darwin",
        "timestamp": "2026-08-11T12:00:00Z",
    }
    receipt = {
        "schema_version": 1,
        "capability_signature": "direct-model-spawn-v1",
        "plugin_version": PLUGIN_VERSION,
        "runtime_version": runtime_version if receipt_version is None else receipt_version,
        "runtime_build": runtime_build if receipt_build is None else receipt_build,
        "host_type": "Desktop",
        "platform": "darwin",
        "observed_child_model": "gpt-5.6-terra",
        "effort_intent": "medium",
        "timestamp": "2026-08-11T12:01:00Z",
    }
    (root / "root-observation-v1.json").write_text(json.dumps(observation), encoding="utf-8")
    (root / "capability-v1.json").write_text(json.dumps(receipt), encoding="utf-8")


class ExactHookLauncherTests(unittest.TestCase):
    def test_hook_definitions_use_only_the_exact_plugin_root_launcher(self) -> None:
        manifest = json.loads((Path(__file__).resolve().parents[1] / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = []
        for groups in manifest["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    commands.extend((hook["command"], hook["commandWindows"]))
        self.assertTrue(commands)
        self.assertTrue(all("scripts/hook_launcher.py" in command.replace("\\", "/") for command in commands))
        self.assertTrue(all("${PLUGIN_ROOT}" in command or "%PLUGIN_ROOT%" in command for command in commands))
        self.assertTrue(all("glob(" not in command and "root.parent" not in command for command in commands))

    def test_missing_exact_hook_fails_open_and_reports_degraded_once(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "plugin"
            data = Path(raw) / "data"
            root.mkdir()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, hook_launcher.launch(root, data))
                self.assertEqual(0, hook_launcher.launch(root, data))
            payloads = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(2, len(payloads))
            self.assertTrue(payloads[0]["continue"])
            self.assertIn("DEGRADED", payloads[0]["systemMessage"])
            self.assertEqual({"continue": True}, payloads[1])

    def test_launcher_executes_only_the_hook_below_the_given_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "selected"
            target = root / "skills" / "route-gpt-5-6-work" / "scripts" / "router_hook.py"
            target.parent.mkdir(parents=True)
            target.write_text("print('{\"continue\":true,\"selected\":true}')\n", encoding="utf-8")
            sibling = Path(raw) / "newer" / "skills" / "route-gpt-5-6-work" / "scripts" / "router_hook.py"
            sibling.parent.mkdir(parents=True)
            sibling.write_text("raise SystemExit(99)\n", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, hook_launcher.launch(root, Path(raw) / "data"))
            self.assertTrue(json.loads(output.getvalue())["selected"])


class EffectiveReadinessTests(unittest.TestCase):
    def test_effective_availability_uses_current_agents_enabled_setting(self) -> None:
        result = _effective()
        self.assertTrue(result["available"])
        self.assertTrue(result["agents_enabled"])
        self.assertNotIn("child_depth_enabled", result)
        self.assertNotIn("multi_agent_enabled", result)

    def test_disabled_agents_or_hooks_make_routing_unavailable(self) -> None:
        for config in (
            {"features": {"hooks": False}},
            {"agents": {"enabled": False}},
        ):
            with self.subTest(config=config):
                config["plugins"] = {"gpt-5-6-router@personal": {"enabled": True}}
                result = check_hooks._effective_readiness({"config": config}, {"requirements": None}, "gpt-5-6-router")
                self.assertFalse(result["available"])

    def test_managed_hooks_only_makes_routing_unavailable(self) -> None:
        result = check_hooks._effective_readiness(
            {"config": {"plugins": {"gpt-5-6-router@personal": {"enabled": True}}}},
            {"requirements": {"allowManagedHooksOnly": True}},
            "gpt-5-6-router",
        )
        self.assertFalse(result["available"])

    def test_missing_legacy_custom_agents_are_not_consulted(self) -> None:
        with mock.patch.object(check_hooks.subprocess, "run", side_effect=AssertionError("legacy controller must not run")):
            self.assertTrue(_effective()["available"])


class RoutingHealthTests(unittest.TestCase):
    def test_ready_requires_luna_and_a_runtime_bound_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data)
            health = check_hooks._routing_health(_effective(), PLUGIN_VERSION, data)
        self.assertEqual("READY", health["status"])
        self.assertTrue(health["ready"])
        self.assertEqual("hook_observation", health["root_model_source"])

    def test_authoritative_non_luna_hook_observation_overrides_luna_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, root_model="gpt-5.6-sol")
            health = check_hooks._routing_health(_effective(model="gpt-5.6-luna"), PLUGIN_VERSION, data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("gpt-5.6-sol", health["root_model"])
        self.assertIn("credit-saving", " ".join(health["reasons"]))

    def test_config_model_is_supporting_evidence_not_authoritative_turn_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw) / "absent-data-root"
            health = check_hooks._routing_health(_effective(model="gpt-5.6-luna"), PLUGIN_VERSION, data)
            self.assertFalse(data.exists())
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("effective_config", health["root_model_source"])
        self.assertIn("authoritative", " ".join(health["reasons"]))

    def test_runtime_change_invalidates_ready_without_a_paid_probe(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, receipt_version="0.87.0", receipt_build="desktop-87")
            with mock.patch.object(check_hooks.subprocess, "run", side_effect=AssertionError("no paid probe")):
                health = check_hooks._routing_health(_effective(), PLUGIN_VERSION, data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertIn("runtime", " ".join(health["reasons"]))

    def test_unknown_runtime_or_build_is_degraded(self) -> None:
        for version, build in ((None, "desktop-88"), ("0.88.0", None)):
            with self.subTest(version=version, build=build), tempfile.TemporaryDirectory() as raw:
                data = Path(raw)
                _write_evidence(data, runtime_version=version, runtime_build=build)
                health = check_hooks._routing_health(_effective(), PLUGIN_VERSION, data)
                self.assertEqual("DEGRADED", health["status"])

    def test_unavailable_precedes_receipt_and_root_health(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data)
            effective = _effective(agents_enabled=False)
            health = check_hooks._routing_health(effective, PLUGIN_VERSION, data)
        self.assertEqual("UNAVAILABLE", health["status"])


class SkillBindingTests(unittest.TestCase):
    def test_skill_binding_requires_the_checker_build(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".codex-plugin").mkdir()
            (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"version": PLUGIN_VERSION}), encoding="utf-8")
            expected = root / "skills" / "route-gpt-5-6-work" / "SKILL.md"
            expected.parent.mkdir(parents=True)
            expected.write_text("---\nname: route-gpt-5-6-work\n---\n", encoding="utf-8")
            ready, summary = check_hooks._skill_binding(
                [{"skills": [{"name": "gpt-5-6-router:route-gpt-5-6-work", "enabled": True, "path": str(expected)}], "errors": []}],
                "gpt-5-6-router",
                root,
            )
            self.assertTrue(ready)
            self.assertEqual(PLUGIN_VERSION, summary["version"])

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
