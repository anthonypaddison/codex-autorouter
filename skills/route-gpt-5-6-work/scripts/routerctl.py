#!/usr/bin/env python3
"""Transactional activation for Codex Autorouter legacy custom-agent definitions.

Plugin hooks are owned by Codex. This helper only manages the namespaced
custom-agent TOMLs that Codex currently discovers outside plugin bundles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
SKILL_ROOT = SCRIPT.parents[1]
PLUGIN_ROOT = SCRIPT.parents[3]
AGENT_SOURCE = SKILL_ROOT / "assets" / "agents"
PLUGIN_MANIFEST = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
STANDALONE_MARKER = SKILL_ROOT / ".gpt56-standalone.json"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().absolute()
_plugin_data = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
DATA_ROOT = Path(
    os.environ.get("GPT56_ROUTER_DATA")
    or (_plugin_data if _plugin_data else CODEX_HOME / "plugin-data" / "gpt-5-6-router")
).expanduser().absolute()
ACTIVATION_ROOT = DATA_ROOT / "activation"
ACTIVE_PATH = ACTIVATION_ROOT / "active.json"
TRANSACTIONS = ACTIVATION_ROOT / "transactions"
ORIGINALS = ACTIVATION_ROOT / "originals"
LOCK_PATH = ACTIVATION_ROOT / "activation.lock"
PROFILE_ROOT = CODEX_HOME / "gpt-5-6-router"
PROFILE_PATH = PROFILE_ROOT / "routing-profile.json"
PROFILE_SCHEMA = 1
ROUTING_PROFILES = {
    "token-saver": "Token Saver",
    "balanced": "Balanced",
    "max-quality": "Max Quality",
}
SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
AGENT_NAMES = (
    "gpt56_luna_worker.toml",
    "gpt56_terra_worker.toml",
    "gpt56_terra_deep.toml",
    "gpt56_sol_owner.toml",
    "gpt56_sol_deep.toml",
    "gpt56_sol_xhigh.toml",
)
LEGACY_AGENT_NAMES = (
    "gpt56_luna_worker.toml",
    "gpt56_terra_worker.toml",
    "gpt56_terra_deep.toml",
    "gpt56_sol_owner.toml",
    "gpt56_sol_judge.toml",
)
SUPPORTED_AGENT_NAMES = frozenset((*AGENT_NAMES, *LEGACY_AGENT_NAMES))
UUIDV7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
HOOK_PROMPT_PATTERN = re.compile(r"<hook_prompt\b[^>]*>.*?</hook_prompt>", re.IGNORECASE | re.DOTALL)
PURE_HOOK_PROMPTS_PATTERN = re.compile(
    r"^\s*(?:<hook_prompt\b[^>]*>.*?</hook_prompt>\s*)+$",
    re.IGNORECASE | re.DOTALL,
)
_DROP = object()


class RouterCtlError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_linklike(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & reparse)


def _require_canonical_path(path: Path) -> None:
    if path.resolve(strict=False) != path:
        raise RouterCtlError(f"refusing a path with symlink, junction, or reparse ancestors: {path}")


def _ensure_private_dir(path: Path, *, tighten_existing: bool = False) -> None:
    if _is_linklike(path):
        raise RouterCtlError(f"refusing symlink, junction, or reparse directory: {path}")
    existed = path.exists()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise RouterCtlError(f"expected directory: {path}")
    if not existed or tighten_existing:
        try:
            os.chmod(path, 0o700)
        except OSError:
            if os.name != "nt":
                raise


def _validate_roots() -> Path:
    _require_canonical_path(CODEX_HOME)
    _require_canonical_path(DATA_ROOT)
    for root in (CODEX_HOME, DATA_ROOT, ACTIVATION_ROOT):
        if _is_linklike(root):
            raise RouterCtlError(f"refusing symlink, junction, or reparse root: {root}")
    if CODEX_HOME.exists() and not CODEX_HOME.is_dir():
        raise RouterCtlError(f"CODEX_HOME is not a directory: {CODEX_HOME}")
    if _is_linklike(AGENT_SOURCE) or not AGENT_SOURCE.is_dir():
        raise RouterCtlError(f"invalid bundled agent source: {AGENT_SOURCE}")
    for name in AGENT_NAMES:
        source = AGENT_SOURCE / name
        if _is_linklike(source) or not source.is_file():
            raise RouterCtlError(f"invalid bundled agent source: {source}")
    _ensure_private_dir(CODEX_HOME)
    agents = CODEX_HOME / "agents"
    if _is_linklike(agents):
        raise RouterCtlError(f"refusing symlink, junction, or reparse agents directory: {agents}")
    _ensure_private_dir(agents)
    _ensure_private_dir(DATA_ROOT, tighten_existing=True)
    _ensure_private_dir(ACTIVATION_ROOT, tighten_existing=True)
    _ensure_private_dir(TRANSACTIONS, tighten_existing=True)
    _ensure_private_dir(ORIGINALS, tighten_existing=True)
    if agents.resolve() != (CODEX_HOME.resolve() / "agents"):
        raise RouterCtlError("agents directory escaped CODEX_HOME")
    return agents


def _inspect_roots() -> Path:
    """Validate lifecycle roots without creating or changing anything."""
    _require_canonical_path(CODEX_HOME)
    _require_canonical_path(DATA_ROOT)
    for root in (CODEX_HOME, DATA_ROOT, ACTIVATION_ROOT):
        if _is_linklike(root):
            raise RouterCtlError(f"refusing symlink, junction, or reparse root: {root}")
        if root.exists() and not root.is_dir():
            raise RouterCtlError(f"expected directory: {root}")
    if _is_linklike(AGENT_SOURCE) or not AGENT_SOURCE.is_dir():
        raise RouterCtlError(f"invalid bundled agent source: {AGENT_SOURCE}")
    for name in AGENT_NAMES:
        source = AGENT_SOURCE / name
        if _is_linklike(source) or not source.is_file():
            raise RouterCtlError(f"invalid bundled agent source: {source}")
    agents = CODEX_HOME / "agents"
    if _is_linklike(agents):
        raise RouterCtlError(f"refusing symlink, junction, or reparse agents directory: {agents}")
    if agents.exists() and not agents.is_dir():
        raise RouterCtlError(f"expected directory: {agents}")
    return agents


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, content: bytes, mode: int = 0o600) -> None:
    _ensure_private_dir(path.parent)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, mode)
        except OSError:
            if os.name != "nt":
                raise
        _replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _message_text(value: Any) -> str:
    """Extract only text-like message content, never arbitrary JSON fields."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := _message_text(item)))
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("text"), str):
        return str(value["text"])
    if isinstance(value.get("input_text"), str):
        return str(value["input_text"])
    if isinstance(value.get("content"), (str, list, dict)):
        return _message_text(value["content"])
    return ""


