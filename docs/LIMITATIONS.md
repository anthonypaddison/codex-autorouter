# Known limitations

## Legacy custom agents are optional

Normal routing uses the direct model-spawn compatibility adapter and does not install or require custom-agent TOMLs. The six namespaced templates remain only for compatibility testing and an explicit legacy mode. Users who deliberately need that mode can run `routerctl activate --legacy-agents`; their absence never degrades normal readiness.

Current direct-spawn schema construction, capability detection, and fallback live in one tested adapter. If Codex changes that schema, normal routing degrades to the current root model until the adapter is updated and a genuine successful Terra or Sol escalation creates a fresh capability receipt. Autorouter never runs an automatic paid probe.

## Hook trust is not filesystem-observable

Codex stores and evaluates hook trust separately. `routerctl status` can validate files and visible configuration but deliberately reports trust as `UNVERIFIED`. The user must confirm `/hooks`.

## Pre-fix open tasks need one restart after upgrade

Codex can retain the resolved, versioned hook command for an already-open task. Builds before the immutable launcher fix cannot rewrite that in-memory registration after the installed version changes. Open a fresh task once after upgrading from such a build. Tasks created by the fixed build launch only from the plugin root Codex supplied; they do not scan sibling cache directories.

## The active root model is turn evidence

`UserPromptSubmit.model` is authoritative for the active root model on each actual turn. Local config and App Server evidence can support health reporting, but neither overrides that hook observation. A non-Luna root is therefore credit-efficiency `DEGRADED` for that turn even if configuration says Luna.

`routerctl status` reads local `CODEX_HOME/config.toml` and `requirements.toml` only. It cannot calculate the final merged value after administrator profiles, policy, project configuration, or command-line overrides. Autorouter reports such evidence as diagnostic context and never writes the root model.

## READY is runtime-bound

`scripts/check_hooks.py` reports `READY` only after a Luna root observation and a genuine successful Terra or Sol escalation receipt for the same plugin version, Codex runtime/build, host type, platform, capability signature, and supported schema. A runtime/build change or unavailable runtime identity returns health to `DEGRADED` until normal work produces a fresh receipt. This is intentional; health checks never spend credits on an automatic probe.

## Fast is reported, not UI-attested

The documented common hook input does not guarantee a live `service_tier` field. A hook-supplied tier wins when available; persisted configuration is used next. When neither exists, the label is `Speed unknown`, not an assumed Standard tier. The router does not change the user's tier.

## Reasoning effort is configuration intent

Lifecycle input exposes the child model but not a guaranteed live reasoning-effort field. The compatibility adapter supplies a validated effort intent with each direct spawn, and receipts report that value as intent rather than unavailable runtime attestation.

## Hook coverage is not an OS sandbox

`PostToolUse` covers matching Codex tool events, not every possible operating-system mutation. Final acceptance remains with the root agent and proportionate deterministic verification.

## Transcript compatibility is best effort

Codex documents transcript format as unstable. Transcript reconciliation is bounded compatibility support, not correctness-authoritative attestation. Autorouter accepts only paired same-turn tool calls and machine-readable successful status after the final mutation, refuses linked or oversized transcript files, and otherwise fails open to root-owned verification.

## Terminal hooks cannot safely hard-block on affected Codex builds

Some Codex builds replay a `Stop` or `SubagentStop` block reason as a persisted user message with a client UUIDv7 identifier. The Responses API later rejects that identifier because message IDs must use the server `msg_` form, which can brick every later turn in the task. Autorouter therefore enforces routing proactively through trusted prompt/subagent context and uses terminal hooks only for advisory ledger recording. True safe terminal hard blocking requires an upstream Codex replay fix that omits the client-generated ID or replaces it with a valid server message ID.

`routerctl sanitize` is an offline persisted-transcript repair, not live in-memory recovery. Close the affected task, sanitize its JSONL (or all persisted sessions), and then reopen it. The command makes a byte-exact sibling backup before atomically replacing changed files. Codex transcript internals remain undocumented, so the sanitizer deliberately targets only the observed UUIDv7 + `<hook_prompt>` signature and fails closed on malformed input.

## Managed environments may block enforcement

`allow_managed_hooks_only`, feature requirements, marketplace restrictions, or disabled multi-agent support can force advisory or managed-blocked operation. The plugin never bypasses organizational policy.

## Supported surfaces and real-host coverage

Full plugin mode targets Codex Desktop and CLI. Codex IDE extensions do not currently support plugins; IDE use is therefore limited to the standalone skill's explicit `ADVISORY` mode without hook enforcement. CI can exercise macOS, Linux, and Windows semantics, but public stable release still requires native acceptance on supported Desktop and CLI hosts, including hook trust and filesystem behavior.

## Same-user lifecycle threat model

Checksums and inventories prevent accidental overwrite, partial lifecycle recovery, and unnoticed ownership drift; they are not signatures against a malicious process already running as the same operating-system user. Post-crash edits, corrupt controller copies, and modified quarantine trees are preserved and require manual review.
