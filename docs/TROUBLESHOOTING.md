# Troubleshooting

## Status says `ADVISORY`

Run `routerctl.py status` and inspect these fields:

- `agents_active`: run explicit activation after reviewing the definitions.
- `agent_conflicts`: preserve or resolve local edits; the router will not overwrite them silently.
- `original_backup_conflicts`: restore the private activation backup before upgrade or deactivation; the router will not discard ownership without it.
- `activation_update_required`: rerun `activate` after a plugin or bundled-agent update.
- `bundled_agent_drift`: rerun `activate` after reviewing changed bundled definitions.
- `hooks_enabled_by_local_config`: enable Codex lifecycle hooks if local policy allows.
- `multi_agent_enabled_by_local_config`: enable multi-agent support if local policy allows.
- `local_agent_depth_allows_children`: use an agent depth of at least one.
- `hook_trust`: always `UNVERIFIED` from the filesystem helper; confirm in `/hooks`.

These fields reflect local files only, not the final merged value after administrator profiles, project settings, or command-line overrides.

## The wrong cost/quality profile is active

Run `routerctl.py profile`. A missing setting safely reports Balanced; an invalid or linked file reports `invalid_default` and also falls back to Balanced. Re-save a valid value with `routerctl.py profile token-saver`, `balanced`, or `max-quality`. The change begins on the next new task, not an in-flight continuation, and does not change Fast/Standard.

Run `python3 scripts/check_hooks.py` from the plugin root for an authoritative app-server trust probe.

## Status says `MANAGED_BLOCKED`

An organization requirement allows only managed hooks. A user-installed plugin cannot override this. Use advisory mode or ask the administrator to distribute an approved managed hook.

## Activation reports a conflict

Do not delete the file reflexively. Compare it with the bundled definition. If it is foreign and you intentionally want the plugin to manage it, use `activate --replace-conflicts`; the original is retained for deactivation. If it is a locally edited managed file, preserve it and decide whether to deactivate with `--keep-modified`.

## A lifecycle command was interrupted

Run `routerctl.py status` or `repair`. The next command acquires the activation lock and rolls back any transaction left in `PREPARED` or `COMMITTING` state before continuing.

## Route labels show an unexpected speed

The hook contract does not currently expose a guaranteed per-task UI Fast field. The router prefers a hook-supplied tier when present and otherwise reports persisted configuration. The router never toggles Fast itself.

## Hooks do not run

Confirm that the plugin is installed and enabled, hooks are enabled, the project is trusted where project configuration matters, and the exact plugin hook definition is trusted in `/hooks`. Managed policy can suppress plugin hooks even when files are present.

## Completion feedback repeats after an update

Tasks created by builds before the stale-cache launcher fix can retain a command resolved to that build's deleted cache directory. The entries under `[hooks.state]` in `config.toml` are trust records keyed by plugin and hook position; their presence is expected and does not identify the active task's resolved command.

Update the plugin, review and trust the changed hook definitions, and open a fresh task once. Do not delete trust state or disable completion gates globally. Tasks created by the fixed build use a self-contained launcher that discovers the newest installed router hook when a later cache replacement removes their original version. If no valid cache exists, the launcher reports the condition once and then fails open without recursively continuing the task.

Within the router, completion feedback is carried into at most one verification continuation. Successful verification—including package scripts such as `pnpm verify:fast`—settles the carried mutation generation. An unmet second Stop records `FAILED_OPEN` without injecting another message, and duplicate Stop delivery against `COMPLETE` or `FAILED_OPEN` is a no-op.

## Standalone install or recovery refuses a tree

Do not delete the target, stage, quarantine, ownership manifest, or pending transaction reflexively. The standalone lifecycle fails closed for foreign content, path or mode drift, links, corrupt state, and post-crash edits. Preserve the reported paths and compare them with the release inventory. Use the durable controller printed by `install` if the original archive is gone. Standalone mode never qualifies as full plugin mode.
