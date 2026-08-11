# Troubleshooting

## Run the health check

From the exact installed plugin root, run:

```bash
python3 scripts/check_hooks.py
```

- `READY` means the latest actual parent turn observed a Luna root and a current capability receipt proves a genuine successful Terra or Sol escalation, with all observable host identity matching.
- `DEGRADED` means Autorouter can still operate but the active root is not Luna, the runtime/build changed, or current escalation capability has not yet been proven. A non-Luna root substantially reduces credit-saving behaviour.
- `UNAVAILABLE` means the supported hook or direct child-routing path cannot operate.

`UserPromptSubmit.model` is the authoritative active root for every actual turn. App Server and config evidence may explain the report, but cannot override the hook's active-model evidence.

If the root is not Luna, select GPT-5.6 Luna in Desktop before starting a new task, or set these personal top-level `config.toml` values:

```toml
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
```

Autorouter never makes this change itself and never claims to have configured Luna. Luna Low is the preferred starting point. Compare Luna Low with Luna Medium later only through a controlled acceptance test if Low is unreliable at routing instructions, bounded child contracts, or result synthesis.

## A Codex update changed `READY` to `DEGRADED`

This is expected when observable Codex runtime/build/host identity no longer matches the capability receipt. A receipt is created only after an expected direct child is observed on the requested Terra or Sol model and the same `agent_id` returns a successful structured completion. It binds, where observable, plugin version, Codex runtime/build, Desktop or CLI host type, platform, observed child model, effort intent, capability/schema signature, and timestamp.

If Codex does not expose optional runtime/build/host fields, the report says `runtime identity: unavailable from current Codex hook surface`. That limitation alone does not prevent `READY`; platform and all other available evidence still have to match. A receipt proves the observed routing capability, not permanent compatibility across future Codex updates.

Continue normal work. A genuine successful Terra or Sol escalation will create a fresh receipt for the current observable environment. The status and health commands never launch an automatic paid probe.

## Status says `UNAVAILABLE`

Confirm that the plugin and its hooks are enabled and trusted, and that Codex's supported direct child-routing capability is available. Organization-managed policy can prevent a user-installed hook from becoming active.

Legacy custom-agent TOMLs are optional and their absence is not a health failure. Normal installation and activation do not install them. Use explicit legacy mode only when intentionally testing or supporting an older host path.

## The wrong cost/quality profile is active

Run `routerctl.py profile`. A missing setting safely reports Balanced; an invalid or linked file reports `invalid_default` and also falls back to Balanced. Re-save a valid value with `routerctl.py profile token-saver`, `balanced`, or `max-quality`. The change begins on the next new task, not an in-flight continuation, and does not change Fast/Standard.

Run `python3 scripts/check_hooks.py` from the plugin root for the combined hook, active-root, and capability-receipt report.

## Status says `MANAGED_BLOCKED`

An organization requirement allows only managed hooks. A user-installed plugin cannot override this. Use advisory mode or ask the administrator to distribute an approved managed hook.

## Explicit legacy activation reports a conflict

This applies only to an intentionally requested legacy custom-agent mode. Do not delete the file reflexively. Compare it with the bundled definition. If it is foreign and you intentionally want the legacy controller to manage it, use the documented explicit legacy conflict option; the original must be retained for deactivation. If it is a locally edited managed file, preserve it.

## A lifecycle command was interrupted

Run `routerctl.py status` or `repair`. The next command acquires the activation lock and rolls back any transaction left in `PREPARED` or `COMMITTING` state before continuing.

## Route labels show an unexpected speed

The hook contract does not currently expose a guaranteed per-task UI Fast field. The router prefers a hook-supplied tier when present and otherwise reports persisted configuration. The router never toggles Fast itself.

## Hooks do not run

Confirm that the plugin is installed and enabled, hooks are enabled, the project is trusted where project configuration matters, and the exact plugin hook definition is trusted in `/hooks`. Managed policy can suppress plugin hooks even when files are present.

## Completion feedback repeats after an update

Tasks created by older builds can retain a hook command resolved to a deleted cache directory. The entries under `[hooks.state]` in `config.toml` are trust records keyed by plugin and hook position; their presence is expected and does not identify the active task's resolved command.

Update the plugin, review and trust the changed hook definitions, and open a fresh task once. Do not delete trust state or disable completion gates globally. Current hook definitions execute only the router under their own exact plugin root; they do not discover or execute a sibling cache. If that exact router is unavailable, the hook reports the condition and fails open without recursively continuing the task.

Within the current router, Stop and SubagentStop never hard-block. Successful observable verification—including package scripts such as `pnpm verify:fast` and tests executed through nested Codex orchestration—settles the current mutation generation. If a nominally read-only turn later mutates files, its recorded gate is promoted from `answer check` to targeted tests or a build. When Codex's incomplete unified-exec interception omits the result, when verification fails, or when orchestration is incomplete, the ledger records `FAILED_OPEN` with root verification still required; it does not pretend the check passed or inject a replayable user message. XML-wrapped feedback from an older build is recognized and discarded rather than reclassified as a new user task, and duplicate Stop delivery against either terminal state is a no-op.

Desktop-created background tasks may wrap the real request in `<codex_delegation>` with a source thread id. Autorouter classifies only the complete wrapper's `<input>` value; source UUID digits never count as work units. For verification executed through nested `exec_command`, assign the result to `r` and emit `text(JSON.stringify({exit_code:r.exit_code,output:r.output}))`. Plain `r.output`, `exit_code=0` text, and completion prose are intentionally unobservable because they cannot safely prove process status.

If an older build already poisoned the persisted transcript, first close the affected task. Then run one of:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py sanitize --session /absolute/path/to/session.jsonl
python3 skills/route-gpt-5-6-work/scripts/routerctl.py sanitize --all
```

The command reports counts and backup paths without printing prompt contents. It removes a message only when it is a UUIDv7-tagged user message containing only `<hook_prompt>` feedback; for mixed legitimate content, it preserves the message and removes only the invalid ID. It also repairs nested `compacted.replacement_history`, leaves unrelated tool output untouched, refuses links/hard links, fails closed on invalid JSONL, and writes nothing when no match exists. Reopen the task after repair. A task whose transcript is already loaded must be closed and reopened; no plugin hook can reliably rewrite that live request history.

## Standalone install or recovery refuses a tree

Do not delete the target, stage, quarantine, ownership manifest, or pending transaction reflexively. The standalone lifecycle fails closed for foreign content, path or mode drift, links, corrupt state, and post-crash edits. Preserve the reported paths and compare them with the release inventory. Use the durable controller printed by `install` if the original archive is gone. Standalone mode never qualifies as full plugin mode.
