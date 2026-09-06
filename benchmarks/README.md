# Autorouter Arena

Autorouter Arena is a controlled benchmark for the part unit tests cannot
prove: whether Autorouter changes execution in a useful way.

It measures three layers independently:

1. **Outcome quality** — deterministic graders run against frozen task fixtures.
2. **Routing behavior** — the router ledger is checked for the expected route,
   orchestration shape, bounded depth, and worker coverage.
3. **Efficiency** — Codex JSON events provide wall time and token usage for the
   baseline, Token Saver, Balanced, and Max Quality runs.
4. **Outsider review** — the same separated GLM 5.2 + DeepSeek V4 Pro panel used
   by Spark Loops can privately review randomized, output-only artifacts.

The suite deliberately includes work where different behavior should emerge:

| Case | Capability under test | Expected Autorouter behavior |
|---|---|---|
| `locale_batch` | repeated, objectively checked transformation | two Luna leaves |
| `webhook_race` | ambiguous concurrency debugging | Terra High unless the root already satisfies it |
| `sqlite_migration` | reversible, expensive-to-get-wrong ownership | Sol ownership and migration/rollback evidence |
| `parallel_audit` | independent security, accessibility, and data review | Terra evidence followed by one Sol owner |

Route-only probes also exercise ordinary implementation, unclear multi-area
work, protected security floors, profile changes, high-volume delegation,
explicit Astra Medium selection, and Astra keyword-noise rejection.

## Start with a zero-cost route audit

```bash
python3 benchmarks/autorouter_bench.py route-audit
```

This calls the checked-in classifier directly. It does not call a model or
spend tokens.

## Prepare inspectable fixtures

```bash
python3 benchmarks/autorouter_bench.py prepare --output /tmp/autorouter-arena
```

Every case gets a clean starter repository, a `TASK.md`, and a deterministic
grader. You can open any fixture in Codex and run the task manually.

## Run the four controlled arms

Real runs spend model tokens and execute Codex. They require both explicit
flags so the cost and reviewed-hook bypass are never accidental:

```bash
python3 benchmarks/autorouter_bench.py run \
  --output /tmp/autorouter-arena \
  --execute \
  --trust-reviewed-hooks
```

The baseline keeps the same root model, effort, and service tier but disables
the Autorouter plugin and ignores routing rules. The other three arms set Token
Saver, Balanced, and Max Quality in turn. Each arm starts from a fresh copy of
the same fixture, run order rotates across repetitions, and the user's original
Autorouter profile is restored even if the run fails.

Defaults match the release test environment (`gpt-5.6-sol`, `high`,
`priority`). Override them only when comparing another controlled root:

```bash
python3 benchmarks/autorouter_bench.py run \
  --output /tmp/autorouter-arena \
  --execute --trust-reviewed-hooks \
  --root-model gpt-5.6-terra --root-effort medium --service-tier default
```

Run one case while iterating:

```bash
python3 benchmarks/autorouter_bench.py run \
  --output /tmp/autorouter-arena \
  --case locale_batch \
  --execute --trust-reviewed-hooks
```

## Run the private outsider panel

This is development tooling only. It is not installed as an Autorouter runtime
gate and users never need it. After the four arms finish, configure the same
active outside seats used by Spark Loops and run:

```bash
export ZAI_API_KEY=...
export DEEPSEEK_API_KEY=...

python3 benchmarks/autorouter_bench.py review \
  --output /tmp/autorouter-arena \
  --execute \
  --acknowledge-external-review-cost
```

On the same Mac used by Spark Loops, the benchmark can reuse its existing
reviewer credentials without printing or copying them into the repository:

```bash
python3 benchmarks/autorouter_bench.py review \
  --output /tmp/autorouter-arena \
  --execute \
  --acknowledge-external-review-cost \
  --reuse-spark-provider-keys
```

That explicit flag checks Spark Loops' macOS Keychain service first and its
permission-restricted `~/.spark/.env` fallback second. Keys are held only in
memory for their matching provider request and are never written to reports.

Each reviewer receives opaque artifact ids, the task, deterministic check
results, the candidate patch, and the candidate's final response. It does not
receive model names, Autorouter profiles, routes, tokens, latency, or the blind
mapping. The mapping is applied only after both reviewers return.

A panel is official only at full `2/2` quorum. Partial or malformed panels are
saved as diagnostic evidence and cannot declare a winner. Reviewer feedback is
repair input for us; it never automatically mutates or promotes routing policy.

## Read the result

`report.md` and `report.json` are written under the output directory. A useful
Autorouter result requires more than passing tasks:

- quality is equal to or better than baseline;
- routing behavior matches the case contract;
- total tokens or elapsed time improve on cheaper/batch cases; and
- deeper orchestration improves coverage on consequential cases enough to
  justify its overhead.

Do not treat one run as a model ranking. Run at least three repetitions before
making cost or quality claims. The CLI records raw evidence so medians can be
computed without relying on screenshots or memory.

## Safety and limitations

- `--trust-reviewed-hooks` passes Codex's hook-trust bypass only for the
  isolated benchmark subprocess. Review the installed Autorouter hooks first.
- Outsider review sends candidate patches and responses to Z.AI and DeepSeek.
  Use only benchmark fixtures or code you are authorized to share with those
  providers. The command refuses to run without explicit cost acknowledgement
  and both provider keys.
- Tasks run with `workspace-write` inside generated fixture directories.
- Token totals depend on what the installed Codex JSON stream exposes. Missing
  usage is reported as unavailable, never estimated.
- Dollar cost is intentionally omitted. Token and service-tier evidence remain
  comparable without baking changing prices into the repository.
- A skill cannot replace the already-running root model. The benchmark makes
  this visible: savings on a Sol root must come from useful bounded delegation,
  not from claiming the root silently became Terra or Luna.
