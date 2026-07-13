# Local routing data and privacy

Plugin hooks keep one JSON ledger per routed turn under `${PLUGIN_DATA}/router-state-v2`. The directory and files are user-private where the host filesystem supports POSIX modes.

Ledgers contain opaque session and turn identifiers; the selected route and orchestration plan; task-profile categories and signal names; custom-agent identifiers, lifecycle status, and model/configuration attestation; mutation and verification counters; violations; timestamps; and routing-council recommendations when used. They do not contain prompt text, assistant responses, tool output, prompt hashes, or other prompt-derived digests.

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
