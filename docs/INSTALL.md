# Installation and lifecycle

This page covers the supported plugin path for Desktop and CLI. Autorouter routes through Codex's direct child capability; the bundled custom-agent TOMLs are not required. For a surface without plugin support, use [Standalone advisory mode](STANDALONE.md).

## Select the cheap root once

Select **GPT-5.6 Luna** in Codex Desktop before starting a new task. For a personal CLI default, use top-level Codex configuration:

```toml
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
```

Low is the preferred initial effort, not an immutable requirement. If controlled acceptance shows that Luna Low cannot reliably follow routing instructions, create bounded child contracts, or synthesise escalated results, compare Luna Low with Luna Medium before changing the recommendation.

This is a user-controlled one-time selection. Autorouter never edits global/root model configuration, and install, update, activate, deactivate, repair, and uninstall never claim to configure Luna.

## Install the immutable reviewed release

After the reviewed `v0.2.0` tag exists:

```bash
codex plugin marketplace add anthonypaddison/Codex-Autorouter --ref v0.2.0
codex plugin add gpt-5-6-router@codex-autorouter
```

Do not substitute `main`: a moving branch does not identify the reviewed bytes. Start a new task after installation or update so Codex reloads plugin skills and hooks.

## Trust the bundled hooks and check health

Open `/hooks`, inspect the five lifecycle entries, and trust the exact current definitions. Installation and enablement do not imply trust. Each command must execute only the router under its own `${PLUGIN_ROOT}` or `%PLUGIN_ROOT%`; it must not search sibling caches or contain a publisher source-machine path.

From the exact installed plugin root, run:

```bash
python3 scripts/check_hooks.py
```

The combined check reports:

- `READY` when the latest actual turn observed Luna and a capability receipt proves a genuine successful Terra or Sol escalation against the same plugin and observable Codex runtime/build;
- `DEGRADED` when Autorouter works but the observed root is not Luna, the runtime/build changed, or current escalation capability is not yet proven; a non-Luna root substantially reduces credit-saving behaviour;
- `ADVISORY` when hooks or the supported direct child path cannot enforce the complete contract.

`UserPromptSubmit.model` is authoritative for the active root on every actual turn. App Server and config evidence may support health reporting but cannot override it. The receipt binds, where observable, plugin version, Codex runtime/build, Desktop or CLI host type, platform, observed child model, effort intent, capability/schema signature, and timestamp. A runtime/build change invalidates `READY` until normal work produces a fresh successful receipt. The check never launches an automatic paid probe.

## Routing preference

Balanced is used when no preference has been stored. To select or inspect the persistent profile:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile token-saver
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile balanced
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile max-quality
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile
```

The preference is stored under `CODEX_HOME/gpt-5-6-router`, survives plugin replacement, and applies to the next new task. It does not modify the active model, root effort, or Fast/Standard setting.

## Optional legacy custom agents

Normal installation and activation do not install custom-agent TOMLs. Their absence is expected and does not cause `DEGRADED`. The files remain available only for compatibility testing or an intentionally selected older host path.

To enter that mode explicitly after reviewing every definition:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py activate --legacy-agents
python3 skills/route-gpt-5-6-work/scripts/routerctl.py status
```

Legacy ownership conflicts fail closed. `--replace-conflicts` is available only with an explicit legacy activation after reviewing the original and bundled definitions. `deactivate`, `repair`, and modified-file preservation apply only to files previously managed through this legacy path. Legacy state never contributes to supported-path readiness.

## Update

1. Install the new reviewed immutable marketplace version.
2. Start a new task.
3. Review and trust any changed hook definitions in `/hooks`.
4. Run `python3 scripts/check_hooks.py`.
5. Expect `DEGRADED` after an observable runtime/build change until a genuine paid escalation occurs during normal or controlled acceptance work; do not probe automatically.

No lifecycle step changes the user-selected Luna root. If legacy agents were never explicitly enabled, there is nothing to activate, repair, or deactivate.

## Uninstall

Optionally purge routing ledgers, then remove the plugin:

```bash
python3 skills/route-gpt-5-6-work/scripts/router_hook.py --purge-ledgers
codex plugin remove gpt-5-6-router
```

If explicit legacy mode was used, deactivate its owned files before plugin removal:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py deactivate
```

If a legacy managed definition was edited, deactivation refuses to discard it. Use `deactivate --keep-modified` only when you intentionally preserve that file and relinquish ownership. Plugin removal disables plugin-native hooks but does not change the global/root model selection. See [Local routing data and privacy](PRIVACY.md) for ledger retention.
