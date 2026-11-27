# Installation and lifecycle

This page covers the plugin workflow for hosts that expose trusted hooks and
native child execution. v0.3.0 is a public prerelease. One
macOS CLI execution of an earlier payload is demonstrated; Desktop credential
inheritance and Linux/Windows real-host execution remain unverified. Python
3.10–3.14 is the CI target, not proof of every host surface. The bundled legacy
custom-agent TOMLs are not required. Non-plugin surfaces use
[Standalone advisory mode](STANDALONE.md), not full hook-driven routing.

## Configure v0.3.0 AI routing

After installing the pinned prerelease and reviewing its bundled hooks below,
run from the installed plugin root:

```sh
python3 scripts/autorouter.py models
python3 scripts/autorouter.py setup
python3 scripts/autorouter.py status
```

Setup asks for the API classifier, credential environment-variable **name**,
executor model/effort allowlist, fallback and explicit API-billing consent. Include
the actual root pair if it should be allowed to stay direct. No fixed model family
is required in configured mode. Catalogue availability is advisory; native Codex
validation and session policy ultimately accept or reject a child. A returned
selection is not execution evidence.

Provision the named variable in the environment that launches Codex. Never place
its value in setup/config JSON, task text, Git or logs. A running Desktop cannot
inherit a later Terminal export; see [TRIAL.md](TRIAL.md) for an explicit relaunch
procedure. Setup does not provision credentials or change global model settings.
Classification uses separately billed OpenAI API credits, not Codex subscription
allowance. Check account-side credit balance, payment/recharge controls and current
pricing before opting in; a timeout or local budget estimate is not a hard cap.

To disable AI classification, repeat the supported setup command with
`--disabled` instead of `--enabled`; preserve the desired allowlist/fallback.
This disables paid classification, **not the plugin's legacy deterministic
routing**. To disable all router hooks, disable the plugin through Codex or remove
it using the uninstall steps below. Neither operation changes the root model.
Status/health do not run inference. New setup deadlines default to ten seconds
and support 1–30 seconds with no automatic retry.

## Experimental direct execution

Use a Codex CLI whose App Server supports thread-local config overrides and
thread-scoped hook inspection. The checked protocol schema is Codex CLI 0.170.0.
Use your existing Codex ChatGPT sign-in and an enabled schema-v2 Auto Router
configuration. Set the classifier credential as for configured routing.

    python3 scripts/autorouter.py run "Investigate this issue" --cwd /path/to/workspace

The current directory is the default workspace. Use --config to select an
existing routing configuration file. The task is classified once, and an
approved explicit model directive can skip the classifier API call. A fallback
may be selected only by the existing classifier before the turn is submitted.

The CLI starts a short-lived App Server and an ephemeral thread. It disables
discovered Auto Router plugin IDs in the thread's config and requires a
successful check for inactive Auto Router hooks before sending the original
task. The turn's disabledPluginIds field also records the selection. In Codex
0.170.0 that field alone does not filter plugin capabilities. Other Codex
settings, including the effective sandbox and approval policy, are inherited.
The classifier credential is removed from the executor environment. Codex
uses its existing ChatGPT authentication.

The command grants no approvals or new permissions. Approval requests end the
run. Use Ctrl+C to request interruption of the bound turn. The JSON receipt
reports requested settings, native reroutes, completion, available usage and
answer text. Keep the receipt private if the answer contains workspace data.

- Exit 0 means Codex completed the turn with no observed reroute or settings
  mismatch. Runtime attestation is reported separately.
- Exit 1 means execution failed or exact-model acceptance failed.
- Exit 2 means the command input, configuration or route was rejected.
- Exit 130 means the user interrupted the command.

The current protocol exposes submitted and effective settings and can report
native reroutes. Those settings do not attest which model or effort served
inference. Runtime identity and effort remain unverified without independent
evidence. Automated tests use offline protocol fixtures. Live acceptance on
Codex CLI 0.170.0 covered a deterministic reply and an independently verified
file edit. Other Codex versions and operating systems still need live testing.

## Legacy deterministic mode: select the cheap root once

Select **GPT-6 Luna** in Codex Desktop before starting a new task. For a personal CLI default, use top-level Codex configuration:

```toml
model = "gpt-6-luna"
model_reasoning_effort = "low"
```

Low is the preferred initial effort, not an immutable requirement. If controlled acceptance shows that Luna Low cannot reliably follow routing instructions, create bounded child contracts, or synthesise escalated results, compare Luna Low with Luna Medium before changing the recommendation.

This is a user-controlled one-time selection. Autorouter never edits global/root model configuration, and install, update, activate, deactivate, repair, and uninstall never claim to configure Luna.

## Install the immutable reviewed release

Use the published `v0.3.0` tag:

```bash
codex plugin marketplace add anthonypaddison/Codex-Autorouter --ref v0.3.0
codex plugin add gpt-5-6-router@codex-autorouter
```

After the experimental tag is published, use its immutable ref instead:

```bash
codex plugin marketplace add anthonypaddison/Codex-Autorouter --ref v0.4.0-experimental.1
codex plugin add gpt-5-6-router@codex-autorouter
```

To roll back, remove the installed plugin and marketplace, then use the published `v0.3.0` commands above.