def _sanitize_transcript_value(value: Any, stats: dict[str, int]) -> Any:
    if isinstance(value, list):
        sanitized = []
        for item in value:
            result = _sanitize_transcript_value(item, stats)
            if result is not _DROP:
                sanitized.append(result)
        return sanitized
    if not isinstance(value, dict):
        return value

    is_message = value.get("type") == "message" and value.get("role") == "user"
    message_id = value.get("id")
    message_text = _message_text(value.get("content")) if is_message else ""
    poisoned = (
        is_message
        and isinstance(message_id, str)
        and UUIDV7_PATTERN.fullmatch(message_id) is not None
        and HOOK_PROMPT_PATTERN.search(message_text) is not None
    )
    if poisoned and PURE_HOOK_PROMPTS_PATTERN.fullmatch(message_text) is not None:
        stats["messages_removed"] += 1
        return _DROP

    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if poisoned and key == "id":
            stats["ids_removed"] += 1
            continue
        result = _sanitize_transcript_value(item, stats)
        if result is _DROP:
            if value.get("type") == "response_item" and key == "payload":
                return _DROP
            continue
        sanitized[key] = result
    return sanitized


def _safe_transcript_path(path: Path) -> Path:
    candidate = path.expanduser().absolute()
    _require_canonical_path(candidate)
    if _is_linklike(candidate):
        raise RouterCtlError(f"refusing symlink, junction, or reparse session: {candidate}")
    if not candidate.is_file() or candidate.suffix.lower() != ".jsonl":
        raise RouterCtlError(f"expected a JSONL session file: {candidate}")
    info = candidate.stat()
    if info.st_nlink != 1:
        raise RouterCtlError(f"refusing hard-linked session file: {candidate}")
    return candidate


