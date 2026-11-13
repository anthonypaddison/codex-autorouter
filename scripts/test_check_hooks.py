#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import check_hooks
import hook_launcher


PLUGIN_VERSION = "1.2.3"
PLUGIN_IDENTITY = "sha256:test-plugin-candidate"
CURRENT_SESSION_ID = "current-task"
NOW = int(time.time())
SOL_BALANCED_MEDIUM = check_hooks.model_policy.capability_key("gpt-6-sol", "balanced", "medium")
SOL_HIGH_HIGH = check_hooks.model_policy.capability_key("gpt-6-sol", "high", "high")
ASTRA_FRONTIER_MEDIUM = check_hooks.model_policy.capability_key("gpt-6-astra", "frontier", "medium")


def _effective(*, model: str = "gpt-6-luna", agents_enabled: bool = True) -> dict[str, object]:
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


def _write_evidence(
    root: Path,
    *,
    root_model: str = "gpt-6-luna",
    runtime_version: str | None = "0.88.0",
    runtime_build: str | None = "desktop-88",
    host_type: str | None = "Desktop",
    receipt_version: str | None = None,
    receipt_build: str | None = None,
    session_id: str = CURRENT_SESSION_ID,
    plugin_identity: str = PLUGIN_IDENTITY,
    receipt_plugin_identity: str | None = None,
    observation_timestamp: int = NOW - 60,
    receipt_timestamp: int = NOW - 30,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    observation = {
        "schema_version": 1,
        "plugin_version": PLUGIN_VERSION,
        "plugin_identity": plugin_identity,
        "session_id": session_id,
        "turn_id": "root-turn",
        "root_model": root_model,
        "runtime_version": runtime_version,
        "runtime_build": runtime_build,
        "host_type": host_type,
        "runtime_identity_source": "hook_payload" if any((runtime_version, runtime_build, host_type)) else "unavailable_from_current_codex_hook_surface",
        "platform": "darwin",
        "timestamp": observation_timestamp,
    }
    receipt = {
        "schema_version": 3,
        "capability_signature": "direct-model-spawn-v1",
        "policy_revision": check_hooks.model_policy.POLICY_REVISION,
        "plugin_version": PLUGIN_VERSION,
        "plugin_identity": receipt_plugin_identity or plugin_identity,
        "runtime_version": runtime_version if receipt_version is None else receipt_version,
        "runtime_build": runtime_build if receipt_build is None else receipt_build,
        "host_type": host_type,
        "runtime_identity_source": "hook_payload" if any((runtime_version, runtime_build, host_type)) else "unavailable_from_current_codex_hook_surface",
        "platform": "darwin",
        "agent_id": "00000000-0000-7000-8000-000000000001",
        "spawn_call_key": "call:test",
        "parent_session_id": session_id,
        "parent_turn_id": "root-turn",
        "child_turn_id": "child-turn",
        "requested_child_model": "gpt-6-sol",
        "observed_child_model": "gpt-6-sol",
        "route_profile": "balanced",
        "capability_key": SOL_BALANCED_MEDIUM,
        "effort_intent": "medium",
        "spawn_contract_valid": True,
        "lifecycle_complete": True,
        "completion_structured": True,
        "ambiguity_clear": True,
        "model_evidence_consistent": True,
        "attestation_matched": True,
        "profile_policy_valid": True,
        "timestamp": receipt_timestamp,
    }
    (root / "root-observation-v1.json").write_text(json.dumps(observation), encoding="utf-8")
    observations = root / "root-observations-v1"
    observations.mkdir()
    (observations / f"{session_id}.json").write_text(json.dumps(observation), encoding="utf-8")
    (root / "capability-v3.json").write_text(json.dumps({
        "schema_version": 3,
        "capability_signature": "direct-model-spawn-v1",
        "policy_revision": check_hooks.model_policy.POLICY_REVISION,
        "capabilities": {SOL_BALANCED_MEDIUM: receipt},
    }), encoding="utf-8")


def _write_capability_evidence(root: Path, capabilities: tuple[str, ...]) -> None:
    _write_evidence(root)
    path = root / "capability-v3.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    base = next(iter(document["capabilities"].values()))
    document["capabilities"] = {}
    for key in capabilities:
        model, profile, effort, _policy_revision = key.split("|")
        document["capabilities"][key] = {
            **base,
            "requested_child_model": model,
            "observed_child_model": model,
            "route_profile": profile,
            "capability_key": key,
            "effort_intent": effort,
        }
    path.write_text(json.dumps(document), encoding="utf-8")


def _write_legacy_model_keyed_evidence(root: Path, model: str) -> None:
    _write_evidence(root)
    (root / "capability-v3.json").unlink()
    (root / "capability-v2.json").write_text(json.dumps({
        "schema_version": 2,
        "capability_signature": "direct-model-spawn-v1",
        "capabilities": {model: {"schema_version": 2, "observed_child_model": model}},
    }), encoding="utf-8")


def _health(
    data: Path,
    *,
    effective: dict[str, object] | None = None,
    session_id: str = CURRENT_SESSION_ID,
) -> dict[str, object]:
    with mock.patch.dict(os.environ, {"CODEX_SESSION_ID": session_id}, clear=False):
        return check_hooks._routing_health(
            effective or _effective(),
            PLUGIN_VERSION,
            data,
            plugin_identity=PLUGIN_IDENTITY,
        )


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
            health = _health(data)
        self.assertEqual("READY", health["status"])
        self.assertTrue(health["ready"])
        self.assertEqual("hook_observation", health["root_model_source"])
        self.assertEqual("CHEAP_ROOT", health["current_task_root_state"])
        self.assertEqual("ESCALATION PREVIOUSLY OBSERVED", health["historical_escalation_state"])
        self.assertEqual("CURRENT RUNTIME ESCALATION CAPABLE", health["current_runtime_capability_state"])
        self.assertEqual("CURRENT", health["capability_status"][SOL_BALANCED_MEDIUM])
        self.assertEqual("UNPROVEN", health["capability_status"][SOL_HIGH_HIGH])
        self.assertEqual("UNPROVEN", health["capability_status"][ASTRA_FRONTIER_MEDIUM])

    def test_gpt61_receipt_proves_only_its_exact_model_and_profile(self) -> None:
        for model in ("gpt-6.1-sol", "gpt-6.1-terra"):
            key = check_hooks.model_policy.capability_key(model, "high", "high")
            with self.subTest(model=model), tempfile.TemporaryDirectory() as raw:
                data = Path(raw)
                _write_capability_evidence(data, (key,))
                health = _health(data)
                self.assertEqual("CURRENT", health["capability_status"][key])
                self.assertEqual("UNPROVEN", health["capability_status"][SOL_HIGH_HIGH])
                receipt_path = data / "capability-v3.json"
                document = json.loads(receipt_path.read_text())
                del document["capabilities"][key]["profile_policy_valid"]
                receipt_path.write_text(json.dumps(document))
                self.assertNotEqual("CURRENT", _health(data)["capability_status"][key])

    def test_profile_keyed_receipts_prove_only_their_exact_capability_tier(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_capability_evidence(data, (SOL_HIGH_HIGH,))
            health = _health(data)
        self.assertEqual("UNPROVEN", health["capability_status"][SOL_BALANCED_MEDIUM])
        self.assertEqual("CURRENT", health["capability_status"][SOL_HIGH_HIGH])
        self.assertEqual("UNPROVEN", health["capability_status"][ASTRA_FRONTIER_MEDIUM])
        self.assertEqual("READY", health["status"])

    def test_profile_keyed_receipt_requires_recorded_execution_gates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_capability_evidence(data, (ASTRA_FRONTIER_MEDIUM,))
            path = data / "capability-v3.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["capabilities"][ASTRA_FRONTIER_MEDIUM].pop("agent_id", None)
            path.write_text(json.dumps(document), encoding="utf-8")
            health = _health(data)
        self.assertEqual("INCOMPATIBLE", health["capability_status"][ASTRA_FRONTIER_MEDIUM])
        self.assertEqual("DEGRADED", health["status"])

    def test_historical_gpt56_receipt_cannot_satisfy_current_gpt6_capability(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_legacy_model_keyed_evidence(data, "gpt-5.6-sol")
            health = _health(data)
        self.assertEqual("UNPROVEN", health["capability_status"][SOL_BALANCED_MEDIUM])
        self.assertEqual("UNPROVEN", health["capability_status"][ASTRA_FRONTIER_MEDIUM])
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("ESCALATION PREVIOUSLY OBSERVED", health["historical_escalation_state"])

    def test_astra_receipt_is_independent_and_astra_root_is_savings_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_capability_evidence(data, (ASTRA_FRONTIER_MEDIUM,))
            health = _health(data, effective=_effective(model="gpt-6-luna"))
            self.assertEqual("CURRENT", health["capability_status"][ASTRA_FRONTIER_MEDIUM])
            self.assertEqual("UNPROVEN", health["capability_status"][SOL_BALANCED_MEDIUM])

            observation_path = data / "root-observations-v1" / f"{CURRENT_SESSION_ID}.json"
            observation = json.loads(observation_path.read_text(encoding="utf-8"))
            observation["root_model"] = "gpt-6-astra"
            observation_path.write_text(json.dumps(observation), encoding="utf-8")
            health = _health(data, effective=_effective(model="gpt-6-luna"))
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("DEGRADED_NON_LUNA", health["current_task_root_state"])
        self.assertEqual("CURRENT", health["capability_status"][ASTRA_FRONTIER_MEDIUM])

    def test_stale_or_incompatible_astra_does_not_erase_current_sol_capability(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_capability_evidence(data, (SOL_BALANCED_MEDIUM, ASTRA_FRONTIER_MEDIUM))
            path = data / "capability-v3.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            astra = document["capabilities"][ASTRA_FRONTIER_MEDIUM]
            astra["timestamp"] = NOW - check_hooks.CAPABILITY_MAX_AGE_SECONDS - 1
            path.write_text(json.dumps(document), encoding="utf-8")
            health = _health(data)
            self.assertEqual("READY", health["status"])
            self.assertEqual("CURRENT", health["capability_status"][SOL_BALANCED_MEDIUM])
            self.assertEqual("STALE", health["capability_status"][ASTRA_FRONTIER_MEDIUM])

            astra["timestamp"] = NOW - 30
            astra["plugin_identity"] = "sha256:other-candidate"
            path.write_text(json.dumps(document), encoding="utf-8")
            health = _health(data)
        self.assertEqual("READY", health["status"])
        self.assertEqual("CURRENT", health["capability_status"][SOL_BALANCED_MEDIUM])
        self.assertEqual("INCOMPATIBLE", health["capability_status"][ASTRA_FRONTIER_MEDIUM])

    def test_authoritative_non_luna_hook_observation_overrides_luna_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, root_model="gpt-6-sol")
            health = _health(data, effective=_effective(model="gpt-6-luna"))
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("gpt-6-sol", health["root_model"])
        self.assertIn("credit-saving", " ".join(health["reasons"]))

    def test_config_model_is_supporting_evidence_not_authoritative_turn_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw) / "absent-data-root"
            health = _health(data, effective=_effective(model="gpt-6-luna"))
            self.assertFalse(data.exists())
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("effective_config", health["root_model_source"])
        self.assertIn("authoritative", " ".join(health["reasons"]))

    def test_non_luna_config_without_a_task_observation_is_not_called_the_active_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw) / "absent-data-root"
            health = _health(data, effective=_effective(model="gpt-6-sol"))
        reasons = " ".join(health["reasons"])
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("UNKNOWN", health["current_task_root_state"])
        self.assertNotIn("Active root is", reasons)
        self.assertIn("supporting configuration", reasons)

    def test_runtime_change_invalidates_ready_without_a_paid_probe(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, receipt_version="0.87.0", receipt_build="desktop-87")
            with mock.patch.object(check_hooks.subprocess, "run", side_effect=AssertionError("no paid probe")):
                health = _health(data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertIn("runtime", " ".join(health["reasons"]))

    def test_missing_optional_runtime_identity_does_not_make_ready_impossible(self) -> None:
        for version, build in ((None, "desktop-88"), ("0.88.0", None)):
            with self.subTest(version=version, build=build), tempfile.TemporaryDirectory() as raw:
                data = Path(raw)
                _write_evidence(data, runtime_version=version, runtime_build=build)
                health = _health(data)
                self.assertEqual("READY", health["status"])

    def test_fully_unavailable_runtime_identity_is_explicit_and_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, runtime_version=None, runtime_build=None, host_type=None)
            health = _health(data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertIn("runtime identity unavailable; capability compatibility unproven", " ".join(health["reasons"]).lower())
        self.assertEqual(
            "unavailable from current Codex hook surface",
            health["runtime_identity"],
        )
        self.assertEqual("UNPROVEN", health["current_runtime_capability_state"])

    def test_current_observable_runtime_missing_from_receipt_is_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data)
            receipt_path = data / "capability-v3.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["capabilities"][SOL_BALANCED_MEDIUM]["runtime_version"] = None
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            health = _health(data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertIn("not bound", " ".join(health["reasons"]))

    def test_unrelated_luna_summary_cannot_override_current_non_luna_task(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, root_model="gpt-6-sol")
            global_observation = json.loads((data / "root-observation-v1.json").read_text(encoding="utf-8"))
            global_observation.update({
                "session_id": "unrelated-task",
                "turn_id": "newer-luna-turn",
                "root_model": "gpt-6-luna",
                "runtime_version": None,
                "runtime_build": None,
                "host_type": None,
                "timestamp": NOW,
            })
            (data / "root-observation-v1.json").write_text(json.dumps(global_observation), encoding="utf-8")
            health = _health(data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("gpt-6-sol", health["root_model"])
        self.assertEqual("DEGRADED_NON_LUNA", health["current_task_root_state"])

    def test_global_summary_without_current_task_context_never_claims_ready(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data)
            with mock.patch.dict(os.environ, {}, clear=True):
                health = check_hooks._routing_health(
                    _effective(), PLUGIN_VERSION, data, plugin_identity=PLUGIN_IDENTITY
                )
        self.assertEqual("DEGRADED", health["status"])
        self.assertIn("task context", " ".join(health["reasons"]).lower())

    def test_receipt_from_an_incompatible_plugin_candidate_is_historical_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, receipt_plugin_identity="sha256:different-candidate")
            health = _health(data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("ESCALATION PREVIOUSLY OBSERVED", health["historical_escalation_state"])
        self.assertEqual("INCOMPATIBLE", health["current_runtime_capability_state"])
        self.assertIn("plugin", " ".join(health["reasons"]).lower())

    def test_stale_receipt_is_retained_as_history_but_cannot_make_ready(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, receipt_timestamp=NOW - (31 * 24 * 60 * 60))
            with mock.patch.object(check_hooks.time, "time", return_value=NOW):
                health = _health(data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("ESCALATION PREVIOUSLY OBSERVED", health["historical_escalation_state"])
        self.assertEqual("STALE", health["current_runtime_capability_state"])

    def test_matching_host_type_cannot_mask_a_versioned_runtime_change(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data, receipt_version="0.87.0", receipt_build="desktop-87")
            health = _health(data)
        self.assertEqual("DEGRADED", health["status"])
        self.assertEqual("INCOMPATIBLE", health["current_runtime_capability_state"])

    def test_unavailable_precedes_receipt_and_root_health(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw)
            _write_evidence(data)
            effective = _effective(agents_enabled=False)
            health = _health(data, effective=effective)
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
