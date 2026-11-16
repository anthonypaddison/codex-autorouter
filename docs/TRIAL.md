# Limited v0.3.0 normal-use trial

## Scope of acceptance

The accepted CLI payload was
`sha256:46a2e7837fad421bc95ee545de509fadb9f4534162267735f6fa5dfa20754448`.
On 16 November 2026, Luna/Low automatically classified one harmless task, selected
Terra/Medium, spawned exactly one matching child, received the correct result
10, and completed with a consistent child attestation and zero violations.
Classifier latency was 5.642154 seconds; total task duration was 25.440 seconds.
Classifier usage was 299 input and 186 output tokens, with zero cached input.
There is no recorded rate card or authoritative dollar debit for that execution.

The finalised source adds setup timeout controls and root-allowlist guidance.
These changes are mock-tested. They have not been reinstalled or subjected to
another live test. Keep the accepted installation unchanged until an explicit
update. A manifest version alone is not payload identity or release approval.

## Root selection and timeout

Include the current root model and effort in the executor allowlist if ordinary
work should be allowed to stay current. If a model already has an entry, extend
that entry's effort list rather than adding a duplicate. The classifier remains
free to select any permitted pair; exact root matches stay direct. A different
effort on the same model is not an exact match. Native execution restrictions,
explicit preferences and the no-recursion/no-retry contract are unchanged.

The setup wizard and `--timeout-seconds` accept 1–30 seconds, defaulting to ten
seconds. The UserPromptSubmit hook allows 35 seconds for classification plus
local bookkeeping. Timeout still terminates the one HTTP worker and records the
configured fallback without retrying. A timed-out request may still be billed.
Existing six-second configurations remain valid and are not changed implicitly.

## Explicit local activation of a finalised commit

Do this only when ready to update, with other affected Codex work quiescent.
These are operator steps, not commands run automatically by finalisation.
Stop on any command error; never continue from a partially staged installation.
Do not create or fetch an unpublished release tag to install this local trial.

From the reviewed repository root, use the bundled CLI and identify the existing
local marketplace root. Set `previous_marketplace` to the root printed for
`codex-autorouter-local`; do not guess it.

```sh
codex_cli='/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
"$codex_cli" plugin marketplace list
git rev-parse HEAD
git diff --exit-code
```

Create a fresh staging/rollback directory. The snapshot includes committed files
only, never `.trigger-tree/`, credentials, or untracked acceptance settings.
The existing local marketplace manifest must use the relative plugin path
`./plugins/gpt-5-6-router` and marketplace name `codex-autorouter-local`.

```sh
test -d "$previous_marketplace/plugins/gpt-5-6-router"
trial_dir=$(mktemp -d "$HOME/.codex/diagnostics/autorouter-v030-final.XXXXXXXX")
chmod 700 "$trial_dir"
cp -p "$HOME/.codex/config.toml" "$trial_dir/config.toml.before"
cp -p "$HOME/.codex/autorouter/config.json" "$trial_dir/autorouter-config.before.json"
cp -pR "$HOME/.codex/plugins/cache/codex-autorouter-local/gpt-5-6-router/0.3.0" "$trial_dir/cache.before"
mkdir -p "$trial_dir/marketplace/.agents/plugins" "$trial_dir/marketplace/plugins/gpt-5-6-router"
cp -p "$previous_marketplace/.agents/plugins/marketplace.json" "$trial_dir/marketplace/.agents/plugins/marketplace.json"
git archive --format=tar --output="$trial_dir/candidate.tar" HEAD
tar -xf "$trial_dir/candidate.tar" -C "$trial_dir/marketplace/plugins/gpt-5-6-router"
"$codex_cli" plugin marketplace remove codex-autorouter-local --json
"$codex_cli" plugin marketplace add "$trial_dir/marketplace" --json
"$codex_cli" plugin add gpt-5-6-router@codex-autorouter-local --json
```

Record the installer's exact root, compare its shipped-payload identity with the
reviewed source, and inspect/trust changed definitions through `/hooks`. Never
use a hook-trust bypass. The same 0.3.0 cache path can contain different bytes;
current processes are not proof that the new candidate was loaded.

Run the supported setup command from that installed root. For a Luna/Low root,
the trial configuration is:

```sh
python3 -B scripts/autorouter.py setup \
  --provider openai --classifier gpt-6-luna --classifier-effort low \
  --credential-env AUTOROUTER_OPENAI_API_KEY --enabled \
  --allow gpt-6-luna=low --allow gpt-6.1-terra=medium \
  --allow gpt-6.1-sol=medium,high --fallback gpt-6.1-sol=high \
  --timeout-seconds 10
python3 -B scripts/autorouter.py status
```

Setup itself performs no inference. Existing settings are backed up before
replacement. Changing settings invalidates in-flight configuration-bound reuse;
start fresh tasks afterward. After trust/setup, preserve the post-update baselines
for guarded rollback:

```sh
cp -p "$HOME/.codex/config.toml" "$trial_dir/config.toml.after"
cp -p "$HOME/.codex/autorouter/config.json" "$trial_dir/autorouter-config.after.json"
```

## Desktop credential availability

The existing Terminal classification and integrated CLI execution succeeded.
The audit Desktop process did not inherit `AUTOROUTER_OPENAI_API_KEY`. A reference
in `.all-env` is not an exported process environment. Do not source that entire
reference file: it may contain non-shell formats and unrelated credentials.

No supported hot-injection interface into an already-running Desktop process
was established. Do not add a secrets loader, copy authentication files, weaken
environment filtering, or set a global launchd/macOS environment variable.

