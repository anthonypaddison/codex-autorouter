# Standalone advisory mode

Codex IDE extensions do not currently load plugins. The release therefore includes a standalone skill lifecycle for IDE and other non-plugin surfaces. Standalone mode can provide the routing instructions and the five reviewed custom-agent roles, but it has no plugin lifecycle hooks and is structurally restricted to `ADVISORY`.

## Install

From an extracted release archive:

```bash
python3 scripts/standalonectl.py status
python3 scripts/standalonectl.py install
```

The installer refuses any unowned `CODEX_HOME/skills/route-gpt-5-6-work`, even if its bytes happen to match. It records an exact recursive inventory of paths, hashes, and modes; uses same-filesystem staging, an external durable transaction, atomic renames, and recovery; and never changes the permissions of an existing `CODEX_HOME` or `skills` directory.

Successful installation prints a durable controller path under `CODEX_HOME/plugin-data/gpt-5-6-router/standalone/controllers`. Keep that path for status, updates, and uninstall. It continues to work after the downloaded archive or plugin cache is removed.

Start a new Codex task after installation so the standalone skill is discovered as `$route-gpt-5-6-work`.

## Optional custom agents

Activate the reviewed roles from the installed skill:

```bash
python3 "$CODEX_HOME/skills/route-gpt-5-6-work/scripts/routerctl.py" activate
python3 "$CODEX_HOME/skills/route-gpt-5-6-work/scripts/routerctl.py" status
```

Standalone `routerctl status` always reports `ADVISORY` and `STANDALONE_ADVISORY`, even when all custom agents are active. Without trusted plugin hooks, routing and completion gates are instruction-driven rather than lifecycle-enforced.

## Update

Run `python3 scripts/standalonectl.py install` from the new extracted release. Exact-owned installations update transactionally. Any modified, missing, extra, linked, special, case-colliding, or mode-drifted content is preserved and causes a fail-closed error.

## Uninstall and purge

Deactivate custom agents first, then use either the new archive or the durable controller printed during installation:

```bash
python3 "$CODEX_HOME/skills/route-gpt-5-6-work/scripts/routerctl.py" deactivate
python3 /path/to/durable/standalonectl.py uninstall
```

`uninstall` removes only an exact-owned skill tree. It deliberately retains versioned durable controllers so interrupted lifecycle recovery remains possible. After status is inactive and the target is absent, run `purge` from a trusted extracted release—not from the durable controller being removed—to validate and remove those controller copies:

```bash
python3 /path/to/extracted-release/scripts/standalonectl.py purge
```

The purge remains serialized by a small private state marker and lock; those tiny files may remain so later lifecycle commands cannot race a cleanup. Do not manually delete transaction state while an install, update, or uninstall is pending. A post-crash edit is preserved and blocks automated recovery instead of being discarded.
