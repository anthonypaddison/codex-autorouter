# Upstream Codex report: terminal-hook feedback can poison a task

## Summary

On affected Codex builds, a plugin `Stop` or `SubagentStop` hook response shaped as `{"decision":"block","reason":"..."}` is converted into a synthetic user message and persisted in the task transcript. Codex assigns that message a client-generated UUIDv7 `id`. On the next request, the Responses API rejects the replayed item because message identifiers are expected to use a server `msg_` prefix. Every later response can then fail, leaving the task unusable.

## Minimal reproduction

1. Install and trust a plugin with a terminal hook that returns `{"decision":"block","reason":"verify the final mutation"}`.
2. Complete a turn that triggers the hook.
3. Observe a persisted JSONL item shaped like:

```json
{"type":"response_item","payload":{"type":"message","id":"019f5182-a1ce-72e1-aab4-5ee0c5de861f","role":"user","content":[{"type":"input_text","text":"<hook_prompt>verify the final mutation</hook_prompt>"}]}}
```

4. Send another user turn. The API rejects the replayed client UUID because it is not a valid server message identifier.
5. The same poisoned item may also survive inside `compacted.payload.replacement_history`.

## Expected behavior

- Hook-generated feedback must not be persisted as an ordinary user-authored message with a client UUID.
- If feedback must enter request history, omit its `id` so the service can assign one, or persist the valid server `msg_` identifier returned by the API.
- A terminal-hook continuation must be marked as hook-generated and must not recursively trigger an identical terminal gate.
- Duplicate Stop delivery must be idempotent.
- Plugin cache replacement should not retain an unusable versioned hook path for an open task.

## Autorouter mitigation

Autorouter no longer hard-blocks in `Stop` or `SubagentStop`. It injects its routing contract proactively via `UserPromptSubmit` and `SubagentStart`, uses terminal events only for advisory `systemMessage` output and `FAILED_OPEN` ledger state, and ships an explicit offline sanitizer for already-persisted poison.

This mitigation prevents new Autorouter poison but cannot make terminal hard blocking safe for plugin authors generally. The complete fix belongs in Codex's hook-feedback-to-transcript conversion and replay identity handling.
