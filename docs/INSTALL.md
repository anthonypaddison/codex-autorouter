# Installation and lifecycle

This page covers full plugin mode for Desktop and CLI. For IDE extensions or another surface without plugin support, use [Standalone advisory mode](STANDALONE.md).

## Install from a marketplace

```bash
codex plugin add gpt-5-6-router@<marketplace>
```

Start a new task after installation or update so Codex reloads plugin skills and hooks.

## Trust the bundled hooks

Open `/hooks`, inspect the five lifecycle entries, and trust the exact current definitions. Installation and enablement do not imply trust. The commands must resolve through `${PLUGIN_ROOT}` or `%PLUGIN_ROOT%`; they must not contain the publisher's source-machine path.

After review, query Codex's authoritative discovered-hook state:

```bash
python3 scripts/check_hooks.py
```

The check passes only when the namespaced plugin skill and the exact five plugin hooks are discovered from the installed cache, enabled, trusted, warning-free, and error-free. It also reads Codex's effective merged configuration and requirements through app-server and refuses readiness when the plugin or hooks are disabled, multi-agent work or child depth is unavailable, or managed-hooks-only policy blocks user plugin hooks.

## Activate custom agents

Use the `Installed plugin root` printed by `codex plugin add`, change into that version directory, and verify that it contains `.codex-plugin/plugin.json`. `codex plugin list` is useful for checking the installed version, but its `PATH` column may identify the marketplace source rather than the installed cache. Then run:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py status
python3 skills/route-gpt-5-6-work/scripts/routerctl.py activate
python3 skills/route-gpt-5-6-work/scripts/routerctl.py status
```

Review conflicts before using `activate --replace-conflicts`. That flag snapshots the original definitions and restores them during clean deactivation.

`routerctl status` always remains `ADVISORY` outside managed blocking, even when `local_agent_ready` is true: an extracted archive and an installed plugin can have the same filesystem shape. Only `scripts/check_hooks.py` may report full readiness after it binds app-server discovery, hook trust, and five active current agent definitions to the exact checker build.

## Repair

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py repair
```

Repair recreates missing owned files only when the bundled checksum matches the active version. It refuses locally modified files and will not silently resolve ownership conflicts.

## Update

1. Update or reinstall the plugin from the marketplace.
2. Start a new task.
3. Review and trust changed hooks in `/hooks`.
4. Run `routerctl.py activate` again. Upgrade proceeds only when every currently managed file still matches its recorded installed hash.
5. Run `routerctl.py status` and the smoke prompts in the release checklist.

## Uninstall

Deactivate external custom-agent files before removing the plugin:

```bash
python3 skills/route-gpt-5-6-work/scripts/router_hook.py --purge-ledgers
python3 skills/route-gpt-5-6-work/scripts/routerctl.py deactivate
codex plugin remove gpt-5-6-router
```

If a managed definition was edited, normal deactivation refuses. Use `deactivate --keep-modified` only when you intentionally want to preserve that file and relinquish plugin ownership.

Plugin removal disables plugin-native hooks. Orphaned custom-agent TOMLs are inert unless another workflow explicitly spawns their names, but clean deactivation remains the supported uninstall path.

The ledger purge is optional but is the supported way to remove routing metadata immediately rather than waiting for opportunistic age cleanup. See [Local routing data and privacy](PRIVACY.md).

If the plugin was removed first by mistake, reinstall the same candidate version from the same marketplace, run `routerctl.py deactivate`, confirm the owned agents are gone or restored, and then remove the plugin again. Do not install a different candidate over orphaned ownership state as a recovery shortcut.
