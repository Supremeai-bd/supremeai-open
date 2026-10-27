# fix(client): [P1] streaming chat client — full-file create lane per bridge guidance (#1333, follows #1442/#1445-verified patch)

## Context
The verified streaming rework of the platform-agnostic SupremeAI service has been
blocked from landing twice by bridge tooling: unified_diff requires the path to
exist on the open-repo patch branch (it is monorepo-only), and #1442 shipped the
ready patch as docs. The bridge now instructs: "use mode full_file to create it."
This order does exactly that — full content of the patched file, produced by
applying the byte-identical r4 diff to the current monorepo file (sha b6cfa2e5).

## What this file is
packages/shared-services/src/services/SupremeAIService.ts — 603 lines (was 339):
1. streamChatMessage(): native fetch + ReadableStream SSE parsing — token-level
   streaming for VS Code extension and Electron desktop (studio's separate copy
   already has this rework in production).
2. Exponential backoff retry on 429/5xx/network (3 attempts), honoring Retry-After.
3. 60s default timeout (was 10s), AbortController-based cancellation.
4. Errors surfaced as structured results instead of swallowed catches.

## Verification
- r4 diff applied with patch(1) cleanly onto the exact current file; result
  parsed with TypeScript 5.9.3: 0 syntax diagnostics.
- Byte-level: this content IS the r4 patch result (same bytes the earlier
  tsc-verified r3 produced).
- Design validated in production by the landed studio copy.

## Acceptance criteria
- [ ] Monorepo packages/shared-services/src/services/SupremeAIService.ts carries
      streamChatMessage (sha no longer b6cfa2e5)
- [ ] VS Code extension chat streams tokens (workspace re-export consumer)
- [ ] Retry/timeout behavior per above; no regression in studio

## Reflection Evidence
**Why:** The last non-streaming consumer path is a P1 with a verified fix
waiting since r3; using the bridge's own suggested create-lane removes the
tooling blocker instead of leaving a docs-only artifact.
**Alternatives rejected:**
- Wait for a bridge lane-gap fix (#1442 remains as the fallback artifact):
  leaves the P1 open with no timeline.
- Submit another unified_diff: just failed — the existence check runs against
  the open-repo patch branch where the monorepo-only path cannot exist.
- Surgical partial rewrite: riskier than shipping the proven full file.
