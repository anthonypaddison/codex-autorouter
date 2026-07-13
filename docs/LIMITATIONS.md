# Known limitations

## Custom agents require explicit activation

Codex plugins do not currently document a native custom-agent component. The plugin bundles reviewed templates, but the user must explicitly install the five namespaced TOMLs into `CODEX_HOME/agents` with `routerctl`.

Native custom-agent selection requires both the exact `agent_type` and `fork_turns: "none"` on each spawn. `task_name` is only an orchestration label; using the role there does not select the custom agent. The default full-history fork inherits the parent identity and is incompatible with a custom `agent_type`. The router injects this contract and lifecycle hooks still require the expected child model and role; do not weaken attestation to accept built-in `default` as a named model route.

## Hook trust is not filesystem-observable

Codex stores and evaluates hook trust separately. `routerctl status` can validate files and visible configuration but deliberately reports trust as `UNVERIFIED`. The user must confirm `/hooks`.

## Config diagnostics are local hints

`routerctl status` reads local `CODEX_HOME/config.toml` and `requirements.toml` only. It cannot calculate the final merged value after administrator profiles, policy, project configuration, or command-line overrides. Fields are named `*_by_local_config` or `*_in_local_requirements` for that reason. `scripts/check_hooks.py` performs the authoritative preflight by reading effective merged configuration and requirements from app-server alongside discovered hook trust.

## Fast is reported, not UI-attested

The documented common hook input does not guarantee a live `service_tier` field. A hook-supplied tier wins when available; persisted configuration is used next. When neither exists, the label is `Speed unknown`, not an assumed Standard tier. The router does not change the user's tier.

## Reasoning effort is configuration intent

Lifecycle input exposes the child model but not a guaranteed live reasoning-effort field. The router validates effort against its owned agent TOML and describes this as configured intent.

## Hook coverage is not an OS sandbox

`PostToolUse` covers matching Codex tool events, not every possible operating-system mutation. Final acceptance remains with the root agent and proportionate deterministic verification.

## Transcript compatibility is best effort

Codex documents transcript format as unstable. Transcript reconciliation is bounded compatibility support, not correctness-authoritative attestation.

## Managed environments may block enforcement

`allow_managed_hooks_only`, feature requirements, marketplace restrictions, or disabled multi-agent support can force advisory or managed-blocked operation. The plugin never bypasses organizational policy.

## Supported surfaces and real-host coverage

Full plugin mode targets Codex Desktop and CLI. Codex IDE extensions do not currently support plugins; IDE use is therefore limited to the standalone skill's explicit `ADVISORY` mode without hook enforcement. CI can exercise macOS, Linux, and Windows semantics, but public stable release still requires native acceptance on supported Desktop and CLI hosts, including hook trust and filesystem behavior.

## Same-user lifecycle threat model

Checksums and inventories prevent accidental overwrite, partial lifecycle recovery, and unnoticed ownership drift; they are not signatures against a malicious process already running as the same operating-system user. Post-crash edits, corrupt controller copies, and modified quarantine trees are preserved and require manual review.
