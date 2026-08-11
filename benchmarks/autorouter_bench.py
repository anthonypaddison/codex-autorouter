#!/usr/bin/env python3
"""Controlled capability and efficiency benchmark for Codex Autorouter."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "skills" / "route-gpt-5-6-work" / "scripts" / "router_hook.py"
DEFAULT_OUTPUT = Path("/tmp/autorouter-arena")
ROUTERCTL = ROOT / "skills" / "route-gpt-5-6-work" / "scripts" / "routerctl.py"
ARMS = ("baseline", "token-saver", "balanced", "max-quality")
AUTOROUTER_ARMS = ARMS[1:]


@dataclass(frozen=True)
class ReviewerSeat:
    seat: str
    provider: str
    model: str
    base_url: str
    key_var: str


REVIEWER_SEATS = (
    ReviewerSeat("glm", "zai-glm-5.2", "glm-5.2", "https://api.z.ai/api/coding/paas/v4", "ZAI_API_KEY"),
    ReviewerSeat("deepseek", "deepseek-v4-pro", "deepseek-v4-pro", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
)


@dataclass(frozen=True)
class Case:
    case_id: str
    title: str
    prompt: str
    expected_mode: str
    expected_roles: dict[str, int]
    build: Callable[[Path], None]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def _common_grader() -> str:
    return """
    import json
    import sys

    def finish(checks):
        passed = sum(1 for item in checks if item["passed"])
        payload = {"passed": passed, "total": len(checks), "score": passed / len(checks), "checks": checks}
        print(json.dumps(payload, sort_keys=True))
        raise SystemExit(0 if passed == len(checks) else 1)
    """


def _build_locale_batch(path: Path) -> None:
    _write(path / "normalize_catalogs.py", """
    #!/usr/bin/env python3
    \"\"\"Normalize every JSON catalog under catalogs/ into normalized/.\"\"\"
    raise NotImplementedError("implement the exact contract in TASK.md")
    """)
    for index in range(120):
        locale = f"x-{index:03d}"
        payload = {
            "locale": f"  {locale.upper()}  ",
            "messages": {
                "welcome": f"  Welcome {index}  ",
                "empty": "   ",
                "count": index,
            },
        }
        _write(path / "catalogs" / f"{locale}.json", json.dumps(payload) + "\n")
    _write(path / "TASK.md", """
    # Normalize 120 locale catalogs

    Implement `normalize_catalogs.py`. Apply the same mechanical contract to
    every JSON file in `catalogs/` and write matching files to `normalized/`:

    - trim surrounding whitespace from every string;
    - lowercase the top-level `locale` value;
    - remove message entries whose trimmed string is empty;
    - preserve non-string message values;
    - sort object keys and emit UTF-8 JSON with a trailing newline;
    - reject a catalog missing `locale` or `messages` without partially replacing
      a previously valid `normalized/` directory.

    The rule is complete, repeated, and objectively checked. Run
    `python3 benchmark_grader.py` after the final mutation.
    """)
    _write(path / "benchmark_grader.py", _common_grader() + """
    import hashlib
    import pathlib
    import subprocess
    import tempfile

    root = pathlib.Path(__file__).parent
    checks = []
    result = subprocess.run([sys.executable, "normalize_catalogs.py"], cwd=root, capture_output=True, text=True)
    checks.append({"name": "command succeeds", "passed": result.returncode == 0, "detail": result.stderr[-300:]})
    outputs = sorted((root / "normalized").glob("*.json")) if (root / "normalized").exists() else []
    checks.append({"name": "all 120 files", "passed": len(outputs) == 120, "detail": str(len(outputs))})
    samples_ok = True
    canonical_ok = True
    for index in (0, 37, 119):
        target = root / "normalized" / f"x-{index:03d}.json"
        try:
            raw = target.read_text(encoding="utf-8")
            value = json.loads(raw)
            samples_ok &= value == {"locale": f"x-{index:03d}", "messages": {"count": index, "welcome": f"Welcome {index}"}}
            canonical_ok &= raw == json.dumps(value, ensure_ascii=False, sort_keys=True) + "\\n"
        except Exception:
            samples_ok = canonical_ok = False
    checks.append({"name": "normalization semantics", "passed": samples_ok, "detail": "sampled 0, 37, 119"})
    checks.append({"name": "canonical JSON", "passed": canonical_ok, "detail": "sorted keys plus newline"})
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}
    bad = root / "catalogs" / "x-bad.json"
    bad.write_text('{"messages":{}}\\n', encoding="utf-8")
    failed = subprocess.run([sys.executable, "normalize_catalogs.py"], cwd=root, capture_output=True, text=True)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "normalized").glob("*.json")}
    bad.unlink()
    checks.append({"name": "invalid input rejected", "passed": failed.returncode != 0, "detail": str(failed.returncode)})
    checks.append({"name": "atomic replacement", "passed": before == after, "detail": "prior output preserved"})
    finish(checks)
    """)


def _build_webhook_race(path: Path) -> None:
    _write(path / "webhooks.py", """
    \"\"\"Tiny webhook deduplicator with an intermittent concurrency defect.\"\"\"
    import time

    class WebhookStore:
        def __init__(self):
            self.processed = set()
            self.effects = []

        def apply(self, event_id, payload):
            if event_id in self.processed:
                return False
            time.sleep(0.001)
            self.effects.append((event_id, payload))
            self.processed.add(event_id)
            return True
    """)
    _write(path / "TASK.md", """
    # Diagnose an intermittent webhook race

    CI occasionally records the same payment webhook side effect more than
    once. The root cause is unclear and appears only under concurrency. Diagnose
    and fix `WebhookStore` while preserving these semantics:

    - exactly one caller applies a given event id;
    - different event ids may still make progress concurrently;
    - public method arguments and return values stay compatible.

    Prove the fix with repeated targeted tests. Finish with
    `python3 benchmark_grader.py`.
    """)
    _write(path / "benchmark_grader.py", _common_grader() + """
    import concurrent.futures
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from webhooks import WebhookStore

    checks = []
    stable = True
    for _ in range(20):
        store = WebhookStore()
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
            results = list(pool.map(lambda _: store.apply("evt-1", {"amount": 7}), range(80)))
        stable &= sum(bool(v) for v in results) == 1 and len(store.effects) == 1
    checks.append({"name": "same-id atomicity", "passed": stable, "detail": "20 x 80 concurrent attempts"})
    store = WebhookStore()
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda i: store.apply(f"evt-{i}", i), range(40)))
    checks.append({"name": "distinct events", "passed": all(results) and len(store.effects) == 40, "detail": str(len(store.effects))})
    store = WebhookStore()
    first = store.apply("evt-retry", object())
    second = store.apply("evt-retry", "ok")
    checks.append({"name": "return compatibility", "passed": first is True and second is False, "detail": f"{first}/{second}"})
    finish(checks)
    """)


def _build_sqlite_migration(path: Path) -> None:
    _write(path / "migrate.py", """
    #!/usr/bin/env python3
    \"\"\"Usage: migrate.py DATABASE up|down\"\"\"
    raise NotImplementedError("implement the reversible migration in TASK.md")
    """)
    _write(path / "TASK.md", """
    # Own a reversible SQLite migration

    Implement `migrate.py DATABASE up|down` for an existing `accounts` table.
    The forward migration adds a normalized, non-null `email_key` used for
    case-insensitive uniqueness and backfills it from `email`. Trim surrounding
    whitespace and lowercase Unicode text. Duplicate normalized addresses must
    abort the entire migration without changing schema or data.

    The rollback removes the uniqueness structure and `email_key` while
    preserving ids, emails, and display names exactly. Both directions must be
    transactional and safely reject an already-applied direction. Own the full
    migration, rollback, and verification. Run `python3 benchmark_grader.py`.
    """)
    _write(path / "benchmark_grader.py", _common_grader() + """
    import pathlib
    import sqlite3
    import subprocess
    import tempfile

    root = pathlib.Path(__file__).parent
    checks = []
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "ok.sqlite"
        con = sqlite3.connect(db)
        con.execute("create table accounts(id integer primary key, email text not null, display_name text not null)")
        rows = [(1, " Alice@Example.COM ", "Alice"), (2, "bob@example.com", "Bób")]
        con.executemany("insert into accounts values(?,?,?)", rows); con.commit(); con.close()
        up = subprocess.run([sys.executable, "migrate.py", str(db), "up"], cwd=root, capture_output=True, text=True)
        con = sqlite3.connect(db)
        columns = [r[1] for r in con.execute("pragma table_info(accounts)")]
        values = con.execute("select id,email,display_name,email_key from accounts order by id").fetchall() if "email_key" in columns else []
        unique_failed = False
        if "email_key" in columns:
            try:
                con.execute("insert into accounts(id,email,display_name,email_key) values(3,'x','X','alice@example.com')"); con.commit()
            except sqlite3.IntegrityError:
                unique_failed = True; con.rollback()
        con.close()
        checks.append({"name": "forward migration", "passed": up.returncode == 0 and values == [(1, rows[0][1], rows[0][2], "alice@example.com"), (2, rows[1][1], rows[1][2], "bob@example.com")], "detail": up.stderr[-200:]})
        checks.append({"name": "normalized uniqueness", "passed": unique_failed, "detail": "duplicate insert rejected"})
        down = subprocess.run([sys.executable, "migrate.py", str(db), "down"], cwd=root, capture_output=True, text=True)
        con = sqlite3.connect(db); columns = [r[1] for r in con.execute("pragma table_info(accounts)")]; restored = con.execute("select id,email,display_name from accounts order by id").fetchall(); con.close()
        checks.append({"name": "lossless rollback", "passed": down.returncode == 0 and "email_key" not in columns and restored == rows, "detail": down.stderr[-200:]})
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "dupe.sqlite"; con = sqlite3.connect(db)
        con.execute("create table accounts(id integer primary key, email text not null, display_name text not null)")
        original = [(1,"A@x.test","A"),(2," a@x.test ","B")]; con.executemany("insert into accounts values(?,?,?)", original); con.commit(); con.close()
        result = subprocess.run([sys.executable, "migrate.py", str(db), "up"], cwd=root, capture_output=True, text=True)
        con = sqlite3.connect(db); columns = [r[1] for r in con.execute("pragma table_info(accounts)")]; rows = con.execute("select * from accounts order by id").fetchall(); con.close()
        checks.append({"name": "duplicate rollback", "passed": result.returncode != 0 and "email_key" not in columns and rows == original, "detail": result.stderr[-200:]})
    finish(checks)
    """)


def _build_parallel_audit(path: Path) -> None:
    _write(path / "auth.py", """
    def export_billing(requester, requested_tenant, database):
        # requester carries requester.tenant_id but it is never checked.
        return database.rows_for_tenant(requested_tenant)
    """)
    _write(path / "settings.html", """
    <html><body>
      <div class="save" onclick="saveSettings()">Save settings</div>
      <input id="email" placeholder="Email address">
      <div id="result"></div>
    </body></html>
    """)
    _write(path / "schema.sql", """
    CREATE TABLE webhook_events (
      id INTEGER PRIMARY KEY,
      provider_event_id TEXT NOT NULL,
      tenant_id INTEGER NOT NULL,
      payload TEXT NOT NULL
    );
    CREATE INDEX webhook_event_lookup ON webhook_events(provider_event_id);
    """)
    _write(path / "TASK.md", """
    # Parallel product audit

    Audit three independent, read-only workstreams in parallel:

    1. tenant isolation in `auth.py`;
    2. keyboard and screen-reader accessibility in `settings.html`;
    3. webhook idempotency and tenant boundaries in `schema.sql`.

    Do not modify those source files. Create `AUDIT.md` with prioritized,
    evidence-backed findings, concrete exploit/failure scenarios, and bounded
    remediations. Separate confirmed defects from assumptions. Finish with
    `python3 benchmark_grader.py`.
    """)
    _write(path / "benchmark_grader.py", _common_grader() + """
    import pathlib
    import re
    text = (pathlib.Path(__file__).parent / "AUDIT.md").read_text(encoding="utf-8") if (pathlib.Path(__file__).parent / "AUDIT.md").exists() else ""
    lower = text.lower()
    checks = [
      {"name": "tenant authorization", "passed": "tenant" in lower and any(x in lower for x in ("authorization", "authorisation", "access check")), "detail": "auth.py boundary"},
      {"name": "keyboard semantics", "passed": "keyboard" in lower and any(x in lower for x in ("button", "tab", "focus")), "detail": "clickable div"},
      {"name": "accessible name", "passed": any(x in lower for x in ("label", "accessible name")) and "placeholder" in lower, "detail": "input labeling"},
      {"name": "status announcement", "passed": any(x in lower for x in ("aria-live", "role=status", 'role=\"status\"')), "detail": "dynamic result"},
      {"name": "webhook uniqueness", "passed": "unique" in lower and "provider_event_id" in text, "detail": "idempotency constraint"},
      {"name": "tenant-scoped key", "passed": "tenant_id" in text and any(x in lower for x in ("composite", "scoped", "per tenant")), "detail": "boundary-aware key"},
      {"name": "prioritization", "passed": len(re.findall(r"\\b(?:critical|high|medium|low|p[0-3])\\b", lower)) >= 3, "detail": "severity language"},
      {"name": "evidence and remediation", "passed": any(x in lower for x in ("line", "evidence", "because")) and any(x in lower for x in ("remediation", "fix", "replace", "add")), "detail": "actionable report"},
    ]
    finish(checks)
    """)


CASES = (
    Case(
        "locale_batch",
        "Mechanical locale normalization",
        "Normalize all 120 independent locale JSON files using the exact repeated schema and validator contract in TASK.md. Complete the mechanical transformation across every file and run python3 benchmark_grader.py after the final mutation.",
        "parallel_leaves",
        {"gpt56_luna_worker": 2},
        _build_locale_batch,
    ),
    Case(
        "webhook_race",
        "Intermittent webhook concurrency bug",
        "Diagnose and fix the intermittent CI-only webhook deduplication failure in TASK.md. The root cause is unclear and involves concurrency edge cases. Prove the fix with repeated targeted tests and finish with python3 benchmark_grader.py.",
        "direct",
        {},
        _build_webhook_race,
    ),
    Case(
        "sqlite_migration",
        "Reversible SQLite migration",
        "Own the reversible SQLite schema migration and data backfill in TASK.md. Implement forward migration, duplicate-safe rollback behavior, and lossless down migration; run python3 benchmark_grader.py after the final mutation.",
        "direct",
        {},
        _build_sqlite_migration,
    ),
    Case(
        "parallel_audit",
        "Independent product risk audit",
        "Audit three independent read-only workstreams in parallel: tenant security, keyboard and screen-reader accessibility, and webhook database integrity. Follow TASK.md, create the prioritized evidence-backed report, and run python3 benchmark_grader.py after the final mutation.",
        "evidence_then_owner",
        {"gpt56_terra_worker": 2, "gpt56_sol_deep": 1},
        _build_parallel_audit,
    ),
)


EXPECTED_PLANS = {
    "locale_batch": {
        "token-saver": ("direct", {}),
        "balanced": ("direct", {}),
        "max-quality": ("direct", {}),
    },
    "webhook_race": {
        "token-saver": ("single_delegate", {"gpt56_terra_worker": 1}),
        "balanced": ("single_delegate", {"gpt56_terra_deep": 1}),
        "max-quality": ("evidence_then_owner", {"gpt56_terra_worker": 2, "gpt56_sol_owner": 1}),
    },
    "sqlite_migration": {
        "token-saver": ("single_delegate", {"gpt56_terra_deep": 1}),
        "balanced": ("single_delegate", {"gpt56_sol_owner": 1}),
        "max-quality": ("evidence_then_owner", {"gpt56_terra_worker": 2, "gpt56_sol_deep": 1}),
    },
    "parallel_audit": {
        "token-saver": ("evidence_then_owner", {"gpt56_terra_worker": 2, "gpt56_sol_deep": 1}),
        "balanced": ("evidence_then_owner", {"gpt56_terra_worker": 2, "gpt56_sol_deep": 1}),
        "max-quality": ("evidence_then_owner", {"gpt56_terra_worker": 2, "gpt56_sol_xhigh": 1}),
    },
}


ROUTE_PROBES = (
    ("trivial", "Fix a typo in README.", "current", "direct"),
    ("batch", "Normalize 120 independent locale JSON catalogs using the exact schema and validator. Apply the same mechanical rule to every file.", "current", "direct"),
    (
        "delegated_fixture",
        """<codex_delegation>
