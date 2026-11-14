# Known limitations

## Legacy custom agents are optional

Normal routing uses the direct model-spawn compatibility adapter and does not install or require custom-agent TOMLs. The six namespaced templates remain only for compatibility testing and an explicit legacy mode. Users who deliberately need that mode can run `routerctl activate --legacy-agents`; their absence never degrades normal readiness.

Current direct-spawn schema construction, capability detection, and fallback live in one tested adapter. If Codex changes that schema, normal routing degrades to the current root model until the adapter is updated and a genuine successful GPT-6 Sol or Astra escalation creates a fresh model-keyed capability receipt. Autorouter never runs an automatic paid probe.

## Hook trust is not filesystem-observable

Codex stores and evaluates hook trust separately. `routerctl status` can validate files and visible configuration but deliberately reports trust as `UNVERIFIED`. The user must confirm `/hooks`.

## Pre-fix open tasks need one restart after upgrade

Codex can retain the resolved, versioned hook command for an already-open task. Builds before the immutable launcher fix cannot rewrite that in-memory registration after the installed version changes. Open a fresh task once after upgrading from such a build. Tasks created by the fixed build launch only from the plugin root Codex supplied; they do not scan sibling cache directories.

## The active root model is turn evidence

`UserPromptSubmit.model` is authoritative for the active root model on each actual turn. Local config and App Server evidence can support health reporting, but neither overrides that hook observation. A non-Luna root is therefore credit-efficiency `DEGRADED` for that turn even if configuration says Luna.

`routerctl status` reads local `CODEX_HOME/config.toml` and `requirements.toml` only. It cannot calculate the final merged value after administrator profiles, policy, project configuration, or command-line overrides. Autorouter reports such evidence as diagnostic context and never writes the root model.

## READY is runtime-bound

GPT-6.1 Sol and Terra are supported exact roots, including same-model effort upgrades and independent workers. They remain non-Luna for credit-efficiency reporting. GPT-6.1 receipts attest only their exact model/profile/effort; they cannot prove GPT-6 Sol capability or another GPT-6.1 model's capability.

Runtime version/host recovery uses only a bounded, matching session metadata header from the hook-supplied transcript. Absent, oversized, unsafe or unrecognised metadata remains unproven. This recovery does not infer reasoning effort, change the root, or refresh historical receipts.

`scripts/check_hooks.py` reports `READY` only after a current-task GPT-6 Luna root observation and at least one genuine successful GPT-6 Sol or Astra escalation receipt for the same plugin content identity/version, at least one matching versioned Codex runtime/build identifier, host type, platform, capability signature, and supported schema. Receipts are keyed by exact model tier and reported independently; one tier never proves another. Another task's observation, missing current-task context, null runtime identity, a candidate change, or a receipt older than 30 days returns health to `DEGRADED` when no other current tier receipt exists. Historical receipts remain auditable as `ESCALATION PREVIOUSLY OBSERVED`. This is intentional; health checks never spend credits on an automatic probe.

## Astra is intentionally rare

Normal classification, severity, keywords, and Max Quality cannot select Astra. Explicit requests support Medium, High, Extra High, and Max and default to Medium; Low and Ultra are rejected. The only automatic path is a fully attested same-task Sol `ROUTE_UP`, always to Astra Medium. Autorouter has no automatic Astra effort retry. An Astra root remains the final owner rather than delegating downward.

## Fast is reported, not UI-attested

The documented common hook input does not guarantee a live `service_tier` field. A hook-supplied tier wins when available; persisted configuration is used next. When neither exists, the label is `Speed unknown`, not an assumed Standard tier. The router does not change the user's tier.

## Reasoning effort is configuration intent

Lifecycle input exposes the child model but not a guaranteed live reasoning-effort field. The compatibility adapter supplies a validated effort intent with each direct spawn, and receipts report that value as intent rather than unavailable runtime attestation.

## Hook coverage is not an OS sandbox

`PostToolUse` covers matching Codex tool events, not every possible operating-system mutation. Final acceptance remains with the root agent and proportionate deterministic verification.

## Observed spawn compliance is separate from child identity

Task-name-only spawn results are supported only through the current host's exact lifecycle bridge: a validated direct call and paired result in the same parent turn, one matching call/child-UUID/task-path start, completion for that same child/path, and a full safe child transcript proving parent identity, depth, path, model, effort and structured completion for the exact parent and child turns. A name alone is never identity evidence. Conflicting claims, missing events, exhausted bounds, malformed records and unsafe paths grant no receipt. Task paths remain transient and are not persisted in routing ledgers or receipts. Existing plugin/runtime/freshness and orchestration gates remain in force.

