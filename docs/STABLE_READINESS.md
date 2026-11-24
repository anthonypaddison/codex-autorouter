# Autorouter v1.0.0 release gates

Assessment date: 23 November 2026. Verdict: **NOT READY**.

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
| Native routing and ledger | Eight pre-scored live synthetic tasks, four expected to stay direct and four to delegate. Require at least 7/8 expected outcomes, zero disallowed pairs, zero duplicate requests/children and zero false completion. Every delegated success must bind one exact child to start, returned evidence and completion. Run one exact directive, one continuation and one missing-key fallback separately. | Corrected candidate: two passes, one route miss, five unrun. The separate exact directive, continuation routing and missing-key fallback passed live. |
| Deadline and recovery | Default deadline ten seconds, one classifier request per new turn, no request without a usable credential. Test timeout and unsupported selections offline. Apply the layered model-validation checks below. | Offline rejection handling and live missing-key fallback passed. Live timing across the full matrix is pending. Native rejection has not been observed on the test host. |
| Performance | Record API success/fallback counts and per-turn elapsed time. On the eight live cases, require at most one classifier timeout or provider failure and no hook deadline errors. On 50 local direct/fallback cases, require p95 under 500 ms and no write outside the disposable profile. Track token usage when available. | 60/60 local launcher cases from the verified v0.3.0 archive, plus two duplicate deliveries, made zero API attempts. Median 98.7 ms, p95 105.7 ms, max 157.1 ms. Earlier live classifier 5.642 s within a 25.440 s turn, with 299 input and 186 output tokens. No comparative cost or live reliability claim. |
| Desktop credentials, if supported | A clean Desktop user follows the documented private relaunch, classifies one task and records the expected configured route and correlated execution. A fresh session launched without the key makes zero classifier calls and reports fallback. No global launch service or saved credentials are copied. | Open. Earlier CLI process inherited an explicitly provisioned key. Desktop inheritance remains unverified. Keep Desktop outside v1 support unless it passes. |
| Removal and rollback | Uninstall by full selector, confirm hook cache is absent and unrelated settings are intact. Reinstall the previous pinned plugin with its saved router config, compare payload identity and re-review changed hooks. | Removal in the fresh profile passed. Router config was retained. Cross-version rollback remains open. |
| Security, compatibility, packaging | Python standard library only for the configured classifier. Fail closed on unsafe config, disallowed models and unverifiable receipt claims. Check supported host versions, offline CI, source hygiene and required notices. Two clean archives from the exact tag must match the published digest. | No Python dependency resolver is required for the plugin. Published v0.3.0 archive was reproduced byte-for-byte and the local validator now supports archive inventories. Hosted CI passed for the published commit. Candidate CI and release review remain open. |

### Model validation and failure handling

1. **Router authorization.** Verify that a disallowed model/effort from an
   explicit directive or classifier result cannot authorize a child. Verify
   that the adapter refuses to attest a call outside the configured contract.
2. **Native execution.** On each advertised host, verify an authorized native
   spawn and correlate the actual model, effort, start and completion to the
   same child and parent turn. Host availability can differ from the allowlist.
   If a supported interface exposes a native rejection, record it separately.
   If none is available, record native rejection as unobserved. Keep Codex's
   native validation in the execution path.
3. **Recovery.** Use offline failure injection to verify that a delivered
   native rejection, ambiguous creation result or post-start failure cannot
   produce a retry, replacement child or false completion. A router-side
   rejection proves authorization enforcement. A synthetic native response
   proves router handling of that response. Neither establishes that the host
   actually rejected a request.

Do not expand the allowlist or bypass host validation to manufacture a
negative test. The live test on the corrected candidate establishes successful
native execution of the observed Terra/Medium pair. It leaves the host's
unsupported-pair behavior unobserved. Require all three layers for configured
release acceptance. Where a supported native negative test is unavailable,
record that host limitation alongside the results of the required checks.

### Scoring

Pre-score an appropriate selection and route for each task. Choose delegation
cases with constraints or verification needs that justify a higher-capability
executor. Luna/Low is appropriate when it can reliably meet the task
requirements. The historical closed-interval merge is one example: the root
produced a correct non-mutating solution and covered the requested edge cases.
Keep the four-direct/four-delegated balance and 7/8 threshold. Use new evidence
to improve future case selection; preserve expectations and outcomes for cases
already run.

