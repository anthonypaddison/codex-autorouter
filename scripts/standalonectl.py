#!/usr/bin/env python3
"""Conflict-safe lifecycle for the advisory standalone router skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None  # type: ignore[assignment]


SCRIPT = Path(__file__).resolve()
PLUGIN_ROOT = SCRIPT.parents[1]
SOURCE = PLUGIN_ROOT / "skills" / "route-gpt-5-6-work"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().absolute()
TARGET = CODEX_HOME / "skills" / "route-gpt-5-6-work"
DATA = Path(
    os.environ.get("GPT56_STANDALONE_DATA")
    or CODEX_HOME / "plugin-data" / "gpt-5-6-router" / "standalone"
).expanduser().absolute()
ACTIVE = DATA / "active.json"
PENDING = DATA / "pending.json"
LOCK = DATA / "standalone.lock"
CONTROLLERS = DATA / "controllers"
STATE_MARKER = DATA / ".state-root.json"
CONTROLLER_PENDING = DATA / "controller-pending.json"
PURGE_STATE = DATA / "purge.json"
SCHEMA_VERSION = 1
SHA256 = __import__("re").compile(r"^[0-9a-f]{64}$")
IGNORED = {"__pycache__", ".DS_Store"}
STANDALONE_MARKER = ".gpt56-standalone.json"
STANDALONE_MARKER_BYTES = b'{"schema_version":1,"surface":"standalone_advisory"}\n'
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class StandaloneError(RuntimeError):
    pass


def _target_id() -> str:
    return hashlib.sha256(os.fsencode(str(TARGET))).hexdigest()


def _running_from_controller() -> bool:
    try:
        relative = SCRIPT.relative_to(CONTROLLERS)
    except ValueError:
        return False
    return len(relative.parts) == 3 and SHA256.fullmatch(relative.parts[0]) is not None and relative.parts[1:] == ("scripts", "standalonectl.py")


def _is_linklike(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(int(getattr(info, "st_file_attributes", 0)) & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def _canonical(path: Path) -> None:
    if path.resolve(strict=False) != path:
        raise StandaloneError(f"refusing a path with symlink, junction, or reparse ancestors: {path}")


def _ensure_dir(path: Path, *, private: bool = False, tighten_existing: bool = False) -> None:
    _canonical(path)
    if _is_linklike(path):
        raise StandaloneError(f"refusing linked directory: {path}")
    existed = path.exists()
    path.mkdir(mode=0o700 if private else 0o755, parents=True, exist_ok=True)
    if not path.is_dir():
        raise StandaloneError(f"expected directory: {path}")
    if private and (not existed or tighten_existing):
        try:
            os.chmod(path, 0o700)
        except OSError:
            if os.name != "nt":
                raise


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace(source: Path, target: Path) -> None:
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 5:
                raise
            time.sleep(0.05 * (2**attempt))


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _ensure_dir(path.parent, private=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            if os.name != "nt":
                raise
        _replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _claim_state_root(value: dict[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(STATE_MARKER, flags, 0o600)
    except FileExistsError:
        _await_state_marker(value)
        return
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_dir(DATA)
    except Exception:
        # A partial exclusive claim must remain fail-closed for explicit review.
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() and not _is_linklike(path):
        return None
    info = path.stat()
    if _is_linklike(path) or not path.is_file() or info.st_size > 4 * 1024 * 1024 or info.st_nlink != 1:
        raise StandaloneError(f"invalid state file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StandaloneError(f"cannot read state file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StandaloneError(f"state file must contain an object: {path}")
    return value


def _await_state_marker(expected: dict[str, Any], timeout: float = 2.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    delay = 0.005
    while True:
        if _is_linklike(STATE_MARKER):
            raise StandaloneError(f"invalid state file: {STATE_MARKER}")
        try:
            info = STATE_MARKER.stat()
            if not STATE_MARKER.is_file() or info.st_size > 4096 or info.st_nlink != 1:
                raise StandaloneError(f"invalid state file: {STATE_MARKER}")
            raw = STATE_MARKER.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = ""
        except (OSError, UnicodeDecodeError) as exc:
            raise StandaloneError(f"cannot read state file {STATE_MARKER}: {exc}") from exc
        try:
            marker = json.loads(raw)
        except json.JSONDecodeError:
            if time.monotonic() >= deadline:
                raise StandaloneError("standalone state-root claim did not complete before timeout")
            time.sleep(delay)
            delay = min(delay * 2, 0.05)
            continue
        if marker != expected:
            raise StandaloneError("standalone state root belongs to a different target")
        return marker


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(relative: str) -> bool:
    path = Path(relative)
    if not relative or "\\" in relative or path.is_absolute() or ".." in path.parts:
        return False
    for part in path.parts:
        stem = part.split(".", 1)[0].upper()
        if not part or part.endswith((" ", ".")) or ":" in part or stem in WINDOWS_RESERVED:
            return False
    return True


def _normalized_mode(info: os.stat_result) -> int:
    return 0 if os.name == "nt" else stat.S_IMODE(info.st_mode) & 0o777


def _tree_hashes(root: Path, *, reject_generated: bool = False, require_skill: bool = True) -> dict[str, dict[str, Any]]:
    if _is_linklike(root) or not root.is_dir():
        raise StandaloneError(f"invalid skill tree: {root}")
    root_info = os.lstat(root)
    files: dict[str, dict[str, Any]] = {"./": {"kind": "directory", "mode": _normalized_mode(root_info)}}
    casefolded: set[str] = {"."}
    for directory, names, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in list(names):
            child = base / name
            if name in IGNORED and reject_generated:
                raise StandaloneError(f"skill source contains a generated artifact: {child}")
            if _is_linklike(child):
                raise StandaloneError(f"skill tree contains a linked directory: {child}")
            info = os.lstat(child)
            if not stat.S_ISDIR(info.st_mode):
                raise StandaloneError(f"skill tree contains a special directory entry: {child}")
            relative = child.relative_to(root).as_posix() + "/"
            folded = relative.rstrip("/").casefold()
            if not _safe_relative(relative) or folded in casefolded:
                raise StandaloneError(f"skill tree contains an unsafe or case-colliding path: {relative}")
            casefolded.add(folded)
            files[relative] = {"kind": "directory", "mode": _normalized_mode(info)}
        for name in filenames:
            child = base / name
            if (name in IGNORED or name.endswith((".pyc", ".pyo"))) and reject_generated:
                raise StandaloneError(f"skill source contains a generated artifact: {child}")
            info = os.lstat(child)
            if _is_linklike(child) or not stat.S_ISREG(info.st_mode) or int(getattr(info, "st_nlink", 1)) != 1:
                raise StandaloneError(f"skill tree contains an invalid file: {child}")
            relative = child.relative_to(root).as_posix()
            folded = relative.rstrip("/").casefold()
            if not _safe_relative(relative) or folded in casefolded:
                raise StandaloneError(f"skill tree contains an unsafe or case-colliding path: {relative}")
            casefolded.add(folded)
            files[relative] = {"kind": "file", "sha256": _sha(child), "mode": _normalized_mode(info)}
    if require_skill and "SKILL.md" not in files:
        raise StandaloneError("skill tree is missing SKILL.md")
    return dict(sorted(files.items()))


def _source_inventory() -> dict[str, dict[str, Any]]:
    return _tree_hashes(SOURCE, reject_generated=True)


def _validate_files(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or not value:
        raise StandaloneError("standalone state contains an invalid file manifest")
    clean: dict[str, dict[str, Any]] = {}
    casefolded: set[str] = set()
    for relative, metadata in value.items():
        folded = relative.rstrip("/").casefold() if isinstance(relative, str) else ""
        kind = metadata.get("kind") if isinstance(metadata, dict) else None
        if (
            not isinstance(relative, str)
            or not _safe_relative(relative)
            or folded in casefolded
            or not isinstance(metadata, dict)
            or kind not in {"file", "directory"}
            or (kind == "file" and (relative.endswith("/") or not isinstance(metadata.get("sha256"), str) or SHA256.fullmatch(metadata["sha256"]) is None))
            or (kind == "directory" and (not relative.endswith("/") or "sha256" in metadata))
            or isinstance(metadata.get("mode"), bool)
            or not isinstance(metadata.get("mode"), int)
            or not 0 <= metadata["mode"] <= 0o777
        ):
            raise StandaloneError("standalone state contains unsafe file metadata")
        casefolded.add(folded)
        clean[relative] = {"kind": kind, "mode": metadata["mode"]}
        if kind == "file":
            clean[relative]["sha256"] = metadata["sha256"]
    return dict(sorted(clean.items()))


def _version() -> str:
    manifest = _read_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    if manifest and isinstance(manifest.get("version"), str) and manifest["version"]:
        return manifest["version"]
    digest = hashlib.sha256(json.dumps(_source_inventory(), sort_keys=True).encode()).hexdigest()[:16]
    return "standalone-" + digest


def _controller_id(version: str, inventory: dict[str, dict[str, Any]]) -> str:
    return hashlib.sha256((version + "\n" + json.dumps(inventory, sort_keys=True)).encode()).hexdigest()


def _installed_inventory(source_files: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    installed = json.loads(json.dumps(source_files))
    installed[STANDALONE_MARKER] = {
        "kind": "file",
        "sha256": hashlib.sha256(STANDALONE_MARKER_BYTES).hexdigest(),
        "mode": 0 if os.name == "nt" else 0o600,
    }
    return dict(sorted(installed.items()))


def _write_standalone_marker(stage: Path) -> None:
    marker = stage / STANDALONE_MARKER
    with marker.open("wb") as stream:
        stream.write(STANDALONE_MARKER_BYTES)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.chmod(marker, 0o600)
    except OSError:
        if os.name != "nt":
            raise


def _ensure_controller(version: str, files: dict[str, dict[str, Any]]) -> str:
    _ensure_dir(CONTROLLERS, private=True, tighten_existing=True)
    with tempfile.TemporaryDirectory(prefix="gpt56-controller-") as raw:
        blueprint = Path(raw) / "controller"
        blueprint.mkdir()
        (blueprint / ".codex-plugin").mkdir()
        shutil.copy2(PLUGIN_ROOT / ".codex-plugin" / "plugin.json", blueprint / ".codex-plugin" / "plugin.json")
        (blueprint / "scripts").mkdir()
        shutil.copy2(SCRIPT, blueprint / "scripts" / "standalonectl.py")
        (blueprint / "skills").mkdir()
        shutil.copytree(SOURCE, blueprint / "skills" / "route-gpt-5-6-work", symlinks=False, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"))
        if not _matches(blueprint / "skills" / "route-gpt-5-6-work", files):
            raise StandaloneError("durable standalone controller staging verification failed")
        inventory = _tree_hashes(blueprint, require_skill=False)
        identifier = _controller_id(version, inventory)
        controller = CONTROLLERS / identifier
        if controller.exists() or _is_linklike(controller):
            _validate_controller(controller)
            if _tree_hashes(controller, require_skill=False) != inventory:
                raise StandaloneError("durable standalone controller inventory collision")
            return identifier
        stage_name = f".controller-stage-{uuid.uuid4()}"
        stage = CONTROLLERS / stage_name
        _atomic_json(CONTROLLER_PENDING, {
            "schema_version": SCHEMA_VERSION,
            "target_id": _target_id(),
            "stage": stage_name,
            "controller_id": identifier,
            "version": version,
            "inventory": inventory,
        })
        _failpoint("controller-prepared")
        shutil.copytree(blueprint, stage)
        _fsync_tree(stage)
        if _tree_hashes(stage, require_skill=False) != inventory:
            raise StandaloneError("durable standalone controller copy drifted")
        _failpoint("controller-staged")
        _replace(stage, controller)
        _fsync_dir(CONTROLLERS)
        _failpoint("controller-installed")
        _unlink_state(CONTROLLER_PENDING)
        return identifier


def _validate_controller(controller: Path) -> None:
    if _is_linklike(controller) or not controller.is_dir() or SHA256.fullmatch(controller.name) is None:
        raise StandaloneError(f"invalid durable controller: {controller}")
    manifest = _read_json(controller / ".codex-plugin" / "plugin.json")
    inventory = _tree_hashes(controller, require_skill=False)
    if (
        not manifest
        or not isinstance(manifest.get("version"), str)
        or _controller_id(manifest["version"], inventory) != controller.name
    ):
        raise StandaloneError(f"durable controller inventory mismatch: {controller}")


def _active_manifest(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or not isinstance(value.get("version"), str)
        or not value["version"]
        or value.get("target") != TARGET.name
        or value.get("target_id") != _target_id()
        or not isinstance(value.get("controller_id"), str)
        or SHA256.fullmatch(value["controller_id"]) is None
    ):
        raise StandaloneError("standalone ownership manifest is corrupt")
    value["files"] = _validate_files(value.get("files"))
    return value


def _pending_manifest(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    operation = value.get("operation")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("target_id") != _target_id() or operation not in {"install", "update", "uninstall"}:
        raise StandaloneError("standalone pending transaction is corrupt")
    for key in ("old_files", "new_files"):
        files = value.get(key)
        value[key] = None if files is None else _validate_files(files)
    for key in ("old_version", "new_version"):
        version = value.get(key)
        if version is not None and (not isinstance(version, str) or not version):
            raise StandaloneError("standalone transaction contains an invalid version")
    for key, prefix in (("stage", f".{TARGET.name}.stage-"), ("quarantine", f".{TARGET.name}.quarantine-")):
        name = value.get(key)
        if name is not None and (not isinstance(name, str) or Path(name).name != name or not name.startswith(prefix)):
            raise StandaloneError("standalone transaction contains an unsafe temporary path")
    required = {
        "install": (None, "new_files", None, "new_version", "stage", None),
        "update": ("old_files", "new_files", "old_version", "new_version", "stage", "quarantine"),
        "uninstall": ("old_files", None, "old_version", None, None, "quarantine"),
    }[operation]
    for actual, expected in zip(
        (value.get("old_files"), value.get("new_files"), value.get("old_version"), value.get("new_version"), value.get("stage"), value.get("quarantine")),
        required,
    ):
        if (expected is None and actual is not None) or (expected is not None and actual is None):
            raise StandaloneError("standalone pending transaction has inconsistent fields")
    return value


def _matches(root: Path, expected: dict[str, dict[str, Any]]) -> bool:
    try:
        return _tree_hashes(root) == expected
    except StandaloneError:
        return False


def _fsync_tree(root: Path) -> None:
    if os.name == "nt":
        return
    directories: list[Path] = []
    for directory, _, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        directories.append(base)
        for name in filenames:
            path = base / name
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for directory in reversed(directories):
        _fsync_dir(directory)


def _unlink_state(path: Path) -> None:
    if path.exists():
        if _is_linklike(path) or not path.is_file():
            raise StandaloneError(f"refusing invalid state cleanup: {path}")
        path.unlink()
        _fsync_dir(path.parent)


def _failpoint(name: str) -> None:
    if os.environ.get("GPT56_STANDALONE_CRASH_AT") == name:
        os._exit(97)
    if os.environ.get("GPT56_STANDALONE_FAIL_AT") == name:
        raise StandaloneError(f"injected failure at {name}")


def _open_lock_file(flags: int) -> int:
    for attempt in range(6):
        try:
            return os.open(LOCK, flags, 0o600)
        except PermissionError:
            if os.name != "nt" or attempt == 5:
                raise
            time.sleep(0.05 * (2**attempt))
    raise AssertionError("unreachable lock-open retry state")


@contextmanager
def _lock():
    _ensure_dir(DATA, private=True, tighten_existing=True)
    if _is_linklike(LOCK):
        raise StandaloneError(f"refusing linked lock: {LOCK}")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = _open_lock_file(flags)
    with os.fdopen(descriptor, "a+b", buffering=0) as stream:
        if fcntl is not None:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"\0")
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _validate_roots() -> Path:
    for path in (CODEX_HOME, TARGET.parent, DATA):
        _canonical(path)
        if _is_linklike(path):
            raise StandaloneError(f"refusing linked lifecycle root: {path}")
    _canonical(SOURCE)
    durable_source = _running_from_controller()
    if (
        DATA in {CODEX_HOME, TARGET.parent, TARGET, SOURCE}
        or TARGET.is_relative_to(DATA)
        or DATA.is_relative_to(TARGET)
        or DATA.is_relative_to(TARGET.parent)
        or DATA.is_relative_to(SOURCE)
        or (SOURCE.is_relative_to(DATA) and not durable_source)
    ):
        raise StandaloneError("standalone state root overlaps a protected lifecycle path")
    _source_inventory()
    _ensure_dir(CODEX_HOME)
    _ensure_dir(TARGET.parent)
    expected_marker = {"schema_version": SCHEMA_VERSION, "purpose": "gpt-5-6-router-standalone", "target_id": _target_id()}
    if DATA.exists():
        if not DATA.is_dir():
            raise StandaloneError(f"standalone state root is not a directory: {DATA}")
        marker = _await_state_marker(expected_marker) if STATE_MARKER.exists() or _is_linklike(STATE_MARKER) else None
        if marker is None and any(DATA.iterdir()):
            marker = _await_state_marker(expected_marker) if STATE_MARKER.exists() or _is_linklike(STATE_MARKER) else None
            if marker is None:
                raise StandaloneError("refusing a nonempty unowned standalone state root")
        if marker is not None and marker != expected_marker:
            raise StandaloneError("standalone state root belongs to a different target")
    _ensure_dir(DATA, private=True, tighten_existing=True)
    if not STATE_MARKER.exists():
        _claim_state_root(expected_marker)
    else:
        _await_state_marker(expected_marker)
    return TARGET.parent


def _inspect_roots() -> Path:
    """Validate standalone roots without creating, locking, chmodding, or recovering."""
    for path in (CODEX_HOME, TARGET.parent, DATA):
        _canonical(path)
        if _is_linklike(path):
            raise StandaloneError(f"refusing linked lifecycle root: {path}")
    _canonical(SOURCE)
    durable_source = _running_from_controller()
    if (
        DATA in {CODEX_HOME, TARGET.parent, TARGET, SOURCE}
        or TARGET.is_relative_to(DATA)
        or DATA.is_relative_to(TARGET)
        or DATA.is_relative_to(TARGET.parent)
        or DATA.is_relative_to(SOURCE)
        or (SOURCE.is_relative_to(DATA) and not durable_source)
    ):
        raise StandaloneError("standalone state root overlaps a protected lifecycle path")
    _source_inventory()
    for path in (CODEX_HOME, TARGET.parent, DATA):
        if path.exists() and not path.is_dir():
            raise StandaloneError(f"expected directory: {path}")
    expected_marker = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "gpt-5-6-router-standalone",
        "target_id": _target_id(),
    }
    if DATA.exists():
        marker_exists = STATE_MARKER.exists() or _is_linklike(STATE_MARKER)
        if marker_exists:
            _await_state_marker(expected_marker)
        elif any(DATA.iterdir()):
            raise StandaloneError("refusing a nonempty unowned standalone state root")
    return TARGET.parent


def _controller_transaction_pending() -> bool:
    value = _read_json(CONTROLLER_PENDING)
    if value is None:
        return False
    stage_name = value.get("stage")
    identifier = value.get("controller_id")
    version = value.get("version")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("target_id") != _target_id()
        or not isinstance(stage_name, str)
        or not stage_name.startswith(".controller-stage-")
        or Path(stage_name).name != stage_name
        or not isinstance(identifier, str)
        or SHA256.fullmatch(identifier) is None
        or not isinstance(version, str)
        or not version
    ):
        raise StandaloneError("durable-controller transaction is corrupt")
    inventory = _validate_files(value.get("inventory"))
    if _controller_id(version, inventory) != identifier:
        raise StandaloneError("durable-controller transaction identity mismatch")
    return True


def _owned_state(version: str, files: dict[str, dict[str, Any]], controller_id: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "version": version, "target": TARGET.name, "target_id": _target_id(), "controller_id": controller_id, "files": files}


def _remove_exact(path: Path, files: dict[str, dict[str, Any]], skills: Path) -> None:
    if not (path.exists() or _is_linklike(path)):
        return
    if _is_linklike(path) or not _matches(path, files):
        raise StandaloneError(f"standalone recovery preserves a modified transaction tree: {path}")
    shutil.rmtree(path)
    _fsync_dir(skills)


def _inventory_is_subset(path: Path, expected: dict[str, dict[str, Any]]) -> bool:
    try:
        observed = _tree_hashes(path, require_skill=False)
    except StandaloneError:
        return False
    return all(expected.get(relative) == metadata for relative, metadata in observed.items())


def _remove_scratch(path: Path, parent: Path, expected: dict[str, dict[str, Any]]) -> None:
    if not (path.exists() or _is_linklike(path)):
        return
    if path.parent != parent or _is_linklike(path) or not path.is_dir() or not _inventory_is_subset(path, expected):
        raise StandaloneError(f"refusing invalid transaction scratch cleanup: {path}")
    shutil.rmtree(path)
    _fsync_dir(parent)


def _recover_controller_stages() -> None:
    pending = _read_json(CONTROLLER_PENDING)
    recorded_stage: str | None = None
    if pending is not None:
        stage_name = pending.get("stage")
        identifier = pending.get("controller_id")
        version = pending.get("version")
        if (
            pending.get("schema_version") != SCHEMA_VERSION
            or pending.get("target_id") != _target_id()
            or not isinstance(stage_name, str)
            or not stage_name.startswith(".controller-stage-")
            or Path(stage_name).name != stage_name
            or not isinstance(identifier, str)
            or SHA256.fullmatch(identifier) is None
            or not isinstance(version, str)
            or not version
        ):
            raise StandaloneError("durable-controller transaction is corrupt")
        inventory = _validate_files(pending.get("inventory"))
        if _controller_id(version, inventory) != identifier:
            raise StandaloneError("durable-controller transaction identity mismatch")
        stage = CONTROLLERS / stage_name
        controller = CONTROLLERS / identifier
        recorded_stage = stage_name
        if controller.exists() or _is_linklike(controller):
            _validate_controller(controller)
            if _tree_hashes(controller, require_skill=False) != inventory or stage.exists() or _is_linklike(stage):
                raise StandaloneError("durable-controller recovery found conflicting trees")
        elif stage.exists() or _is_linklike(stage):
            _remove_scratch(stage, CONTROLLERS, inventory)
        _unlink_state(CONTROLLER_PENDING)
    if CONTROLLERS.exists():
        for path in CONTROLLERS.iterdir():
            if path.name.startswith(".controller-stage-") and path.name != recorded_stage:
                raise StandaloneError(f"unowned durable-controller scratch requires review: {path}")


def _recover(skills: Path) -> str | None:
    _recover_controller_stages()
    pending = _pending_manifest(_read_json(PENDING))
    if pending is None:
        return None
    operation = pending["operation"]
    active = _active_manifest(_read_json(ACTIVE))
    stage = skills / str(pending["stage"]) if pending.get("stage") else None
    quarantine = skills / str(pending["quarantine"]) if pending.get("quarantine") else None
    old_files = pending.get("old_files")
    new_files = pending.get("new_files")

    if operation == "install":
        committed = bool(active) and active["version"] == pending["new_version"] and active["files"] == new_files
        if committed:
            if not _matches(TARGET, new_files):
                raise StandaloneError("committed standalone install target is modified")
        else:
            if active is not None:
                raise StandaloneError("standalone install recovery found unexpected ownership state")
            _remove_exact(TARGET, new_files, skills)
        if stage is not None:
            _remove_scratch(stage, skills, new_files)

    elif operation == "update":
        active_is_old = bool(active) and active["version"] == pending["old_version"] and active["files"] == old_files
        active_is_new = bool(active) and active["version"] == pending["new_version"] and active["files"] == new_files
        if not active_is_old and not active_is_new:
            raise StandaloneError("standalone update recovery found unexpected ownership state")
        if active_is_new:
            if not _matches(TARGET, new_files):
                raise StandaloneError("committed standalone update target is modified")
            if quarantine is not None:
                _remove_scratch(quarantine, skills, old_files)
            if stage is not None:
                _remove_scratch(stage, skills, new_files)
        else:
            if TARGET.exists() or _is_linklike(TARGET):
                if _matches(TARGET, old_files):
                    if quarantine is not None and (quarantine.exists() or _is_linklike(quarantine)):
                        raise StandaloneError("standalone update rollback found duplicate old trees")
                elif _matches(TARGET, new_files) and quarantine is not None and _matches(quarantine, old_files):
                    if stage is None or stage.exists() or _is_linklike(stage):
                        raise StandaloneError("standalone update rollback lacks a safe recorded stage")
                    _replace(TARGET, stage)
                    _replace(quarantine, TARGET)
                    _fsync_dir(skills)
                    _remove_scratch(stage, skills, new_files)
                else:
                    raise StandaloneError("standalone update rollback preserves conflicting trees")
            elif quarantine is not None and _matches(quarantine, old_files):
                _replace(quarantine, TARGET)
                _fsync_dir(skills)
            else:
                raise StandaloneError("standalone update rollback cannot restore the old tree")
            if stage is not None:
                _remove_scratch(stage, skills, new_files)

    else:
        active_is_old = bool(active) and active["version"] == pending["old_version"] and active["files"] == old_files
        if active is None:
            if TARGET.exists() or _is_linklike(TARGET):
                raise StandaloneError("committed standalone uninstall found a target")
            if quarantine is not None:
                _remove_scratch(quarantine, skills, old_files)
        elif active_is_old:
            if TARGET.exists() or _is_linklike(TARGET):
                if not _matches(TARGET, old_files) or (quarantine is not None and (quarantine.exists() or _is_linklike(quarantine))):
                    raise StandaloneError("standalone uninstall rollback found conflicting trees")
            elif quarantine is not None and _matches(quarantine, old_files):
                _replace(quarantine, TARGET)
                _fsync_dir(skills)
            else:
                raise StandaloneError("standalone uninstall rollback cannot restore the owned tree")
        else:
            raise StandaloneError("standalone uninstall recovery found unexpected ownership state")
    _unlink_state(PENDING)
    return operation


def install() -> dict[str, Any]:
    skills = _validate_roots()
    with _lock():
        recovered = _recover(skills)
        active = _active_manifest(_read_json(ACTIVE))
        source_files = _source_inventory()
        installed_files = _installed_inventory(source_files)
        source_version = _version()
        active_controller_ready = False
        if active:
            if not _matches(TARGET, active["files"]):
                raise StandaloneError("managed standalone skill was modified")
            try:
                _validate_controller(CONTROLLERS / active["controller_id"])
                active_controller_ready = True
            except StandaloneError:
                active_controller_ready = False
        elif TARGET.exists() or _is_linklike(TARGET):
            raise StandaloneError(f"refusing to overwrite an unowned standalone skill: {TARGET}")
        controller_id = _ensure_controller(source_version, source_files)
        if active:
            if active["version"] == source_version and active["files"] == installed_files and active["controller_id"] == controller_id:
                return {"status": "active", "changed": not active_controller_ready, "recovered": recovered, "mode": "ADVISORY", "controller": str(CONTROLLERS / controller_id / "scripts" / "standalonectl.py")}
            if active["files"] == installed_files:
                _atomic_json(ACTIVE, _owned_state(source_version, installed_files, controller_id))
                return {"status": "active", "changed": True, "recovered": recovered, "mode": "ADVISORY", "controller": str(CONTROLLERS / controller_id / "scripts" / "standalonectl.py")}
            operation = "update"
            old_files = active["files"]
            old_version = active["version"]
            quarantine_name = f".{TARGET.name}.quarantine-{uuid.uuid4()}"
        else:
            operation = "install"
            old_files = None
            old_version = None
            quarantine_name = None
        stage_name = f".{TARGET.name}.stage-{uuid.uuid4()}"
        pending = {
            "schema_version": SCHEMA_VERSION,
            "target_id": _target_id(),
            "operation": operation,
            "old_version": old_version,
            "new_version": source_version,
            "old_files": old_files,
            "new_files": installed_files,
            "stage": stage_name,
            "quarantine": quarantine_name,
        }
        _atomic_json(PENDING, pending)
        _failpoint(f"{operation}-prepared")
        stage = skills / stage_name
        shutil.copytree(SOURCE, stage, symlinks=False, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"))
        _write_standalone_marker(stage)
        if not _matches(stage, installed_files):
            raise StandaloneError("standalone staging verification failed")
        _fsync_tree(stage)
        _failpoint(f"{operation}-staged")
        if operation == "update":
            quarantine = skills / quarantine_name
            _replace(TARGET, quarantine)
            _fsync_dir(skills)
            _failpoint("update-old-renamed")
        _replace(stage, TARGET)
        _fsync_dir(skills)
        _failpoint(f"{operation}-target")
        _atomic_json(ACTIVE, _owned_state(source_version, installed_files, controller_id))
        _failpoint(f"{operation}-active")
        _recover(skills)
        return {"status": "active", "changed": True, "recovered": recovered, "mode": "ADVISORY", "controller": str(CONTROLLERS / controller_id / "scripts" / "standalonectl.py")}


def uninstall() -> dict[str, Any]:
    skills = _validate_roots()
    with _lock():
        recovered = _recover(skills)
        active = _active_manifest(_read_json(ACTIVE))
        if active is None:
            if TARGET.exists() or _is_linklike(TARGET):
                raise StandaloneError("refusing to remove an unowned standalone skill")
            return {"status": "inactive", "changed": False, "recovered": recovered}
        if not _matches(TARGET, active["files"]):
            raise StandaloneError("standalone uninstall refuses a modified target")
        pending = {
            "schema_version": SCHEMA_VERSION,
            "target_id": _target_id(),
            "operation": "uninstall",
            "old_version": active["version"],
            "new_version": None,
            "old_files": active["files"],
            "new_files": None,
            "stage": None,
            "quarantine": f".{TARGET.name}.quarantine-{uuid.uuid4()}",
        }
        _atomic_json(PENDING, pending)
        _failpoint("uninstall-prepared")
        quarantine = skills / pending["quarantine"]
        _replace(TARGET, quarantine)
        _fsync_dir(skills)
        _failpoint("uninstall-renamed")
        _unlink_state(ACTIVE)
        _failpoint("uninstall-inactive")
        _recover(skills)
        return {"status": "inactive", "changed": True, "recovered": recovered}


def status() -> dict[str, Any]:
    _inspect_roots()
    pending = _pending_manifest(_read_json(PENDING))
    recovery_required: list[str] = []
    if _controller_transaction_pending():
        recovery_required.append("controller")
    if pending is not None:
        recovery_required.append(str(pending["operation"]))
    if _read_json(PURGE_STATE) is not None or (DATA / "controllers.purging").exists():
        recovery_required.append("purge")
    active = _active_manifest(_read_json(ACTIVE))
    conflicts = bool(active) and not _matches(TARGET, active["files"])
    controller_ready = False
    if active:
        try:
            _validate_controller(CONTROLLERS / active["controller_id"])
            controller_ready = True
        except StandaloneError:
            controller_ready = False
    update = bool(active) and (
        active["version"] != _version()
        or active["files"] != _installed_inventory(_source_inventory())
        or not controller_ready
    )
    foreign = not active and (TARGET.exists() or _is_linklike(TARGET))
    return {
        "mode": "ADVISORY",
        "surface": "STANDALONE_NO_PLUGIN_HOOKS",
        "active": bool(active),
        "modified": conflicts,
        "update_required": update,
        "controller_ready": controller_ready,
        "foreign_target": foreign,
        "recovered": None,
        "recovery_required": recovery_required,
        "version": _version(),
        "controller": str(CONTROLLERS / active["controller_id"] / "scripts" / "standalonectl.py") if active else None,
    }


def purge() -> dict[str, Any]:
    skills = _validate_roots()
    with _lock():
        if _running_from_controller():
            raise StandaloneError("run purge from a trusted extracted release, not from the durable controller being removed")
        _recover(skills)
        active = _active_manifest(_read_json(ACTIVE))
        if active is not None or TARGET.exists() or _is_linklike(TARGET):
            raise StandaloneError("purge requires a clean standalone uninstall first")
        if PENDING.exists() or _is_linklike(PENDING):
            raise StandaloneError("purge refuses pending standalone state")
        purging = DATA / "controllers.purging"
        prior = _read_json(PURGE_STATE)
        if prior is not None:
            if prior.get("schema_version") != SCHEMA_VERSION or prior.get("target_id") != _target_id():
                raise StandaloneError("standalone purge transaction is corrupt")
            prior_inventory = _validate_files(prior.get("inventory"))
            if purging.exists() or _is_linklike(purging):
                _remove_scratch(purging, DATA, prior_inventory)
            elif CONTROLLERS.exists() and _tree_hashes(CONTROLLERS, require_skill=False) == prior_inventory:
                _replace(CONTROLLERS, purging)
                _fsync_dir(DATA)
                _remove_scratch(purging, DATA, prior_inventory)
            elif not CONTROLLERS.exists() and not _is_linklike(CONTROLLERS):
                # The owned tree was already removed and only the durable commit
                # journal survived the final state-file unlink.
                pass
            else:
                raise StandaloneError("standalone purge recovery cannot identify its owned tree")
            _unlink_state(PURGE_STATE)
        controllers = list(CONTROLLERS.iterdir()) if CONTROLLERS.exists() else []
        for controller in controllers:
            _validate_controller(controller)
        if CONTROLLERS.exists():
            inventory = _tree_hashes(CONTROLLERS, require_skill=False)
            _atomic_json(PURGE_STATE, {"schema_version": SCHEMA_VERSION, "target_id": _target_id(), "inventory": inventory})
            _replace(CONTROLLERS, purging)
            _fsync_dir(DATA)
            _failpoint("purge-renamed")
            _remove_scratch(purging, DATA, inventory)
            _failpoint("purge-cleaned")
            _unlink_state(PURGE_STATE)
    return {"status": "purged", "controllers_removed": len(controllers)}


def main() -> int:
    if sys.version_info < (3, 10):
        print(json.dumps({"status": "error", "error": "standalonectl requires Python 3.10 or newer"}))
        return 2
    parser = argparse.ArgumentParser(description="Manage the advisory standalone GPT-5.6 Router skill")
    parser.add_argument("command", choices=("install", "status", "uninstall", "purge"))
    args = parser.parse_args()
    try:
        result = {"install": install, "status": status, "uninstall": uninstall, "purge": purge}[args.command]()
    except (OSError, StandaloneError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
