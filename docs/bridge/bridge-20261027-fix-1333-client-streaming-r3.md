# 🌉 Bridge Work Order — [P1] Fix: streaming chat, retry discipline and typed errors for the ROOT shared-services package (fix for #1333, r3)

Parent issue #1333 / bridge-20261027-client-streaming-retry. Third attempt: #1373 (r2) was rejected
because full_file ingress on an existing tracked file renders a create-patch that fails with
"already exists in working directory"; the first r3 attempt with unified_diff was rejected because
the patch-branch existence check runs against the PUBLIC repo tip, where
`packages/shared-services/src/services/SupremeAIService.ts` does not exist (the public mirror only has the
nested `studio/packages/...` copy — which is already fixed). This order uses the same
established lane as the verdict-executor template: **NEW file + one-command swap**.

## Why this still matters
The streaming/retry fix already landed for the studio-nested copy
(`studio/packages/shared-services/src/services/SupremeAIService.ts` — verified on main). But the
**root** package is a separate live consumer path: `tools/vscode-extension/package.json` declares
`"@supremeai/shared-services": "workspace:^"`, which resolves to the root
`packages/shared-services` — still the pre-fix client (no streaming, 10s hardcoded timeout,
silent catch-swallowing). Every VS Code extension chat/completion call goes through it.

## Landing step (coder lane, one command, after this order lands)
```bash
git mv packages/shared-services/src/services/SupremeAIService.fixed.ts packages/shared-services/src/services/SupremeAIService.ts
```
No other edits: all pre-existing public method signatures and return shapes are preserved; the
new exports (ApiError, normalizeApiError, streamChatMessage) are additive; `src/index.ts` is
untouched. Then delete this stub work order file if desired.

## What the implementation does
1. **streamChatMessage()** — native fetch + ReadableStream SSE against POST /api/v1/stream/chat,
   mirroring studio's secureSse.ts patterns; zero new dependencies.
2. **requestWithRetry()** — x2 exponential backoff + jitter on network/5xx/429; AbortController
   plumbed through; 120s overall budget (Render cold starts exceed the old 10s default).
3. **Typed ApiError** replaces silent catch-swallowing; error channel leveled.
4. **getInlineCompletions** — prefix-hash cache + capped prefix payload.

## Verification performed on the payload
- Brace balance 0; TypeScript sanity checks; CRLF-free; base re-fetched from monorepo tip at
  r2 time (blob SHA b6cfa2e5) and byte-identical to the current unfixed root file.
- Live endpoint confirmed: the API service stream router defines prefix /api/v1/stream with a
  POST chat route (see fix evidence on parent issue #1333).

## Labels
`bridge:queued` `P1-high` `area:shared-services` `handoff:coder`
