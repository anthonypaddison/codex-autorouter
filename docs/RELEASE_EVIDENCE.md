# Release evidence

- Current source candidate: manifest version `0.2.0` on the fork's `ap-cheap-root-routing` branch
- Recorded: 2026-08-11
- Release status: **not released**; the planned immutable `v0.2.0` tag, archive, SHA256, host acceptance, publication, and merge have not been performed.

This file distinguishes current-candidate proof from predecessor history. Evidence from `0.1.0` custom-agent builds does not prove the `0.2.0` direct-child path, receipt binding, or cheap-root behaviour.

## Current-candidate source evidence

Record exact command output and commit identifiers here before checking the matching rows in `RELEASE_CHECKLIST.md`.

- Release-contract tests cover fork metadata, immutable planned ref, retained Alchemist attribution, cheap-root documentation, and the future tag/archive/SHA256 procedure.
- The release validator requires manifest `0.2.0`, fork URLs, privacy URL pinned to `v0.2.0`, known optional legacy assets only, and the release procedure. It rejects moving `main`, `master`, or `HEAD` marketplace refs.
- Normal lifecycle behaviour and health no longer depend on legacy custom-agent TOMLs. Those assets remain optional compatibility material selected only through `activate --legacy-agents`.
- Direct Terra/Sol/Astra argument construction, schema detection, and fallback are expected to pass only through the central compatibility adapter; current automated and real-host results must be attached before release.
- Hook definitions are expected to execute only the router under their own exact plugin root and fail open without sibling-cache discovery; current exact-candidate test output must be attached before release.
- `UserPromptSubmit.model` is the required per-turn active-root evidence. Current tests must prove Luna/Terra/Sol/Astra policy, clarification without escalation for user-intent ambiguity, and `DEGRADED` health for every non-Luna turn.
- Astra evidence must prove that generic classification never selects it, explicit requests default to Medium and reject Low/Ultra, the sole automatic Sol route-up targets Medium with exact attestation, and no automatic Astra effort retry exists.
- Capability receipts must bind plugin version, observable Codex runtime/build, host type, platform, observed child model, effort intent, capability/schema signature, and timestamp. Current tests and host runs must prove runtime invalidation and absence of automatic paid probes.
- Status commands must be proven read-only against an absent `CODEX_HOME` tree and existing state. This cannot be inferred from implementation review alone.

The full suite, 5,000-case fuzz run, clean-tree release validation, and hosted Python/OS matrix remain candidate gates until their exact commit and outputs are recorded.

## Current real-host evidence required

No `0.2.0` Desktop or CLI row is accepted yet. Each row must follow `HOST_ACCEPTANCE.md` and retain:

- exact plugin/tag/archive identity and SHA256;
- Codex runtime/build, Desktop or CLI host, platform, and hook trust;
- hook-observed Luna root for the efficient path;
- a genuine successful Terra and Sol escalation through the direct compatibility adapter, plus a separately bounded Astra gate check;
- a matching `READY` receipt followed by proven `DEGRADED` behaviour after runtime/build identity changes;
- proof that health/status did not launch a paid child;
- bounded Luna Low evidence and, only if Low is unreliable, a controlled Luna Medium comparison;
- truthful non-Luna `DEGRADED` matrix evidence and no classifier-driven downward delegation from Sol.

## Historical predecessor evidence

The upstream `0.1.0` line had extensive automated coverage for routing classification, nonce-bound ledgers, fail-open terminal hooks, sanitizer behaviour, standalone transaction recovery, filesystem ownership, Windows path safety, and deterministic fuzzing. Historical hosted runs included [29233219101](https://github.com/vibeforge1111/Codex-Autorouter/actions/runs/29233219101) and [29333382896](https://github.com/vibeforge1111/Codex-Autorouter/actions/runs/29333382896).

Those builds also produced live macOS CLI custom-agent evidence using named `gpt56_terra_worker` and `gpt56_sol_deep` TOMLs. That evidence is retained only as regression context for ledger and verification behaviour. It is not current-path acceptance because `0.2.0` deliberately replaces normal named-agent activation with direct model/effort spawning behind a compatibility adapter.

Historical failures remain relevant test motivations:

- source-thread UUID digits and synthetic technical vocabulary once distorted classification;
- incomplete orchestration results once made successful verification unobservable;
- terminal hard-block feedback once poisoned persisted transcripts;
- stale-cache discovery once risked executing a sibling installation;
- default/full-history spawns and custom `agent_type` mismatches once invalidated child attestation.

The `0.2.0` candidate must retain regression coverage for the underlying privacy, verification, idempotency, and fail-open properties without restoring obsolete legacy-agent requirements.

## Distribution evidence required

Before publication, append:

1. the reviewed commit and annotated `v0.2.0` tag resolution;
2. clean-room archive validation and full suite output;
3. the archive SHA256 and successful checksum verification;
4. every required Desktop/CLI row;
5. private vulnerability-reporting evidence;
6. confirmation that the immutable marketplace/privacy URLs resolve to the reviewed tag.

Until those items exist, do not describe `0.2.0` as stable, installable, fully accepted, released, or `READY` on any untested host.
