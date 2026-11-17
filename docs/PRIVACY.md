# Local routing data and privacy

Plugin hooks keep one JSON ledger per routed turn under `${PLUGIN_DATA}/router-state-v2`. The directory and files are user-private where the host filesystem supports POSIX modes.

Health evidence under `CODEX_HOME/gpt-5-6-router` contains a latest global root summary, one latest root observation per opaque task/session ID, and the latest capability receipt. Root observations contain task and turn identifiers, model, plugin identity, observable runtime identity, platform, and timestamp. Capability receipts additionally contain the correlated child agent and turn identifiers, requested/observed child model, effort evidence, and route purpose. They contain no prompt text, assistant response, or tool output. Historical receipts are retained even when they are identity-null, incompatible, or older than the 30-day readiness window.

New ledgers contain opaque session and turn identifiers; ledger-scoped event identities such as `event-000001`; opaque host lifecycle-event identifiers when Codex supplies them, including mutation-generation call bindings; the selected route and orchestration plan; task-profile categories and signal names; custom-agent identifiers, lifecycle status, and model/configuration attestation; mutation and verification counters; transcript-reconciliation status plus record/byte counts; violations; timestamps; and routing-council recommendations when used. Event identities are allocated from non-content state and are never derived from prompt, assistant, or tool-output contents. New ledgers do not contain transcript paths, prompt text, assistant responses, tool output, prompt hashes, or other content-derived digests.

Historical ledgers created by affected earlier builds can contain a truncated SHA-256 `event_key` derived from child prompt material. This release does not silently rewrite or delete those records. It recognises that legacy format, refuses to treat it as current-format capability proof, and lets the existing 14-day opportunistic retention or the explicit owner-checked purge remove it. No historical purge is claimed unless the purge command is run and its result is verified.

The persistent routing preference file contains only a schema version and one enum value: `token-saver`, `balanced`, or `max-quality`. It contains no prompt, task, model transcript, account, or usage data. The hook launcher may also create one empty `.gpt56-stale-hook-reported` marker in plugin data after a missing-cache failure so that the diagnostic is emitted only once.

Ledgers older than 14 days are removed opportunistically when a later user prompt reaches the router. If no later prompt occurs, metadata can remain until manual cleanup or plugin-data removal. Each state directory has a private ownership marker, and each ledger carries that installation's random ownership nonce. Purge refuses an unmarked or mismatched directory. To remove all valid router ledgers immediately while preserving unrelated or malformed JSON files, pass the exact state directory reported for the installed plugin:

```bash
CODEX_ROUTER_STATE_DIR="/absolute/path/to/plugin-data/router-state-v2" \
  python3 skills/route-gpt-5-6-work/scripts/router_hook.py --purge-ledgers
```

Run that command from the installed plugin root before uninstalling if you want an explicit cleanup result. Do not guess the state path; the command fails if no explicit plugin-data or state-root environment value is present. It serializes with hook writes, deletes only ledgers matching the root's private owner nonce, retains the ownership marker and lock file, and reports the number removed.

Standalone advisory mode has no plugin hooks and does not create routing ledgers. Its lifecycle state contains only target-bound ownership inventories, versions, transaction metadata, and durable controller copies.

### Private-beta state migration

Builds before the ownership-marker hardening used an unbound `router-state` directory. This release deliberately starts in `router-state-v2`; it never claims, migrates, or deletes the old directory automatically. After upgrading, confirm the new router is healthy, then archive or remove the old `router-state` directory manually if you no longer need its routing metadata. If you set `CODEX_ROUTER_STATE_DIR` yourself, update it to a new empty absolute directory before enabling this build.

Checksums protect lifecycle consistency and ownership decisions; they are not cryptographic authentication against another process already running as the same operating-system user.
# Configured AI routing candidate

Setup stores only the provider, credential environment-variable name, enabled
flag, exact model identifiers, allowed efforts, fallback and classifier timeout
in `CODEX_HOME/autorouter/config.json`. It rejects
unknown configuration fields and never stores credentials. Reconfiguration
preserves an owner-only byte-exact backup. It does not edit global Codex settings.
Status reports only whether the configured credential variable's name is present
in that command's environment. It does not print its value, validate the key,
prove a billing organisation, or attest a different Desktop process's environment.

When explicitly enabled, classification sends the bounded supplied task and
executor allowlist to OpenAI's Responses API. It does not read repository files,
transcripts or saved Codex/ChatGPT authentication. Its only credential source is
the explicitly configured API environment variable. The Python HTTP worker
inherits that credential and required OS metadata, not unrelated environment
secrets. No credential or prompt is put in argv or written to temporary files.
Requests explicitly exclude tools and use `store:false`; this is not a claim
that provider abuse-monitoring retention is disabled. Provider data controls and
the user's API account apply, separately from Codex authentication/allowance.
Development tests use fake keys and mocked HTTP only.

The classifier's short rationale is schema-validated but deliberately discarded:
it can paraphrase private prompt content. Ledgers retain only selected model and
effort, classifier provider/model/effort, fixed reason/status codes, elapsed milliseconds, request attempts
and observed numeric token counts. Invocation attempts are not billed-request
counts. A reserved interrupted attempt has unknown call count, not a claimed
zero. Missing usage is unknown, not zero; cached input is already part of input.
Delegation outcome records contain only opaque call IDs, selected model/effort
and fixed outcome categories. Native error bodies and available-model text are
not persisted. HTTP error bodies are never read or logged.

Configured roles/settings fingerprints derive only from model/effort choices and
configuration, never prompts. Existing no-raw-prompt/no-transcript-path ledger
rules and independent execution evidence requirements still apply. Model
selection does not authorize additional filesystem/network access or permission
changes. The root and child lifecycle evidence remains independent of the API
classification result. No gateway, proxy, database or external router service is
introduced.
