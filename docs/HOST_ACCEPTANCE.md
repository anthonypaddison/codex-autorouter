# Real-host acceptance

Run this checklist on the exact archive or marketplace version being evaluated. Do not copy files from the source tree into an installed cache, and do not promote app-server discovery into proof of a Desktop UI route.

## Evidence to record

For every row in `RELEASE_CHECKLIST.md`, record:

- operating system, architecture, Codex surface, and Codex version;
- exact plugin version and archive SHA-256 when applicable;
- clean or pre-existing `CODEX_HOME` state;
- hook discovery and trust result;
- custom-agent activation and deactivation result;
- public route label and final acceptance result;
- ledger status, child role/model attestation, continuation count, and violations;
- any warning, retry, manual intervention, or environmental limitation.

A passing route requires `COMPLETE`, the expected custom role and model, zero unexpected agents, zero unresolved violations, and no correction retry. A successful-looking final answer is not sufficient.

## CLI plugin smoke

1. Install the exact marketplace version and start a fresh task.
2. Review and trust the five plugin hooks.
3. From the installed cache root, run:

   ```bash
   python3 skills/route-gpt-5-6-work/scripts/routerctl.py activate
   python3 scripts/check_hooks.py
   ```

4. Require `ready: true`, exactly five trusted hooks, the exact cached skill version, and five current agent definitions.
5. Run this bounded non-mutating prompt in a fresh task:

   > Perform a bounded security review of this hypothetical only; do not inspect files or use shell tools. The handler verifies an RS256 signature, pins issuer and audience, validates exp and nbf, binds tenant_id to the authenticated account, requires exact admin:write scope, rejects missing claims, and rejects alg none. Follow the installed GPT-5.6 routing policy exactly. The specialist must return Evidence:, Verification:, and Uncertainty:. After verifying it, reply exactly ROUTER_DELEGATED_OK.

6. Confirm `Sol High Fast` or the truthful current speed label, one `gpt56_sol_judge` child, Sol/high attestation, inherited speed, zero continuations, `COMPLETE`, zero violations, and `ROUTER_DELEGATED_OK`.
7. Purge test ledgers if desired, deactivate the agents, and confirm owned files are removed or reviewed originals are restored.

On native Windows use `py -3` where `python3` is unavailable. Exercise the Windows lock, atomic replacement, rollback, reparse-point, and hardlink cases through the automated suite before accepting the host.

## Desktop plugin smoke

1. Install or enable the exact candidate, then fully start a new Desktop task so discovery is not inherited from an older task.
2. Open `/hooks`, inspect the exact five entries, and trust them. Changed definitions must require renewed trust.
3. Activate the five custom agents from the exact installed cache and run `scripts/check_hooks.py`.
4. Submit the same bounded security prompt above in the new Desktop task.
5. Record the visible route, final response, and ledger evidence using the same acceptance criteria as CLI.
6. Test Fast on and off in separate fresh tasks. The router must preserve the task's setting and must never claim UI attestation when only persisted configuration is available.
7. Deactivate the agents before uninstalling the plugin.

Desktop acceptance is manual when UI automation policy prevents another Codex task from controlling the Codex app. Do not replace this row with a CLI run against the bundled Desktop binary.

## IDE standalone smoke

IDE extensions do not currently load plugin hooks. Use a fresh `CODEX_HOME`, extract the archive, and follow `STANDALONE.md`:

1. Check inactive status, install, and repeat install to prove idempotence.
2. Start a new IDE task and confirm `$route-gpt-5-6-work` discovery.
3. Activate the five custom agents and require `ADVISORY` plus `STANDALONE_ADVISORY`; never report full hook enforcement.
4. Run a bounded routing prompt and confirm the route advice is truthful about its advisory state.
5. Repair, deactivate, uninstall through the durable controller, purge controllers from the trusted extracted archive, and confirm the skill and agent targets are absent.

## Failure handling

Preserve failed ledgers and minimal redacted evidence. Do not weaken role, model, effort, speed, worker-cap, ordering, mutation, or return-contract checks to make a host pass. Record the candidate as rejected, fix the source, stamp a new cache version, and repeat acceptance on the new exact build.
