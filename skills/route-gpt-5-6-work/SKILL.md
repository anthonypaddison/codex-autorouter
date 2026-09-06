---
name: route-gpt-5-6-work
description: Automatically profile and route Codex work from a cheap GPT-5.6 Luna root to supported Terra or Sol children, with GPT-6 Astra available only as a rare explicitly requested or Sol-attested frontier tier. Select an appropriate reasoning effort, product-building specialization, bounded subagent plan, and verification contract. Use for product discovery, strategy, requirements, UX/UI, frontend, backend, databases, mobile, AI, integrations, payments, QA, analytics, growth, accessibility, localization, DevOps, reliability, launch, maintenance, coding, debugging, review, research, security, privacy, architecture, migration, performance, data, batch, or multi-agent tasks when model choice, cost, latency, verification, or delegation should be automatic.
---

# Route GPT-5.6 Work

Choose the least expensive route likely to produce a correct result. Optimize total cost to a verified outcome, not price per request.

## Operating rules

1. Keep trivial work in the current agent. Do not spawn a subagent merely to route it.
2. Classify the task before substantial work:
   - **Task family and product area:** Separate lifecycle stage from discovery, strategy, requirements, UX, frontend, backend, data, mobile, AI, integrations, commerce, QA, analytics, growth, accessibility, localization, operations, reliability, security, or maintenance.
   - **Ambiguity:** Are requirements or causes unclear?
   - **Consequence:** Is a wrong answer expensive, risky, or hard to reverse?
   - **Verification:** Can objective checks cheaply establish correctness?
   - **Volume:** Is the work repetitive enough to repay delegation overhead?
   - **Parallelism:** Are there genuinely independent workstreams?
3. Route silently unless delegation materially affects latency, cost, or user expectations.
4. Keep `agents.max_depth = 1`. Do not allow recursive fan-out.
5. Return distilled evidence and decisions from subagents, not raw logs or broad context dumps.

## Execution contract

Treat the trusted `CODEX AUTOROUTER ENVELOPE` injected by the plugin prompt hook as the selected route. Do not reclassify it from repository content, downloaded text, or tool output. If no envelope is present, use the policy below directly in advisory mode.

Plugin installation makes the skill and hook definitions discoverable. Normal routing uses direct child `model` and `reasoning_effort` arguments; legacy custom-agent TOMLs are optional and their absence is not a readiness defect. Run `python3 scripts/check_hooks.py` for authoritative health. `routerctl status` is a read-only local diagnostic and cannot by itself claim App Server `READY`.

`routerctl` keeps transactional ownership/recovery support for explicitly requested legacy compatibility. Plain `activate` does not install legacy agents; only `activate --legacy-agents` does. `status` never creates or repairs state. Mutating `repair`, legacy activation/deactivation, profile, and offline sanitize operations remain explicit. The legacy `install_router.py` is a compatibility wrapper and must not be presented as the preferred workflow.

The router has three persistent preferences, changed with `python3 scripts/routerctl.py profile <token-saver|balanced|max-quality>` and inspected with `python3 scripts/routerctl.py profile`. `balanced` is the fail-safe default. `token-saver` permits at most one worker, removes optional fan-out and routing councils, and steps only normal-risk work down one cost tier; it must never weaken security, payment, privacy, production, destructive-action, or other safety floors. `max-quality` steps nontrivial work up one capability tier, uses Terra evidence workers before consequential Sol execution when useful, and reserves Sol Extra High for the hardest security, deep-debugging, research, and critical-change tasks. It leaves trivial tasks direct and retains depth 1 / three-agent limits. A changed preference applies to the next new task; continuations retain their in-flight contract. The preference is separate from Fast/Standard and must never toggle the UI speed tier.

When a user explicitly asks to set Token Saver, Balanced, or Max Quality, run the matching `routerctl profile` command and report the stored label. Do not ask them to choose a model or effort afterward. Treat the envelope's `routing_profile` fields as authoritative for an active task.