def _sanitize_session(path: Path) -> dict[str, Any]:
    target = _safe_transcript_path(path)
    initial_info = target.stat()
    original = target.read_bytes()
    output: list[bytes] = []
    stats = {"messages_removed": 0, "ids_removed": 0, "lines_removed": 0}
    changed = False
    for line_number, raw_line in enumerate(original.splitlines(keepends=True), start=1):
        body = raw_line.rstrip(b"\r\n")
        ending = raw_line[len(body):]
        if not body.strip():
            output.append(raw_line)
            continue
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RouterCtlError(f"invalid JSONL at {target}:{line_number}: {exc}") from exc
        before = (stats["messages_removed"], stats["ids_removed"])
        sanitized = _sanitize_transcript_value(value, stats)
        if sanitized is _DROP:
            stats["lines_removed"] += 1
            changed = True
            continue
        if before != (stats["messages_removed"], stats["ids_removed"]):
            changed = True
            output.append(json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + ending)
        else:
            output.append(raw_line)

    result: dict[str, Any] = {"path": str(target), "modified": changed, **stats}
    if not changed:
        return result
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = target.with_name(f"{target.name}.autorouter-backup.{timestamp}.{uuid.uuid4().hex[:8]}")
    mode = stat.S_IMODE(target.stat().st_mode)
    _atomic_bytes(backup, original, mode)
    current_info = target.stat()
    if (
        current_info.st_dev,
        current_info.st_ino,
        current_info.st_size,
        current_info.st_mtime_ns,
    ) != (
        initial_info.st_dev,
        initial_info.st_ino,
        initial_info.st_size,
        initial_info.st_mtime_ns,
    ):
        raise RouterCtlError(f"session changed during sanitization; original preserved and backup retained: {target}")
    _atomic_bytes(target, b"".join(output), mode)
    result["backup"] = str(backup)
    return result


def sanitize_sessions(*, session: Path | None = None, all_sessions: bool = False) -> dict[str, Any]:
    if (session is None) == (not all_sessions):
        raise RouterCtlError("choose exactly one of --session PATH or --all")
    if session is not None:
        paths = [session]
    else:
        paths = sorted({
            path
            for root in (CODEX_HOME / "sessions", CODEX_HOME / "archived_sessions")
            if root.is_dir() and not _is_linklike(root)
            for path in root.rglob("*.jsonl")
        })
    results = [_sanitize_session(path) for path in paths]
    return {
        "status": "sanitized",
        "files_scanned": len(results),
        "files_modified": sum(bool(item["modified"]) for item in results),
        "messages_removed": sum(int(item["messages_removed"]) for item in results),
        "ids_removed": sum(int(item["ids_removed"]) for item in results),
        "lines_removed": sum(int(item["lines_removed"]) for item in results),
        "backups": [str(item["backup"]) for item in results if "backup" in item],
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _replace(source: Path, target: Path) -> None:
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 5:
                raise
            time.sleep(0.05 * (2**attempt))


def _read_json(path: Path, *, required: bool = False) -> dict[str, Any] | None:
    if not path.exists() and not _is_linklike(path):
        if required:
            raise RouterCtlError(f"missing state file: {path}")
        return None
    try:
        if _is_linklike(path) or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise RouterCtlError(f"invalid state file: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if required:
            raise RouterCtlError(f"missing state file: {path}")
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouterCtlError(f"cannot read state file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RouterCtlError(f"state file must contain an object: {path}")
    return value


def _validate_profile_root(*, create: bool) -> None:
    _require_canonical_path(CODEX_HOME)
    _require_canonical_path(PROFILE_ROOT)
    for root in (CODEX_HOME, PROFILE_ROOT):
        if _is_linklike(root):
            raise RouterCtlError(f"refusing symlink, junction, or reparse profile root: {root}")
    if CODEX_HOME.exists() and not CODEX_HOME.is_dir():
        raise RouterCtlError(f"CODEX_HOME is not a directory: {CODEX_HOME}")
    if PROFILE_ROOT.exists() and not PROFILE_ROOT.is_dir():
        raise RouterCtlError(f"profile root is not a directory: {PROFILE_ROOT}")
    if create:
        _ensure_private_dir(CODEX_HOME)
        _ensure_private_dir(PROFILE_ROOT, tighten_existing=True)


def _profile_status() -> dict[str, Any]:
    try:
        _validate_profile_root(create=False)
        if not PROFILE_PATH.exists() and not _is_linklike(PROFILE_PATH):
            return {
                "profile": "balanced",
                "label": ROUTING_PROFILES["balanced"],
                "source": "default",
                "valid": True,
            }
        if _is_linklike(PROFILE_PATH) or not PROFILE_PATH.is_file():
            raise RouterCtlError(f"invalid profile file: {PROFILE_PATH}")
        info = PROFILE_PATH.stat()
        if info.st_size > 4096 or int(getattr(info, "st_nlink", 1)) != 1:
            raise RouterCtlError(f"invalid profile file: {PROFILE_PATH}")
        value = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "profile"}
            or value.get("schema_version") != PROFILE_SCHEMA
            or value.get("profile") not in ROUTING_PROFILES
        ):
            raise RouterCtlError(f"invalid routing profile payload: {PROFILE_PATH}")
        selected = str(value["profile"])
        return {
            "profile": selected,
            "label": ROUTING_PROFILES[selected],
            "source": "configured",
            "valid": True,
        }
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RouterCtlError) as exc:
        return {
            "profile": "balanced",
            "label": ROUTING_PROFILES["balanced"],
            "source": "invalid_default",
            "valid": False,
            "error": str(exc),
        }


