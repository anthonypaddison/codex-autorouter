#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import routerctl


SCRIPT = Path(__file__).with_name("routerctl.py")
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
HOOKS = PLUGIN_ROOT / "hooks" / "hooks.json"


class RouterCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.env = {
            **os.environ,
            "CODEX_HOME": str(self.home),
            "PLUGIN_DATA": str(self.data),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_ctl(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=env or self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertTrue(result.stdout, result.stderr)
        return json.loads(result.stdout)

    def write_legacy_activation(self, judge_original: bytes | None = None) -> None:
        agents = self.home / "agents"
        originals = self.data / "activation" / "originals"
        transactions = self.data / "activation" / "transactions"
        agents.mkdir(parents=True)
        originals.mkdir(parents=True)
        transactions.mkdir(parents=True)
        files = {}
        for name in routerctl.LEGACY_AGENT_NAMES:
            target = agents / name
            if name == "gpt56_sol_judge.toml":
                target.write_bytes(b"legacy-managed-sol-high\n")
            else:
                target.write_bytes((routerctl.AGENT_SOURCE / name).read_bytes())
            original = {"kind": "absent"}
            if name == "gpt56_sol_judge.toml" and judge_original is not None:
                backup = originals / name
                backup.write_bytes(judge_original)
                original = {
                    "kind": "file",
                    "backup": name,
                    "sha256": hashlib.sha256(judge_original).hexdigest(),
                    "mode": 0o600,
                }
            files[name] = {"installed_sha256": routerctl._sha(target), "original": original}
        (self.data / "activation" / "active.json").write_text(json.dumps({
            "schema_version": 1,
            "plugin_version": "legacy-build",
            "transaction_id": "legacy-activation",
            "files": files,
        }), encoding="utf-8")

    def test_plugin_hooks_are_native_and_relocatable(self) -> None:
        hooks = json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(
            {"UserPromptSubmit", "PreToolUse", "SubagentStart", "PostToolUse", "SubagentStop", "Stop"},
            set(hooks),
        )
        for groups in hooks.values():
            for group in groups:
                for hook in group["hooks"]:
                    self.assertIn("${PLUGIN_ROOT}", hook["command"])
                    self.assertIn("%PLUGIN_ROOT%", hook["commandWindows"])
                    self.assertNotIn(str(PLUGIN_ROOT), json.dumps(hook))
        for name in routerctl.AGENT_NAMES:
            self.assertRegex(Path(name).stem, r"^[a-z0-9_]+$")

    def _run_hook_command(self, command: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            input=json.dumps({
                "hook_event_name": "UserPromptSubmit",
                "session_id": "stale-cache",
                "turn_id": "t1",
                "model": "gpt-5.6-terra",
                "prompt": "How are things now?",
            }),
            env=env,
            text=True,
            capture_output=True,
            shell=True,
            check=False,
        )

    def test_cached_hook_command_never_migrates_to_a_sibling_plugin_version(self) -> None:
        cache = self.root / "cache" / "gpt-5-6-router"
        old_root = cache / "0.1.0+codex.retired"
        current_root = cache / "0.1.0+codex.current"
        hook_target = current_root / "skills" / "route-gpt-5-6-work" / "scripts" / "router_hook.py"
        hook_target.parent.mkdir(parents=True)
        hook_target.write_bytes((PLUGIN_ROOT / "skills" / "route-gpt-5-6-work" / "scripts" / "router_hook.py").read_bytes())
        manifest = current_root / ".codex-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"name": "gpt-5-6-router", "version": "0.1.0+codex.current"}), encoding="utf-8")
        (old_root / "scripts").mkdir(parents=True)
        shutil.copy2(PLUGIN_ROOT / "scripts" / "hook_launcher.py", old_root / "scripts" / "hook_launcher.py")
        hooks = json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]
        hook = hooks["UserPromptSubmit"][0]["hooks"][0]
        command = hook["commandWindows" if os.name == "nt" else "command"]
        env = {
            **self.env,
            "PLUGIN_ROOT": str(old_root),
            "CODEX_ROUTER_STATE_DIR": str(self.data / "router-state-v2"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        result = self._run_hook_command(command, env)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("systemMessage", payload)
        self.assertIn("selected plugin root", payload["systemMessage"])
        self.assertFalse((self.data / "router-state-v2" / "stale-cache--t1.json").exists())

    def test_cached_hook_command_fails_open_with_only_one_missing_cache_diagnostic(self) -> None:
        old_root = self.root / "empty-cache" / "gpt-5-6-router" / "0.1.0+codex.retired"
        (old_root / "scripts").mkdir(parents=True)
        shutil.copy2(PLUGIN_ROOT / "scripts" / "hook_launcher.py", old_root / "scripts" / "hook_launcher.py")
        hooks = json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]
        hook = hooks["UserPromptSubmit"][0]["hooks"][0]
        command = hook["commandWindows" if os.name == "nt" else "command"]
        env = {
            **self.env,
            "PLUGIN_ROOT": str(old_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        first = self._run_hook_command(command, env)
        second = self._run_hook_command(command, env)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        self.assertIn("systemMessage", json.loads(first.stdout))
        self.assertEqual({"continue": True}, json.loads(second.stdout))

    def test_profile_defaults_to_balanced_and_persists_all_three_modes(self) -> None:
        initial = self.payload(self.run_ctl("profile"))
        self.assertEqual("balanced", initial["profile"])
        self.assertEqual("default", initial["source"])
        for profile, label in (
            ("token-saver", "Token Saver"),
            ("balanced", "Balanced"),
            ("max-quality", "Max Quality"),
        ):
            with self.subTest(profile=profile):
                configured = self.payload(self.run_ctl("profile", profile))
                self.assertEqual(profile, configured["profile"])
                self.assertEqual(label, configured["label"])
                observed = self.payload(self.run_ctl("profile"))
                self.assertEqual(profile, observed["profile"])
                self.assertEqual("configured", observed["source"])
        payload = json.loads((self.home / "gpt-5-6-router" / "routing-profile.json").read_text())
        self.assertEqual({"schema_version": 1, "profile": "max-quality"}, payload)

    def test_status_reports_routing_profile(self) -> None:
        self.assertEqual(0, self.run_ctl("profile", "token-saver").returncode)
        status = self.payload(self.run_ctl("status"))
        self.assertEqual("token-saver", status["routing_profile"])
        self.assertEqual("Token Saver", status["routing_profile_label"])
        self.assertTrue(status["routing_profile_valid"])

    def test_status_on_absent_roots_is_strictly_non_mutating(self) -> None:
        self.assertFalse(self.home.exists())
        self.assertFalse(self.data.exists())
        status = self.payload(self.run_ctl("status"))
        self.assertFalse(status["legacy_agents_active"])
        self.assertTrue(status["legacy_agents_optional"])
        self.assertEqual([], status["recovery_required"])
        self.assertFalse(self.home.exists())
        self.assertFalse(self.data.exists())

    def test_normal_activate_does_not_install_legacy_agents(self) -> None:
        result = self.payload(self.run_ctl("activate"))
        self.assertEqual("supported-routing", result["status"])
        self.assertFalse(result["changed"])
        self.assertFalse(self.home.exists())
        self.assertFalse(self.data.exists())

    def test_status_reports_interrupted_legacy_transaction_without_recovery(self) -> None:
        crashed = self.run_ctl(
            "activate",
            "--legacy-agents",
            env={**self.env, "GPT56_ROUTER_CRASH_AT": "committing"},
        )
        self.assertEqual(97, crashed.returncode)
        before = {
            path.relative_to(self.root).as_posix(): (
                "directory" if path.is_dir() else path.read_bytes()
            )
            for path in sorted(self.root.rglob("*"))
        }
        status = self.payload(self.run_ctl("status"))
        self.assertEqual(1, len(status["recovery_required"]))
        self.assertEqual([], status["recovered_transactions"])
        after = {
            path.relative_to(self.root).as_posix(): (
                "directory" if path.is_dir() else path.read_bytes()
            )
            for path in sorted(self.root.rglob("*"))
        }
        self.assertEqual(before, after)
        recovered = self.payload(self.run_ctl("activate", "--legacy-agents"))
        self.assertEqual(1, len(recovered["recovered"]))

    def test_status_on_active_legacy_state_is_strictly_non_mutating(self) -> None:
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        before = {
            path.relative_to(self.root).as_posix(): (
                "directory" if path.is_dir() else path.read_bytes()
            )
            for path in sorted(self.root.rglob("*"))
        }
        self.assertEqual(0, self.run_ctl("status").returncode)
        after = {
            path.relative_to(self.root).as_posix(): (
                "directory" if path.is_dir() else path.read_bytes()
            )
            for path in sorted(self.root.rglob("*"))
        }
        self.assertEqual(before, after)

    def test_status_on_corrupt_legacy_state_fails_without_mutation(self) -> None:
        activation = self.data / "activation"
        activation.mkdir(parents=True)
        active = activation / "active.json"
        active.write_text('{"schema_version":999,"files":{}}', encoding="utf-8")
        before = active.read_bytes()
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertEqual(before, active.read_bytes())
        self.assertFalse((activation / "activation.lock").exists())

    def test_invalid_profile_value_is_rejected_by_cli(self) -> None:
        result = self.run_ctl("profile", "unlimited")
        self.assertEqual(2, result.returncode)
        self.assertFalse((self.home / "gpt-5-6-router" / "routing-profile.json").exists())

    def test_malformed_profile_fails_safe_in_status(self) -> None:
        target = self.home / "gpt-5-6-router" / "routing-profile.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"schema_version":1,"profile":"unknown"}', encoding="utf-8")
        observed = self.payload(self.run_ctl("profile"))
        self.assertEqual("balanced", observed["profile"])
        self.assertEqual("invalid_default", observed["source"])
        self.assertFalse(observed["valid"])

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_profile_write_refuses_linked_target(self) -> None:
        root = self.home / "gpt-5-6-router"
        root.mkdir(parents=True)
        external = self.root / "external-profile.json"
        external.write_text('{"schema_version":1,"profile":"balanced"}', encoding="utf-8")
        (root / "routing-profile.json").symlink_to(external)
        result = self.run_ctl("profile", "max-quality")
        self.assertEqual(2, result.returncode)
        self.assertIn("refusing", result.stdout)
        self.assertEqual("balanced", json.loads(external.read_text())["profile"])

    def test_status_activate_repair_deactivate_lifecycle(self) -> None:
        self.home.mkdir(parents=True)
        hooks = self.home / "hooks.json"
        hooks.write_bytes(b'{"hooks":{"Other":[]}}\n')
        initial = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", initial["mode"])
        self.assertEqual("UNVERIFIED", initial["hook_trust"])
        self.assertEqual("REPORTED_CONFIG_ONLY", initial["fast_state"])
        activated = self.run_ctl("activate", "--legacy-agents")
        self.assertEqual(0, activated.returncode, activated.stdout + activated.stderr)
        active = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", active["mode"])
        self.assertTrue(active["local_agent_ready"])
        self.assertEqual("PLUGIN_LAYOUT_UNATTESTED", active["runtime_surface"])
        self.assertEqual("scripts/check_hooks.py", active["static_readiness_authority"])
        self.assertEqual("LOCAL_FILES_ONLY", active["diagnostic_scope"])
        self.assertTrue(active["agents_active"])
        self.assertEqual([], self.payload(self.run_ctl("repair"))["repaired"])
        deactivated = self.run_ctl("deactivate")
        self.assertEqual(0, deactivated.returncode, deactivated.stdout + deactivated.stderr)
        self.assertEqual([], list((self.home / "agents").glob("gpt56_*.toml")))
        self.assertFalse((self.data / "activation" / "active.json").exists())
        self.assertEqual([], list((self.data / "activation" / "transactions").iterdir()))
        self.assertEqual([], list((self.data / "activation" / "originals").iterdir()))
        self.assertEqual(b'{"hooks":{"Other":[]}}\n', hooks.read_bytes())
        self.assertEqual(0, self.run_ctl("deactivate").returncode)

    def test_activate_migrates_legacy_agent_set_without_leaving_the_old_role(self) -> None:
        self.write_legacy_activation()
        stale = self.payload(self.run_ctl("status"))
        self.assertTrue(stale["activation_update_required"])
        migrated = self.payload(self.run_ctl("activate", "--legacy-agents"))
        self.assertEqual("active", migrated["status"])
        self.assertFalse((self.home / "agents" / "gpt56_sol_judge.toml").exists())
        self.assertEqual(set(routerctl.AGENT_NAMES), set(path.name for path in (self.home / "agents").glob("gpt56_*.toml")))
        self.assertTrue(self.payload(self.run_ctl("status"))["local_agent_ready"])
        self.assertEqual(0, self.run_ctl("deactivate").returncode)
        self.assertEqual([], list((self.home / "agents").glob("gpt56_*.toml")))

    def test_legacy_migration_restores_a_preexisting_old_role_file(self) -> None:
        self.write_legacy_activation(b"user-owned-before-legacy-activation\n")
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        old_role = self.home / "agents" / "gpt56_sol_judge.toml"
        self.assertEqual(b"user-owned-before-legacy-activation\n", old_role.read_bytes())
        self.assertEqual(0, self.run_ctl("deactivate").returncode)
        self.assertEqual(b"user-owned-before-legacy-activation\n", old_role.read_bytes())

    def test_conflict_requires_explicit_replacement_and_original_is_restored(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        target = agents / "gpt56_luna_worker.toml"
        target.write_text("user-owned\n", encoding="utf-8")
        refused = self.run_ctl("activate", "--legacy-agents")
        self.assertEqual(2, refused.returncode)
        self.assertIn("--replace-conflicts", refused.stdout)
        self.assertEqual("user-owned\n", target.read_text(encoding="utf-8"))
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents", "--replace-conflicts").returncode)
        self.assertEqual(0, self.run_ctl("deactivate").returncode)
        self.assertEqual("user-owned\n", target.read_text(encoding="utf-8"))

    def test_injected_exception_rolls_back_exact_tree(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        original = agents / "gpt56_luna_worker.toml"
        original.write_bytes(b"original-bytes\n")
        env = {**self.env, "GPT56_ROUTER_FAIL_AT": "agent-3"}
        result = self.run_ctl("activate", "--legacy-agents", "--replace-conflicts", env=env)
        self.assertEqual(2, result.returncode)
        self.assertEqual(b"original-bytes\n", original.read_bytes())
        self.assertEqual([original], list(agents.glob("gpt56_*.toml")))
        self.assertFalse((self.data / "activation" / "active.json").exists())

    def test_hard_crash_is_recovered_on_next_command(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        original = agents / "gpt56_sol_owner.toml"
        original.write_bytes(b"pre-crash\n")
        env = {**self.env, "GPT56_ROUTER_CRASH_AT": "agent-4"}
        crashed = self.run_ctl("activate", "--legacy-agents", "--replace-conflicts", env=env)
        self.assertEqual(97, crashed.returncode)
        status = self.payload(self.run_ctl("status"))
        self.assertTrue(status["recovery_required"])
        recovered = self.payload(self.run_ctl("deactivate"))
        self.assertTrue(recovered["recovered"])
        self.assertEqual("ADVISORY", status["mode"])
        self.assertEqual(b"pre-crash\n", original.read_bytes())
        self.assertEqual([original], list(agents.glob("gpt56_*.toml")))

    def test_every_activate_commit_failpoint_rolls_back_or_recovers(self) -> None:
        for point in ("prepared", "committing", "agent-1", "agent-2", "agent-3", "agent-4", "agent-5", "agent-6", "active-manifest"):
            with self.subTest(point=point):
                case = self.root / point
                home, data = case / "home", case / "data"
                agents = home / "agents"
                agents.mkdir(parents=True)
                original = agents / "gpt56_luna_worker.toml"
                original.write_bytes((point + "\n").encode())
                env = {**os.environ, "CODEX_HOME": str(home), "PLUGIN_DATA": str(data), "GPT56_ROUTER_CRASH_AT": point}
                crashed = self.run_ctl("activate", "--legacy-agents", "--replace-conflicts", env=env)
                self.assertEqual(97, crashed.returncode)
                recovered = self.run_ctl("deactivate", env={key: value for key, value in env.items() if key != "GPT56_ROUTER_CRASH_AT"})
                self.assertEqual(0, recovered.returncode, recovered.stdout + recovered.stderr)
                self.assertEqual((point + "\n").encode(), original.read_bytes())
                self.assertEqual([original], list(agents.glob("gpt56_*.toml")))
                self.assertFalse((data / "activation" / "active.json").exists())

    def test_every_deactivate_failpoint_recovers_the_active_tree(self) -> None:
        for point in ("deactivate-1", "deactivate-2", "deactivate-3", "deactivate-4", "deactivate-5", "deactivate-6", "inactive-manifest"):
            with self.subTest(point=point):
                case = self.root / point
                env = {**os.environ, "CODEX_HOME": str(case / "home"), "PLUGIN_DATA": str(case / "data")}
                self.assertEqual(0, self.run_ctl("activate", "--legacy-agents", env=env).returncode)
                agents = case / "home" / "agents"
                before = {path.name: path.read_bytes() for path in agents.glob("gpt56_*.toml")}
                crashed = self.run_ctl("deactivate", env={**env, "GPT56_ROUTER_CRASH_AT": point})
                self.assertEqual(97, crashed.returncode)
                observed = self.payload(self.run_ctl("status", env=env))
                self.assertTrue(observed["recovery_required"])
                recovered = self.payload(self.run_ctl("activate", "--legacy-agents", env=env))
                self.assertTrue(recovered["recovered"])
                self.assertEqual(before, {path.name: path.read_bytes() for path in agents.glob("gpt56_*.toml")})
                self.assertEqual(0, self.run_ctl("deactivate", env=env).returncode)

    def test_modified_managed_file_is_preserved_only_with_explicit_flag(self) -> None:
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        target = self.home / "agents" / "gpt56_terra_worker.toml"
        target.write_text(target.read_text(encoding="utf-8") + "# user edit\n", encoding="utf-8")
        refused = self.run_ctl("deactivate")
        self.assertEqual(2, refused.returncode)
        self.assertIn("locally modified", refused.stdout)
        kept = self.payload(self.run_ctl("deactivate", "--keep-modified"))
        self.assertIn("gpt56_terra_worker.toml", kept["preserved_modified"])
        self.assertIn("# user edit", target.read_text(encoding="utf-8"))

    def test_repair_recreates_missing_but_refuses_modified(self) -> None:
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        missing = self.home / "agents" / "gpt56_terra_deep.toml"
        missing.unlink()
        repaired = self.payload(self.run_ctl("repair"))
        self.assertEqual(["gpt56_terra_deep.toml"], repaired["repaired"])
        modified = self.home / "agents" / "gpt56_sol_deep.toml"
        modified.write_text("modified\n", encoding="utf-8")
        self.assertEqual(2, self.run_ctl("repair").returncode)

    def test_managed_and_disabled_config_modes_are_explicit(self) -> None:
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(
            "[features]\nhooks = false\n[agents]\nenabled = false\nmax_depth = 0\n",
            encoding="utf-8",
        )
        advisory = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", advisory["mode"])
        self.assertFalse(advisory["multi_agent_enabled_by_local_config"])
        (self.home / "requirements.toml").write_text("allow_managed_hooks_only = true\n", encoding="utf-8")
        blocked = self.payload(self.run_ctl("status"))
        self.assertEqual("MANAGED_BLOCKED", blocked["mode"])

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_linked_codex_home_is_refused(self) -> None:
        external = self.root / "external"
        external.mkdir()
        linked = self.root / "linked-home"
        linked.symlink_to(external, target_is_directory=True)
        result = self.run_ctl("activate", "--legacy-agents", env={**self.env, "CODEX_HOME": str(linked)})
        self.assertEqual(2, result.returncode)
        self.assertIn("symlink", result.stdout)
        self.assertEqual([], list(external.iterdir()))

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_linked_agent_target_and_plugin_data_are_refused(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        external = self.root / "external-file"
        external.write_text("untouched\n", encoding="utf-8")
        (agents / "gpt56_sol_owner.toml").symlink_to(external)
        result = self.run_ctl("activate", "--legacy-agents")
        self.assertEqual(2, result.returncode)
        self.assertEqual("untouched\n", external.read_text(encoding="utf-8"))

        external_data = self.root / "external-data"
        external_data.mkdir()
        linked_data = self.root / "linked-data"
        linked_data.symlink_to(external_data, target_is_directory=True)
        result = self.run_ctl("status", env={**self.env, "PLUGIN_DATA": str(linked_data)})
        self.assertEqual(2, result.returncode)
        self.assertEqual([], list(external_data.iterdir()))

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_linked_ancestor_is_refused(self) -> None:
        external = self.root / "ancestor-target"
        external.mkdir()
        linked = self.root / "ancestor-link"
        linked.symlink_to(external, target_is_directory=True)
        result = self.run_ctl("activate", "--legacy-agents", env={**self.env, "CODEX_HOME": str(linked / "home")})
        self.assertEqual(2, result.returncode)
        self.assertIn("ancestors", result.stdout)
        self.assertEqual([], list(external.iterdir()))

    def test_prejournal_orphan_is_safely_discarded(self) -> None:
        orphan = self.data / "activation" / "transactions" / "orphan"
        (orphan / "before").mkdir(parents=True)
        (orphan / "before" / "gpt56_sol_owner.toml").write_text("staged-only\n", encoding="utf-8")
        result = self.payload(self.run_ctl("status"))
        self.assertIn("orphan", result["recovery_required"])
        self.assertTrue(orphan.exists())
        repaired = self.payload(self.run_ctl("repair"))
        self.assertIn("orphan", repaired["recovered"])
        self.assertFalse(orphan.exists())

    def test_status_does_not_chmod_existing_codex_or_agents_directories(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        if os.name != "nt":
            os.chmod(self.home, 0o755)
            os.chmod(agents, 0o755)
        self.assertEqual(0, self.run_ctl("status").returncode)
        if os.name != "nt":
            self.assertEqual(0o755, self.home.stat().st_mode & 0o777)
            self.assertEqual(0o755, agents.stat().st_mode & 0o777)

    def test_corrupt_ownership_and_journal_fail_closed(self) -> None:
        activation = self.data / "activation"
        activation.mkdir(parents=True)
        (activation / "active.json").write_text('{"schema_version":999,"files":{}}', encoding="utf-8")
        self.assertEqual(2, self.run_ctl("status").returncode)
        (activation / "active.json").unlink()
        transaction = activation / "transactions" / "broken"
        transaction.mkdir(parents=True)
        (transaction / "journal.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(2, self.run_ctl("status").returncode)

    def test_nested_corrupt_state_returns_json_without_traceback(self) -> None:
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        active_path = self.data / "activation" / "active.json"
        active = json.loads(active_path.read_text(encoding="utf-8"))
        active["files"]["gpt56_sol_owner.toml"] = "not-an-object"
        active_path.write_text(json.dumps(active), encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertEqual("error", self.payload(result)["status"])
        self.assertNotIn("Traceback", result.stderr)

    def test_nested_corrupt_journal_returns_json_without_traceback(self) -> None:
        transactions = self.data / "activation" / "transactions"
        transaction = transactions / "broken-nested"
        transaction.mkdir(parents=True)
        journal = {
            "schema_version": 1,
            "id": "broken-nested",
            "operation": "activate",
            "state": "PREPARED",
            "targets": ["gpt56_sol_owner.toml"],
            "snapshots": {"gpt56_sol_owner.toml": {"kind": "file", "backup": "../escape", "sha256": "x", "mode": True}},
            "active_snapshot": {"kind": "absent"},
        }
        (transaction / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertEqual("error", self.payload(result)["status"])
        self.assertNotIn("Traceback", result.stderr)

    def test_activation_drift_requires_reactivation(self) -> None:
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        active_path = self.data / "activation" / "active.json"
        active = json.loads(active_path.read_text(encoding="utf-8"))
        active["plugin_version"] = "0.0.0"
        active_path.write_text(json.dumps(active), encoding="utf-8")
        stale = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", stale["mode"])
        self.assertTrue(stale["activation_update_required"])
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        current = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", current["mode"])
        self.assertTrue(current["local_agent_ready"])
        self.assertFalse(current["activation_update_required"])

    def test_bundled_agent_drift_cannot_report_ready(self) -> None:
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents").returncode)
        target = self.home / "agents" / "gpt56_sol_owner.toml"
        target.write_text("validly-owned-but-not-current-bundle\n", encoding="utf-8")
        active_path = self.data / "activation" / "active.json"
        active = json.loads(active_path.read_text(encoding="utf-8"))
        active["files"][target.name]["installed_sha256"] = routerctl._sha(target)
        active_path.write_text(json.dumps(active), encoding="utf-8")
        status = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", status["mode"])
        self.assertTrue(status["activation_update_required"])
        self.assertEqual([target.name], status["bundled_agent_drift"])

    def test_missing_or_corrupt_original_backup_blocks_ready_and_lifecycle(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        original = agents / "gpt56_sol_owner.toml"
        original.write_text("user-owned\n", encoding="utf-8")
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents", "--replace-conflicts").returncode)
        backup = self.data / "activation" / "originals" / original.name
        backup.unlink()
        status = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", status["mode"])
        self.assertEqual([original.name], status["original_backup_conflicts"])
        for command in (("activate", "--legacy-agents"), ("repair",), ("deactivate",)):
            with self.subTest(command=command):
                result = self.run_ctl(*command)
                self.assertEqual(2, result.returncode)
                self.assertIn("original backups", result.stdout)

    def test_corrupt_original_backup_blocks_ready(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        original = agents / "gpt56_terra_worker.toml"
        original.write_text("user-owned\n", encoding="utf-8")
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents", "--replace-conflicts").returncode)
        backup = self.data / "activation" / "originals" / original.name
        backup.write_text("corrupt\n", encoding="utf-8")
        status = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", status["mode"])
        self.assertEqual([original.name], status["original_backup_conflicts"])

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_linked_original_backup_blocks_ready(self) -> None:
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        original = agents / "gpt56_luna_worker.toml"
        original.write_text("user-owned\n", encoding="utf-8")
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents", "--replace-conflicts").returncode)
        backup = self.data / "activation" / "originals" / original.name
        external = self.root / "external-original"
        external.write_text("user-owned\n", encoding="utf-8")
        backup.unlink()
        backup.symlink_to(external)
        status = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", status["mode"])
        self.assertEqual([original.name], status["original_backup_conflicts"])

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_recovery_rejects_linked_transaction_backup_directory(self) -> None:
        target = self.home / "agents" / "gpt56_sol_owner.toml"
        target.parent.mkdir(parents=True)
        target.write_text("mutated\n", encoding="utf-8")
        transaction = self.data / "activation" / "transactions" / "linked-before"
        transaction.mkdir(parents=True)
        external = self.root / "external-before"
        external.mkdir()
        backup = external / target.name
        backup.write_text("external-backup\n", encoding="utf-8")
        (transaction / "before").symlink_to(external, target_is_directory=True)
        journal = {
            "schema_version": 1,
            "id": transaction.name,
            "operation": "activate",
            "state": "COMMITTING",
            "targets": [target.name],
            "snapshots": {target.name: {"kind": "file", "backup": target.name, "sha256": routerctl._sha(backup), "mode": 0o600}},
            "active_snapshot": {"kind": "absent"},
        }
        (transaction / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertIn("symlink", result.stdout)
        self.assertEqual("mutated\n", target.read_text(encoding="utf-8"))

    def test_paths_with_spaces_and_unicode(self) -> None:
        base = self.root / "space and Δ"
        env = {**os.environ, "CODEX_HOME": str(base / "codex home"), "PLUGIN_DATA": str(base / "plugin data")}
        self.assertEqual(0, self.run_ctl("activate", "--legacy-agents", env=env).returncode)
        self.assertEqual("ADVISORY", self.payload(self.run_ctl("status", env=env))["mode"])
        self.assertEqual(0, self.run_ctl("deactivate", env=env).returncode)

    def test_windows_locking_branch_locks_and_unlocks_one_byte(self) -> None:
        class FakeMsvcrt:
            LK_LOCK = 1
            LK_UNLCK = 2

            def __init__(self) -> None:
                self.calls: list[tuple[int, int, int, int]] = []

            def locking(self, fileno: int, mode: int, size: int) -> None:
                self.calls.append((mode, size, os.lseek(fileno, 0, os.SEEK_CUR), os.fstat(fileno).st_size))

        original = (routerctl.ACTIVATION_ROOT, routerctl.LOCK_PATH, routerctl.fcntl, routerctl.msvcrt)
        fake = FakeMsvcrt()
        try:
            routerctl.ACTIVATION_ROOT = self.root / "windows-lock"
            routerctl.LOCK_PATH = routerctl.ACTIVATION_ROOT / "activation.lock"
            routerctl.fcntl = None
            routerctl.msvcrt = fake
            with routerctl._lock():
                self.assertTrue(routerctl.LOCK_PATH.exists())
        finally:
            routerctl.ACTIVATION_ROOT, routerctl.LOCK_PATH, routerctl.fcntl, routerctl.msvcrt = original
        self.assertEqual([(fake.LK_LOCK, 1, 0, 0), (fake.LK_UNLCK, 1, 0, 0)], fake.calls)

    def test_concurrent_activation_is_serialized_and_idempotent(self) -> None:
        def invoke(_: int) -> subprocess.CompletedProcess[str]:
            return self.run_ctl("activate", "--legacy-agents")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, range(2)))
        self.assertEqual(
            [0, 0], [result.returncode for result in results],
            [(result.stdout, result.stderr) for result in results if result.returncode != 0],
        )
        status = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", status["mode"])
        self.assertTrue(status["local_agent_ready"])
        self.assertEqual(6, len(list((self.home / "agents").glob("gpt56_*.toml"))))

    def test_sanitize_repairs_top_level_and_compacted_poison_conservatively(self) -> None:
        session = self.home / "sessions" / "2026" / "poisoned.jsonl"
        session.parent.mkdir(parents=True)
        uuid7_a = "019f5182-a1ce-72e1-aab4-5ee0c5de861f"
        uuid7_b = "019f5182-a1ce-72e1-aab4-5ee0c5de8620"
        uuid7_c = "019f5182-a1ce-72e1-aab4-5ee0c5de8621"
        hook = '<hook_prompt hook_run_id="stop:4:test">secret gate text</hook_prompt>'
        records = [
            {"type": "response_item", "payload": {"type": "message", "id": "msg_valid", "role": "user", "content": [{"type": "input_text", "text": "normal"}]}},
            {"type": "response_item", "payload": {"type": "message", "id": uuid7_a, "role": "user", "content": [{"type": "input_text", "text": hook}]}},
            {"type": "compacted", "payload": {"replacement_history": [
                {"type": "message", "id": uuid7_b, "role": "user", "content": [{"type": "input_text", "text": hook}]},
                {"type": "message", "id": uuid7_c, "role": "user", "content": [{"type": "input_text", "text": "keep this request\n" + hook}]},
            ]}},
            {"type": "custom_tool_call_output", "id": uuid7_a, "output": hook},
        ]
        original = b"".join(json.dumps(record).encode() + b"\n" for record in records)
        session.write_bytes(original)

        result = self.run_ctl("sanitize", "--session", str(session))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = self.payload(result)
        self.assertEqual(1, payload["files_modified"])
        self.assertEqual(2, payload["messages_removed"])
        self.assertEqual(1, payload["ids_removed"])
        self.assertEqual(1, payload["lines_removed"])
        self.assertNotIn("secret gate text", result.stdout)
        backup = Path(payload["backups"][0])
        self.assertEqual(original, backup.read_bytes())

        sanitized = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(3, len(sanitized))
        history = sanitized[1]["payload"]["replacement_history"]
        self.assertEqual(1, len(history))
        self.assertNotIn("id", history[0])
        self.assertIn("keep this request", history[0]["content"][0]["text"])
        self.assertEqual("custom_tool_call_output", sanitized[2]["type"])
        self.assertEqual(uuid7_a, sanitized[2]["id"])

    def test_sanitize_all_scans_active_and_archived_sessions_idempotently(self) -> None:
        hook = "<hook_prompt>gate</hook_prompt>"
        poisoned = {"type": "response_item", "payload": {"type": "message", "id": "019f5182-a1ce-72e1-aab4-5ee0c5de861f", "role": "user", "content": hook}}
        for root, name in (("sessions", "active.jsonl"), ("archived_sessions", "old.jsonl")):
            target = self.home / root / name
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(poisoned) + "\n", encoding="utf-8")
        first = self.payload(self.run_ctl("sanitize", "--all"))
        self.assertEqual(2, first["files_scanned"])
        self.assertEqual(2, first["files_modified"])
        self.assertEqual(2, first["lines_removed"])
        second = self.payload(self.run_ctl("sanitize", "--all"))
        self.assertEqual(2, second["files_scanned"])
        self.assertEqual(0, second["files_modified"])
        self.assertEqual([], second["backups"])

    def test_sanitize_invalid_json_fails_closed_without_backup_or_rewrite(self) -> None:
        session = self.home / "sessions" / "broken.jsonl"
        session.parent.mkdir(parents=True)
        original = b'{"valid":true}\n{broken\n'
        session.write_bytes(original)
        result = self.run_ctl("sanitize", "--session", str(session))
        self.assertEqual(2, result.returncode)
        self.assertEqual(original, session.read_bytes())
        self.assertEqual([], list(session.parent.glob("*.autorouter-backup.*")))

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_sanitize_refuses_linked_session(self) -> None:
        external = self.root / "external.jsonl"
        external.write_text('{"safe":true}\n', encoding="utf-8")
        linked = self.root / "linked.jsonl"
        linked.symlink_to(external)
        result = self.run_ctl("sanitize", "--session", str(linked))
        self.assertEqual(2, result.returncode)
        self.assertIn("refusing", result.stdout)
        self.assertEqual('{"safe":true}\n', external.read_text(encoding="utf-8"))

    @unittest.skipIf(not hasattr(os, "link"), "hard links unavailable")
    def test_sanitize_refuses_hard_linked_session(self) -> None:
        original = self.root / "original.jsonl"
        original.write_text('{"safe":true}\n', encoding="utf-8")
        linked = self.root / "hard-linked.jsonl"
        os.link(original, linked)
        result = self.run_ctl("sanitize", "--session", str(linked))
        self.assertEqual(2, result.returncode)
        self.assertIn("hard-linked", result.stdout)
        self.assertEqual('{"safe":true}\n', original.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
