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

Within the current router, Stop and SubagentStop never hard-block. Successful observable verification—including package scripts such as `pnpm verify:fast` and tests executed through nested Codex orchestration—settles the current mutation generation. If a nominally read-only turn later mutates files, its recorded gate is promoted from `answer check` to targeted tests or a build. When Codex's incomplete unified-exec interception omits the result, when verification fails, or when orchestration is incomplete, the ledger records `FAILED_OPEN` with root verification still required; it does not pretend the check passed or inject a replayable user message. XML-wrapped feedback from an older build is recognized and discarded rather than reclassified as a new user task, and duplicate Stop delivery against either terminal state is a no-op.

If an older build already poisoned the persisted transcript, first close the affected task. Then run one of:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py sanitize --session /absolute/path/to/session.jsonl
python3 skills/route-gpt-5-6-work/scripts/routerctl.py sanitize --all
```

The command reports counts and backup paths without printing prompt contents. It removes a message only when it is a UUIDv7-tagged user message containing only `<hook_prompt>` feedback; for mixed legitimate content, it preserves the message and removes only the invalid ID. It also repairs nested `compacted.replacement_history`, leaves unrelated tool output untouched, refuses links/hard links, fails closed on invalid JSONL, and writes nothing when no match exists. Reopen the task after repair. A task whose transcript is already loaded must be closed and reopened; no plugin hook can reliably rewrite that live request history.

## Standalone install or recovery refuses a tree

Do not delete the target, stage, quarantine, ownership manifest, or pending transaction reflexively. The standalone lifecycle fails closed for foreign content, path or mode drift, links, corrupt state, and post-crash edits. Preserve the reported paths and compare them with the release inventory. Use the durable controller printed by `install` if the original archive is gone. Standalone mode never qualifies as full plugin mode.