Record model selection, observed execution route, answer quality and lifecycle
evidence separately. A correct answer cannot establish a delegated route or
repair a routing miss. Record output-format failures even when routing passes.

For a follow-up that only asks for a completed explanation to be restated in a
specified number of sentences in the same session, require zero new classifier
calls and zero new children. The root handles the rewrite using the existing
answer. A follow-up that adds a new task or changes the argument should receive
a new routing decision.

### Corrected-candidate matrix

Recorded against source commit `864e1c65026d8f7912ecc76f0810d9120a629b81`.
The score is **two passes, one routing miss, five unrun**.

| Task | Expected route | Recorded outcome |
| --- | --- | --- |
| Independent arithmetic | Direct | Pass. Luna/Low, correct `114`. |
| Minutes to seconds | Direct | Unrun. |
| Alphabetical sorting | Direct | Unrun. |
| ISO date extraction | Direct | Unrun. |
| Lease fencing | Delegated | Miss. Luna/Low answered directly. The answer addressed the task. |
| FIFO linearizability | Delegated | Pass. One Terra/Medium child with matched start, model, effort and completion. |
| Online cycle detector | Delegated | Unrun. |
| Crash-safe FIFO | Delegated | Unrun. |

Separate live checks on this candidate verified the exact Luna/Low directive,
the Sol/High missing-key fallback, and the completed-turn rewrite. The rewrite
linked the prior turn, made zero new classifier calls and started zero children.
It returned two sentences when asked for one. Record that as an answer-quality
miss. The earlier Sol/High explicit-preference result is historical live
evidence. Replayed negative cases are offline evidence. These checks do not add
independent tasks to the matrix.

Keep evidence tied to its tested commit and runtime. For a documentation-only
revision, carry forward runtime evidence only after verifying the executable
payload, hook definitions and runtime settings relevant to that evidence match.
Validate the final publication artefact on its own commit.

### Run the five unrun cases

Use the same private Terminal and disposable, authenticated Luna/Low CLI with
the corrected candidate selected and its five hooks trusted. Before starting
the CLI in that Terminal, check only whether the classifier variable is present
and exported. This check never prints its value:

```sh
python3 -c 'import os, sys; present = bool(os.getenv("AUTOROUTER_OPENAI_API_KEY")); print("Classifier key present" if present else "Classifier key absent"); sys.exit(0 if present else 1)'
```

If absent, stop. Use the [private CLI credential procedure](TRIAL.md#desktop-credential-availability)
to load it. Verify included Personal credit is still available and paid funding
is disabled. Launch the same disposable profile from that Terminal with
`--no-daemon`. Confirm API classification is enabled and native agents are
permitted. Send the following prompts verbatim in order, waiting until the CLI
is idle after each. Each prompt is one independent turn.

1. **Direct**

   > Convert 37 minutes to seconds. Reply with the number only.

2. **Direct**

   > Sort `pear, apple, plum` alphabetically. Reply with the comma-separated list only.

3. **Direct**

   > Extract the ISO date from `dispatch settled on 2026-03-14 at noon`. Reply with the date only.

4. **Delegated**

   > Explain an online directed-graph cycle detector that maintains a topological order after each edge insertion. Give pseudocode for the affected-region search and reorder, justify the invariant and bounds, and walk through an insertion that requires a reorder and one that creates a cycle. Chat only, no file edits.

5. **Delegated**

   > Explain a crash-safe durable FIFO on a single disk using a write-ahead log. Define enqueue acknowledgement and dequeue acknowledgement, give recovery pseudocode, and walk through torn-tail and crash-after-delivery-before-ack cases. State the guarantees and limits. Chat only, no file edits.

Keep the recorded route expectations. Do not add model directives, replay a
failed task or repeat a completed one. Record each session and turn, root
model/effort, classifier selection and calls, observed child and its lifecycle,
ledger outcome, latency and token usage where available. Score the answer
separately. Stop on a credential, trust or safety error and preserve the record.

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
