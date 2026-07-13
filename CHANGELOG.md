# Changelog

## 0.1.0 - Private beta

- Renamed the user-facing plugin to **Autorouter** while retaining the technical `gpt-5-6-router` package ID for upgrade continuity, and added a GitHub-ready visual system covering model choice, profiles, subagent orchestration, architecture, and readiness.
- Replaced the orbit-heavy app icon with a simpler three-input, one-output routing mark and aligned the README hero branding with it.
- Added persistent Token Saver, Balanced, and Max Quality routing profiles with safety floors, bounded quality escalation, CLI/status visibility, and upgrade-stable storage independent of Fast/Standard.

- Added deterministic task, risk, ambiguity, verification, volume, and product-area profiling.
- Added factual Sol/Terra/Luna model-effort-speed route labels.
- Added bounded single-delegate, parallel-leaf, evidence-owner, and uncertainty-council plans.
- Added Sol Extra High for narrowly qualified Max Quality work and removed the separate judge stage in favor of useful evidence workers plus one final executor.
- Added native plugin hooks using `${PLUGIN_ROOT}` and persistent state under `${PLUGIN_DATA}`.
- Made cached hook commands upgrade-resilient: open tasks discover the newest installed router after cache replacement, while a missing installation reports once and then fails open silently.
- Made Stop completion idempotent and non-recursive, migrated ledger build identity across cache versions, and recognized successful `verify:*`, `check:*`, and `ci:*` package scripts as verification evidence.
- Normalized nested Codex tool commands and JSON-wrapped results so successful observable tests settle the exact mutation generation; XML-wrapped hook continuations are no longer reclassified, and a route that mutates after starting read-only receives a real test/build gate instead of an `answer check`. When unified-exec interception withholds the result, the ledger records an explicit silent `FAILED_OPEN` instead of claiming success or recursively prompting.
- Added explicit `ADVISORY` and `MANAGED_BLOCKED` local modes, with full readiness reserved for exact app-server and hook-trust attestation.
- Added transactional custom-agent activation, recovery, repair, conflict-safe upgrade behavior, and deactivation.
- Added adversarial routing, lifecycle, concurrency, crash-recovery, symlink, managed-policy, and portability tests.
- Clarified that live reasoning effort and UI Fast state are not currently hook-attested.
- Added a transactional, conflict-refusing standalone advisory lifecycle for IDE and other non-plugin surfaces, including durable controllers and crash-safe update/uninstall recovery.
- Added authoritative app-server checks for effective configuration and managed requirements.
- Moved hook ledgers to nonce-bound `router-state-v2`; legacy private-beta state is never claimed or deleted automatically.
- Required native custom-agent spawns to carry the exact `agent_type` plus `fork_turns: "none"`, with a literal four-key call contract.
- Accepted substantive multiline Evidence, Verification, and Uncertainty sections without weakening empty-section rejection.
- Added five-run native delegation stability acceptance and a final exact-installed-cache replay.
- Added cross-platform CI bytecode hygiene and a clean-room release-archive lifecycle gate.
