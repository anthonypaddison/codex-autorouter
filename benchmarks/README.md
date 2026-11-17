# Autorouter Arena — offline tools and restricted review

## Live execution and grading are disabled

`run` always returns nonzero, even with `--execute --trust-reviewed-hooks`.
Single-run execution and `_grade` also refuse. No hook-trust bypass, profile
change, Codex inference or host-Python grading occurs through that command.

Previously model-written `benchmark_grader.py` and imported application code ran
with unrestricted host Python after sandboxed generation. A grader hash cannot
isolate imports. This workflow stays disabled until an enforced grading sandbox
is implemented and reviewed. Do not manually execute a grader or its imports
after a model has modified the workspace.

## Non-billable tools

From the repository root:

```sh
python3 -B benchmarks/autorouter_bench.py route-audit --strict
python3 -B -m unittest -v benchmarks.test_autorouter_bench
python3 -B benchmarks/autorouter_bench.py prepare --output /tmp/autorouter-arena
```

The route audit checks ten **legacy deterministic** contracts. The separate
`test_ai_routing` suite uses mocked API responses for configured allowlisting,
transport, deduplication, fallback and telemetry. Neither measures real classifier
quality, unnecessary escalation, latency or savings.

Preparation writes inspectable fixtures and trusted initial grader source, not
model results. Tests execute only freshly generated repository-defined fixture
graders in temporary directories before any model changes; live grading is disabled.

## Output ownership and cleanup

Use a new empty directory outside this repository. Preparation creates
`.autorouter-arena.json`, binding ownership to its canonical path. Reuse/cleanup
requires that exact marker:

```sh
python3 -B benchmarks/autorouter_bench.py prepare --output /tmp/autorouter-arena --clean
```

Cleanup deletes/recreates only positively owned output. Home, filesystem/repository
roots and their ancestors, repository subdirectories, nonempty unowned paths,
copied markers, traversal and linked paths are refused. Fixed macOS `/tmp` and
`/var` system aliases are canonicalised; user-created links are refused. Old output
without a marker is not adopted or deleted: use a new directory.

Workspace/review operations require POSIX descriptor-relative no-follow access.
Windows is intentionally unsupported for these optional tools; router Windows
compatibility tests remain separate. Route auditing and pure parser/report tests
do not require this filesystem capability.

## Optional external review of existing authorised artifacts

Review is optional development tooling, not installation or a runtime/release gate.
It requires `--execute`, `--acknowledge-external-review-cost`, both provider keys,
and permission to share selected fixture contents with Z.AI and DeepSeek. This
version does not generate new live benchmark results.

For existing owned output with `report.json`, the reader validates each exact
`runs/repeat-N/ARM/CASE/workspace`. It bounds report, task, final response and file
snapshot reads; rejects linked files/directories, traversal and substituted
workspaces; and refuses unsupported platforms. It never runs workspace Git
configuration, filters or hooks. The compatible `candidate_patch` packet key now
contains a bounded regular-file snapshot, **not a Git diff**.

Missing optional text is empty; inaccessible snapshot entries abort review rather
than claiming complete evidence. Depth, entry count and output size are bounded.
Only authorised non-sensitive fixtures belong here: no path checker detects
secrets deliberately placed in regular files. The optional machine-specific
`--reuse-spark-provider-keys` flag explicitly accesses another application's local
credentials; it is not required for review or normal router setup.

Reviewers receive opaque artifact IDs, task/check data, snapshots and final
responses, not model/profile labels, tokens, elapsed time or blind mappings.
Full panel quorum is required for official scores. Historical deterministic checks
are report assertions, not newly executed grading. Feedback never changes source,
policy or installation.

## Interpreting historical reports

Keep quality, planned routing, actual children, tokens and elapsed time separate.
Missing usage is unknown, not zero; cached input is already included in input.
A rate-card comparison does not establish causal savings or subscription debit.
One accepted task is execution evidence, not a workload benchmark or guarantee.
