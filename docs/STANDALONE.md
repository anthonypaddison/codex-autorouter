# Standalone advisory mode

Some IDE and non-plugin surfaces can discover a standalone skill but do not load plugin lifecycle hooks. Standalone mode is therefore structurally `ADVISORY`: it can provide routing instructions and use the central direct-child compatibility adapter when the host exposes a supported spawn capability, but it cannot attest hook-enforced completion or earn plugin `READY` health.

Select Luna once in the host UI or personal top-level Codex configuration before starting a task:

```toml
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
```

Standalone lifecycle commands never make or claim this root-model change. If a prompt hook is available on a future standalone host, `UserPromptSubmit.model` remains authoritative for the actual turn; static config evidence does not override it.

## Install

From an extracted immutable release archive:

```bash
python3 scripts/standalonectl.py status
python3 scripts/standalonectl.py install
```

The installer refuses any unowned `CODEX_HOME/skills/route-gpt-5-6-work`, even if its bytes happen to match. It records an exact recursive inventory of paths, hashes, and modes; uses same-filesystem staging, an external durable transaction, atomic renames, and recovery; and never changes permissions on an existing `CODEX_HOME` or `skills` directory.

Successful installation prints a durable controller path under `CODEX_HOME/plugin-data/gpt-5-6-router/standalone/controllers`. Keep that path for status, updates, and uninstall. Start a new task after installation so the standalone skill is discovered as `$route-gpt-5-6-work`.

The supported routing instructions use the central compatibility boundary for direct Terra or Sol child spawning. Capability and fallback assumptions must not be duplicated in standalone instructions. Because plugin hooks are absent, `scripts/check_hooks.py` cannot promote standalone mode to `READY`; it must remain truthful about `ADVISORY` capability.

## Optional explicit legacy mode

Bundled custom-agent TOMLs are obsolete compatibility material. Their absence is expected and does not degrade standalone advisory mode. Normal standalone installation does not install or activate them.

Only when intentionally testing an older custom-agent host path, review the definitions and run:

```bash
python3 "$CODEX_HOME/skills/route-gpt-5-6-work/scripts/routerctl.py" activate --legacy-agents
python3 "$CODEX_HOME/skills/route-gpt-5-6-work/scripts/routerctl.py" status
```

Legacy activation cannot make standalone mode `READY` and does not prove Terra/Sol direct-spawn capability.

## Update

Run `python3 scripts/standalonectl.py install` from the new extracted release. Exact-owned installations update transactionally. Any modified, missing, extra, linked, special, case-colliding, or mode-drifted content is preserved and causes a fail-closed error. No update step changes root model configuration or performs a paid capability probe.

## Uninstall and purge

If and only if explicit legacy mode was used, deactivate its owned custom-agent files first:

```bash
python3 "$CODEX_HOME/skills/route-gpt-5-6-work/scripts/routerctl.py" deactivate
```

Then use either the new archive or the durable controller printed during installation:

```bash
python3 /path/to/durable/standalonectl.py uninstall
```

`uninstall` removes only an exact-owned skill tree and retains versioned durable controllers so interrupted recovery remains possible. After status is inactive and the target is absent, run `purge` from a trusted extracted release, not from the controller being removed:

```bash
python3 /path/to/extracted-release/scripts/standalonectl.py purge
```

The purge remains serialized by a small private state marker and lock. Do not manually delete transaction state while an install, update, or uninstall is pending. A post-crash edit is preserved and blocks automated recovery instead of being discarded. Uninstall and purge leave the user-selected root model untouched.
