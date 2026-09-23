"""Bounded, read-only discovery and drift reporting for Codex's local model cache."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

MAX_CATALOGUE_BYTES = 4 * 1024 * 1024
MAX_MODELS = 4096
MAX_BASELINE_BYTES = 256 * 1024
MAX_AGE = timedelta(days=7)
MAX_FUTURE_SKEW = timedelta(minutes=5)


class CatalogueState(str, Enum):
    COMPLETE = "complete"
    UNAVAILABLE = "discovery_unavailable"


class Availability(str, Enum):
    AVAILABLE = "available"
    ABSENT = "absent"
    HIDDEN = "hidden_nonselectable"
    UNAVAILABLE = "discovery_unavailable"


@dataclass(frozen=True)
class ModelObservation:
    canonical_id: str
    visibility: str
    efforts: tuple[str, ...]
    service_tiers: tuple[str, ...]
    upgrade_model: str | None
    retirement_at: str | None


@dataclass(frozen=True)
class CatalogueResult:
    state: CatalogueState
    models: tuple[ModelObservation, ...] = ()
    fetched_at: str | None = None
    client_version: str | None = None
    reason: str | None = None

    def availability(self, model_id: str) -> Availability:
        if self.state != CatalogueState.COMPLETE:
            return Availability.UNAVAILABLE
        match = next((model for model in self.models if model.canonical_id == model_id), None)
        if match is None:
            return Availability.ABSENT
        return Availability.AVAILABLE if match.visibility == "list" else Availability.HIDDEN


@dataclass(frozen=True)
class DriftReport:
    status: str
    added_ids: tuple[str, ...] = ()
    removed_ids: tuple[str, ...] = ()
    visibility_changes: tuple[dict[str, str], ...] = ()
    effort_changes: tuple[dict[str, Any], ...] = ()
    service_tier_changes: tuple[dict[str, Any], ...] = ()
    migration_changes: tuple[dict[str, Any], ...] = ()
    policy_states: tuple[dict[str, str], ...] = ()
    reason: str | None = None


def codex_cache_path() -> Path:
    home = os.environ.get("CODEX_HOME")
    return (Path(home).expanduser() if home else Path.home() / ".codex") / "models_cache.json"


def discover_catalogue(path: Path | None = None, *, now: datetime | None = None) -> CatalogueResult:
    """Read only one bounded regular cache file without following a final symlink."""
    target = path or codex_cache_path()
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_CATALOGUE_BYTES:
                return CatalogueResult(CatalogueState.UNAVAILABLE, reason="unsafe_or_oversized_file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_CATALOGUE_BYTES + 1)
            if len(raw) > MAX_CATALOGUE_BYTES:
                return CatalogueResult(CatalogueState.UNAVAILABLE, reason="oversized_file")
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason="unreadable_file")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason="malformed_json")
    return parse_catalogue(document, now=now, encoded_size=len(raw))


def parse_catalogue(document: Any, *, now: datetime | None = None, encoded_size: int | None = None) -> CatalogueResult:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if encoded_size is not None and encoded_size > MAX_CATALOGUE_BYTES:
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason="oversized_file")
    if not isinstance(document, dict) or not isinstance(document.get("models"), list):
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason="incomplete_schema")
    models = document["models"]
    if not models or len(models) > MAX_MODELS:
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason="invalid_model_count")
    fetched = _timestamp(document.get("fetched_at"))
    if fetched is None or fetched > current + MAX_FUTURE_SKEW or current - fetched > MAX_AGE:
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason="stale_or_invalid_timestamp")
    client = document.get("client_version")
    if not isinstance(client, str) or not client or len(client) > 64:
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason="invalid_client_version")
    observations = []
    seen = set()
    try:
        for item in models:
            if not isinstance(item, dict):
                raise ValueError("invalid_model_record")
            model_id = item.get("slug")
            visibility = item.get("visibility")
            if not isinstance(model_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,127}", model_id):
                raise ValueError("invalid_model_id")
            if model_id in seen:
                raise ValueError("duplicate_model_id")
            seen.add(model_id)
            if visibility not in {"list", "hide"}:
                raise ValueError("invalid_visibility")
            efforts = _string_fields(item.get("supported_reasoning_levels", []), "effort", 32)
            tiers = _string_fields(item.get("service_tiers", []), "id", 32)
            upgrade = item.get("upgrade")
            if upgrade is not None and not isinstance(upgrade, dict):
                raise ValueError("invalid_upgrade")
            upgrade_model = upgrade.get("model") if isinstance(upgrade, dict) else None
            retirement = upgrade.get("retirement_at") if isinstance(upgrade, dict) else None
            if upgrade_model is not None and (not isinstance(upgrade_model, str) or len(upgrade_model) > 128):
                raise ValueError("invalid_upgrade_model")
            if retirement is not None and (not isinstance(retirement, str) or _timestamp(retirement) is None):
                raise ValueError("invalid_retirement_time")
            observations.append(ModelObservation(model_id, visibility, efforts, tiers, upgrade_model, retirement))
    except (TypeError, ValueError) as exc:
        return CatalogueResult(CatalogueState.UNAVAILABLE, reason=str(exc))
    return CatalogueResult(CatalogueState.COMPLETE, tuple(sorted(observations, key=lambda model: model.canonical_id)), document["fetched_at"], client)


def compare_catalogue(current: CatalogueResult, baseline: Any) -> DriftReport:
    """Compare allowlisted fields only; never make routing or receipt decisions."""
    if current.state != CatalogueState.COMPLETE:
        return DriftReport("DISCOVERY UNAVAILABLE", reason=current.reason)
    if not _valid_baseline(baseline):
        return DriftReport("DISCOVERY UNAVAILABLE", reason="invalid_baseline")
    before = {item["id"]: item for item in baseline["models"]}
    after = {model.canonical_id: model for model in current.models}
    added = tuple(sorted(after.keys() - before.keys()))
    removed = tuple(sorted(before.keys() - after.keys()))
    visibility = []
    efforts = []
    tiers = []
    migrations = []
    for model_id in sorted(before.keys() & after.keys()):
        old, new = before[model_id], after[model_id]
        if old["visibility"] != new.visibility:
            visibility.append({"id": model_id, "before": old["visibility"], "current": new.visibility})
        if tuple(old["efforts"]) != new.efforts:
            efforts.append({"id": model_id, "before": list(old["efforts"]), "current": list(new.efforts)})
        if tuple(old["service_tiers"]) != new.service_tiers:
            tiers.append({"id": model_id, "before": list(old["service_tiers"]), "current": list(new.service_tiers)})
        old_migration = (old.get("upgrade_model"), old.get("retirement_at"))
        new_migration = (new.upgrade_model, new.retirement_at)
        if old_migration != new_migration:
            migrations.append({"id": model_id, "before": list(old_migration), "current": list(new_migration)})
    policy_states = tuple({"id": model_id, "state": _policy_state(model_id, after[model_id].visibility)} for model_id in sorted(after))
    changed = bool(added or removed or visibility or efforts or tiers or migrations)
    return DriftReport("MODEL CATALOGUE CHANGED" if changed else "MODEL CATALOGUE OK", added, removed, tuple(visibility), tuple(efforts), tuple(tiers), tuple(migrations), policy_states)


def load_baseline(path: Path) -> dict[str, Any] | None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BASELINE_BYTES:
            return None
        with path.open("rb") as stream:
            raw = stream.read(MAX_BASELINE_BYTES + 1)
        if len(raw) > MAX_BASELINE_BYTES:
            return None
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if _valid_baseline(data) else None


def _valid_baseline(data: Any) -> bool:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return False
    if not isinstance(data.get("revision"), str) or not data["revision"] or _timestamp(data.get("reviewed_at")) is None:
        return False
    models = data.get("models")
    if not isinstance(models, list) or not models or len(models) > MAX_MODELS:
        return False
    seen = set()
    for item in models:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in seen:
            return False
        seen.add(item["id"])
        if item.get("visibility") not in {"list", "hide"} or not all(isinstance(item.get(field), list) for field in ("efforts", "service_tiers")):
            return False
        if any(not isinstance(value, str) or len(value) > 64 for field in ("efforts", "service_tiers") for value in item[field]):
            return False
        if item.get("upgrade_model") is not None and not isinstance(item["upgrade_model"], str):
            return False
        if item.get("retirement_at") is not None and not isinstance(item["retirement_at"], str):
            return False
    return True


def _string_fields(items: Any, key: str, limit: int) -> tuple[str, ...]:
    if not isinstance(items, list) or len(items) > limit:
        raise ValueError("invalid_model_metadata")
    values = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid_model_metadata")
        value = item.get(key)
        if not isinstance(value, str) or not value or len(value) > 64:
            raise ValueError("invalid_model_metadata")
        values.append(value)
    return tuple(sorted(set(values)))


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _policy_state(model_id: str, visibility: str) -> str:
    if model_id in {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.5"}:
        return "legacy_transition"
    if model_id in {"gpt-6-luna", "gpt-6-sol", "gpt-6-astra"}:
        return "active" if visibility == "list" else "ignored"
    if visibility != "list":
        return "ignored"
    return "discovered_unapproved"


def main() -> int:
    result = discover_catalogue()
    baseline_path = Path(__file__).parent / "data" / "model_catalogue_baseline.json"
    baseline = load_baseline(baseline_path)
    report = compare_catalogue(result, baseline)
    print(report.status)
    if report.reason:
        print(f"reason: {report.reason}")
    for label, values in (("added", report.added_ids), ("removed", report.removed_ids), ("visibility", report.visibility_changes), ("efforts", report.effort_changes), ("service_tiers", report.service_tier_changes), ("migration", report.migration_changes)):
        if values:
            print(f"{label}: {json.dumps(values, sort_keys=True)}")
    for item in report.policy_states:
        if item["state"] == "legacy_transition":
            print(f"{item['id']}: LEGACY / TRANSITION — NOT ACTIVE POLICY")
        elif item["state"] == "discovered_unapproved":
            print(f"{item['id']}: DISCOVERED — POLICY UNAPPROVED")
    return 0 if report.status != "DISCOVERY UNAVAILABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