For Desktop, save work, fully quit through the app menu, and confirm in Activity
Monitor that the main app and its old app-server exited. In a private zsh Terminal
run the following, entering the existing key only at the hidden local prompt:

```zsh
set +x
read -rs 'AUTOROUTER_OPENAI_API_KEY?API key (hidden): '
printf '\n'
if [[ -n "$AUTOROUTER_OPENAI_API_KEY" ]]; then
  export AUTOROUTER_OPENAI_API_KEY
  nohup "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT" >/dev/null 2>&1 &
fi
unset AUTOROUTER_OPENAI_API_KEY
```

Never paste the key into chat, command arguments, JSON or the repository. The
key must belong to the organisation with the verified included-credit grant;
environment presence alone does not prove ownership or remaining balance.
Do not change billing or purchase credits. A previously running app can absorb
and exit the new launcher without acquiring its environment.

Without quitting Desktop, a fresh interactive CLI launched from the existing
key-bearing Terminal can inherit it; use the bundled CLI's `--no-daemon` option
to avoid reusing a server with an older environment. This does not update
Desktop's environment or bypass the new session's execution policy.

Use `autorouter.py status` from the target process to inspect
`credential_environment_present`. This is a name-presence check only, not an
authentication request or proof for another process. Do not run another paid
acceptance just to refresh the already-established execution evidence.

## Trial observability from existing records

No new telemetry store or dashboard is needed. Use the installed plugin's
`${PLUGIN_DATA}/router-state-v2` ledgers. Group by `plugin_identity` and
`decision.configuration_id`, identify roots by `(session_id, turn_id)`, and count
each child UUID once. Configuration status and hook health do not replace task
execution records. Do not count `FAILED_OPEN` as user-visible task failure.
Exclude `classification.execution_reused` continuations from new selection,
latency and request metrics; report zero-call explicit preferences separately.

| Trial metric | Existing evidence and interpretation |
| --- | --- |
| Classification requests | `decision.classification.calls`: recorded attempts, not billing debits; null means interrupted/unknown, not zero |
| Successful selections | Classification `status=selected`, `reason_code=classifier_selected`; explicit preferences can select without an API call |
| Direct/delegated routes | `decision.delegate`, route and required-agent plan describe intent; actual children come from `agents` and attestation |
| Latency/timeouts | Classification `duration_ms` and `reason_code=classifier_timeout`; reused continuations are not new requests |
| Child success/failure | Child `status`, exact spawn contract, `agent_attestations`, completion match and violations; retain pending/unobservable separately |
| Model distribution | Classification model/effort versus each child's requested and observed model/effort |
| Token usage | Classification `usage`; executor `token_usage_record` joined by exact root/child session and turn; missing usage is unavailable |
| Fallback frequency | Classification `status=fallback`, grouped by reason; credential-missing fallbacks have zero request attempts |

Cached input is included in input, not added twice. The ledger's
`delegation_attempts.*.outcome` is an initial result snapshot and may remain
`outcome_unobservable` after independent lifecycle reconciliation proves
completion. Use terminal child status, attestation and root status together.
Likewise `decision.profile_satisfaction` is the initial planning state, not a
replacement for final completion evidence. Wait summaries can omit child
results that arrive separately; exact child lifecycle events are authoritative.

Ledger retention is opportunistically fourteen days. Review before data ages
out; do not silently rewrite historical ledgers. Dollar estimates require a
recorded applicable rate card. Actual subscription debit and financial savings
are unavailable without independent account/baseline evidence.

## Roll back a later finalised-candidate update

Keep the original accepted trial, source marketplace and rollback directories.
With affected tasks stopped, first check for concurrent configuration changes:

```sh
cmp "$HOME/.codex/config.toml" "$trial_dir/config.toml.after"
cmp "$HOME/.codex/autorouter/config.json" "$trial_dir/autorouter-config.after.json"
```

If either differs, stop: preserve unrelated edits and reconcile only the trial's
plugin/config changes. Never force-copy a stale full config. If unchanged,
reinstall the accepted source through the supported workflow below, preserve
the recreated cache, then restore the exact cache/configuration backups:

```sh
test ! -e "$trial_dir/cache.reinstalled"
"$codex_cli" plugin marketplace remove codex-autorouter-local --json
"$codex_cli" plugin marketplace add "$previous_marketplace" --json
"$codex_cli" plugin add gpt-5-6-router@codex-autorouter-local --json
mv "$HOME/.codex/plugins/cache/codex-autorouter-local/gpt-5-6-router/0.3.0" "$trial_dir/cache.reinstalled"
cp -pR "$trial_dir/cache.before" "$HOME/.codex/plugins/cache/codex-autorouter-local/gpt-5-6-router/0.3.0"
cp -p "$trial_dir/autorouter-config.before.json" "$HOME/.codex/autorouter/config.json"
cp -p "$trial_dir/config.toml.before" "$HOME/.codex/config.toml"
diff -qr "$trial_dir/cache.before" "$HOME/.codex/plugins/cache/codex-autorouter-local/gpt-5-6-router/0.3.0"
cmp "$trial_dir/autorouter-config.before.json" "$HOME/.codex/autorouter/config.json"
cmp "$trial_dir/config.toml.before" "$HOME/.codex/config.toml"
```

Do not delete ledgers or unrelated files. Reload/restart before using restored
bytes. Earlier pre-v0.3 backups are a separate rollback boundary; their guarded
scripts may refuse later config drift and must not be forced.