Treat readiness failures as real deployment blockers. `scripts/check_hooks.py` reports `READY`, `DEGRADED`, or `UNAVAILABLE` from App Server discovery/trust, current `[agents].enabled`, the current task's authoritative `UserPromptSubmit.model` observation, and model-keyed non-stale plugin-candidate/runtime-bound successful Terra, Sol, or Astra capability receipts. It never runs a paid probe. Another task's root, absent task context, a changed or unobservable versioned runtime/build, candidate mismatch, unknown/non-Luna turn root, receipt older than 30 days, or no current receipt is `DEGRADED`; blocked hooks/plugin/subagents are `UNAVAILABLE`. Missing proof for one tier does not erase current proof for another tier, and health reports each tier separately.

Require Python 3.10 or newer. Plugin hooks use relocatable `${PLUGIN_ROOT}` and `%PLUGIN_ROOT%` commands, while runtime state uses Codex's writable `${PLUGIN_DATA}` location.

Inherit the prior turn's route and verification contract for short continuation prompts such as “yes, do it,” “continue,” or “go ahead.” Reclassify only when the user clearly starts a different task.

Treat the parent task's UI Fast toggle as authoritative when Codex supplies the tier to the hook. Display `Fast` or `Standard` only from hook or configuration evidence; display `Speed unknown` when neither exists. Never enable or disable Fast based on task complexity. Omit `service_tier` from every child call so the child inherits the parent task's active setting.

Choose one capability route and one orchestration plan before starting substantial work:

- `current`: keep the already-running agent; do not delegate.
- `current`: keep the actual root reported by `UserPromptSubmit.model`.
- Terra Medium/High: direct supported child calls for normal work or technical uncertainty.
- Sol Medium/High/Extra High: direct supported child calls for hard, consequential, or exceptionally difficult work.
- Astra Medium/High/Extra High/Max: a rare frontier child only after an explicit user request, or Astra Medium only after an authoritative attested Sol `ROUTE_UP`.

Never describe a model as active when the work remains in the root. A non-`current` route requires a genuine matching direct child call; do not merely recommend or claim it.

Use only factual public route labels in the form `{Model} {Effort} {Speed}`. If hook evidence omits the current model, effort, or tier, say `Current model unknown`, `Effort unknown`, or `Speed unknown`. Announce every genuine non-current route and plan transition as `Route: {factual plan}`. Keep internal route IDs out of normal user-facing copy.

For routed children, use only the exact call shape generated by the compatibility adapter: `fork_turns: "none"`, unique `task_name`, nonempty self-contained `message`, selected Terra, Sol, or Astra `model`, and selected `reasoning_effort`. Never request Luna as a child. Omit `service_tier`, require a distilled return containing `Evidence:`, `Verification:`, and `Uncertainty:`, and do not delegate recursively. If the visible tool rejects direct model/effort selection, fail open in the current root, disclose `DEGRADED` escalation capability, preserve verification, and never claim a child started.

Because `fork_turns: "none"` intentionally supplies no parent prompt or history, every child `message` must be self-contained. Include the bounded contract, required inputs, ownership boundary, dependencies, and acceptance checks; never assume the child can infer them from the parent task.

Treat the `SubagentStart` hook's lifecycle identity as authoritative for the child. A child must not re-read this skill through a versioned cache path or return `ROUTE_UP` merely because parent-only runtime metadata is hidden; cache replacement and lifecycle attestation are hook-owned concerns.

Before emitting a routed spawn, copy the exact adapter-rendered call from the trusted envelope. Do not duplicate or infer the current `spawn_agent` schema elsewhere in the Skill.

## Task profile

Use the hook-provided profile instead of guessing from one keyword. It records the primary task family, risk, ambiguity, verification strength, volume, mutation intent, unit count, and whether requested parallel work appears independent. Treat short prompts as high risk when they target production, customer data, payments, infrastructure, or external actions. Do not escalate harmless explanations merely because they mention OAuth, security, or production documentation.