Do not substitute `main`: a moving branch does not identify the reviewed bytes. Start a new task after installation or update so Codex reloads plugin skills and hooks.

## Hook review by version

Open `/hooks`, review the entries for the installed version, and trust the exact definitions. Each command should resolve to the installed plugin's own `${PLUGIN_ROOT}` or `%PLUGIN_ROOT%`.

| Version | Bundled hooks | `PreToolUse` spawn guard |
| --- | ---: | --- |
| Published `v0.3.0` | 5 | No |
| Experimental `v0.4.0-experimental.1` candidate | 6 | Yes |

Published `v0.3.0` uses Codex's native model and effort validation and checks child lifecycle evidence after spawning. When testing the experimental candidate, review the additional `PreToolUse` entry. It checks the pending native call against the authorised route before child creation. Report a guard denial and stop that spawn attempt. The [stable release gates](STABLE_READINESS.md) govern future publication.

### Check health

From the exact installed plugin root, run:

```bash
python3 scripts/check_hooks.py
```

The following cheap-root/frontier readiness descriptions apply to **legacy
deterministic mode**, not configured allowlist policy. Configured-mode checks use
the configured exact executor pairs; unknown runtime/build or entitlement stays
unproven. A conservative global `DEGRADED` result does not invalidate a separately
correlated successful child. The legacy combined check reports:

- `READY` when the current task observed GPT-6 Luna and at least one model-keyed non-stale capability receipt proves a genuine successful GPT-6 Sol or Astra escalation against the same plugin candidate and at least one matching versioned Codex runtime/build identifier;
- `DEGRADED` when Autorouter works but the observed root is not Luna, the runtime/build changed, or current escalation capability is not yet proven; a non-Luna root substantially reduces credit-saving behaviour;
- `ADVISORY` when hooks or the supported direct child path cannot enforce the complete contract.

`UserPromptSubmit.model` is authoritative for the active root on every actual turn. Root observations carry task and turn identity, and `CODEX_SESSION_ID`/`CODEX_THREAD_ID` selects current-task evidence; another task's Luna observation cannot establish readiness. Without authoritative task context the global report remains conservative. App Server and config evidence may support health reporting but cannot override hook evidence. Each GPT-6 Sol or Astra receipt binds only its exact model tier plus plugin content identity, plugin version, Codex runtime/build where exposed, Desktop or CLI host type, platform, effort intent, capability/schema signature, and timestamp. Null runtime identity never proves compatibility, and receipts older than 30 days are history rather than current capability. The check reports each tier separately and never launches an automatic paid probe.

Astra is not part of normal automatic classification. Explicit Astra requests default to Medium and may select Medium, High, Extra High, or Max; Low and Ultra are rejected. The sole automatic Astra path is an authoritative attested Sol `ROUTE_UP`, always to Astra Medium, with no automatic effort retry.

## Routing preference

Balanced is used when no preference has been stored. To select or inspect the persistent profile:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile token-saver
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile balanced
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile max-quality
python3 skills/route-gpt-5-6-work/scripts/routerctl.py profile
```

The preference is stored under `CODEX_HOME/gpt-5-6-router`, survives plugin replacement, and applies to the next new task. It does not modify the active model, root effort, or Fast/Standard setting.

## Optional legacy custom agents

Normal installation and activation do not install custom-agent TOMLs. Their absence is expected and does not cause `DEGRADED`. The files remain available only for compatibility testing or an intentionally selected older host path.

To enter that mode explicitly after reviewing every definition:

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py activate --legacy-agents
python3 skills/route-gpt-5-6-work/scripts/routerctl.py status
```

Legacy ownership conflicts fail closed. `--replace-conflicts` is available only with an explicit legacy activation after reviewing the original and bundled definitions. `deactivate`, `repair`, and modified-file preservation apply only to files previously managed through this legacy path. Legacy state never contributes to supported-path readiness.

## Update

1. Install the new reviewed immutable marketplace version.
2. Start a new task.
3. Review and trust any changed hook definitions in `/hooks`.
4. Run `python3 scripts/check_hooks.py`.
5. Expect `DEGRADED` after an observable runtime/build change until a genuine paid escalation occurs during normal or controlled acceptance work; do not probe automatically.

No lifecycle step changes the user-selected Luna root. If legacy agents were never explicitly enabled, there is nothing to activate, repair, or deactivate.

## Uninstall

If explicit legacy custom-agent mode was used, deactivate its owned files first.
If a legacy managed definition was edited, deactivation refuses to discard it.
Use `deactivate --keep-modified` when you intend to preserve that file and
relinquish ownership.

```bash
python3 skills/route-gpt-5-6-work/scripts/routerctl.py deactivate
```

From the installed plugin root, optionally purge routing ledgers before removing
the plugin. Close active Codex tasks that use the plugin first.

```bash
# Optional: purge local routing ledgers from the installed plugin root.
python3 skills/route-gpt-5-6-work/scripts/router_hook.py --purge-ledgers
codex plugin remove gpt-5-6-router@codex-autorouter
```

If you also want to remove the marketplace source, run
`codex plugin marketplace remove codex-autorouter`. Plugin removal disables
plugin-native hooks. Router setup under `CODEX_HOME/autorouter` is retained for
reinstallation. See [Local routing data and privacy](PRIVACY.md) for ledger retention.
