# Real-host acceptance

Run this checklist on the exact archive or immutable marketplace version being evaluated. Do not copy files from the source tree into an installed cache, and do not promote App Server or config discovery into proof of the active Desktop/CLI turn.

These are controlled, explicitly authorized acceptance runs. The ordinary status and health commands must never create a paid child merely to prove capability.

## Evidence to record

For every row in `RELEASE_CHECKLIST.md`, record:

- operating system, architecture, Codex surface, host type, and Codex runtime/build version;
- exact plugin version, tag commit, and archive SHA256 where applicable;
- clean or pre-existing `CODEX_HOME` state;
- hook discovery, trust, and exact-root command result;
- `UserPromptSubmit.model` for each actual turn;
- public route label and final acceptance result;
- requested child model, effort intent, observed child model, adapter schema/signature, and fallback result;
- capability receipt timestamp and its plugin/runtime/build/host/platform binding;
- ledger status, continuation count, verification evidence, and violations;
- any warning, retry, manual intervention, or environmental limitation.

A passing delegated route requires the expected model/effort intent, no unplanned children, satisfied verification, no unresolved violation, and a receipt created only after genuine successful Terra or Sol work. A successful-looking final answer is insufficient.

## Cheap-root setup and health boundary

1. Select GPT-5.6 Luna in Desktop, or set the personal top-level CLI configuration:

   ```toml
   model = "gpt-5.6-luna"
   model_reasoning_effort = "low"
   ```

2. Start a fresh task and prove that `UserPromptSubmit.model` observed `gpt-5.6-luna`. Config and App Server evidence may support the report but may not override the hook field.
3. Trust the five exact plugin hooks.
4. From the exact installed cache root, run:

   ```bash
   python3 scripts/check_hooks.py
   ```

5. Before a current receipt exists, require `DEGRADED`, not a false `READY`. Confirm the command did not launch a child or spend credits.

Luna Low is the preferred starting point. If it fails to follow routing instructions, construct bounded child contracts, or synthesise the escalated result, repeat the same bounded cases with Luna Medium and record the comparison. Do not change the architectural requirement that Luna remains the cheap root.

## Direct Terra/Sol capability smoke

Use two clear, bounded, non-mutating prompts: one normal technical task expected to justify Terra and one hard technical task expected to justify Sol. Avoid user-intent ambiguity; ambiguity must cause a concise clarification from Luna rather than stronger-model spend.

For each run:

1. Start a fresh Luna task and confirm the hook's actual active model.
2. Confirm the router constructs the direct child request through the single compatibility adapter, with `fork_turns: "none"`, the requested Terra or Sol model, bounded task name/message, and effort intent supported by the runtime.
3. Confirm no obsolete custom `agent_type` is required and no legacy TOML is installed as a prerequisite.
4. Require the observed child model and returned evidence to match the contract. Exercise the adapter's unsupported-schema fallback separately without launching a paid child.
5. After a genuine successful escalation, run `python3 scripts/check_hooks.py` again. Require `READY` only when the receipt matches the plugin and observable Codex runtime/build and records host type, platform, child model, effort intent, capability/schema signature, and timestamp.
6. Change or simulate the observable runtime/build identity without launching another child. Require `DEGRADED`; a later health invocation must not auto-probe. A subsequent genuine successful escalation on that runtime may create a fresh receipt.

On native Windows use `py -3` where `python3` is unavailable. Exercise native lock, atomic replacement, rollback, reparse-point, and hardlink cases through the automated suite before accepting the host.

## Active-root routing matrix

Run the matrix only with explicit acceptance authorization because non-Luna selections reduce credit efficiency:

| Hook-observed root | Routine | Normal | Hard | Expected turn health |
|---|---|---|---|---|
| Luna | remain Luna | Terra allowed | Sol allowed | eligible for `READY` with a current receipt |
| Terra | remain Terra | remain Terra | Sol allowed | `DEGRADED` |
| Sol | remain Sol | remain Sol | remain Sol | `DEGRADED` |

Sol must not delegate downward merely to satisfy the classifier. A Sol child is permissible only for separately justified independent parallel work. A non-Luna actual root must report that credit-saving behaviour is substantially reduced for that turn.

## Desktop-specific smoke

Use the Codex Desktop UI to test Fast on and off in separate fresh Luna tasks. Do not type `/fast on` or `/fast off` into a task. The router must preserve the UI setting and must never claim UI attestation when only persisted configuration is available.

Desktop acceptance is manual when UI automation policy prevents another task from controlling the Codex app. Do not replace this row with a CLI run against the bundled Desktop binary.

## IDE standalone smoke

Use a fresh `CODEX_HOME`, extract the archive, and follow `STANDALONE.md`:

1. Check inactive status, install, and repeat install to prove idempotence.
2. Start a new IDE task and confirm `$route-gpt-5-6-work` discovery.
3. Require `ADVISORY`; absent legacy custom-agent TOMLs are not a failure.
4. Confirm the direct adapter path is used only when the host exposes compatible child spawning and that fallback remains truthful.
5. Update, uninstall through the durable controller, purge from the trusted archive, and confirm the skill target is absent. Exercise legacy activation/deactivation only as a separate explicitly labeled compatibility case.

## Failure handling

Preserve failed ledgers and minimal redacted evidence. Do not weaken model, effort, worker-cap, ordering, mutation, receipt, runtime-binding, or return-contract checks to make a host pass. Record the candidate as rejected, fix the source, create a new candidate version, and repeat acceptance on that exact build.