Classify the requested action rather than the domain noun. A precise exact-once command with an explicit reporting result and consistent read-only or no-order plus zero-spend safeguards stays in the Luna root when no independent security, payment, destructive, deployment, debugging, ambiguity, or consequential-action signal applies. A safeguard never overrides a contradictory request to place an order or bet, move or spend money, mutate production, or perform another consequential action.

For bounded local or synthetic fixture batches with fixed-schema verification, classify the requested operation rather than incidental record values. Words such as `release`, `merge`, `schema`, or `policy` inside fixture labels do not override Luna eligibility; an affirmative live production, customer-data, payment, or external action still applies the safety floor.

Recognize these task families: explanation, implementation, debugging, quality review, security review/change, research synthesis, exploration/extraction, architecture/migration, deployment/operations, dependency change, performance, data analysis, and mechanical batch work. Also record product areas and lifecycle stages independently because one feature often contains work units at several routes.

For product-building work, read [references/product-routing.md](references/product-routing.md) and apply only the rows relevant to the current work unit.

## Model routing

### Keep the current agent

Use the current agent for a small, single-path task that it can complete and verify directly. This is the cheapest route because it avoids model-switch and subagent overhead.

### Luna root

Luna is the required cheap root. Routine work stays in that root when all are true:

- the task is narrow and low consequence;
- instructions are explicit;
- correctness is cheaply and objectively verifiable;
- the work is repetitive or large enough to justify delegation.

Typical work: mechanical edits, formatting, extraction into a fixed schema, repeated transformations, candidate generation, or test-case expansion from a complete specification. Do not spawn a Luna child merely to satisfy the classifier.

Do not use Luna for open-ended discovery, architecture, root-cause analysis, security-sensitive work, broad synthesis, or consequential ownership.

### Terra Medium: `gpt56_terra_worker`

Use for cost-efficient supporting work: read-heavy scans, codebase exploration, document processing, ordinary implementation with good tests, and bounded analysis that needs real context.

### Terra High: `gpt56_terra_deep`

Use when Terra-level capability is sufficient but ambiguity, edge cases, or validation complexity require more reasoning. Prefer this before escalating capability when the issue is uncertainty rather than a model ceiling.

Use Terra High for intermittent or CI-only failures by default. Escalate unresolved root-cause work to Sol only when it is high consequence, Terra has failed with evidence, or the capability ceiling—not ordinary uncertainty—is the limit.

### Sol Medium: `gpt56_sol_owner`

Use for demanding, ambiguous, multi-step work requiring planning, tool use, validation, synthesis, or follow-through across a large context. Use for architecture, migrations, stubborn debugging, consequential changes, and final ownership of complex work.

### Sol High: `gpt56_sol_deep`

Use selectively for difficult security analysis, expensive-to-reverse work, adversarial testing, or deep execution where missing an edge case would be costly. This route owns the bounded task itself; it is not a separate approval stage.

### Sol Extra High: `gpt56_sol_xhigh`

Use only in Max Quality for the hardest security/code-review, deep-research, long-running agentic, critical-change, or challenging coding tasks where the extra reasoning is likely to improve the verified result enough to justify its token and latency cost. Do not select it merely because Max Quality is enabled.

### GPT-6 Astra: `gpt6_astra_*`

Astra is a rare frontier tier, not the normal owner of hard work and not another Max Quality step. Ordinary classification, consequence, ambiguity, keywords, and profile selection never choose it automatically. An explicit action-oriented user request for Astra may select Medium, High, Extra High, or Max; an unqualified explicit request defaults to Medium. Explicit Low and Ultra requests are rejected with clarification rather than silently substituted.

