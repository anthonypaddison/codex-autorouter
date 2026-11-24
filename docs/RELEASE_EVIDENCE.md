# v0.3.0 release evidence

Status: **public prerelease for a limited normal-use trial**. The recorded live
test predates the published payload. See [v1.0.0 release gates](STABLE_READINESS.md)
for the current publication decision.

## Source baseline and scope

The publication audit reviewed `9bd875ca91e5a2c572d3542193f1f659d7554437` on
`ap-configurable-ai-routing`. Identify its subsequent publication-correction
commit using `git rev-parse HEAD`; version 0.3.0 alone is not payload identity.

Configured mode uses one bounded OpenAI API classification, exact user-approved
executor pairs, an approved fallback and native Codex delegation. Exact root
matches stay direct. Legacy deterministic GPT-6 policy and compatibility assets
remain separate regression coverage, not evidence of AI-classifier quality.

## Recorded live evidence — earlier installed payload only

[TRIAL.md](TRIAL.md) records limited macOS CLI acceptance of payload
`sha256:46a2e7837fad421bc95ee545de509fadb9f4534162267735f6fa5dfa20754448`:

- Luna/Low root; one automatic classification selected Terra/Medium.
- One native-accepted child started and completed, returned 10, and matched its
  lifecycle/attestation with zero violations.
- Classifier latency 5.642154 seconds; task duration 25.440 seconds.
- Classifier usage 299 input and 186 output tokens; cached input zero.
- No authoritative API dollar debit or causal cost-saving comparison.

Later timeout/setup and publication-security changes are offline-tested, not
installed or covered by another live acceptance. This evidence does not prove
Desktop credential inheritance, arbitrary-model entitlement, other hosts,
workload-wide quality or savings. Missing runtime/build identity still limits
global capability-receipt claims.

## Publication-security corrections

- Live benchmark run, single-run execution and grading fail closed before model
  calls or workspace Python execution. Grader hashes are not isolation.
- Review packets read bounded regular files from the exact owned run. Links,
  traversal and substituted workspaces are rejected; no workspace Git commands
  execute. POSIX no-follow access is required for workspace/review operations.
- Cleanup requires a marker bound to a benchmark-created output directory.
  Protected roots, foreign directories and linked paths are refused.
- Local credentials, acceptance settings and telemetry are ignored, not deleted.
  MIT/Alchemist attribution remains; legacy screenshots are retained as source
  assets but no longer advertised as configured AI mode.

The exact reviewed commit must pass all CI-defined offline tests, the strict
10-contract route audit, 5,000-case fuzz and release validation. Current command
results belong in the delivery report. Hosted CI cannot be inferred from local
tests. CI targets Python 3.10–3.14 on macOS/Linux/Windows; POSIX-only benchmark
workspace tests explicitly skip unsupported Windows operations.

## Historical evidence and history publication

Earlier v0.1/v0.2 policy, custom-agent and release-planning evidence remains in Git
history; it does not prove configured v0.3.0 execution. The audit found no confirmed
credentials in reachable history; scanner matches were synthetic test route/event
identifiers. Commit author identities remain public metadata if history is
published. Review those deliberately. Old commits retain the benchmark defects:
do not distribute an older branch/tag as the corrected release.

## Still required before publication

1. Review the corrected commit and obtain hosted CI for those exact bytes.
2. Enable and test GitHub private vulnerability reporting before public
   installation; see [SECURITY.md](../SECURITY.md).
3. Under separate approval, create/publish an immutable reviewed tag, validate its
   archive in a clean checkout, record/verify SHA256, and check marketplace and
   privacy URLs resolve to it.
4. Label the distribution as a limited trial. Keep unverified environments
   unverified until separately authorised real-host evidence exists.
