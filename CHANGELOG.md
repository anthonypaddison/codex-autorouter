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
- Hardened live Desktop delegation: classifier input now unwraps only the user-owned `<input>` payload, comma-formatted batch sizes are parsed correctly, synthetic fixture values and negated production/data/schema phrases cannot masquerade as critical payments work, and the RelayForge 1,200-record replay routes to two Luna leaves.
- Reconciled the current `collaboration.spawn_agent` transcript shape—including repeated roles—so missing lifecycle delivery can recover every child id and model attestation. Spawn contracts now require self-contained messages when history is intentionally not forked.
- Added transcript recovery for machine-readable nested-command exit status after the final mutation. Bare command output and assistant completion prose remain insufficient verification evidence.
- Made the verification contract emit an exact structured nested-command result and prevented Python `>=` version checks from being misclassified as shell redirection mutations during transcript recovery.
- Recognized explicitly named Python validator scripts as verification evidence while continuing to reject arbitrary Python programs, and added bounded session-transcript discovery when Desktop omits `transcript_path` from Stop events, so successful custom fixture/schema checks settle the post-mutation ledger.
- Hardened the LaunchGrid acceptance path: local fixed-schema fixture batches ignore incidental release/merge/schema/policy labels, delayed sibling completion is reconciled before staged-owner admission, and children trust hook-owned lifecycle identity instead of stale cache locators.
- Restricted route-up to evidence-backed task-capability limits and preserved completed historical plans so a valid escalation cannot retroactively create unexpected-agent, worker-cap, or ordering violations.
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
- Made `Stop` and `SubagentStop` strictly advisory: terminal hooks record unmet routing, attestation, and verification debt as `FAILED_OPEN` and can no longer emit a hard-block response that Codex may replay as a poisoned user message.
- Front-loaded required-agent coverage, lifecycle attestation, final-mutation verification, service-tier inheritance, and no-recursion rules into trusted `UserPromptSubmit` and `SubagentStart` context.
- Added `routerctl sanitize --session PATH|--all` for conservative offline repair of already-poisoned JSONL sessions, including nested compacted history, exact backups, atomic replacement, idempotency, and fail-closed malformed-input handling.
- Added a release guard that rejects any reintroduced `{"decision":"block"}` terminal response, plus regression coverage and an upstream Codex replay bug report.