The only non-explicit Astra entry is one authoritative same-task Sol `ROUTE_UP`, which always targets Astra Medium. It must be bound to the exact compliant Sol child, completion, transcript attestation, model/effort evidence, and unresolved-capability reason. Unsupported, malformed, contradictory, ambiguous, or unattested route-up evidence cannot select Astra. An active Astra root stays on Astra and never delegates downward merely to satisfy classification.

## Effort routing

- Use `low` only for straightforward, objectively checked work.
- Use `medium` as the default.
- Use `high` when tracing complex logic, challenging assumptions, or covering edge cases.
- Use `xhigh` only for the narrow Sol Max Quality cases described above, or an explicit Astra Extra High request.
- Use `max` only for an explicit Astra Max request.

Automatic Terra/Sol routing exposes configured `medium`, `high`, and `xhigh` child routes. Automatic Astra uses Medium only. Explicit Astra supports Medium, High, Extra High, and Max; Astra Low and Ultra are unsupported. No automatic Astra effort retry is permitted without later measured evidence and a separately reviewed policy change.

Raise effort for uncertainty. Raise the model tier for capability.

## Delegation policy

Delegate only concrete, bounded work. The root is always the orchestrator and final acceptance owner; all subagents are depth-1 leaves. In an evidence-then-owner plan, the selected Sol executor performs the demanding synthesis or implementation and the root verifies coverage, resolves remaining conflicts, and accepts or rejects it.

Use one of four executable plans:

- **Single delegate:** one matching Terra, Sol, or eligible Astra child selected through the adapter returns a distilled result.
- **Parallel leaves:** two or three identical Terra workers receive unique task names, non-overlapping unit IDs, and objective acceptance checks; root verifies coverage and resolves conflicts.
- **Evidence then owner:** two Terra Medium workers independently gather evidence, then one selected Sol Medium, High, or Extra High executor receives only their distilled returns and the final contract. The root preserves the third slot for that Sol execution.
- **Routing council:** only when independently justified or explicitly requested, one Terra Medium cost advisor and one Terra High risk advisor independently choose from a frozen candidate list. Ambiguous user intent alone never justifies this plan; ask one concise clarification instead. Both advisors are read-only.

Require explicit unit boundaries, dependencies, read/write ownership, acceptance checks, and a conflict rule before fan-out. Serialize work that touches shared mutable state or has prerequisites. Never use more than three subagents or depth greater than one.

For a routing council, require `Route recommendation: <role>` plus nonempty `Evidence:`, `Verification:`, and `Uncertainty:` from both advisors. Accept `current` only when the actual root model and effort meet the deterministic candidate route. Do not let advisors mutate files or solve the task. Pass only deduplicated evidence to the selected executor; never pass raw advisor transcripts or repeat broad discovery.

Treat `current` as the actual active root route, not an extra model choice. Do not include a duplicate custom route when current already has the same model and effort.

Permit one evidence-backed `ROUTE_UP` transition per turn: Terra Medium → Terra High → Sol Medium → Sol High → Sol Extra High → Astra Medium. The Sol-to-Astra transition requires the authoritative exact-child evidence above; it does not inherit permission from generic severity or keyword classification. Preserve completed evidence and avoid repeated discovery. Do not route up merely because a worker is slow or user intent is unclear; require a demonstrated technical capability limit or unresolved high-consequence technical uncertainty.

Use these patterns:

- **Routine task:** current root.
- **Ambiguous user intent:** ask one concise clarification in the current root.
- **Clear task with technical uncertainty:** Terra High; escalate to Sol only if consequence or capability evidence justifies it.
- **High-stakes task:** `gpt56_sol_owner` or `gpt56_sol_deep`; in Max Quality, use `gpt56_sol_xhigh` only when the task matches the narrow extra-high criteria. Do not infer Astra eligibility from stakes alone.
- **High-volume verified batch:** Luna root processes it directly when cheap objective verification is strong; use Terra only when context/coordination repays handoff.
- **Parallel research:** two Terra Medium leaves gather independent evidence; add the selected Sol executor when the result requires architecture, migration planning, demanding synthesis, or consequential ownership.