def set_profile(profile: str) -> dict[str, Any]:
    if profile not in ROUTING_PROFILES:
        raise RouterCtlError("unknown routing profile")
    _validate_profile_root(create=True)
    if PROFILE_PATH.exists() or _is_linklike(PROFILE_PATH):
        if _is_linklike(PROFILE_PATH) or not PROFILE_PATH.is_file():
            raise RouterCtlError(f"refusing invalid profile file: {PROFILE_PATH}")
        if int(getattr(PROFILE_PATH.stat(), "st_nlink", 1)) != 1:
            raise RouterCtlError(f"refusing hard-linked profile file: {PROFILE_PATH}")
    _atomic_json(PROFILE_PATH, {"schema_version": PROFILE_SCHEMA, "profile": profile})
    return {
        "status": "configured",
        "profile": profile,
        "label": ROUTING_PROFILES[profile],
        "applies": "next_new_task",
        "fast_setting": "unchanged",
    }


def _plugin_version() -> str:
    manifest = _read_json(PLUGIN_MANIFEST) if _runtime_surface() == "PLUGIN_LAYOUT_UNATTESTED" else None
    if manifest is not None:
        return str(manifest.get("version") or "unknown")
    digest = hashlib.sha256()
    for path in (SKILL_ROOT / "SKILL.md", *(AGENT_SOURCE / name for name in AGENT_NAMES)):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return "standalone-" + digest.hexdigest()[:16]


def _runtime_surface() -> str:
    marker = _read_json(STANDALONE_MARKER)
    installed_standalone = SKILL_ROOT == CODEX_HOME / "skills" / "route-gpt-5-6-work"
    if installed_standalone:
        if marker == {"schema_version": 1, "surface": "standalone_advisory"}:
            return "STANDALONE_ADVISORY"
        return "STANDALONE_INVALID"
    if marker is not None:
        if marker == {"schema_version": 1, "surface": "standalone_advisory"}:
            return "STANDALONE_ADVISORY"
        return "STANDALONE_INVALID"
    manifest = _read_json(PLUGIN_MANIFEST)
    hooks = PLUGIN_ROOT / "hooks" / "hooks.json"
    if (
        manifest is not None
        and manifest.get("name") == "gpt-5-6-router"
        and hooks.is_file()
        and not _is_linklike(hooks)
        and SKILL_ROOT == PLUGIN_ROOT / "skills" / "route-gpt-5-6-work"
    ):
        return "PLUGIN_LAYOUT_UNATTESTED"
    return "UNATTESTED_FILESYSTEM"


def _validate_snapshot(value: Any, *, expected_backup: str | None = None) -> None:
    if not isinstance(value, dict) or value.get("kind") not in {"absent", "file"}:
        raise RouterCtlError("state contains an invalid snapshot")
    if value["kind"] == "absent":
        return
    backup = value.get("backup")
    checksum = value.get("sha256")
    mode = value.get("mode")
    if (
        not isinstance(backup, str)
        or not backup
        or backup in {".", ".."}
        or Path(backup).name != backup
        or (expected_backup is not None and backup != expected_backup)
        or not isinstance(checksum, str)
        or SHA256_PATTERN.fullmatch(checksum) is None
        or isinstance(mode, bool)
        or not isinstance(mode, int)
        or not 0 <= mode <= 0o7777
    ):
        raise RouterCtlError("state contains invalid snapshot metadata")


def _validate_journal(transaction: Path, journal: dict[str, Any]) -> None:
    targets = journal.get("targets")
    snapshots = journal.get("snapshots")
    if (
        journal.get("schema_version") != SCHEMA_VERSION
        or journal.get("id") != transaction.name
        or journal.get("operation") not in {"activate", "deactivate", "repair"}
        or journal.get("state") not in {"PREPARED", "COMMITTING", "COMMITTED", "ROLLED_BACK"}
        or not isinstance(targets, list)
        or any(not isinstance(name, str) or name not in SUPPORTED_AGENT_NAMES for name in targets)
        or len(targets) != len(set(targets))
        or not isinstance(snapshots, dict)
        or set(snapshots) != set(targets)
    ):
        raise RouterCtlError(f"transaction has a corrupt journal: {transaction}")
    for name in targets:
        _validate_snapshot(snapshots[name], expected_backup=name)
    _validate_snapshot(journal.get("active_snapshot"), expected_backup="active.json")


def _snapshot(path: Path, destination: Path) -> dict[str, Any]:
    if _is_linklike(path):
        raise RouterCtlError(f"refusing linked target: {path}")
    if not path.exists():
        return {"kind": "absent"}
    if not path.is_file():
        raise RouterCtlError(f"target is not a regular file: {path}")
    content = path.read_bytes()
    _atomic_bytes(destination, content, stat.S_IMODE(path.stat().st_mode) or 0o600)
    return {
        "kind": "file",
        "backup": destination.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "mode": stat.S_IMODE(path.stat().st_mode),
    }


