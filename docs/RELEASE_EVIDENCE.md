# Release evidence

Current installed candidate: `0.1.0+codex.20260713064025`
Recorded: 2026-07-13

## Proven on the candidate source snapshot

- Release, plugin, skill, and source-integrity validators pass.
- 155 routing, profile-policy, activation, checker, standalone, ownership, concurrency, and crash-recovery tests pass locally on macOS with Python 3.14; the hosted cross-version matrix is pending for this snapshot.
- The deterministic routing fuzz suite passes 5,000 cases on every tested Python runtime.
- GitHub Actions run [29227761286](https://github.com/vibeforge1111/gpt-5-6-router/actions/runs/29227761286) passes all 15 combinations of `ubuntu-latest`, `macos-latest`, and `windows-latest` with Python 3.10–3.14 on source snapshot `5ea0dfce31b0f63260f69a4a01ab1e3f986b0cbe`.
- The prior hosted snapshot ran all 142 then-current tests in every job; this candidate adds 13 profile-policy and persistence tests and awaits the same 15-job matrix.
- Hosted Windows tests exercise native file locking, atomic replacement, rollback, reparse-point refusal, hardlink handling, concurrency, and crash recovery; the Windows Desktop and CLI product surfaces remain separate real-host gates.
- Fifty consecutive concurrent first-install stress rounds pass; a deterministic delayed-marker writer proves contenders wait for an exclusive standalone state claim to finish.
- Every declared activation and standalone transaction boundary has rollback-or-commit coverage, including preservation of post-crash edits and terminal purge recovery.
- Adversarial contract, security, and routing re-audits reproduced the reported failures, verified their fixes, and returned no remaining P0/P1 finding.
- The source scan contains no symlinks, bytecode, transient state, source-machine paths, or detected credential patterns.
- Private-beta ledger upgrades start in nonce-bound `router-state-v2` and preserve the unbound legacy directory without claiming or deleting it.

## Proven on the exact installed candidate

- The installed cache is byte-for-byte identical to the candidate source.
- App-server discovered the exact cached skill plus five enabled, trusted, error-free plugin hooks; all five local custom-agent files were active and current.
- Installed-cache hook smokes proved Token Saver selected one Terra Medium worker, Max Quality selected one Sol Medium owner for the same ambiguous diagnosis, both preserved Fast, and the persistent preference was restored to Balanced afterward.
- The preference survived immutable cache replacement, accepted every valid profile through the installed CLI, and remained independent of agent activation state.
- A live macOS CLI security-review prompt selected `gpt56_sol_judge` with `agent_type: "gpt56_sol_judge"`, `fork_turns: "none"`, and no model, effort, or service-tier override.
- The child lifecycle attested model `gpt-5.6-sol`, configured effort `high`, and inherited Fast service tier.
- The nonce-bound ledger completed with route label `Sol High Fast`, exactly one required custom judge, zero continuations, status `COMPLETE`, and zero violations.
- The final response matched the bounded acceptance token `ROUTER_DELEGATED_OK`.
- The same runtime code passed five consecutive fresh-task delegated stability trials on precursor build `0.1.0+codex.20260713013700`; every ledger had the exact judge, zero continuations, `COMPLETE`, and zero violations. The final documentation-only cache build was then replayed once against the same gate.
- The extracted release ZIP passed a clean-room standalone lifecycle under a fresh canonical `CODEX_HOME`: inactive status, install, identical idempotent reinstall, five-agent activation, status, repair, deactivation, durable-controller status and uninstall, controller purge, and final target/agent absence checks.
- The same clean-room test confirmed that a symlinked `/var` temporary ancestor is refused while its canonical `/private/var` physical path succeeds, preserving the path-safety contract on macOS.

## Regressions caught by live acceptance

- Candidate `0.1.0+codex.20260713005838` used the custom role only as `task_name`; Codex launched built-in `default`. The completion hook rejected it.
- Candidate `0.1.0+codex.20260713012039` added `agent_type`, but the model's first attempt used the default full-history fork. Codex inherited `default`; a corrective custom spawn succeeded, but the ledger correctly remained `FAILED_OPEN` because the unexpected worker could not be erased.
- Candidate `0.1.0+codex.20260713013300` proved that a correct custom judge can naturally place section content below `Evidence:`, `Verification:`, and `Uncertainty:` headings. The one-line-only parser falsely rejected it, caused unnecessary retries, and kept the ledger failed. The parser now accepts substantive multiline bodies while still rejecting empty sections, including transcript-reconciliation coverage.
- The current candidate injects a literal four-key spawn shape requiring `agent_type`, `fork_turns: "none"`, `task_name`, and `message`; it also accepts natural nonempty section formatting. The stability and final exact-build runs completed on the first spawn without retry.

## External acceptance still required

- macOS Desktop, Linux CLI, Windows CLI, and Windows Desktop real-host acceptance.
- Codex Desktop UI automation is safety-blocked from controlling the Codex app itself, so the Desktop row requires a manual fresh-task smoke rather than an app-server-only substitute.
- A tested private vulnerability-reporting channel on the eventual public distribution. GitHub exposes this feature only after the repository is public, so enabling it remains a publication-time gate.

The current candidate clears every automated gate plus the macOS CLI and native custom-agent gates. Pending real-host UI/CLI rows and the publication-time reporting channel still block a public-stable declaration; a clearly labeled private beta may proceed.
