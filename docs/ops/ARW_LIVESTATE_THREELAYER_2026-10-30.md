# ARW Live State — Three-Layer Fix Chain Observed Live (2026-10-30, cycle 4)

- **Agent:** GLM Agent 13 (Job 486783)
- **Class:** report-only evidence receipt — zero-credential tower probes, zero claims,
  no closure requested, no auto-close
- **Subject rows:** #2557 (closed), #3093 (closed) — this receipt is the event-timed
  live-state follow-up both rows' verification criterion anticipated
- **Refs:** #2557 #3093 #2974 #3026 #2925 #3441

## 1. One-paragraph verdict

Between 15:02Z and 15:26Z on 2026-10-30 the Agent Review Workflow (ARW) outage moved
through its full three-layer chain, observed first-hand in one session: the
byte-identical `Error: SUPREMEAI_BACKEND_URL is not configured` signature that every
recorded probe since 2026-10-29 c31 returned (8+ consecutive first-hand probes across
the lane's receipts) is **gone**. Layer 1 (tower config) is FIXED, layer 2 (backend
route deployment) is FIXED, layer 3 (backend auth) is now the live, final blocker:
`Error: Backend returned HTTP 401`. The remaining remedy is one env var —
`SUPREMEAI_BACKEND_SERVICE_TOKEN` on render-mcp — derived from the deployed tower
source, not guessed.

## 2. Timeline (all first-hand this session, zero-credential)

| Time (UTC) | Observation | Layer |
| --- | --- | --- |
| 15:13:35Z | `system_health`: 19 healthy / 1 degraded / 1 unreachable; render-primary `update_in_progress` | context |
| 15:14–15:16Z | `agent_review_workflow_status` ×4 → `Error: Backend returned HTTP 404` — **first non-config-error signature in the incident's recorded history** | L2 surface |
| 15:1xZ | `render_get_env_var_keys` (render-mcp `srv-dabm7inqj5pc738jkrt0`): **43 keys, `SUPREMEAI_BACKEND_URL` PRESENT** (the Oct-28/30 receipts' 42-key listing lacked it; service `updatedAt` 15:02:52Z = the redeploy that carried it) | **L1 FIXED** |
| 15:18:41–43Z | render-primary build logs: every heavy step `CACHED`, image exported and pushed, **zero error lines** in the 100-line build window | build plane healthy |
| ~15:21Z | `system_health`: render-primary deployStatus **`live`** (previous record: `update_failed` streak, 42nd–44th consecutive proof windows per the CI_4617 lane receipts); render-worker also `live` | **L2 FIXED** |
| 15:12:43Z / 15:18:22Z | core main CI runs 44 (`2403406`) and 45 (`059542f`) **success** — first push-plan greens after run 43 (`4d33070`, 14:32:19Z, the #3441-family red); the deploy train finally had green source to move to | corroboration |
| 15:22Z, 15:26:07–25Z | `agent_review_workflow_status` ×4 → `Error: Backend returned HTTP 401` — the route now EXISTS on the deployed backend and rejects the unauthenticated tower call | **L3 LIVE** |

## 3. Layer-3 root cause (source-derived)

1. `infrastructure/mcp-control-plane/src/tools/agent_review_workflow.tools.ts`,
   `backendRequest()`: the tower attaches
   `bearerAuth(env.backendServiceToken)` **only when the token is set**; otherwise the
   call goes out with no `Authorization` header at all, and the backend route answers
   401. `Error: Backend returned HTTP ${status}` is the tool's verbatim surface for it.
2. `infrastructure/mcp-control-plane/src/lib/env.ts` line 119:
   `get backendServiceToken(): string { return optional("SUPREMEAI_BACKEND_SERVICE_TOKEN"); }`
3. render-mcp 43-key census (names only, zero values): `SUPREMEAI_BACKEND_SERVICE_TOKEN`
   **ABSENT** — the only ARW-chain key missing, exactly where the source says it must be.

**Admin remedy (smallest safe, same one-env-var class as layer 1):** set
`SUPREMEAI_BACKEND_SERVICE_TOKEN` on render-mcp (`srv-dabm7inqj5pc738jkrt0`) to the
service token the core backend's ARW route expects (the value must match the
backend-side config); the service auto-redeploys on save. **Verification probe (the
#3093/#2557 criterion):** `agent_review_workflow_status` returning a capabilities
payload instead of an error. Until then 401 is the expected signature.

## 4. Why this is not the duplicate-evidence class

Every prior receipt in this lane documents the config-error face
(`SUPREMEAI_BACKEND_URL is not configured`). The 404 and 401 signatures, the 43-key
fix confirmation, the first `live` deploy status after the 44-window `update_failed`
streak, and the runs-44/45 green corroboration are all **first observations**,
event-timed 15:02–15:26Z, recorded once here and nowhere else. One receipt, one delta.

## 5. Governance notes

- Destructive-tool discipline honored: `action_render_deploy` was **not** invoked
  (per the RENDER_2225 build-logs-first doctrine; the build plane proved healthy on
  its own and the deploy train advanced without agent intervention).
- Env privacy: key NAMES only via `render_get_env_var_keys`; no secret value was read,
  stored, or transmitted.
- Both subject rows are closed, so this receipt files evidence, not a claim; the
  reopen/verdict decision stays with maintainers.

## 6. বাংলা ব্যাখ্যা (Bangla explanation)

আজ 15:02–15:26Z-এর মধ্যে আমি নিজে চোখে দেখলাম যে #2557/#3093-এর ARW বিভ্রাটটি
তিন স্তরের চেইন দিয়ে যাচ্ছে। প্রথম স্তর (tower-এ `SUPREMEAI_BACKEND_URL`
অনুপস্থিত) — admin সেটি ঠিক করেছেন (এখন 43-key তালিকায় সেটি আছে)। দ্বিতীয় স্তর
(backend-এ route-ই ছিল না, কারণ core main ভাঙা থাকায় deploy-train আটকে ছিল) —
আজ core-এর রান ৪৪ ও ৪৫ সবুজ হওয়ায় render-primary প্রথমবার `live` হলো, 404 চলে গেল।
তৃতীয় ও শেষ স্তর এখনও বাকি: tower যেহেতু `SUPREMEAI_BACKEND_SERVICE_TOKEN` ছাড়া
চলছে, সে `Authorization` header ছাড়াই কল পাঠায় এবং backend 401 দেয়। সমাধান
মাত্র একটি env var যোগ করা — tower-এর নিজের সোর্স কোড (env.ts লাইন ১১৯) থেকে
নিশ্চিত। এরপর একটি `agent_review_workflow_status` প্রোবই যাচাই করে দেবে।
আমি শুধু পাঠযোগ্য প্রোব চালিয়েছি — কোনো deploy trigger, secret পাঠ, claim বা
auto-close করিনি।

## 7. Rollback

git revert-safe: single new docs/ops file; zero code/config/env/workflow touch;
delete this file to fully undo.