def _restore_snapshot(target: Path, metadata: dict[str, Any], directory: Path) -> None:
    if _is_linklike(target):
        raise RouterCtlError(f"refusing linked rollback target: {target}")
    if metadata.get("kind") == "absent":
        if target.exists():
            if not target.is_file():
                raise RouterCtlError(f"rollback target is not a file: {target}")
            target.unlink()
            _fsync_dir(target.parent)
        return
    backup = directory / str(metadata.get("backup") or "")
    if not backup.is_file() or _is_linklike(backup):
        raise RouterCtlError(f"missing rollback backup: {backup}")
    if _sha(backup) != metadata.get("sha256"):
        raise RouterCtlError(f"rollback checksum mismatch: {backup}")
    _atomic_bytes(target, backup.read_bytes(), int(metadata.get("mode") or 0o600))


@contextmanager
def _lock():
    _ensure_private_dir(ACTIVATION_ROOT)
    if _is_linklike(LOCK_PATH):
        raise RouterCtlError(f"refusing linked lock: {LOCK_PATH}")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(LOCK_PATH, flags, 0o600)
    with os.fdopen(descriptor, "a+b", buffering=0) as stream:
        if fcntl is not None:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:
            # Windows can lock past EOF. A write here could race another holder.
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


def _failpoint(name: str) -> None:
    if os.environ.get("GPT56_ROUTER_CRASH_AT") == name:
        os._exit(97)
    if os.environ.get("GPT56_ROUTER_FAIL_AT") == name:
        raise RouterCtlError(f"injected failure at {name}")


def _new_transaction(operation: str, agents: Path, targets: list[str]) -> tuple[Path, dict[str, Any]]:
    transaction = TRANSACTIONS / str(uuid.uuid4())
    _ensure_private_dir(transaction)
    before = transaction / "before"
    _ensure_private_dir(before)
    snapshots: dict[str, Any] = {}
    for name in targets:
        snapshots[name] = _snapshot(agents / name, before / name)
    active_snapshot = _snapshot(ACTIVE_PATH, before / "active.json")
    journal = {
        "schema_version": SCHEMA_VERSION,
        "id": transaction.name,
        "operation": operation,
        "state": "PREPARED",
        "targets": targets,
        "snapshots": snapshots,
        "active_snapshot": active_snapshot,
    }
    _atomic_json(transaction / "journal.json", journal)
    _failpoint("prepared")
    return transaction, journal


def _set_journal(transaction: Path, journal: dict[str, Any], state_value: str) -> None:
    journal["state"] = state_value
    _atomic_json(transaction / "journal.json", journal)


def _rollback(transaction: Path, journal: dict[str, Any], agents: Path) -> None:
    before = transaction / "before"
    for name in reversed(list(journal.get("targets", []))):
        _restore_snapshot(agents / name, journal["snapshots"][name], before)
    _restore_snapshot(ACTIVE_PATH, journal["active_snapshot"], before)
    journal["state"] = "ROLLED_BACK"
    _atomic_json(transaction / "journal.json", journal)


def _discard_transaction(transaction: Path) -> None:
    if _is_linklike(transaction):
        raise RouterCtlError(f"refusing linked transaction cleanup: {transaction}")
    shutil.rmtree(transaction)
    _fsync_dir(TRANSACTIONS)


def _commit_transaction(transaction: Path, journal: dict[str, Any]) -> None:
    _set_journal(transaction, journal, "COMMITTED")
    try:
        _discard_transaction(transaction)
    except OSError:
        # A committed journal is safe to prune during the next lifecycle call.
        pass


def _recover(agents: Path) -> list[str]:
    recovered: list[str] = []
    for transaction in sorted(TRANSACTIONS.iterdir()):
        if not transaction.is_dir() or _is_linklike(transaction):
            continue
        journal_path = transaction / "journal.json"
        if not journal_path.exists() and not _is_linklike(journal_path):
            # Targets are never mutated before the durable journal exists, so
            # a pre-journal crash leaves disposable staging only.
            _discard_transaction(transaction)
            recovered.append(transaction.name)
            continue
        journal = _read_json(journal_path, required=True)
        _validate_journal(transaction, journal)
        state_value = journal.get("state")
        if state_value in {"PREPARED", "COMMITTING"}:
            before = transaction / "before"
            _require_canonical_path(before)
            if _is_linklike(before) or not before.is_dir():
                raise RouterCtlError(f"transaction has an invalid backup directory: {transaction}")
            _rollback(transaction, journal, agents)
            recovered.append(transaction.name)
            _discard_transaction(transaction)
        elif state_value in {"COMMITTED", "ROLLED_BACK"}:
            _discard_transaction(transaction)
    return recovered


