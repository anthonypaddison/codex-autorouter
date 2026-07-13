# Release checklist

Record candidate-specific proof in `RELEASE_EVIDENCE.md`; never infer a checked gate from a source-only test.

## Automated gates

- [x] Plugin manifest and skill validation pass.
- [x] Router and activator tests pass on Python 3.10, 3.11, 3.12, 3.13, and the current runtime.
- [x] All 155 tests pass on hosted macOS, Ubuntu, and native Windows across Python 3.10–3.14 ([run 29229808684](https://github.com/vibeforge1111/gpt-5-6-router/actions/runs/29229808684)).
- [x] Clean install, identical reinstall, conflict refusal, reviewed replacement, upgrade, repair, deactivation, and modified-file preservation pass.
- [x] Exception and hard-crash failure injection at every declared failpoint restore the exact pre-operation agent tree.
- [x] Concurrent lifecycle commands serialize without lost ownership state.
- [x] Standalone install, exact-owned update, uninstall, durable-controller recovery, and purge pass without overwriting foreign or drifted skill trees.
- [x] Every declared standalone install/update/uninstall crash boundary rolls back or commits deterministically, and post-crash edits are preserved.
- [x] Plugin cache contains no source-machine absolute paths, secrets, symlinks, bytecode, or transient state.
- [x] Installed-cache hooks use only plugin-relative commands and plugin data.
- [x] `scripts/check_hooks.py` observes exactly five trusted, enabled, error-free plugin hooks and five active current agent definitions after explicit review.
- [x] Routing golden cases, product taxonomy, adversarial prompts, continuations, Fast reporting, and 5,000-case fuzzing pass.
- [x] `ADVISORY`, local-agent-ready, authoritative full-ready, and `MANAGED_BLOCKED` diagnostics are covered.

## Real-host acceptance

Complete every row with the released archive or marketplace snapshot, not the source directory. Follow `HOST_ACCEPTANCE.md` and retain its evidence fields for each row.

| OS | Surface | Install/cache relocation | Hook trust | Route smoke | Activate/deactivate | Result |
|---|---|---:|---:|---:|---:|---|
| macOS | Desktop | required | required | required | required | pending |
| macOS | CLI | pass | pass | pass | pass | delegated acceptance on `0.1.0+codex.20260713061434`; installed profile smokes on `0.1.0+codex.20260713064025` |
| Linux | CLI | required | required | required | required | pending |
| Windows | Desktop | required | required | required | required | pending |
| Windows | CLI | required | required | required | required | pending |

IDE extensions are excluded from the full-plugin matrix because Codex plugins are not currently supported there. The standalone advisory skill still requires an IDE discovery, routing, custom-agent, update, and uninstall smoke on each supported host.

## Policy and degraded modes

- [x] Untrusted hooks are skipped and status does not claim full activation.
- [x] Changed hook definitions require renewed trust.
- [x] Hooks-disabled and multi-agent-disabled configurations remain advisory.
- [x] `allow_managed_hooks_only` reports managed blocked and never attempts bypass.
- [x] Missing custom agents remain advisory without breaking normal Codex work.
- [x] Fast and effort labels never claim unavailable runtime attestation.
- [ ] The public repository or marketplace exposes a tested private vulnerability-reporting channel (GitHub makes repository private reporting available only after public visibility).

## Public-release decision

Do not mark stable or publish broadly until every automated gate passes and every real-host row has evidence. A private marketplace beta may proceed with explicitly documented pending rows.