<source_thread_id>019f4ab3-2b7a-7932-a6a6-f401afced4e3</source_thread_id>
<input>Generate exactly 1,200 synthetic JSONL fixture records in three independent 400-record shards using fixed formulas. One example projectSlug is billing-reliability. These are synthetic fixtures, not customer data. Add a strict validator, do not modify runtime or database schema, and run tests, typecheck, lint, and build. Record the routing ledger.</input>
</codex_delegation>""",
        "current",
        "direct",
    ),
    ("ordinary", "Implement the bounded feedback tags API from complete acceptance tests.", "gpt56_terra_worker", "single_delegate"),
    ("ambiguous", "Diagnose and fix an intermittent CI-only webhook deduplication failure involving unclear concurrency edge cases.", "gpt56_terra_deep", "single_delegate"),
    ("critical", "Fix a critical authorization bypass in the production billing export endpoint and review adversarial edge cases.", "gpt56_sol_deep", "evidence_then_owner"),
    ("clarify", "We need to improve onboarding, but it is unclear whether this is a UX flow problem, analytics blind spot, or implementation defect.", "current", "clarify"),
    ("parallel", "Audit three independent workstreams in parallel: tenant security, accessibility, and database integrity. Create a prioritized report.", "gpt56_sol_deep", "evidence_then_owner"),
)


def _load_router():
    spec = importlib.util.spec_from_file_location("autorouter_benchmark_router", ROUTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {ROUTER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route_audit(strict: bool = False) -> int:
    router = _load_router()
    rows = []
    for name, prompt, expected_route, expected_mode in ROUTE_PROBES:
        decision = router.classify_prompt(prompt, "gpt-5.6-luna", "low", "balanced")
        passed = decision["route"] == expected_route and decision["orchestration"]["mode"] == expected_mode
        rows.append((name, decision["route"], decision["orchestration"]["mode"], passed))
    width = max(len(row[0]) for row in rows)
    for name, route, mode, passed in rows:
        print(f"{'PASS' if passed else 'FAIL'}  {name:<{width}}  {route:<22} {mode}")
    passed = sum(row[3] for row in rows)
    print(f"route audit: {passed}/{len(rows)} contracts matched")
    return 1 if strict and passed != len(rows) else 0


def _select_cases(case_ids: list[str]) -> list[Case]:
    wanted = set(case_ids)
    selected = [case for case in CASES if not wanted or case.case_id in wanted]
    unknown = wanted - {case.case_id for case in selected}
    if unknown:
        raise ValueError("unknown case(s): " + ", ".join(sorted(unknown)))
    return selected


def prepare(output: Path, cases: list[Case], clean: bool = False) -> None:
    if clean and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    for case in cases:
        starter = output / "starters" / case.case_id
        if starter.exists():
            shutil.rmtree(starter)
        starter.mkdir(parents=True)
        case.build(starter)
    print(f"prepared {len(cases)} cases in {output}")


def _copy_starter(output: Path, case: Case, arm: str, repetition: int) -> Path:
    source = output / "starters" / case.case_id
    target = output / "runs" / f"repeat-{repetition}" / arm / case.case_id / "workspace"
    if target.parent.exists():
        shutil.rmtree(target.parent)
    shutil.copytree(source, target)
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "add", "."], cwd=target, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Autorouter Arena", "-c", "user.email=arena@example.invalid", "commit", "-qm", "frozen starter"],
        cwd=target,
        check=True,
    )
    return target


def _usage_from_events(event_path: Path) -> dict[str, Any]:
    aggregates: list[dict[str, int]] = []
    observations: list[dict[str, int]] = []

    def normalized(value: dict[str, Any]) -> dict[str, int] | None:
        if not isinstance(value.get("input_tokens"), int) or not isinstance(value.get("output_tokens"), int):
            return None
        return {key: int(value.get(key, 0)) for key in (
            "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"
        )}

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            usage = normalized(value)
            if usage is not None:
                (aggregates if key == "total_token_usage" else observations).append(usage)
                return
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                visit(child, key)

    if not event_path.exists():
        return {"provenance": "UNAVAILABLE", "aggregation": "none", "total_tokens": None, "observations": []}
    for line in event_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            visit(json.loads(line))
        except json.JSONDecodeError:
            continue
    if aggregates:
        return {
            **aggregates[-1],
            "provenance": "TOKEN ESTIMATE",
            "aggregation": "documented_total_token_usage",
            "observations": observations,
        }
    if observations:
        return {
            "provenance": "TOKEN ESTIMATE",
            "aggregation": "partial_per_thread",
            "total_tokens": None,
            "observations": observations,
        }
    return {"provenance": "UNAVAILABLE", "aggregation": "none", "total_tokens": None, "observations": []}


def _thread_id_from_events(event_path: Path) -> str | None:
    if not event_path.exists():
        return None
    for line in event_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("thread_id", "session_id"):
            if isinstance(value.get(key), str):
                return value[key]
        payload = value.get("payload")
        if isinstance(payload, dict):
            for key in ("thread_id", "session_id"):
                if isinstance(payload.get(key), str):
                    return payload[key]
    return None


def _find_ledger(thread_id: str | None, started: float) -> tuple[dict[str, Any] | None, Path | None]:
    roots = [
        Path(os.environ.get("CODEX_ROUTER_STATE_DIR", "")),
        Path.home() / ".codex" / "plugins" / "data" / "gpt-5-6-router-personal" / "router-state-v2",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not str(root) or not root.is_dir():
            continue
        pattern = f"{thread_id}--*.json" if thread_id else "*.json"
        for path in root.glob(pattern):
            try:
                if path.stat().st_mtime >= started - 2:
                    candidates.append(path)
            except OSError:
                pass
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            return json.loads(path.read_text(encoding="utf-8")), path
        except (OSError, json.JSONDecodeError):
            continue
    return None, None


def _grade(workspace: Path) -> dict[str, Any]:
    result = subprocess.run([sys.executable, "benchmark_grader.py"], cwd=workspace, capture_output=True, text=True)
    payload: dict[str, Any]
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        payload = {"passed": 0, "total": 1, "score": 0.0, "checks": [], "parse_error": result.stdout[-500:]}
    payload["exit_code"] = result.returncode
    payload["stderr"] = result.stderr[-1000:]
    return payload


def _route_score(case: Case, ledger: dict[str, Any] | None, arm: str) -> dict[str, Any]:
    if arm == "baseline":
        return {"available": ledger is None, "passed": ledger is None, "detail": "no Autorouter ledger expected"}
    if ledger is None:
        return {"available": False, "passed": False, "detail": "no correlated Autorouter ledger"}
    decision = ledger.get("decision", {})
    plan = decision.get("orchestration", {})
    actual_roles: dict[str, int] = {}
    agents = ledger.get("agents")
    if isinstance(agents, dict):
        for child in agents.values():
            if not isinstance(child, dict):
                continue
            role = child.get("type")
            if isinstance(role, str):
                actual_roles[role] = actual_roles.get(role, 0) + 1
    expected_mode, expected = EXPECTED_PLANS[case.case_id][arm]
    route_ok = plan.get("mode") == expected_mode
    coverage_ok = all(actual_roles.get(role, 0) >= count for role, count in expected.items())
    if not expected:
        coverage_ok = not actual_roles
    return {
        "available": True,
        "passed": route_ok and coverage_ok,
        "expected_mode": expected_mode,
        "actual_mode": plan.get("mode"),
        "expected_roles": expected,
        "actual_roles": actual_roles,
        "ledger_status": ledger.get("status"),
    }


def _codex_command(args: argparse.Namespace, arm: str, workspace: Path, prompt: str) -> list[str]:
    command = [
        args.codex,
        "exec",
        "--json",
        "--ephemeral",
        "--color",
        "never",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(workspace),
        "--model",
        args.root_model,
        "-c",
        f'model_reasoning_effort="{args.root_effort}"',
        "-c",
        f'service_tier="{args.service_tier}"',
    ]
    if arm == "baseline":
        command.extend(["--ignore-rules", "-c", 'plugins."gpt-5-6-router@personal".enabled=false'])
    else:
        command.append("--dangerously-bypass-hook-trust")
    command.append(prompt)
    return command


def _run_one(args: argparse.Namespace, output: Path, case: Case, arm: str, repetition: int) -> dict[str, Any]:
    workspace = _copy_starter(output, case, arm, repetition)
    run_dir = workspace.parent
    events = run_dir / "events.jsonl"
    final_message = run_dir / "final.txt"
    command = _codex_command(args, arm, workspace, case.prompt)
    command[-1:-1] = ["--output-last-message", str(final_message)]
    started = time.time()
    with events.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, text=True, timeout=args.timeout)
    elapsed = time.time() - started
    thread_id = _thread_id_from_events(events)
    ledger, ledger_path = _find_ledger(thread_id, started) if arm != "baseline" else (None, None)
    if ledger_path is not None:
        shutil.copy2(ledger_path, run_dir / "router-ledger.json")
    grade = _grade(workspace)
    result = {
        "case": case.case_id,
        "arm": arm,
        "routing_profile": arm if arm in AUTOROUTER_ARMS else None,
        "repetition": repetition,
        "codex_exit_code": completed.returncode,
        "codex_stderr": completed.stderr[-2000:],
        "elapsed_seconds": round(elapsed, 3),
        "usage": _usage_from_events(events),
        "thread_id": thread_id,
        "quality": grade,
        "routing": _route_score(case, ledger, arm),
        "workspace": str(workspace),
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _profile(value: str | None = None) -> str:
    command = [sys.executable, str(ROUTERCTL), "profile"]
    if value is not None:
        command.append(value)
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    payload = json.loads(completed.stdout)
    selected = payload.get("profile")
    if selected not in AUTOROUTER_ARMS:
        raise ValueError(f"routerctl returned an invalid profile: {selected}")
    return str(selected)


def _arm_order(repetition: int) -> tuple[str, ...]:
    offset = (repetition - 1) % len(ARMS)
    return ARMS[offset:] + ARMS[:offset]


def _bounded_text(path: Path, limit: int = 50_000) -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return value if len(value) <= limit else value[:limit] + "\n[truncated]\n"


def _blind_final_response(value: str) -> str:
    lines = [line for line in value.splitlines() if not re.match(r"^\s*route\s*:", line, re.I)]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\b(?:token saver|balanced|max quality)\b", "[profile hidden]", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:gpt[- ]?5\.6\s+)?(?:luna|terra|sol)(?:\s+(?:low|medium|high|extra high))?\b", "[route hidden]", cleaned, flags=re.I)
    return cleaned[:8_000]


def _workspace_patch(workspace: Path, limit: int = 25_000) -> str:
    completed = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary", "HEAD", "--", "."],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    chunks = [completed.stdout]
    for relative in sorted(line for line in untracked.stdout.splitlines() if line):
        path = workspace / relative
        if not path.is_file() or path.stat().st_size > 200_000:
            continue
        chunks.append(f"\n--- untracked: {relative} ---\n{_bounded_text(path, 5_000)}")
    value = "".join(chunks)
    return value if len(value) <= limit else value[:limit] + "\n[artifact patch truncated]\n"


def _blind_packet(case: Case, repetition: int, results: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    by_arm = {str(item.get("arm")): item for item in results}
    missing = [arm for arm in ARMS if arm not in by_arm]
    if missing:
        raise ValueError(f"cannot build blind packet; missing arms: {', '.join(missing)}")
    mapping: dict[str, str] = {}
    artifacts: list[dict[str, Any]] = []
    for arm in ARMS:
        opaque = "artifact-" + hashlib.sha256(f"autorouter-arena:{case.case_id}:{repetition}:{arm}".encode()).hexdigest()[:10]
        mapping[opaque] = arm
        item = by_arm[arm]
        workspace = Path(str(item["workspace"]))
        run_dir = workspace.parent
        quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
        artifacts.append({
            "artifact_id": opaque,
            "deterministic_checks": {
                "passed": quality.get("passed"),
                "total": quality.get("total"),
                "checks": quality.get("checks", []),
            },
            "candidate_patch": _workspace_patch(workspace),
            "candidate_final_response": _blind_final_response(_bounded_text(run_dir / "final.txt", 8_000)),
        })
    artifacts.sort(key=lambda item: item["artifact_id"])
    task_path = Path(str(results[0]["workspace"])) / "TASK.md"
    packet = {
        "schema_version": "autorouter-arena.blind-packet.v1",
        "case_id": case.case_id,
        "case_title": case.title,
        "repetition": repetition,
        "task": _bounded_text(task_path, 20_000),
        "evaluation_axes": ["correctness", "completeness", "robustness", "maintainability", "verification"],
        "artifacts": artifacts,
        "blindness_contract": {
            "generator_labels_hidden": True,
            "model_and_profile_hidden": True,
            "token_and_latency_hidden": True,
            "reviewers_receive_output_only_evidence": True,
        },
    }
    packet["packet_digest"] = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return packet, mapping


def _review_prompt(packet: dict[str, Any], retry_reason: str | None = None) -> str:
    artifact_ids = [item["artifact_id"] for item in packet["artifacts"]]
    retry = f"Your previous response was invalid: {retry_reason}. " if retry_reason else ""
    return (
        "You are an independent blind reviewer for an offline Autorouter development benchmark. "
        "You are not routing or modifying user work. Judge only the supplied output artifacts. "
        "The artifact labels are randomized; do not infer models, profiles, cost, or generation process. "
        "Deterministic checks are evidence but not a substitute for inspecting the patch and response. "
        + retry
        + "Return exactly one JSON object and no markdown. Use this schema: "
        '{"schema_version":"autorouter-arena.outsider-review.v1","ranking":["artifact-id"],'
        '"artifacts":{"artifact-id":{"quality_score":0,"correctness":0,"completeness":0,"robustness":0,'
        '"maintainability":0,"verification":0,"safety_veto":false,"strengths":["..."],"weaknesses":["..."],'
        '"recommended_changes":["..."]}},"overall_observations":["..."],"confidence":0.0}. '
        f"Ranking and artifact keys must contain each of these exactly once: {artifact_ids}. "
        "Every numeric quality field is 0-100. A safety veto is only for a concrete harmful or integrity-breaking defect. "
        "Recommendations must be repair-grade and evidence-cited. Packet: "
        + json.dumps(packet, sort_keys=True, separators=(",", ":"))
    )


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.rsplit("```", 1)[0].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("reviewer returned non-JSON output")
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("reviewer output is not an object")
    return value


def _validate_review(value: dict[str, Any], artifact_ids: list[str]) -> None:
    if value.get("schema_version") != "autorouter-arena.outsider-review.v1":
        raise ValueError("wrong review schema_version")
    ranking = value.get("ranking")
    artifacts = value.get("artifacts")
    if not isinstance(ranking, list) or set(ranking) != set(artifact_ids) or len(ranking) != len(artifact_ids):
        raise ValueError("review ranking does not cover the blind artifacts exactly once")
    if not isinstance(artifacts, dict) or set(artifacts) != set(artifact_ids):
        raise ValueError("review artifact rows do not match the blind packet")
    axes = ("quality_score", "correctness", "completeness", "robustness", "maintainability", "verification")
    for artifact_id in artifact_ids:
        row = artifacts[artifact_id]
        if not isinstance(row, dict):
            raise ValueError(f"invalid review row for {artifact_id}")
        for axis in axes:
            score = row.get(axis)
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= float(score) <= 100:
                raise ValueError(f"invalid {axis} for {artifact_id}")
        if not isinstance(row.get("safety_veto"), bool):
            raise ValueError(f"invalid safety_veto for {artifact_id}")


def _spark_provider_key(var: str) -> str:
    def valid(value: str) -> bool:
        return bool(value) and len(value) <= 512 and not any(ord(char) < 32 or ord(char) == 127 for char in value)

    security = shutil.which("security")
    if security:
        completed = subprocess.run(
            [security, "find-generic-password", "-s", "ai.sparkswarm.loops-desktop", "-a", var, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        value = completed.stdout.strip()
        if completed.returncode == 0 and valid(value):
            return value
    dotenv = Path.home() / ".spark" / ".env"
    try:
        if dotenv.stat().st_mode & 0o077:
            return ""
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            name, separator, raw = line.partition("=")
            if separator and name.strip() == var:
                value = raw.strip().strip("'\"")
                if valid(value):
                    return value
    except OSError:
        pass
    return ""


def _reviewer_keys(reuse_spark_provider_keys: bool) -> dict[str, str]:
    keys = {}
    for seat in REVIEWER_SEATS:
        value = os.environ.get(seat.key_var, "").strip()
        if not value and reuse_spark_provider_keys:
            value = _spark_provider_key(seat.key_var)
        if value:
            keys[seat.key_var] = value
    return keys


def _provider_review(
    seat: ReviewerSeat,
    packet: dict[str, Any],
    timeout: int,
    key_override: str | None = None,
) -> dict[str, Any]:
    key = (key_override or os.environ.get(seat.key_var, "")).strip()
    if not key:
        return {
            "seat": seat.seat,
            "provider": seat.provider,
            "model": seat.model,
            "status": "provider_missing",
            "blocked_reason": f"set {seat.key_var}",
        }
    artifact_ids = [item["artifact_id"] for item in packet["artifacts"]]
    retry_reason: str | None = None
    usages: list[dict[str, Any]] = []
    for attempt in range(2):
        body = {
            "model": seat.model,
            "messages": [
                {"role": "system", "content": "You are a separated blind evaluator. Output strict JSON only."},
                {"role": "user", "content": _review_prompt(packet, retry_reason)},
            ],
            "temperature": 0,
            "max_tokens": 5000,
            "stream": False,
        }
        request = urllib.request.Request(
            seat.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            usage = payload.get("usage")
            if isinstance(usage, dict):
                usages.append({key: value for key, value in usage.items() if isinstance(value, (int, float))})
            content = payload["choices"][0]["message"]["content"]
            value = _json_object(str(content))
            _validate_review(value, artifact_ids)
            return {
                "seat": seat.seat,
                "provider": seat.provider,
                "model": seat.model,
                "status": "scored",
                "attempts": attempt + 1,
                "usage": usages,
                "review": value,
            }
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            retry_reason = str(exc)[:240]
        except urllib.error.HTTPError as exc:
            retry_reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError) as exc:
            retry_reason = type(exc).__name__
    return {
        "seat": seat.seat,
        "provider": seat.provider,
        "model": seat.model,
        "status": "provider_failed",
        "attempts": 2,
        "blocked_reason": retry_reason or "reviewer retry exhausted",
        "usage": usages,
    }


def _fold_panel(packet: dict[str, Any], mapping: dict[str, str], rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("status") == "scored" and isinstance(row.get("review"), dict)]
    full_quorum = len(scored) == len(REVIEWER_SEATS)
    arms: dict[str, dict[str, Any]] = {}
    for artifact_id, arm in mapping.items():
        scores = [float(row["review"]["artifacts"][artifact_id]["quality_score"]) for row in scored]
        recommendations = []
        vetoes = []
        for row in scored:
            artifact = row["review"]["artifacts"][artifact_id]
            recommendations.extend(str(item) for item in artifact.get("recommended_changes", []) if str(item).strip())
            vetoes.append(bool(artifact.get("safety_veto")))
        run = next(item for item in results if item.get("arm") == arm)
        usage = run.get("usage") if isinstance(run.get("usage"), dict) else {}
        arms[arm] = {
            "blind_artifact_id": artifact_id,
            "reviewer_quality_mean": round(sum(scores) / len(scores), 2) if scores else None,
            "reviewer_scores": scores,
            "safety_veto": any(vetoes),
            "repair_recommendations": list(dict.fromkeys(recommendations))[:8],
            "deterministic_quality": run.get("quality"),
            "total_tokens": usage.get("total_tokens"),
            "elapsed_seconds": run.get("elapsed_seconds"),
        }
    winners = [mapping[row["review"]["ranking"][0]] for row in scored]
    consensus_winner = winners[0] if full_quorum and len(set(winners)) == 1 else None
    return {
        "schema_version": "autorouter-arena.outsider-panel.v1",
        "packet_digest": packet["packet_digest"],
        "required_reviewers": [seat.seat for seat in REVIEWER_SEATS],
        "reviewer_count": len(scored),
        "required_reviewer_count": len(REVIEWER_SEATS),
        "full_quorum": full_quorum,
        "official": full_quorum,
        "consensus_winner": consensus_winner,
        "top_rank_votes": winners,
        "arms": arms,
        "claim_boundary": "Offline development evidence only. It may guide Autorouter policy changes but is not a runtime gate, user-facing judge, or automatic promotion.",
    }


def _summarize_panels(panels: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for arm in ARMS:
        quality_scores: list[float] = []
        token_deltas: list[float] = []
        recommendations: list[str] = []
        veto_count = 0
        wins = 0
        for panel in panels:
            row = panel.get("arms", {}).get(arm, {})
            if panel.get("official") and isinstance(row.get("reviewer_quality_mean"), (int, float)):
                quality_scores.append(float(row["reviewer_quality_mean"]))
                recommendations.extend(str(item) for item in row.get("repair_recommendations", []) if str(item).strip())
                veto_count += int(bool(row.get("safety_veto")))
            if panel.get("consensus_winner") == arm:
                wins += 1
            baseline_tokens = panel.get("arms", {}).get("baseline", {}).get("total_tokens")
            arm_tokens = row.get("total_tokens")
            if isinstance(baseline_tokens, (int, float)) and baseline_tokens > 0 and isinstance(arm_tokens, (int, float)):
                token_deltas.append((float(arm_tokens) - float(baseline_tokens)) / float(baseline_tokens) * 100)
        summary[arm] = {
            "official_quality_mean": round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else None,
            "mean_token_delta_vs_baseline_pct": round(sum(token_deltas) / len(token_deltas), 2) if token_deltas else None,
            "consensus_wins": wins,
            "safety_veto_count": veto_count,
            "repair_backlog": list(dict.fromkeys(recommendations))[:20],
            "official_panel_samples": len(quality_scores),
        }
    return summary


def _render_outsider_report(output: Path, panels: list[dict[str, Any]]) -> None:
    summary = _summarize_panels(panels)
    payload = {
        "schema_version": "autorouter-arena.outsider-report.v1",
        "generated_at": int(time.time()),
        "active_reviewer_roster": [seat.__dict__ | {"key_var": seat.key_var} for seat in REVIEWER_SEATS],
        "panels": panels,
        "profile_summary": summary,
        "official_panel_count": sum(1 for panel in panels if panel.get("official")),
        "claim_boundary": "Private Autorouter development benchmark only; no reviewer machinery ships in the runtime plugin.",
    }
    (output / "outsider-review.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Autorouter outsider review",
        "",
        "This is private development evidence. GLM 5.2 and DeepSeek V4 Pro reviewed randomized output-only artifacts; the panel is not part of Autorouter runtime.",
        "",
        "| Case / repeat | Quorum | Consensus winner | Baseline | Token Saver | Balanced | Max Quality |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for panel in panels:
        scores = panel.get("arms", {})
        label = f"{panel.get('case_id')} / {panel.get('repetition')}"
        def score(arm: str) -> str:
            value = scores.get(arm, {}).get("reviewer_quality_mean")
            return "—" if value is None else f"{float(value):.1f}"
        lines.append(
            f"| {label} | {panel.get('reviewer_count', 0)}/{panel.get('required_reviewer_count', 2)} | "
            f"{panel.get('consensus_winner') or 'none'} | {score('baseline')} | {score('token-saver')} | {score('balanced')} | {score('max-quality')} |"
        )
    lines.extend([
        "",
        "## Profile signals",
        "",
        "| Arm | External quality | Token delta vs baseline | Consensus wins | Safety vetoes |",
        "|---|---:|---:|---:|---:|",
    ])
    for arm in ARMS:
        row = summary[arm]
        quality = "—" if row["official_quality_mean"] is None else f"{row['official_quality_mean']:.1f}"
        delta = "—" if row["mean_token_delta_vs_baseline_pct"] is None else f"{row['mean_token_delta_vs_baseline_pct']:+.1f}%"
        lines.append(f"| {arm} | {quality} | {delta} | {row['consensus_wins']} | {row['safety_veto_count']} |")
    lines.extend([
        "",
        "## Profile improvement backlog",
        "",
    ])
    for arm in AUTOROUTER_ARMS:
        lines.append(f"### {arm}")
        lines.append("")
        backlog = summary[arm]["repair_backlog"]
        if backlog:
            lines.extend(f"- {item}" for item in backlog)
        else:
            lines.append("- Awaiting a full reviewer quorum.")
        lines.append("")
    lines.extend([
        "## How to use this",
        "",
        "Treat deterministic graders as correctness evidence, reviewer scores as qualitative external evidence, and token totals as efficiency evidence. Change routing policy only where repeated runs show a stable profile-specific tradeoff; never optimize directly for one panel score.",
        "",
    ])
    (output / "outsider-review.md").write_text("\n".join(lines), encoding="utf-8")


def review(args: argparse.Namespace, output: Path, cases: list[Case]) -> int:
    if not args.execute:
        print("refusing external reviewer spend without --execute", file=sys.stderr)
        return 2
    if not args.acknowledge_external_review_cost:
        print("refusing GLM/DeepSeek calls without --acknowledge-external-review-cost", file=sys.stderr)
        return 2
    keys = _reviewer_keys(args.reuse_spark_provider_keys)
    missing = [seat.key_var for seat in REVIEWER_SEATS if seat.key_var not in keys]
    if missing:
        print("outsider reviewer quorum unavailable; missing " + ", ".join(missing), file=sys.stderr)
        return 3
    report_path = output / "report.json"
    if not report_path.is_file():
        raise ValueError(f"benchmark report not found: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    all_results = report.get("results")
    if not isinstance(all_results, list):
        raise ValueError("benchmark report has no results")
    selected_ids = {case.case_id for case in cases}
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for item in all_results:
        if not isinstance(item, dict) or item.get("case") not in selected_ids:
            continue
        groups.setdefault((str(item["case"]), int(item.get("repetition", 1))), []).append(item)
    panels = []
    case_by_id = {case.case_id: case for case in cases}
    for (case_id, repetition), group in sorted(groups.items()):
        packet, mapping = _blind_packet(case_by_id[case_id], repetition, group)
        review_dir = output / "reviews" / f"repeat-{repetition}" / case_id
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "blind-packet.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (review_dir / "blind-map.json").write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(REVIEWER_SEATS)) as pool:
            futures = [
                pool.submit(_provider_review, seat, packet, args.timeout, keys[seat.key_var])
                for seat in REVIEWER_SEATS
            ]
            rows = [future.result() for future in futures]
        panel = _fold_panel(packet, mapping, rows, group)
        panel["case_id"] = case_id
        panel["repetition"] = repetition
        (review_dir / "reviewer-rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (review_dir / "panel.json").write_text(json.dumps(panel, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        panels.append(panel)
        _render_outsider_report(output, panels)
    print(f"wrote {output / 'outsider-review.md'}")
    return 0 if panels and all(panel.get("official") for panel in panels) else 4


def _render_report(output: Path, results: list[dict[str, Any]]) -> None:
    report = {"schema_version": 1, "generated_at": int(time.time()), "results": results}
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Autorouter Arena report", "", "| Case | Arm | Quality | Routing | Tokens | Seconds |", "|---|---|---:|---:|---:|---:|"]
    for item in results:
        quality = item["quality"]
        usage = item.get("usage") or {}
        tokens = usage.get("total_tokens", "unavailable")
        lines.append(
            f"| {item['case']} | {item['arm']} | {quality.get('passed', 0)}/{quality.get('total', 0)} | "
            f"{'pass' if item['routing'].get('passed') else 'fail'} | {tokens} | {item['elapsed_seconds']:.1f} |"
        )
    lines.extend(["", "## Interpretation", "", "Autorouter earns its overhead only when quality is preserved or improved and routing evidence shows that the selected plan actually executed. Compare repeated-run medians before making cost, latency, or quality claims.", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace, output: Path, cases: list[Case]) -> int:
    if not args.execute:
        print("refusing to spend tokens without --execute", file=sys.stderr)
        return 2
    if not args.trust_reviewed_hooks:
        print("refusing Autorouter subprocesses without --trust-reviewed-hooks", file=sys.stderr)
        return 2
    prepare(output, cases, clean=False)
    results: list[dict[str, Any]] = []
    original_profile = _profile()
    try:
        for repetition in range(1, args.repetitions + 1):
            for case in cases:
                for arm in _arm_order(repetition):
                    if arm in AUTOROUTER_ARMS:
                        _profile(arm)
                    print(f"running repeat {repetition}: {case.case_id} / {arm}", flush=True)
                    results.append(_run_one(args, output, case, arm, repetition))
                    _render_report(output, results)
    finally:
        _profile(original_profile)
    print(f"wrote {output / 'report.md'}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("route-audit", help="zero-token classifier contract audit")
    audit.add_argument("--strict", action="store_true")
    prep = sub.add_parser("prepare", help="generate inspectable benchmark fixtures")
    prep.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    prep.add_argument("--case", action="append", default=[])
    prep.add_argument("--clean", action="store_true")
    live = sub.add_parser("run", help="run paid baseline plus all three Autorouter profiles")
    live.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    live.add_argument("--case", action="append", default=[])
    live.add_argument("--repetitions", type=int, default=1)
    live.add_argument("--execute", action="store_true", help="acknowledge real model execution and token use")
    live.add_argument("--trust-reviewed-hooks", action="store_true", help="acknowledge Codex hook trust bypass for the isolated run")
    live.add_argument("--codex", default="codex")
    live.add_argument("--root-model", default="gpt-5.6-sol")
    live.add_argument("--root-effort", choices=("low", "medium", "high", "xhigh"), default="high")
    live.add_argument("--service-tier", default="priority")
    live.add_argument("--timeout", type=int, default=1800)
    outsider = sub.add_parser("review", help="run the private GLM and DeepSeek blind reviewer panel")
    outsider.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    outsider.add_argument("--case", action="append", default=[])
    outsider.add_argument("--execute", action="store_true", help="acknowledge real external reviewer execution")
    outsider.add_argument("--acknowledge-external-review-cost", action="store_true")
    outsider.add_argument(
        "--reuse-spark-provider-keys",
        action="store_true",
        help="read the existing Spark Loops reviewer keys from its macOS keychain or 0600 dotenv",
    )
    outsider.add_argument("--timeout", type=int, default=240)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "route-audit":
            return route_audit(args.strict)
        cases = _select_cases(args.case)
        if args.command == "prepare":
            prepare(args.output.resolve(), cases, args.clean)
            return 0
        if args.command == "review":
            return review(args, args.output.resolve(), cases)
        if args.repetitions < 1:
            raise ValueError("--repetitions must be at least 1")
        return run(args, args.output.resolve(), cases)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"autorouter arena failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
