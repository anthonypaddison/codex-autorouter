"""Small, model-family-independent configuration owned by Autorouter."""

from __future__ import annotations

import json
import hashlib
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path
from typing import Any


MAX_CONFIG_BYTES = 64 * 1024
DEFAULT_CLASSIFIER_TIMEOUT_SECONDS = 10
MAX_CLASSIFIER_TIMEOUT_SECONDS = 30
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
ENV_REFERENCE = re.compile(r"[A-Z_][A-Z0-9_]{0,127}\Z")


class ConfigError(ValueError):
    """A configuration cannot safely authorize routing."""


def config_path() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "autorouter" / "config.json"


def role_specs(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Stable model/effort identities; hashes cover settings, never prompt content."""
    document = validate_config(config)
    revision = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    specs = {}
    for entry in document["executors"]:
        for effort in entry["efforts"]:
            pair = entry["model"] + "|" + effort
            role = "configured_" + hashlib.sha256(pair.encode()).hexdigest()[:24]
            specs[role] = {"model": entry["model"], "effort": effort,
                           "profile": "configured_" + revision, "delegate": True}
    return specs


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def validate_config(document: Any, catalogue: dict[str, list[str]] | None = None) -> dict[str, Any]:
    # Catalogue metadata is advisory; Codex validates native spawn compatibility.
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int:
        raise ConfigError("invalid_configuration_schema")
    version = document["schema_version"]
    fields = {"schema_version", "classifier", "executors", "fallback", "timeout_seconds"}
    if version == 2:
        fields.add("enabled")
    if version not in (1, 2) or set(document) != fields:
        raise ConfigError("invalid_configuration_schema")
    if version == 2 and type(document["enabled"]) is not bool:
        raise ConfigError("invalid_enabled_setting")
    timeout = document["timeout_seconds"]
    if type(timeout) not in (int, float) or not 1 <= timeout <= MAX_CLASSIFIER_TIMEOUT_SECONDS:
        raise ConfigError("invalid_classifier_timeout")
    executors = document["executors"]
    if not isinstance(executors, list) or not 1 <= len(executors) <= 64:
        raise ConfigError("invalid_executors")
    models = {}
    for entry in executors:
        if not isinstance(entry, dict) or set(entry) != {"model", "efforts"}:
            raise ConfigError("invalid_executor")
        model, efforts = entry["model"], entry["efforts"]
        if not _identifier(model) or model in models:
            raise ConfigError("invalid_or_duplicate_model")
        if not isinstance(efforts, list) or not 1 <= len(efforts) <= 16 or not all(_identifier(e) for e in efforts):
            raise ConfigError("invalid_efforts")
        if len(set(efforts)) != len(efforts):
            raise ConfigError("duplicate_effort")
        models[model] = efforts
    for key in ("classifier", "fallback"):
        pair = document[key]
        expected = {"model", "effort"}
        if key == "classifier" and version == 2:
            expected.update({"provider", "credential_env"})
        if (not isinstance(pair, dict) or set(pair) != expected
                or not all(_identifier(pair[k]) for k in ("model", "effort"))):
            raise ConfigError("invalid_model_effort_pair")
    if version == 2:
        classifier = document["classifier"]
        if classifier["provider"] != "openai":
            raise ConfigError("unsupported_classifier_provider")
        reference = classifier["credential_env"]
        if not isinstance(reference, str) or ENV_REFERENCE.fullmatch(reference) is None:
            raise ConfigError("invalid_credential_reference")
    fallback = document["fallback"]
    if fallback["effort"] not in models.get(fallback["model"], []):
        raise ConfigError("fallback_not_permitted")
    if len(json.dumps(document).encode()) > MAX_CONFIG_BYTES:
        raise ConfigError("configuration_too_large")
    return json.loads(json.dumps(document))


def _read(path: Path) -> bytes | None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigError("configuration_unreadable") from exc
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.is_symlink():
            raise ConfigError("unsafe_configuration_file")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise ConfigError("configuration_owner_mismatch")
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ConfigError("configuration_too_large")
    return raw


def load_config(path: Path | None = None) -> dict[str, Any] | None:
    raw = _read(path or config_path())
    if raw is None:
        return None
    try:
        return validate_config(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ConfigError("malformed_configuration") from exc


def save_config(path: Path, config: dict[str, Any]) -> Path | None:
    raw = (json.dumps(validate_config(config), indent=2) + "\n").encode()
    if path.parent.is_symlink():
        raise ConfigError("unsafe_configuration_directory")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError as exc:
        raise ConfigError("configuration_locked") from exc
    os.close(fd)
    temporary = None
    try:
        before = _read(path)
        backup = None
        if before is not None:
            backup = path.with_name(path.name + ".backup-" + secrets.token_hex(8))
            with os.fdopen(os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as stream:
                stream.write(before)
                stream.flush()
                os.fsync(stream.fileno())
        fd, name = tempfile.mkstemp(prefix=".autorouter-", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if _read(path) != before:
            raise ConfigError("configuration_changed_concurrently")
        os.replace(temporary, path)
        return backup
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink()
