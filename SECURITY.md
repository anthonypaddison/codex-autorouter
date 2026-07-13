# Security policy

## Report a vulnerability

Do not include secrets, private prompts, session transcripts, or customer data in a public report. After publication, use the repository's **Security → Report a vulnerability** flow and include a minimal reproduction plus the affected plugin version. Do not open a public issue for an undisclosed vulnerability.

If the private reporting button is absent or cannot be tested by the publisher, treat the distribution as private beta rather than public stable. A marketplace listing must link to the same security policy and repository.

## Security model

- Router ledgers contain opaque task identifiers and routing metadata, never prompt contents or prompt-derived hashes.
- Plugin hooks run only after Codex hook trust and can be disabled by managed policy.
- The activator writes only six allowlisted custom-agent filenames under `CODEX_HOME/agents`.
- Activation state is private, checksummed, journaled, and recovered before another lifecycle operation.
- Symlink, junction, reparse-point, foreign-file, and locally modified-file conflicts are refused by default.
- Standalone skill ownership uses an exact path/hash/mode inventory, same-filesystem staging, durable state outside the target, and fail-closed recovery that preserves post-crash edits.
- Transcript parsing is compatibility-only and is not a stable or correctness-authoritative security boundary.

No hook is an operating-system sandbox. Users must keep Codex permissions and approval policy appropriate for the task.

See `docs/PRIVACY.md` for the exact local ledger fields, opportunistic retention behavior, and supported manual purge.