This recovery also requires a turn ledger created by the exact current plugin candidate. A pre-update ledger cannot be promoted to current capability proof by replaying an old execution. Normal new turns capture that candidate identity automatically; no saved receipt or historical ledger is upgraded.

A real, correlated, completed child is not necessarily compliant routed execution. Required-role fulfilment and capability receipts require a validated observed spawn call: explicit supported model/effort, `fork_turns: "none"`, nonblank `task_name` and `message`, and no service-tier override. Construction and validation share the compatibility adapter. Lifecycle model/effort or the intended envelope cannot substitute for the actual arguments.

Structured spawn calls use exact call/activity identities. Nested `functions.exec` recovery parses complete literal argument objects without executing JavaScript; variables, computed/spread properties, duplicate fields, incomplete syntax and bounded-parser exhaustion cannot prove compliance. It never searches message contents for missing argument fields. Multiple nested spawns in one wrapper without an authoritative inner call/result bridge remain unproven per child; response order, model and timing are not identity evidence. Call-specific reason codes are retained without raw messages. Malformed-call history remains visible, but a later compliant child can fulfil the role where existing orchestration policy permits.

Pre-execution blocking for the exact nested spawn surface remains **HOST CAPABILITY UNPROVEN**. This validation refuses compliant execution/receipt credit; it does not claim to prevent the host from launching a malformed child. Lifecycle-only historical fixtures and receipts are not new proof of this contract.

## Classification uses local action context

Security-changing intent requires a local affirmative action on a security-sensitive subject. Reporting or preserving permissions, sandbox state, plugin/hook trust, or configuration is not itself a security change. A prohibition extends over its coordinated action list, but does not suppress a later affirmative instruction such as `Do not change permissions; actually chmod the directory 777`.

Operational root/routing/audit ledgers and ledger identifiers are not financial actions. Actual financial ledger or account-balance changes remain critical; underspecified financial changes still require clarification. An exact-once command plus an explicit reporting requirement and safeguards can stay on the current root, including the inline form `Run exactly <command> once`. Independent security and consequential-action gates still apply.

These are deterministic language rules, not a complete natural-language parser or a security sandbox. Other task-complexity signals still select the route; classification-only replay does not prove model quality, savings, or live child-contract compliance.

## Transcript compatibility is best effort

Exact-child discovery searches only the effective `CODEX_HOME/sessions/YYYY/MM/DD` hierarchy and flat `CODEX_HOME/archived_sessions`, irrespective of the parent's date directory. It accepts canonical UUIDv7 child IDs and the exact Codex rollout filename scheme. A filename is only a candidate: unique discovery, safe file validation, matching child/parent session metadata, and an unambiguous child turn/model/effort are still required. Discovery never chooses by timestamp, date proximity, model or filename order. It retains at most two candidates and searches at most 4,096 directories and 65,536 entries per child. Search exhaustion or duplicate candidates return `INCOMPLETE`; traversal errors return `IO_ERROR`; unsafe paths return `PATH_REJECTED`. Only a complete safe search without a candidate returns `NOT_FOUND`. No persistent index or transcript path/content is retained, and successful recovery does not bypass any runtime-bound capability-receipt gate.

Codex documents transcript format as unstable. Transcript reconciliation is bounded compatibility support, not correctness-authoritative attestation. Autorouter descriptor-validates and incrementally scans regular, singly-linked, owner-matched JSONL files; it accepts complete JSON records up to 16 MiB and retains at most 256 KiB of relevant decoded text, 256 calls, and 64 agents per scan. Whole-transcript size is not a rejection condition. Linked paths, malformed JSONL, oversized individual lines, I/O failures, and bounded-summary exhaustion remain explicit conservative outcomes and cannot establish evidence. Autorouter accepts only paired exact-turn tool calls with bounded, schema-located machine status. A recovered success must follow every mutation and bind one-to-one to the recorded mutation generation through opaque call identities where available; incomplete historical provenance remains conservative. Otherwise Autorouter fails open to root-owned verification.

## Terminal hooks cannot safely hard-block on affected Codex builds

Some Codex builds replay a `Stop` or `SubagentStop` block reason as a persisted user message with a client UUIDv7 identifier. The Responses API later rejects that identifier because message IDs must use the server `msg_` form, which can brick every later turn in the task. Autorouter therefore enforces routing proactively through trusted prompt/subagent context and uses terminal hooks only for advisory ledger recording. True safe terminal hard blocking requires an upstream Codex replay fix that omits the client-generated ID or replaces it with a valid server message ID.