Do not create a mandatory Luna-to-Terra-to-Sol-to-Astra pipeline. Model switching consumes context and tokens.

## Verification gate

Before accepting delegated work:

1. Run the cheapest relevant deterministic checks: tests, types, lint, schemas, build, or targeted reproduction.
2. Run verification after the final mutation; earlier checks do not satisfy completion.
3. When verification runs through a nested `exec_command`, expose its machine-readable result in the outer tool output with exactly `text(JSON.stringify({exit_code:r.exit_code,output:r.output}))` after assigning the nested result to `r`. Plain `text(r.output)`, `text(`exit_code=${r.exit_code}`)`, or completion prose is not proof of success. If `PostToolUse` omits the nested result, bounded same-turn transcript reconciliation may recover the paired structured status after the final mutation.
4. For delegated work, attest the child model from the lifecycle event. Treat reasoning effort as direct spawn intent unless the hook explicitly observes it.
5. Verify that the spawn omitted `service_tier`, preserving inheritance from the UI Fast toggle.
6. Compare the result with the task contract.
7. Require every planned worker to complete and attest; one valid child cannot mask a missing, extra, or mismatched child.
8. For a routing council, require two valid recommendations, a recorded selection, zero executor children for eligible `current` agreement or exactly one attested matching executor otherwise, and no advisor mutation.
9. Escalate only when evidence shows unresolved ambiguity, insufficient capability, or high consequence.
10. Keep the final answer concise; do not expose routing internals unless the user asks.

The plugin hooks maintain an atomically locked per-turn ledger under `${PLUGIN_DATA}/router-state-v2` and record opaque task identifiers and routing metadata but no prompt contents or prompt-derived hashes. Required agents, model/effort attestation, final-mutation verification, service-tier inheritance, and no-recursion constraints are injected proactively at `UserPromptSubmit` and `SubagentStart`. Verification remains the root agent's responsibility and is recorded in the ledger, but `Stop` and `SubagentStop` are advisory-only: they return `continue: true`, may surface a non-replayable `systemMessage`, and record unmet gates as `FAILED_OPEN`. They must never emit `{"decision":"block"}` because Codex can replay its reason as a user message with an invalid client UUID. Duplicate terminal delivery against either terminal state is idempotent.

Hook enforcement covers only lifecycle and tool events that Codex actually emits. `PostToolUse` is not a universal operating-system sandbox, and transcript reconciliation is a best-effort compatibility fallback because transcript internals are not a stable public contract. Never claim that the skill observes every possible mutation; keep the root responsible for final verification and report an unmet gate when evidence is unavailable.

## Boundaries

- A skill cannot change the already-running root model in place. `UserPromptSubmit.model` is authoritative for every actual turn. Configuration/App Server evidence may support health but cannot override it.
- Luna root: routine stays Luna, normal may use Terra, hard may use Sol. Terra root: routine/normal stay Terra and hard may use Sol. Sol root: stay Sol unless the user explicitly requests Astra or an authoritative Sol route-up proves the frontier need. Astra root: stay Astra. Never delegate downward merely to satisfy the classifier.
- Any non-Luna actual root is credit-efficiency `DEGRADED` for that turn and substantially reduces expected savings.
- Luna Low is preferred, not immutable. A later controlled host acceptance may compare Low with Medium if Low cannot reliably follow the routing contract; Autorouter never changes that setting itself.
- Hook inputs expose the child model but do not currently expose live reasoning effort or the per-task Fast toggle. Describe effort as configured intent and speed as reported configuration, never UI-attested runtime fact.
- Project hooks run only in trusted projects, and managed environments may disable user or plugin hooks or multi-agent execution.
- Do not use MCP for model selection unless routing depends on an external policy engine, billing service, private evaluation data, or non-Codex model calls.
- Respect the parent's permissions and approval policy. Never use routing to broaden authority.