def _transactions_requiring_recovery() -> list[str]:
    """Inspect transaction journals without pruning or rolling them back."""
    if not TRANSACTIONS.exists() and not _is_linklike(TRANSACTIONS):
        return []
    if _is_linklike(TRANSACTIONS) or not TRANSACTIONS.is_dir():
        raise RouterCtlError(f"invalid transactions directory: {TRANSACTIONS}")
    pending: list[str] = []
    for transaction in sorted(TRANSACTIONS.iterdir()):
        if _is_linklike(transaction):
            raise RouterCtlError(f"refusing linked transaction: {transaction}")
        if not transaction.is_dir():
            continue
        journal_path = transaction / "journal.json"
        if not journal_path.exists() and not _is_linklike(journal_path):
            pending.append(transaction.name)
            continue
        journal = _read_json(journal_path, required=True)
        _validate_journal(transaction, journal)
        if journal.get("state") in {"PREPARED", "COMMITTING", "COMMITTED", "ROLLED_BACK"}:
            if journal.get("state") in {"PREPARED", "COMMITTING"}:
                before = transaction / "before"
                _require_canonical_path(before)
                if _is_linklike(before) or not before.is_dir():
                    raise RouterCtlError(f"transaction has an invalid backup directory: {transaction}")
            pending.append(transaction.name)
    return pending


def _load_active() -> dict[str, Any] | None:
    value = _read_json(ACTIVE_PATH)
    if value is None:
        return None
    files = value.get("files")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or not isinstance(value.get("plugin_version"), str)
        or not value["plugin_version"]
        or not isinstance(value.get("transaction_id"), str)
        or not value["transaction_id"]
        or not isinstance(files, dict)
        or frozenset(files) not in {frozenset(AGENT_NAMES), frozenset(LEGACY_AGENT_NAMES)}
    ):
        raise RouterCtlError("active ownership manifest has an unsupported or corrupt schema")
    for name, record in files.items():
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("installed_sha256"), str)
            or SHA256_PATTERN.fullmatch(record["installed_sha256"]) is None
        ):
            raise RouterCtlError("active ownership manifest contains an invalid file record")
        _validate_snapshot(record.get("original"), expected_backup=name)
    return value