`routerctl sanitize` is an offline persisted-transcript repair, not live in-memory recovery. Close the affected task, sanitize its JSONL (or all persisted sessions), and then reopen it. The command makes a byte-exact sibling backup before atomically replacing changed files. Codex transcript internals remain undocumented, so the sanitizer deliberately targets only the observed UUIDv7 + `<hook_prompt>` signature and fails closed on malformed input.

## Managed environments may block enforcement

`allow_managed_hooks_only`, feature requirements, marketplace restrictions, or disabled multi-agent support can force advisory or managed-blocked operation. The plugin never bypasses organizational policy.

## Supported surfaces and real-host coverage

Automation hook delivery is host/version dependent. The currently observed Codex Desktop host dispatches Autorouter hook context and ledgers for automation-triggered turns, disproving the earlier blanket assumption that automation hooks never run. Autorouter has not yet validated automation routing semantics as a supported savings surface, so automation activity remains excluded from Autorouter-attributable routing and savings claims. Operators must not infer either hook absence or savings coverage without host-specific evidence.

Full plugin mode targets Codex Desktop and CLI. Codex IDE extensions do not currently support plugins; IDE use is therefore limited to the standalone skill's explicit `ADVISORY` mode without hook enforcement. CI can exercise macOS, Linux, and Windows semantics, but public stable release still requires native acceptance on supported Desktop and CLI hosts, including hook trust and filesystem behavior.

## Same-user lifecycle threat model

Checksums and inventories prevent accidental overwrite, partial lifecycle recovery, and unnoticed ownership drift; they are not signatures against a malicious process already running as the same operating-system user. Post-crash edits, corrupt controller copies, and modified quarantine trees are preserved and require manual review.
# Configured AI routing candidate (proposed v0.3)

The nested CLI classifier was removed because feature-disable flags did not
establish tool exclusion. Configured mode instead uses the OpenAI Responses API
with `tools: []`, `tool_choice: "none"` and strict JSON schema. Only the `openai`
provider is supported in this candidate. User-selected API models must support
that interface and reasoning effort; setup does not prove API entitlement.
No live inference is part of automated development tests.

The classifier can recommend only configured model/effort pairs. Codex performs
native compatibility validation before child creation; the router does not
reproduce that policy or treat API availability as Codex child support. A local
catalogue is advisory and can be stale. Native validation is not a guarantee
against account restrictions, transient failures, worker limits or later errors.
Known model/effort preparation errors can prove rejection before creation. Other
errors without start evidence retain an unknown creation boundary. Missing
PostToolUse/result evidence remains unobservable, never successful by default.

Fallback is a classification-time choice only, using the same configured
allowlist. After a spawn request there is no automatic retry, fallback child,
cost-tier escalation or reclassification. The parent reports failures and retains
responsibility for verification. A successful return/child ID is not proof of
child start, completion or model/effort attestation.

The standard-library HTTP worker has no model tools, Codex invocation or hooks.
Its parent enforces the total request deadline, including DNS/TLS and slow reads,
and terminates the worker on timeout. A timeout can still mean a provider received
and billed the request; unknown usage is not zero and cancellation does not prove
refund. There is no automatic retry. API response bodies are bounded at 128 KiB,
task input at 32 KiB, output at 256 tokens, timeout at 1–6 seconds. The output cap
includes reasoning usage and can cause incomplete results/fallback.

API billing must be explicitly enabled. CLI-era schema-v1 configs require setup;
they never silently start API spending. The ledger is reserved before an attempt
to suppress duplicate delivery after interruption. Simple continuations do not
repeat classification or execution. Configuration changes invalidate in-flight
reuse. Setup/status do not claim execution acceptance or capability receipts.

The classifier is prompted to minimize cost to reliable completion, but no live
rate card or verified intelligence ranking is inferred from model names. Real
selection quality, unnecessary escalation/under-routing, classifier cost and
task quality are unmeasured. The existing benchmark fixtures test the transport
using mocked selections only. Legacy route-audit/fuzz checks still test the v0.2
compatibility path; they do not grade an AI classifier.

No new model-family edit is needed to prepare configured executors. Exact allowed
model/effort pairs produce configuration-bound roles and receipt keys. All
independent identity, lifecycle, ambiguity, verification and receipt gates remain
in force; a valid classification cannot manufacture a receipt. Existing receipt
documents with incompatible settings remain historical and may prevent a new
current receipt rather than being rewritten automatically.

The deterministic classifier, family policies and historical roles are retained
for unconfigured installation compatibility and fixture comparisons. They do
not select an executor after successful AI setup. This is a staged replacement,
not removal of functioning lifecycle safeguards or historical evidence.
