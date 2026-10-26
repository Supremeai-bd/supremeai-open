# 🌉 Bridge Work Order — [P1] Fix: streaming chat, retry discipline and typed errors for the shared client service (fix for #1333, r3)

Parent issue #1333 / bridge-20261027-client-streaming-retry. This is the **r3 resubmission** of the rejected order #1373 (bridge-20261027-fix-1333-client-streaming-r2).

## Why r3 exists
r2 carried the same code but used the default full_file ingress on an **existing** tracked file
(`packages/shared-services/src/services/SupremeAIService.ts`). The intake rendered it as a create-file git patch, and landing failed with
"already exists in working directory" (verdict on #1373, 2026-10-26T19:22Z). Per the bridge
contract ingressModes (#539), existing files must go as `unified_diff` against the branch tip —
that is exactly what this order does. The diff base was re-fetched from the monorepo tip the same
day as submission (blob SHA b6cfa2e5), so it applies cleanly.

## What the patch does (unchanged from r2)
1. **streamChatMessage()** — native fetch + ReadableStream SSE against POST /api/v1/stream/chat,
   mirroring studio's secureSse.ts patterns; zero new dependencies.
2. **requestWithRetry()** — x2 exponential backoff + jitter on network/5xx/429; AbortController
   plumbed through; overall budget 120s (Render cold starts exceed the old 10s default).
3. **Typed ApiError** replaces silent catch-swallowing; error channel stays leveled.
4. **getInlineCompletions** — prefix-hash cache + capped prefix payload (FIM endpoint remains a
   backend follow-up).

## Status of sibling fixes (context)
Of the 15 artifacts filed in the 20261027 A-to-Z series, 12 are already landed on main by the
intake coder lane (redis attribution guard, tower audit honesty, core hygiene set, health
alarm-hygiene pair, memory sidecar, tenant kit, studio size guard, verdict-executor template,
conformance self-test). Knowledge-loop is in constitutional gates (private PR #332). This
streaming client is the last unlanded artifact — and the one with the largest user-facing impact
(streaming responses, sane timeouts, honest errors).

## Labels
`bridge:queued` `P1-high` `area:shared-services` `handoff:coder`
