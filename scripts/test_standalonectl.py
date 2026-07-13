#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


SCRIPT = Path(__file__).with_name("standalonectl.py")


class StandaloneCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "codex-home"
        self.data = self.root / "standalone-data"
        self.env = {
            **os.environ,
            "CODEX_HOME": str(self.home),
            "GPT56_STANDALONE_DATA": str(self.data),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_ctl(self, command: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_script(SCRIPT, command, env=env)

    def run_script(self, script: Path, command: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), command],
            env=env or self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertTrue(result.stdout, result.stderr)
        return json.loads(result.stdout)

    @property
    def target(self) -> Path:
        return self.home / "skills" / "route-gpt-5-6-work"

    def test_install_is_idempotent_and_uninstall_is_owned(self) -> None:
        initial = self.payload(self.run_ctl("status"))
        self.assertEqual("ADVISORY", initial["mode"])
        self.assertFalse(initial["active"])
        installed = self.payload(self.run_ctl("install"))
        self.assertTrue(installed["changed"])
        self.assertTrue((self.target / "SKILL.md").is_file())
        repeated = self.payload(self.run_ctl("install"))
        self.assertFalse(repeated["changed"])
        removed = self.payload(self.run_ctl("uninstall"))
        self.assertTrue(removed["changed"])
        self.assertFalse(self.target.exists())

    def test_purge_requires_uninstall_and_removes_valid_controllers(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        self.assertEqual(2, self.run_ctl("purge").returncode)
        self.assertEqual(0, self.run_ctl("uninstall").returncode)
        purged = self.payload(self.run_ctl("purge"))
        self.assertEqual("purged", purged["status"])
        self.assertGreaterEqual(purged["controllers_removed"], 1)
        self.assertFalse((self.data / "controllers").exists())

    def test_purge_refuses_controller_extras_and_preserves_them(self) -> None:
        installed = self.payload(self.run_ctl("install"))
        controller_root = Path(installed["controller"]).parents[1]
        extra = controller_root / "keep-me.txt"
        extra.write_text("preserve\n", encoding="utf-8")
        self.assertEqual(0, self.run_ctl("uninstall").returncode)
        result = self.run_ctl("purge")
        self.assertEqual(2, result.returncode)
        self.assertTrue(extra.exists())

    def test_purge_is_serialized_and_resumes_owned_scratch_cleanup(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        self.assertEqual(0, self.run_ctl("uninstall").returncode)
        crashed = self.run_ctl("purge", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "purge-renamed"})
        self.assertEqual(97, crashed.returncode)
        self.assertTrue((self.data / "controllers.purging").exists())
        with ThreadPoolExecutor(max_workers=2) as pool:
            purge_result, status_result = list(pool.map(lambda command: self.run_ctl(command), ("purge", "status")))
        self.assertEqual(0, purge_result.returncode)
        self.assertEqual(0, status_result.returncode)
        self.assertFalse((self.data / "controllers.purging").exists())

    def test_purge_recovers_after_owned_tree_was_deleted_before_journal_unlink(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        self.assertEqual(0, self.run_ctl("uninstall").returncode)
        crashed = self.run_ctl("purge", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "purge-cleaned"})
        self.assertEqual(97, crashed.returncode)
        self.assertFalse((self.data / "controllers").exists())
        self.assertFalse((self.data / "controllers.purging").exists())
        self.assertTrue((self.data / "purge.json").exists())
        self.assertEqual(0, self.run_ctl("purge").returncode)
        self.assertFalse((self.data / "purge.json").exists())

    def test_partial_purge_cleanup_is_resumable(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        self.assertEqual(0, self.run_ctl("uninstall").returncode)
        crashed = self.run_ctl("purge", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "purge-renamed"})
        self.assertEqual(97, crashed.returncode)
        purging = self.data / "controllers.purging"
        victim = next(path for path in purging.rglob("*") if path.is_file())
        victim.unlink()
        self.assertEqual(0, self.run_ctl("purge").returncode)
        self.assertFalse(purging.exists())

    def test_post_crash_purge_extra_is_preserved(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        self.assertEqual(0, self.run_ctl("uninstall").returncode)
        crashed = self.run_ctl("purge", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "purge-renamed"})
        self.assertEqual(97, crashed.returncode)
        extra = self.data / "controllers.purging" / "keep-me.txt"
        extra.write_text("post-crash edit\n", encoding="utf-8")
        result = self.run_ctl("purge")
        self.assertEqual(2, result.returncode)
        self.assertTrue(extra.exists())

    def test_standalone_routerctl_activates_agents_but_stays_advisory(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        (self.home / ".codex-plugin").mkdir()
        (self.home / ".codex-plugin" / "plugin.json").write_text('{"name":"gpt-5-6-router","version":"999.0.0"}', encoding="utf-8")
        (self.home / "hooks").mkdir()
        (self.home / "hooks" / "hooks.json").write_text('{"hooks":{}}', encoding="utf-8")
        routerctl = self.target / "scripts" / "routerctl.py"
        env = {**self.env, "PLUGIN_DATA": str(self.root / "agent-data")}
        activated = subprocess.run([sys.executable, str(routerctl), "activate"], env=env, text=True, capture_output=True, check=False)
        self.assertEqual(0, activated.returncode, activated.stdout + activated.stderr)
        status = subprocess.run([sys.executable, str(routerctl), "status"], env=env, text=True, capture_output=True, check=False)
        payload = json.loads(status.stdout)
        self.assertEqual("ADVISORY", payload["mode"])
        self.assertEqual("STANDALONE_ADVISORY", payload["runtime_surface"])
        self.assertTrue(payload["agents_active"])
        marker = self.target / ".gpt56-standalone.json"
        marker_bytes = marker.read_bytes()
        marker.unlink()
        invalid = subprocess.run([sys.executable, str(routerctl), "status"], env=env, text=True, capture_output=True, check=False)
        invalid_payload = json.loads(invalid.stdout)
        self.assertEqual("ADVISORY", invalid_payload["mode"])
        self.assertEqual("STANDALONE_INVALID", invalid_payload["runtime_surface"])
        marker.write_bytes(marker_bytes)
        if os.name != "nt":
            os.chmod(marker, 0o600)
        self.assertEqual(0, subprocess.run([sys.executable, str(routerctl), "deactivate"], env=env, capture_output=True, check=False).returncode)

    def test_every_controller_crash_boundary_recovers_deterministically(self) -> None:
        for point in ("controller-prepared", "controller-staged", "controller-installed"):
            with self.subTest(point=point):
                base = self.root / point
                env = {**self.env, "CODEX_HOME": str(base / "home"), "GPT56_STANDALONE_DATA": str(base / "data")}
                crashed = self.run_ctl("install", env={**env, "GPT56_STANDALONE_CRASH_AT": point})
                self.assertEqual(97, crashed.returncode)
                status = self.payload(self.run_ctl("status", env=env))
                self.assertFalse(status["active"])
                self.assertFalse((base / "data" / "controller-pending.json").exists())
                self.assertEqual([], list((base / "data" / "controllers").glob(".controller-stage-*")))

    def test_partial_controller_stage_cleanup_is_resumable(self) -> None:
        crashed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "controller-staged"})
        self.assertEqual(97, crashed.returncode)
        pending = json.loads((self.data / "controller-pending.json").read_text(encoding="utf-8"))
        stage = self.data / "controllers" / pending["stage"]
        next(path for path in stage.rglob("*") if path.is_file()).unlink()
        self.assertEqual(0, self.run_ctl("status").returncode)
        self.assertFalse(stage.exists())

    def test_post_crash_controller_stage_extra_is_preserved(self) -> None:
        crashed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "controller-staged"})
        self.assertEqual(97, crashed.returncode)
        pending = json.loads((self.data / "controller-pending.json").read_text(encoding="utf-8"))
        stage = self.data / "controllers" / pending["stage"]
        extra = stage / "keep-me.txt"
        extra.write_text("post-crash edit\n", encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertTrue(extra.exists())

    def test_durable_controller_survives_original_archive_removal(self) -> None:
        distribution = self.root / "removable-distribution"
        shutil.copytree(SCRIPT.parents[1], distribution, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        installed = self.payload(self.run_script(distribution / "scripts" / "standalonectl.py", "install"))
        controller = Path(installed["controller"])
        self.assertTrue(controller.is_file())
        shutil.rmtree(distribution)
        status = self.payload(self.run_script(controller, "status"))
        self.assertTrue(status["active"])
        self.assertEqual(0, self.run_script(controller, "uninstall").returncode)
        self.assertFalse(self.target.exists())

    def test_status_marks_a_missing_durable_controller_as_not_ready(self) -> None:
        installed = self.payload(self.run_ctl("install"))
        controller_root = Path(installed["controller"]).parents[1]
        shutil.rmtree(controller_root)
        status = self.payload(self.run_ctl("status"))
        self.assertTrue(status["active"])
        self.assertFalse(status["controller_ready"])
        self.assertTrue(status["update_required"])
        repaired = self.payload(self.run_ctl("install"))
        self.assertTrue(repaired["changed"])
        self.assertTrue(self.payload(self.run_ctl("status"))["controller_ready"])

    def test_foreign_target_is_never_overwritten_or_removed(self) -> None:
        self.target.mkdir(parents=True)
        marker = self.target / "SKILL.md"
        marker.write_text("foreign\n", encoding="utf-8")
        install = self.run_ctl("install")
        self.assertEqual(2, install.returncode)
        self.assertEqual("foreign\n", marker.read_text(encoding="utf-8"))
        uninstall = self.run_ctl("uninstall")
        self.assertEqual(2, uninstall.returncode)
        self.assertEqual("foreign\n", marker.read_text(encoding="utf-8"))

    def test_modified_owned_target_blocks_uninstall(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        marker = self.target / "SKILL.md"
        marker.write_text(marker.read_text(encoding="utf-8") + "\nuser edit\n", encoding="utf-8")
        status = self.payload(self.run_ctl("status"))
        self.assertTrue(status["modified"])
        result = self.run_ctl("uninstall")
        self.assertEqual(2, result.returncode)
        self.assertIn("modified", result.stdout)
        self.assertTrue(marker.exists())

    def test_extra_file_or_mode_drift_blocks_uninstall(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        extra = self.target / "user-note.txt"
        extra.write_text("keep me\n", encoding="utf-8")
        self.assertEqual(2, self.run_ctl("uninstall").returncode)
        self.assertTrue(extra.exists())
        extra.unlink()
        cache = self.target / "__pycache__"
        cache.mkdir()
        (cache / "keep-me.txt").write_text("user data\n", encoding="utf-8")
        (self.target / "user-owned.pyc").write_bytes(b"user data")
        status = self.payload(self.run_ctl("status"))
        self.assertTrue(status["modified"])
        self.assertEqual(2, self.run_ctl("uninstall").returncode)
        self.assertTrue((cache / "keep-me.txt").exists())
        self.assertTrue((self.target / "user-owned.pyc").exists())
        shutil.rmtree(cache)
        (self.target / "user-owned.pyc").unlink()
        if os.name != "nt":
            marker = self.target / "SKILL.md"
            os.chmod(marker, (marker.stat().st_mode & 0o777) ^ 0o100)
            self.assertEqual(2, self.run_ctl("uninstall").returncode)

    def test_shared_state_cannot_claim_or_delete_another_home(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        other_home = self.root / "other-home"
        other_target = other_home / "skills" / "route-gpt-5-6-work"
        other_target.parent.mkdir(parents=True)
        shutil.copytree(self.target, other_target)
        other_env = {**self.env, "CODEX_HOME": str(other_home)}
        self.assertEqual(2, self.run_ctl("status", env=other_env).returncode)
        self.assertEqual(2, self.run_ctl("uninstall", env=other_env).returncode)
        self.assertTrue(other_target.exists())
        self.assertTrue(self.target.exists())

    def test_state_root_overlap_is_refused_without_chmod_or_writes(self) -> None:
        skills = self.home / "skills"
        skills.mkdir(parents=True)
        if os.name != "nt":
            os.chmod(skills, 0o755)
        env = {**self.env, "GPT56_STANDALONE_DATA": str(skills)}
        result = self.run_ctl("status", env=env)
        self.assertEqual(2, result.returncode)
        self.assertEqual([], list(skills.iterdir()))
        if os.name != "nt":
            self.assertEqual(0o755, skills.stat().st_mode & 0o777)

    def test_corrupt_or_case_colliding_ownership_state_fails_cleanly(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        active_path = self.data / "active.json"
        active = json.loads(active_path.read_text(encoding="utf-8"))
        active["files"]["skill.md"] = dict(active["files"]["SKILL.md"])
        active_path.write_text(json.dumps(active), encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual("error", self.payload(result)["status"])

    def test_concurrent_installs_are_serialized(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_ctl("install"), range(2)))
        self.assertEqual(
            [0, 0],
            [result.returncode for result in results],
            "\n".join(result.stdout + result.stderr for result in results),
        )
        self.assertTrue(self.payload(self.run_ctl("status"))["active"])

    def test_concurrent_reader_waits_for_an_incomplete_exclusive_state_claim(self) -> None:
        self.data.mkdir(parents=True)
        marker = self.data / ".state-root.json"
        expected = {
            "schema_version": 1,
            "purpose": "gpt-5-6-router-standalone",
            "target_id": hashlib.sha256(os.fsencode(str(self.target))).hexdigest(),
        }
        payload = json.dumps(expected, indent=2, sort_keys=True) + "\n"
        writer = subprocess.Popen([
            sys.executable,
            "-c",
            (
                "import os,sys,time; "
                "fd=os.open(sys.argv[1], os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600); "
                "time.sleep(0.3); os.write(fd, sys.argv[2].encode()); os.fsync(fd); os.close(fd)"
            ),
            str(marker),
            payload,
        ])
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(marker.exists())
        result = self.run_ctl("status")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(0, writer.wait(timeout=2))

    def test_spaces_and_unicode_paths(self) -> None:
        base = self.root / "space and Δ"
        env = {**self.env, "CODEX_HOME": str(base / "codex home"), "GPT56_STANDALONE_DATA": str(base / "state data")}
        self.assertEqual(0, self.run_ctl("install", env=env).returncode)
        status = self.payload(self.run_ctl("status", env=env))
        self.assertTrue(status["active"])
        self.assertEqual(0, self.run_ctl("uninstall", env=env).returncode)

    def test_unowned_byte_identical_target_is_still_refused(self) -> None:
        self.target.parent.mkdir(parents=True)
        shutil.copytree(SCRIPT.parents[1] / "skills" / "route-gpt-5-6-work", self.target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        result = self.run_ctl("install")
        self.assertEqual(2, result.returncode)
        self.assertIn("unowned", result.stdout)

    def test_install_crash_after_target_is_recovered(self) -> None:
        crashed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "install-target"})
        self.assertEqual(97, crashed.returncode)
        status = self.payload(self.run_ctl("status"))
        self.assertFalse(status["active"])
        self.assertEqual("install", status["recovered"])
        self.assertFalse((self.data / "pending.json").exists())
        self.assertFalse(self.target.exists())
        self.assertEqual(0, self.run_ctl("install").returncode)

    def test_post_crash_user_edit_is_preserved_and_recovery_fails_closed(self) -> None:
        crashed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "install-target"})
        self.assertEqual(97, crashed.returncode)
        marker = self.target / "SKILL.md"
        marker.write_text(marker.read_text(encoding="utf-8") + "\npost-crash user edit\n", encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertIn("preserves", result.stdout)
        self.assertIn("post-crash user edit", marker.read_text(encoding="utf-8"))

    def test_uninstall_crash_after_rename_is_recovered(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        crashed = self.run_ctl("uninstall", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "uninstall-renamed"})
        self.assertEqual(97, crashed.returncode)
        status = self.payload(self.run_ctl("status"))
        self.assertTrue(status["active"])
        self.assertEqual("uninstall", status["recovered"])
        self.assertTrue(self.target.exists())
        self.assertEqual(0, self.run_ctl("uninstall").returncode)

    def test_modified_uninstall_quarantine_is_preserved(self) -> None:
        self.assertEqual(0, self.run_ctl("install").returncode)
        crashed = self.run_ctl("uninstall", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "uninstall-renamed"})
        self.assertEqual(97, crashed.returncode)
        quarantines = list((self.home / "skills").glob(".route-gpt-5-6-work.quarantine-*"))
        self.assertEqual(1, len(quarantines))
        marker = quarantines[0] / "SKILL.md"
        marker.write_text(marker.read_text(encoding="utf-8") + "\npost-crash edit\n", encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertTrue(quarantines[0].exists())
        self.assertIn("post-crash edit", marker.read_text(encoding="utf-8"))

    def test_managed_update_is_transactional(self) -> None:
        distribution = self.root / "distribution"
        shutil.copytree(SCRIPT.parents[1], distribution, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        script = distribution / "scripts" / "standalonectl.py"
        self.assertEqual(0, self.run_script(script, "install").returncode)
        reference = distribution / "skills" / "route-gpt-5-6-work" / "references" / "product-routing.md"
        reference.write_text(reference.read_text(encoding="utf-8") + "\nupdate-marker\n", encoding="utf-8")
        manifest = distribution / ".codex-plugin" / "plugin.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["version"] = "9.9.9"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        updated = self.payload(self.run_script(script, "install"))
        self.assertTrue(updated["changed"])
        self.assertIn("update-marker", (self.target / "references" / "product-routing.md").read_text(encoding="utf-8"))
        status = self.payload(self.run_script(script, "status"))
        self.assertFalse(status["update_required"])
        active = json.loads((self.data / "active.json").read_text(encoding="utf-8"))
        self.assertEqual("9.9.9", active["version"])

    def test_update_crash_before_manifest_rolls_back_exact_old_tree(self) -> None:
        distribution = self.root / "distribution"
        shutil.copytree(SCRIPT.parents[1], distribution, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        script = distribution / "scripts" / "standalonectl.py"
        self.assertEqual(0, self.run_script(script, "install").returncode)
        before = {path.relative_to(self.target).as_posix(): path.read_bytes() for path in self.target.rglob("*") if path.is_file()}
        source = distribution / "skills" / "route-gpt-5-6-work" / "SKILL.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nnew-version\n", encoding="utf-8")
        manifest = distribution / ".codex-plugin" / "plugin.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["version"] = "9.9.8"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        crashed = self.run_script(script, "install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "update-target"})
        self.assertEqual(97, crashed.returncode)
        status = self.payload(self.run_script(script, "status"))
        self.assertEqual("update", status["recovered"])
        after = {path.relative_to(self.target).as_posix(): path.read_bytes() for path in self.target.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(status["update_required"])

    def test_update_crash_after_manifest_commits_new_tree(self) -> None:
        distribution = self.root / "distribution"
        shutil.copytree(SCRIPT.parents[1], distribution, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        script = distribution / "scripts" / "standalonectl.py"
        self.assertEqual(0, self.run_script(script, "install").returncode)
        source = distribution / "skills" / "route-gpt-5-6-work" / "SKILL.md"
        source.write_text(source.read_text(encoding="utf-8") + "\ncommitted-version\n", encoding="utf-8")
        manifest = distribution / ".codex-plugin" / "plugin.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["version"] = "9.9.7"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        crashed = self.run_script(script, "install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "update-active"})
        self.assertEqual(97, crashed.returncode)
        status = self.payload(self.run_script(script, "status"))
        self.assertEqual("update", status["recovered"])
        self.assertFalse(status["update_required"])
        self.assertIn("committed-version", (self.target / "SKILL.md").read_text(encoding="utf-8"))

    def test_every_install_crash_boundary_recovers_deterministically(self) -> None:
        for point in ("install-prepared", "install-staged", "install-target", "install-active"):
            with self.subTest(point=point):
                base = self.root / point
                env = {**self.env, "CODEX_HOME": str(base / "home"), "GPT56_STANDALONE_DATA": str(base / "data")}
                crashed = self.run_ctl("install", env={**env, "GPT56_STANDALONE_CRASH_AT": point})
                self.assertEqual(97, crashed.returncode)
                status = self.payload(self.run_ctl("status", env=env))
                self.assertEqual("install", status["recovered"])
                self.assertEqual(point == "install-active", status["active"])

    def test_every_uninstall_crash_boundary_recovers_deterministically(self) -> None:
        for point in ("uninstall-prepared", "uninstall-renamed", "uninstall-inactive"):
            with self.subTest(point=point):
                base = self.root / point
                env = {**self.env, "CODEX_HOME": str(base / "home"), "GPT56_STANDALONE_DATA": str(base / "data")}
                self.assertEqual(0, self.run_ctl("install", env=env).returncode)
                crashed = self.run_ctl("uninstall", env={**env, "GPT56_STANDALONE_CRASH_AT": point})
                self.assertEqual(97, crashed.returncode)
                status = self.payload(self.run_ctl("status", env=env))
                self.assertEqual("uninstall", status["recovered"])
                self.assertEqual(point != "uninstall-inactive", status["active"])

    def test_every_update_crash_boundary_rolls_back_or_commits(self) -> None:
        distribution = self.root / "boundary-distribution"
        shutil.copytree(SCRIPT.parents[1], distribution, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        script = distribution / "scripts" / "standalonectl.py"
        points = ("update-prepared", "update-staged", "update-old-renamed", "update-target", "update-active")
        for point in points:
            with self.subTest(point=point):
                base = self.root / point
                env = {**self.env, "CODEX_HOME": str(base / "home"), "GPT56_STANDALONE_DATA": str(base / "data")}
                self.assertEqual(0, self.run_script(script, "install", env=env).returncode)
                target = Path(env["CODEX_HOME"]) / "skills" / "route-gpt-5-6-work" / "SKILL.md"
                old_bytes = target.read_bytes()
                source = distribution / "skills" / "route-gpt-5-6-work" / "SKILL.md"
                source.write_bytes(source.read_bytes() + f"\n{point}\n".encode())
                manifest = distribution / ".codex-plugin" / "plugin.json"
                value = json.loads(manifest.read_text(encoding="utf-8"))
                value["version"] = f"8.0.{points.index(point)}"
                manifest.write_text(json.dumps(value), encoding="utf-8")
                crashed = self.run_script(script, "install", env={**env, "GPT56_STANDALONE_CRASH_AT": point})
                self.assertEqual(97, crashed.returncode)
                status = self.payload(self.run_script(script, "status", env=env))
                self.assertEqual("update", status["recovered"])
                if point == "update-active":
                    self.assertIn(point.encode(), target.read_bytes())
                    self.assertFalse(status["update_required"])
                else:
                    self.assertEqual(old_bytes, target.read_bytes())
                    self.assertTrue(status["update_required"])

    def test_pre_stage_failure_is_safely_retried(self) -> None:
        failed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_FAIL_AT": "install-prepared"})
        self.assertEqual(2, failed.returncode)
        status = self.payload(self.run_ctl("status"))
        self.assertFalse(status["active"])
        self.assertEqual("install", status["recovered"])
        self.assertEqual(0, self.run_ctl("install").returncode)

    def test_partial_transaction_stage_cleanup_is_resumable(self) -> None:
        crashed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "install-prepared"})
        self.assertEqual(97, crashed.returncode)
        pending = json.loads((self.data / "pending.json").read_text(encoding="utf-8"))
        partial = self.home / "skills" / pending["stage"]
        partial.mkdir(parents=True)
        shutil.copy2(SCRIPT.parents[1] / "skills" / "route-gpt-5-6-work" / "SKILL.md", partial / "SKILL.md")
        status = self.payload(self.run_ctl("status"))
        self.assertEqual("install", status["recovered"])
        self.assertFalse(partial.exists())
        self.assertFalse(status["active"])

    def test_post_crash_stage_extra_is_preserved(self) -> None:
        crashed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "install-staged"})
        self.assertEqual(97, crashed.returncode)
        pending = json.loads((self.data / "pending.json").read_text(encoding="utf-8"))
        stage = self.home / "skills" / pending["stage"]
        extra = stage / "keep-me.txt"
        extra.write_text("post-crash edit\n", encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertTrue(extra.exists())

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_linked_target_is_refused(self) -> None:
        external = self.root / "external"
        external.mkdir()
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(external, target_is_directory=True)
        result = self.run_ctl("install")
        self.assertEqual(2, result.returncode)
        self.assertEqual([], list(external.iterdir()))

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_linked_codex_home_ancestor_is_refused(self) -> None:
        external = self.root / "external-home"
        external.mkdir()
        linked = self.root / "linked-home"
        linked.symlink_to(external, target_is_directory=True)
        result = self.run_ctl("install", env={**self.env, "CODEX_HOME": str(linked)})
        self.assertEqual(2, result.returncode)
        self.assertEqual([], list(external.iterdir()))

    def test_corrupt_pending_paths_fail_cleanly(self) -> None:
        crashed = self.run_ctl("install", env={**self.env, "GPT56_STANDALONE_CRASH_AT": "install-prepared"})
        self.assertEqual(97, crashed.returncode)
        pending_path = self.data / "pending.json"
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        pending["stage"] = "../escape"
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        result = self.run_ctl("status")
        self.assertEqual(2, result.returncode)
        self.assertEqual("error", self.payload(result)["status"])
        self.assertNotIn("Traceback", result.stderr)

    def test_hardlinked_source_file_is_rejected(self) -> None:
        if not hasattr(os, "link"):
            self.skipTest("hardlinks unavailable")
        distribution = self.root / "hardlinked-distribution"
        shutil.copytree(SCRIPT.parents[1], distribution, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        skill = distribution / "skills" / "route-gpt-5-6-work"
        linked = skill / "references" / "hardlinked.md"
        os.link(skill / "SKILL.md", linked)
        result = self.run_script(distribution / "scripts" / "standalonectl.py", "status")
        self.assertEqual(2, result.returncode)
        self.assertIn("invalid file", result.stdout)

    def test_existing_user_directory_modes_are_unchanged(self) -> None:
        skills = self.home / "skills"
        skills.mkdir(parents=True)
        if os.name != "nt":
            os.chmod(self.home, 0o755)
            os.chmod(skills, 0o755)
        self.assertEqual(0, self.run_ctl("status").returncode)
        if os.name != "nt":
            self.assertEqual(0o755, self.home.stat().st_mode & 0o777)
            self.assertEqual(0o755, skills.stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main(verbosity=2)
