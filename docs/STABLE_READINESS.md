# Autorouter v1.0.0 release gates

Assessment date: 22 November 2026. Verdict: **NOT READY**.

Start with an Apple silicon macOS interactive Codex CLI release. The test host
ran macOS 27.3, Codex CLI 0.170.0 and Python 3.14.2. List only exact CLI builds
and Python versions that pass live acceptance. Desktop is a separate support
row. Linux, Windows, IDE extensions, managed environments that disallow the
hooks or native delegation, and automation routing have no stable acceptance.

## Acceptance criteria

Every gate applicable to the advertised support matrix must pass on the exact
publication commit. Missing evidence leaves the gate open.

| Gate | Pass criteria | Current evidence |
| --- | --- | --- |
| Public install and first run | Fresh account or profile installs the publicly pinned marketplace and plugin without publisher data or GitHub credentials. The wizard accepts the user's exact pairs, requires billing consent and preserves config on invalid input. Review all five hooks through Codex. | Partial. Local tag mirror installed into an empty Codex profile and setup made zero classifier calls. Offline wizard tests cover consent, validation and backup. Public Git transport and interactive host trust remain open. |
| Native routing and ledger | Eight pre-scored live synthetic tasks, four expected to stay direct and four to delegate. Require at least 7/8 expected outcomes, zero disallowed pairs, zero duplicate requests/children and zero false completion. Every delegated success must bind one exact child to start, returned evidence and completion. Run one exact directive, one continuation and one missing-key fallback separately. | Open. One historical CLI task on an earlier payload completed correctly. Local cases prove hook decisions and duplicate handling independently of Codex model execution. |
| Deadline and recovery | Default deadline ten seconds, one classifier request per new turn, no request without a usable credential. Force timeout and invalid/unsupported results in offline tests. Native rejection and ambiguous child outcomes must never spawn an automatic replacement. | Automated coverage passes. Live timing and a supported host's native rejection remain open. |
| Performance | Record API success/fallback counts and per-turn elapsed time. On the eight live cases, require at most one classifier timeout or provider failure and no hook deadline errors. On 50 local direct/fallback cases, require p95 under 500 ms and no write outside the disposable profile. Track token usage when available. | 60/60 local launcher cases from the verified v0.3.0 archive, plus two duplicate deliveries, made zero API attempts. Median 98.7 ms, p95 105.7 ms, max 157.1 ms. Earlier live classifier 5.642 s within a 25.440 s turn, with 299 input and 186 output tokens. No comparative cost or live reliability claim. |
| Desktop credentials, if supported | A clean Desktop user follows the documented private relaunch, classifies one task and records the expected configured route and correlated execution. A fresh session launched without the key makes zero classifier calls and reports fallback. No global launch service or saved credentials are copied. | Open. Earlier CLI process inherited an explicitly provisioned key. Desktop inheritance remains unverified. Keep Desktop outside v1 support unless it passes. |
| Removal and rollback | Uninstall by full selector, confirm hook cache is absent and unrelated settings are intact. Reinstall the previous pinned plugin with its saved router config, compare payload identity and re-review changed hooks. | Removal in the fresh profile passed. Router config was retained. Cross-version rollback remains open. |
| Security, compatibility, packaging | Python standard library only for the configured classifier. Fail closed on unsafe config, disallowed models and unverifiable receipt claims. Check supported host versions, offline CI, source hygiene and required notices. Two clean archives from the exact tag must match the published digest. | No Python dependency resolver is required for the plugin. Published v0.3.0 archive was reproduced byte-for-byte and the local validator now supports archive inventories. Hosted CI passed for the published commit. Candidate CI and release review remain open. |

Choose delegation cases where the task's constraints or verification needs
justify a higher-capability executor. The closed-interval merge from the first
trial is a direct-root case. Luna/Low produced a correct non-mutating solution
and covered the requested edge cases. Keep genuinely demanding cases in the
delegation set.

For a follow-up that only asks for a completed explanation to be restated in a
specified number of sentences in the same session, require zero new classifier
calls and zero new children. The root handles the rewrite using the existing
answer. A follow-up that adds a new task or changes the argument should receive
a new routing decision.

## Pull request and publication

1. After push approval, push `ap/stable-v1-readiness` and open a PR against
   `main`. Require all `release-quality` jobs and review the small source and
   documentation diffs. Retain the offline architecture and API-billing opt-in.
2. Complete the clean-user gates above on a reviewed candidate. Use temporary
   user/Codex state and a benign scratch Git repo. Provision a key only with
   verified account-side credit or an authorised spend limit. Use small
   correctness tasks and keep automated benchmarking offline. Record elapsed
   times, actual root and child pairs, redacted ledgers and failure reasons.
3. Once the gates pass, prepare the v1 version metadata, pinned marketplace
   ref, validation expectations and supported-version table together. Keep
   existing prereleases intact. Exercise the exact candidate before approval
   using an isolated local Git mirror of the future tag, then merge only after
   separate approval. Revalidate the exact merged tree and repeat the artefact
   smoke if its payload differs.
4. After separate publication approval, verify that `refs/tags/v1.0.0` is
   unused. Tag the reviewed merged commit with
   `git tag -a v1.0.0 REVIEWED_COMMIT -m "release v1.0.0"`. Build and verify
   `git archive --format=zip --prefix=Codex-Autorouter-v1.0.0/ -o Codex-Autorouter-v1.0.0.zip v1.0.0`
   and `shasum -a 256 Codex-Autorouter-v1.0.0.zip` from the tag. Save a
   `.zip.SHA256` file and scan the extracted archive with
   `python3 scripts/validate_release.py --archive`.
5. Push only the new tag. Test the real public marketplace install and
   rollback on the pinned tag. Create the GitHub release as a draft with the
   ZIP, checksum and acceptance summary. Verify the asset digest and release
   links, then publish as stable only after all checks pass.

[Public v0.3.0 release](https://github.com/anthonypaddison/codex-autorouter/releases/tag/v0.3.0) ·
[Hosted v0.3.0 CI](https://github.com/anthonypaddison/codex-autorouter/actions/runs/44178056685)
