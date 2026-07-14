# Release evidence

Current source candidate: the cachebusted version in `.codex-plugin/plugin.json`
Recorded: 2026-07-14

## Proven on the candidate source snapshot

- Release, plugin, skill, and source-integrity validators pass.
- 199 routing, profile-policy, activation, sanitizer, terminal-event, benchmark-harness, stale-cache dispatch, delegated-input isolation, current collaboration transcript reconciliation, nested-tool verification, unobservable-result fail-open, wrapped Stop-idempotency, checker, standalone, ownership, concurrency, and crash-recovery tests pass locally on macOS with Python 3.14.
- The deterministic routing fuzz suite passes 5,000 cases on every tested Python runtime.
- GitHub Actions run [29233219101](https://github.com/vibeforge1111/Codex-Autorouter/actions/runs/29233219101) passes all 15 combinations of `ubuntu-latest`, `macos-latest`, and `windows-latest` with Python 3.10–3.14 at runtime snapshot `6e3a39f18055e3944ba27f9d46d65a3d5382b8ab`. The terminal-hook and sanitizer candidate has repeated the complete gate locally; its exact hosted branch run remains required before merge or public-stable promotion.
- Every hosted job validates the release, runs all 199 tests, runs 5,000 deterministic fuzz cases, and revalidates source integrity after execution.
- Hosted Windows tests exercise native file locking, atomic replacement, rollback, reparse-point refusal, hardlink handling, concurrency, and crash recovery; the Windows Desktop and CLI product surfaces remain separate real-host gates.
- Fifty consecutive concurrent first-install stress rounds pass; a deterministic delayed-marker writer proves contenders wait for an exclusive standalone state claim to finish.
- Every declared activation and standalone transaction boundary has rollback-or-commit coverage, including preservation of post-crash edits and terminal purge recovery.
- Adversarial contract, security, and routing re-audits reproduced the reported failures, verified their fixes, and returned no remaining P0/P1 finding.
- The source scan contains no symlinks, bytecode, transient state, source-machine paths, or detected credential patterns.
- Private-beta ledger upgrades start in nonce-bound `router-state-v2` and preserve the unbound legacy directory without claiming or deleting it.

## Proven on the exact installed candidate

- The personal-marketplace installed cache contains the same 47-file, byte-for-byte inventory as the candidate source.
- App-server discovered the current candidate, the exact cached skill, five enabled and trusted error-free plugin hooks, and six active current custom-agent definitions; `scripts/check_hooks.py` returned `ready: true` with no warnings or errors.
- `routerctl activate` migrated the six owned agent definitions to the current build. `routerctl status` reports Balanced, `local_agent_ready: true`, no conflicts or drift, and `activation_update_required: false`.
- `codex plugin list` reports only the current candidate installed and enabled; the retired pre-hardening cache is absent.
- A synthetic unmet `Stop` event returned `continue: true` plus an advisory `systemMessage`, wrote `FAILED_OPEN` and `failed_open_problems`, and contained no block decision.
- A fresh Codex CLI session started without another hook-review prompt after trust was recorded, proving the five unchanged definitions remained active across the cache replacement.
- Installed-cache hook smokes on precursor cache `0.1.0+codex.20260713064025` proved Token Saver selected one Terra Medium worker, Max Quality selected one Sol Medium owner for the same ambiguous diagnosis, both preserved Fast, and the persistent preference was restored to Balanced afterward. The current candidate additionally hardens stale-hook dispatch, makes verification-only Stop state silent, and refreshes the public branding and documentation.
- The preference survived immutable cache replacement, accepted every valid profile through the installed CLI, and remained independent of agent activation state.
- A live macOS CLI security-analysis prompt on precursor candidate `0.1.0+codex.20260713113358` started from a Terra Medium root and selected `Terra Medium Fast ×2 → Sol High Fast`, the current Balanced consequential-work plan. Because the current candidate changes hook event normalization, the exact-candidate delegated CLI row must be replayed before public-stable release.
- Two `gpt56_terra_worker` evidence leaves and one `gpt56_sol_deep` owner launched with exact custom `agent_type`, `fork_turns: "none"`, and no model, effort, or service-tier override. Lifecycle events attested both Terra models at configured Medium intent and the Sol model at configured High intent; all three inherited Fast and reported no mutation or recursive spawn.
- The nonce-bound precursor ledger recorded plugin version `0.1.0+codex.20260713113358`, all three required agents complete, zero continuations, status `COMPLETE`, and zero violations.
- The final response matched the bounded acceptance token `ROUTER_DELEGATED_OK`.
- The first post-reinstall app-server readiness probe timed out during local Codex state-database slowness; an immediate retry returned `ready: true`. The ephemeral CLI smoke also logged transcript-path fallback warnings, but stable lifecycle events attested every required child and the completed ledger retained zero violations. These host warnings did not require a router retry or weaken an acceptance check.
- The same runtime code passed five consecutive fresh-task delegated stability trials on precursor build `0.1.0+codex.20260713013700`; every ledger had the exact Sol High specialist, zero continuations, `COMPLETE`, and zero violations. The final documentation-only cache build was then replayed once against the same gate.
- The extracted release ZIP passed a clean-room standalone lifecycle under a fresh canonical `CODEX_HOME`: inactive status, install, identical idempotent reinstall, agent activation, status, repair, deactivation, durable-controller status and uninstall, controller purge, and final target/agent absence checks.
- The same clean-room test confirmed that a symlinked `/var` temporary ancestor is refused while its canonical `/private/var` physical path succeeds, preserving the path-safety contract on macOS.

## README and visual QA

- The user-facing plugin name is **Autorouter**. The technical `gpt-5-6-router` package ID remains stable so existing preferences, plugin state, and upgrades are not stranded.
- The README presents six accessible SVG assets: icon/hero, model-effort routing map, profile comparison, bounded-subagent orchestration, routing architecture, and install-to-live-proof readiness.
- Every SVG parses as valid XML, includes an accessible title and description, renders successfully at 1,600 pixels wide, and was visually inspected for clipping, contrast, and text legibility.
- Every local README image and documentation link resolves in the candidate tree.

## Regressions caught by live acceptance

- The RelayForge acceptance build exposed three coupled failures: a delegated task's source UUID produced `unit_count: 7932`; synthetic values such as `billing-reliability` plus the phrase `routing ledger` produced a critical payments route; and one of two completed Terra workers was absent from lifecycle attestation. A frozen replay now extracts only `<input>`, parses `1,200` correctly, selects two Luna leaves at normal risk, and reconciles all current collaboration activity records into distinct child ids and attestations.
- RelayForge also showed ten successful root checks as unobservable because unified-exec omitted `tool_response` while the transcript retained the actual paired call/output. Stop reconciliation now accepts a successful post-mutation transcript result only when it contains machine-readable exit status. The proactive contract tells nested verification calls to expose that status; plain output and completion claims still fail open.
- The LaunchGrid replay added a harder local 2,400-record fixture containing release, merge, schema, and policy vocabulary; it now selects two Luna leaves while an affirmative production release remains protected. Delayed sibling completion is reconciled before staged-owner admission, metadata/cache confusion cannot trigger route-up, completed pre-escalation plans remain valid, and paired same-turn transcript exit status settles the final mutation generation.

- A pre-fix open task retained an absolute command into a retired plugin cache. Its successful `pnpm verify:fast` was not recognized, the carried mutation generation remained unpaid, and terminal `FAILED_OPEN` stops emitted another system message. The hook command now resolves the newest installed sibling cache, package `verify:*` scripts count only with successful tool evidence, completion feedback is carried once, and terminal Stop delivery is idempotent.
- A later open-task replay exposed a second adapter defect: Codex's orchestration tool returns nested command inputs while unified-exec `PostToolUse` interception may omit the result entirely. The hook recognized the test command but could not prove its successful exit code, leaving mutation generations unpaid and producing the misleading gate `answer check after the final mutation`. The adapter now extracts literal nested commands, safely decodes bounded JSON result blocks when available, recognizes environment-prefixed verification, promotes any post-route mutation to a test/build gate, and discards the app's XML-wrapped legacy feedback instead of treating it as a new task. Verification state—including observable failure or unavailable results—is recorded for root ownership and cannot inject replayable Stop feedback.
- Disk analysis of poisoned tasks established that Codex persisted terminal-hook block reasons as user messages carrying client UUIDv7 IDs, then replayed those invalid IDs to the Responses API. The current candidate prohibits block decisions throughout the hook source, moves governance to safe proactive context, records terminal violations as advisory `FAILED_OPEN`, and provides conservative offline repair for top-level and compacted JSONL history.

- Candidate `0.1.0+codex.20260713005838` used the custom role only as `task_name`; Codex launched built-in `default`. The completion hook rejected it.
- Candidate `0.1.0+codex.20260713012039` added `agent_type`, but the model's first attempt used the default full-history fork. Codex inherited `default`; a corrective custom spawn succeeded, but the ledger correctly remained `FAILED_OPEN` because the unexpected worker could not be erased.
- Candidate `0.1.0+codex.20260713013300` proved that a correct custom specialist can naturally place section content below `Evidence:`, `Verification:`, and `Uncertainty:` headings. The one-line-only parser falsely rejected it, caused unnecessary retries, and kept the ledger failed. The parser now accepts substantive multiline bodies while still rejecting empty sections, including transcript-reconciliation coverage.
- The current candidate injects a literal four-key spawn shape requiring `agent_type`, `fork_turns: "none"`, `task_name`, and `message`; it also accepts natural nonempty section formatting. The stability and final exact-build runs completed on the first spawn without retry.

## External acceptance still required

- macOS Desktop, Linux CLI, Windows CLI, and Windows Desktop real-host acceptance.
- Codex Desktop UI automation is safety-blocked from controlling the Codex app itself, so the Desktop row requires a manual fresh-task smoke rather than an app-server-only substitute.
- A tested private vulnerability-reporting channel on the eventual public distribution. GitHub exposes this feature only after the repository is public, so enabling it remains a publication-time gate.

The current candidate clears every automated gate plus the macOS CLI and native custom-agent gates. Pending real-host UI/CLI rows and the publication-time reporting channel still block a public-stable declaration; a clearly labeled private beta may proceed.
