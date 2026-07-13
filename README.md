# GPT-5.6 Router for Codex

GPT-5.6 Router profiles each Codex task and chooses the least expensive GPT-5.6 route likely to produce a verified result. It distinguishes Sol, Terra, and Luna work; selects low, medium, or high configured reasoning effort; and uses bounded depth-1 subagents only when delegation repays its overhead.

> **Public release pending:** macOS CLI acceptance now passes on the exact installed candidate, including a native custom-agent delegation with zero routing violations. Ubuntu, native Windows, remaining real-host rows, and a tested private vulnerability-reporting channel are still required before a public-stable declaration. See [release evidence](docs/RELEASE_EVIDENCE.md).

The installed skill is namespaced as `$gpt-5-6-router:route-gpt-5-6-work`.

## What it does

- Keeps small, single-path work in the current agent.
- Uses Luna only for narrow, repetitive work with cheap objective verification.
- Uses Terra for cost-efficient implementation, exploration, analysis, and ambiguous debugging.
- Uses Sol for architecture, migrations, demanding synthesis, consequential changes, and critical review.
- Understands product strategy, requirements, UX, frontend, backend, data, mobile, AI, integrations, payments, QA, analytics, growth, accessibility, localization, DevOps, reliability, security, privacy, performance, and maintenance.
- Preserves the configured speed tier without silently enabling Fast.
- Requires routed agents, coverage, configuration intent, and post-mutation verification before completion.

## Installation

Install the plugin from its marketplace in Codex Desktop or CLI, start a new Codex task, and review the bundled commands in `/hooks`. Codex intentionally does not trust plugin hooks merely because a plugin was installed. Codex IDE extensions do not currently support plugins, so the release provides a conflict-safe [standalone advisory mode](docs/STANDALONE.md) instead of pretending full plugin enforcement exists there.

Custom-agent definitions are not currently a documented native plugin component. After reviewing the five bundled definitions, activate them explicitly:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py status
python3 skills/route-gpt-5-6-work/scripts/routerctl.py activate
python3 scripts/check_hooks.py
```

Record the `Installed plugin root` printed by `codex plugin add`, then run those commands there; `codex plugin list` verifies the installed version but may display the marketplace source path instead of the cache. Python 3.10 or newer is required. See [Installation and lifecycle](docs/INSTALL.md) for full marketplace, trust, upgrade, repair, and uninstall steps.

## Honest operating modes

- `ADVISORY` with `local_agent_ready: true`: agent definitions are ready, but a filesystem helper cannot prove that Codex discovered or trusted this exact plugin build.
- `scripts/check_hooks.py` proves static installation readiness: effective app-server configuration, exact skill discovery, hook trust, and five active current agent files. A successful non-current live delegated ledger is still mandatory before release.
- `ADVISORY`: the skill can advise and work in the current agent, but one or more enforcement or delegation requirements are unavailable.
- `MANAGED_BLOCKED`: organization policy permits only managed hooks, so plugin hooks cannot enforce the route.

`Fast` or `Standard` appears only when Codex supplies the tier to the hook or persisted configuration reports it; otherwise the label says `Speed unknown`. The effort word in labels such as `Terra High Standard` is route/configuration intent, not a live runtime attestation. See [Known limitations](docs/LIMITATIONS.md).

## Safety

The plugin never edits global `hooks.json`. Codex owns plugin enablement and hooks. `routerctl` manages only five allowlisted `gpt56_*.toml` files, using a private ownership manifest, write-ahead transaction, checksums, atomic replacement, rollback, and recovery at tested transaction boundaries. It refuses foreign or locally modified definitions unless the user chooses an explicit conflict-preserving command.

Routing ledgers contain no prompt content or prompt-derived hashes and have a lock-safe manual purge command. See [Local routing data and privacy](docs/PRIVACY.md).

## Development

```bash
python3 scripts/validate_release.py
cd skills/route-gpt-5-6-work/scripts
python3 -m unittest -v test_router test_routerctl
```

The release gate and real-host matrix are documented in [Release checklist](docs/RELEASE_CHECKLIST.md), the exact manual and CLI procedure is in [Real-host acceptance](docs/HOST_ACCEPTANCE.md), and candidate-specific results are recorded in [Release evidence](docs/RELEASE_EVIDENCE.md).
