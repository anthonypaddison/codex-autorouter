# Release checklist

Record candidate-specific proof in `RELEASE_EVIDENCE.md`; never infer a checked gate from a source-only test or an older release. The planned `v0.2.0` marketplace ref is not a release until the reviewed tag exists and every required gate below is evidenced.

## Automated gates

- [ ] Plugin manifest, immutable-ref, attribution, documentation, skill, and source-integrity validation pass.
- [ ] Router, compatibility-adapter, lifecycle, health, standalone, benchmark, and release-contract tests pass on the supported Python/OS matrix.
- [ ] Deterministic routing fuzzing passes without weakening high-consequence or verification gates.
- [ ] `UserPromptSubmit.model` is authoritative in Luna, Terra, Sol, and Astra root-policy tests; config/App Server evidence never overrides it.
- [ ] Luna stays Luna for routine work, may use Terra for normal work, and may use Sol for hard work.
- [ ] Terra stays Terra for routine/normal work and may use Sol only for hard work.
- [ ] Sol never delegates downward merely to satisfy the classifier; separately justified parallel work remains bounded.
- [ ] Astra remains the final owner; generic severity, keywords, and Max Quality never select it.
- [ ] Explicit Astra defaults to Medium, accepts Medium/High/Extra High/Max, and rejects Low/Ultra without substitution.
- [ ] The only automatic Astra path is an authoritative exact-child Sol `ROUTE_UP` to Medium; insufficient evidence and automatic effort retries are rejected.
- [ ] User-intent ambiguity asks one concise clarification without escalation; technical uncertainty in an otherwise clear task can escalate.
- [ ] All direct Terra/Sol/Astra spawn construction, schema detection, capability handling, and fallback live behind the tested compatibility adapter.
- [ ] Capability receipts bind plugin version, observable Codex runtime/build, Desktop or CLI host, platform, observed child model, effort intent, schema/signature, and timestamp.
- [ ] Runtime/build mismatch changes `READY` to `DEGRADED` and no health/status path launches an automatic paid probe.
- [ ] Missing legacy custom-agent TOMLs do not reduce health; normal installation/activation does not install them.
- [ ] Explicit `activate --legacy-agents`, conflict refusal, repair, deactivation, and modified-file preservation remain isolated compatibility tests.
- [ ] `routerctl status`, standalone status, and health checks are read-only when their state/config directories do not exist.
- [ ] Installed-cache hooks execute only their exact plugin-root router, fail open with one diagnostic when unavailable, and never discover sibling caches.
- [ ] Stop and SubagentStop remain fail-open and idempotent; successful verification evidence cannot be fabricated from prose or an unobservable result.
- [ ] Standalone install/update/uninstall/durable-controller recovery/purge preserve foreign or drifted content and remain `ADVISORY`.
- [ ] Release archive contains no source-machine paths, secrets, symlinks, bytecode, or transient state.

## Real-host acceptance

Complete every row with the exact immutable marketplace snapshot or release archive. Follow `HOST_ACCEPTANCE.md` and retain the stated receipt/runtime evidence.

| OS | Surface | Exact install/cache | Hook trust | Luna root | Direct Terra/Sol | Rare Astra gate | Receipt health | Result |
|---|---|---:|---:|---:|---:|---:|---:|---|
| macOS | Desktop | required | required | required | required | required | required | pending |
| macOS | CLI | required | required | required | required | required | required | pending |
| Linux | CLI | required | required | required | required | required | required | pending |
| Windows | Desktop | required | required | required | required | required | required | pending |
| Windows | CLI | required | required | required | required | required | required | pending |

IDE extensions are excluded from full-plugin `READY` acceptance when they do not load plugin hooks. The standalone advisory skill still requires discovery, direct-adapter fallback, update, and uninstall smoke tests. Legacy TOMLs are exercised only in a separately labeled optional compatibility row.

## Policy and degraded modes

- [ ] Untrusted or disabled hooks never claim `READY`.
- [ ] Managed-hooks-only policy reports the supported unavailable/advisory state and never attempts bypass.
- [ ] A non-Luna `UserPromptSubmit.model` reports `DEGRADED` for that turn and explains that credit-saving behaviour is substantially reduced.
- [ ] Missing/stale receipt or changed runtime/build reports `DEGRADED` without auto-probing.
- [ ] Fast and effort labels never claim unavailable runtime attestation.
- [ ] Luna Low versus Luna Medium controlled acceptance is recorded if Low is unreliable; Low is not treated as an immutable architecture requirement.
- [ ] The public repository exposes a tested private vulnerability-reporting channel before broad publication.

## Distribution gate

- [ ] The reviewed commit exactly matches annotated tag `v0.2.0`.
- [ ] The archive is produced from that tag, passes clean-room validation, and has a recorded verified SHA256.
- [ ] Marketplace and privacy links resolve to the immutable tag.
- [ ] No install, activation, tag, release, publish, or merge occurred as a side effect of validation.

## Public-release decision

Do not mark stable, push the tag, or publish broadly until every required automated and real-host row has exact-candidate evidence. Any later code change requires a new version and a new review; never move an existing release tag.