def _activation_drift(active: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if active is None:
        return False, []
    if set(active["files"]) != set(AGENT_NAMES):
        changed = sorted(set(active["files"]).symmetric_difference(AGENT_NAMES))
        return True, changed
    bundled_drift = [
        name for name in AGENT_NAMES
        if _sha(AGENT_SOURCE / name) != active["files"][name]["installed_sha256"]
    ]
    return active["plugin_version"] != _plugin_version() or bool(bundled_drift), bundled_drift


def _validate_owned_files(agents: Path, active: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    for name, record in active["files"].items():
        target = agents / name
        if _is_linklike(target) or not target.is_file() or _sha(target) != record.get("installed_sha256"):
            conflicts.append(name)
    return conflicts


def _validate_original_backups(active: dict[str, Any] | None) -> list[str]:
    if active is None:
        return []
    conflicts: list[str] = []
    for name, record in active["files"].items():
        original = record["original"]
        if original["kind"] == "absent":
            continue
        backup = ORIGINALS / name
        if _is_linklike(backup) or not backup.is_file() or _sha(backup) != original["sha256"]:
            conflicts.append(name)
    return conflicts


def activate(*, replace_conflicts: bool = False, legacy_agents: bool = False) -> dict[str, Any]:
    if not legacy_agents:
        return {
            "status": "supported-routing",
            "changed": False,
            "legacy_agents_optional": True,
            "message": "supported direct-child routing requires no legacy custom-agent installation",
        }
    agents = _validate_roots()
    with _lock():
        recovered = _recover(agents)
        active = _load_active()
        if active:
            backup_conflicts = _validate_original_backups(active)
            if backup_conflicts:
                raise RouterCtlError("missing or corrupt original backups: " + ", ".join(backup_conflicts))
            conflicts = _validate_owned_files(agents, active)
            if conflicts:
                raise RouterCtlError("locally modified managed agents: " + ", ".join(conflicts))

        sources = {name: AGENT_SOURCE / name for name in AGENT_NAMES}
        active_names = tuple(active["files"]) if active else ()
        added_names = [name for name in AGENT_NAMES if name not in active_names]
        removed_names = [name for name in active_names if name not in AGENT_NAMES]
        for name in AGENT_NAMES:
            if _is_linklike(agents / name):
                raise RouterCtlError(f"refusing linked agent target: {agents / name}")
        foreign = [
            name for name in (AGENT_NAMES if not active else added_names)
            if (agents / name).exists() and _sha(agents / name) != _sha(sources[name])
        ]
        if foreign and not replace_conflicts:
            raise RouterCtlError(
                "conflicting agent files; rerun with --replace-conflicts only after review: " + ", ".join(foreign)
            )

        targets = list(dict.fromkeys((*active_names, *AGENT_NAMES)))
        transaction, journal = _new_transaction("activate", agents, targets)
        try:
            originals: dict[str, Any] = dict(active.get("files", {})) if active else {}
            for name in (AGENT_NAMES if not active else added_names):
                original = _snapshot(agents / name, ORIGINALS / name)
                originals[name] = {"original": original}
            _set_journal(transaction, journal, "COMMITTING")
            _failpoint("committing")
            for name in removed_names:
                _restore_snapshot(agents / name, active["files"][name]["original"], ORIGINALS)
            installed: dict[str, Any] = {}
            for index, name in enumerate(AGENT_NAMES, 1):
                source = sources[name]
                _atomic_bytes(agents / name, source.read_bytes(), 0o600)
                installed[name] = {
                    "installed_sha256": _sha(source),
                    "original": originals[name]["original"],
                }
                _failpoint(f"agent-{index}")
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "plugin_version": _plugin_version(),
                "transaction_id": transaction.name,
                "files": installed,
            }
            _atomic_json(ACTIVE_PATH, manifest)
            _failpoint("active-manifest")
            _commit_transaction(transaction, journal)
            try:
                for name in removed_names:
                    old_backup = ORIGINALS / name
                    if old_backup.exists() and not _is_linklike(old_backup):
                        old_backup.unlink()
                if removed_names:
                    _fsync_dir(ORIGINALS)
            except OSError:
                # Migration is already committed; stale private backups are safe.
                pass
            return {"status": "active", "recovered": recovered, "files": list(AGENT_NAMES)}
        except Exception:
            _rollback(transaction, journal, agents)
            _discard_transaction(transaction)
            raise


def deactivate(*, keep_modified: bool = False) -> dict[str, Any]:
    agents = _validate_roots()
    with _lock():
        recovered = _recover(agents)
        active = _load_active()
        if not active:
            return {"status": "inactive", "recovered": recovered, "changed": False}
        backup_conflicts = _validate_original_backups(active)
        if backup_conflicts:
            raise RouterCtlError("missing or corrupt original backups: " + ", ".join(backup_conflicts))
        conflicts = _validate_owned_files(agents, active)
        if conflicts and not keep_modified:
            raise RouterCtlError("locally modified managed agents: " + ", ".join(conflicts))
        managed = list(active["files"])
        transaction, journal = _new_transaction("deactivate", agents, managed)
        try:
            _set_journal(transaction, journal, "COMMITTING")
            for index, name in enumerate(managed, 1):
                if name in conflicts:
                    continue
                record = active["files"][name]
                _restore_snapshot(agents / name, record["original"], ORIGINALS)
                _failpoint(f"deactivate-{index}")
            if ACTIVE_PATH.exists():
                ACTIVE_PATH.unlink()
                _fsync_dir(ACTIVE_PATH.parent)
            _failpoint("inactive-manifest")
            _commit_transaction(transaction, journal)
            try:
                for name in managed:
                    original = ORIGINALS / name
                    if original.exists() and not _is_linklike(original):
                        original.unlink()
                _fsync_dir(ORIGINALS)
            except OSError:
                # Deactivation is already committed; stale private backups are
                # preferable to claiming a rollback that can no longer occur.
                pass
            return {
                "status": "inactive",
                "recovered": recovered,
                "changed": True,
                "preserved_modified": conflicts,
            }
        except Exception:
            _rollback(transaction, journal, agents)
            _discard_transaction(transaction)
            raise


def repair() -> dict[str, Any]:
    agents = _validate_roots()
    with _lock():
        recovered = _recover(agents)
        active = _load_active()
        if not active:
            return {"status": "inactive", "recovered": recovered, "repaired": []}
        if set(active["files"]) != set(AGENT_NAMES):
            raise RouterCtlError("activation uses a legacy agent set; run activate to migrate it")
        backup_conflicts = _validate_original_backups(active)
        if backup_conflicts:
            raise RouterCtlError("missing or corrupt original backups: " + ", ".join(backup_conflicts))
        modified: list[str] = []
        missing: list[str] = []
        for name, record in active["files"].items():
            target = agents / name
            if not target.exists():
                missing.append(name)
            elif _is_linklike(target) or not target.is_file() or _sha(target) != record["installed_sha256"]:
                modified.append(name)
        if modified:
            raise RouterCtlError("repair refuses locally modified managed agents: " + ", ".join(modified))
        if not missing:
            return {"status": "active", "recovered": recovered, "repaired": []}
        transaction, journal = _new_transaction("repair", agents, missing)
        try:
            _set_journal(transaction, journal, "COMMITTING")
            for name in missing:
                source = AGENT_SOURCE / name
                if _sha(source) != active["files"][name]["installed_sha256"]:
                    raise RouterCtlError(f"bundled version differs; use activate for upgrade: {name}")
                _atomic_bytes(agents / name, source.read_bytes(), 0o600)
            _commit_transaction(transaction, journal)
            return {"status": "active", "recovered": recovered, "repaired": missing}
        except Exception:
            _rollback(transaction, journal, agents)
            _discard_transaction(transaction)
            raise


def _toml_value(path: Path, section: str, key: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return None
    active = ""
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            active = line[1:-1].strip()
        elif active == section and "=" in line:
            candidate, value = line.split("=", 1)
            if candidate.strip() == key:
                return value.strip().strip("'\"").lower()
    return None


def status() -> dict[str, Any]:
    agents = _inspect_roots()
    active = _load_active()
    conflicts = _validate_owned_files(agents, active) if active else []
    original_backup_conflicts = _validate_original_backups(active)
    update_required, bundled_drift = _activation_drift(active)
    recovery_required = _transactions_requiring_recovery()
    config = CODEX_HOME / "config.toml"
    requirements = CODEX_HOME / "requirements.toml"
    managed_blocked = _toml_value(requirements, "", "allow_managed_hooks_only") == "true"
    hooks_disabled = _toml_value(config, "features", "hooks") == "false"
    agents_disabled = _toml_value(config, "agents", "enabled") == "false"
    depth_zero = _toml_value(config, "agents", "max_depth") == "0"
    surface = _runtime_surface()
    local_agent_ready = not any((agents_disabled, depth_zero))
    mode = "MANAGED_BLOCKED" if managed_blocked else "ADVISORY"
    profile = _profile_status()
    return {
        "mode": mode,
        "runtime_surface": surface,
        "diagnostic_scope": "LOCAL_FILES_ONLY",
        "local_agent_ready": local_agent_ready,
        "legacy_agents_optional": True,
        "legacy_agents_active": bool(active),
        "static_readiness_authority": "scripts/check_hooks.py",
        "agents_active": bool(active),
        "agent_conflicts": conflicts,
        "original_backup_conflicts": original_backup_conflicts,
        "activation_update_required": update_required,
        "bundled_agent_drift": bundled_drift,
        "hooks_enabled_by_local_config": not hooks_disabled,
        "multi_agent_enabled_by_local_config": not agents_disabled,
        "local_agent_depth_allows_children": not depth_zero,
        "managed_hooks_only_in_local_requirements": managed_blocked,
        "hook_trust": "UNVERIFIED",
        "fast_state": "REPORTED_CONFIG_ONLY",
        "recovered_transactions": [],
        "recovery_required": recovery_required,
        "plugin_version": _plugin_version(),
        "routing_profile": profile["profile"],
        "routing_profile_label": profile["label"],
        "routing_profile_source": profile["source"],
        "routing_profile_valid": profile["valid"],
    }


def main() -> int:
    if sys.version_info < (3, 10):
        print("routerctl requires Python 3.10 or newer", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Manage Codex Autorouter legacy custom-agent activation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("--replace-conflicts", action="store_true")
    activate_parser.add_argument(
        "--legacy-agents",
        action="store_true",
        help="explicitly install the obsolete custom-agent compatibility set",
    )
    deactivate_parser = subparsers.add_parser("deactivate")
    deactivate_parser.add_argument("--keep-modified", action="store_true")
    subparsers.add_parser("repair")
    subparsers.add_parser("status")
    profile_parser = subparsers.add_parser("profile")
    profile_parser.add_argument("value", nargs="?", choices=tuple(ROUTING_PROFILES))
    sanitize_parser = subparsers.add_parser(
        "sanitize",
        help="repair persisted sessions poisoned by replayed terminal-hook messages",
    )
    sanitize_group = sanitize_parser.add_mutually_exclusive_group(required=True)
    sanitize_group.add_argument("--session", type=Path, metavar="PATH")
    sanitize_group.add_argument("--all", action="store_true", dest="all_sessions")
    args = parser.parse_args()
    try:
        if args.command == "activate":
            result = activate(
                replace_conflicts=args.replace_conflicts,
                legacy_agents=args.legacy_agents,
            )
        elif args.command == "deactivate":
            result = deactivate(keep_modified=args.keep_modified)
        elif args.command == "repair":
            result = repair()
        elif args.command == "status":
            result = status()
        elif args.command == "sanitize":
            result = sanitize_sessions(session=args.session, all_sessions=args.all_sessions)
        elif args.value:
            result = set_profile(args.value)
        else:
            result = _profile_status()
    except (OSError, RouterCtlError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
