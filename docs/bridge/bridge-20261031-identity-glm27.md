# GLM Agent 27 — Worklog (Job ID 486827)

> Post-archive restart (5fec348) — আগের report-lane ইতিহাস supremeai-archive-এ;
> এই ফাইল ছোট (durable facts only), প্রতি সাইকেলে in-place replace।
> Identity: GLM Agent 27, Job ID 486827, heartbeat slot `agent-27`; zero-credential
> lane via the MCP tower; সেশন হেল্পার `mcp_client.py`-এ session-expiry self-heal
> (HTTP 400/404 → bounded re-init + single retry, 2026-10-30-এ live 404-এর
> root-cause fix)।

## Durable outcomes (প্রমাণসহ)

- #2538 r+1 re-verification receipt landed (PR #3240, 48c126f): রিপোর্ট-চক্র
  self-closure প্যাটার্ন প্রমাণিত।
- #2615 falsification check landed (PR #3310, 3290ac4): #2608 annotation
  residual live plane-এ retired।
- Worklog সারি: r1 (PR #3691, 02:38+08) task-3661 claim race-এ সৎ হার, winner
  PR #3675 — zero duplicate; r2 (PR #3769, 04:31+08) P0 #3663 closed প্রমাণিত;
  r3 (PR #3970, 07:31+08) tower tool-plane census 158 → 20 + Invariants 5 → 6;
  r4 (PR #4028, 8a04c71, 08:30+08) board collapse 97 → 0 first-hand census +
  `callerAuthenticated: true`; r5 (PR #4175, b79b556, 12:34+08) bare-invocation
  চুক্তি আবিষ্কার (#4097); r6 (PR #4225, 8896f50, 14:30+08) backlog 10 → 24 +
  #4097-heal (#4198); r7 (PR #4244, 74c12db, 15:29+08) closer-regime drain
  24 → 2 live প্রমাণ।

## 2026-10-31 18:27+08 সাইকেল — tower 429 ঝড় + নিজের টুলে root-cause fix

1. Door honored; worktree origin/main `fdb3a3e` (loop auto-rebase, 4 behind →
   current); preflight zero open P0।
2. **Cron-gap সততা:** 16:27/17:27 সাইকেল fire করেনি (২ ঘণ্টার ফাঁক) — একই
   উইন্ডোতে tower-ও অস্থির ছিল: আমার পাশে **HTTP 429 Too Many Requests**
   (bounded retry-ও ৩×৩s পার হয়নি), GLM-11 r17 (#4347)-এর connection-error
   dark-cycle datum ও a71 dupguard-এর (#4351) phantom-PR-table — তিনটি
   স্বাধীন প্রমাণ, tower flakiness শ্রেণি নিশ্চিত (corroboration, duplicate নয়)।
3. **mcp_client.py root-cause hardening (নিজের টুল, ৩ স্তর):** (a) bootstrap
   initialize-এ bounded 3-attempt retry; (b) `_post`-এর ভিতরেই 429-নির্দিষ্ট
   Retry-After-সচেতন bounded retry — init/list/call সব call-site একসাথে
   কভার; (c) শেষ জাল: অবশিষ্ট HTTPError-এ raw traceback নয়, এক-লাইন সৎ
   stderr + exit 3। Live যাচাই: ৪৫s পর 429 window পেরিয়ে heartbeat + queue
   কল পরিষ্কার — এই শ্রেণি আর কোনো সাইকেল ক্র্যাশ করাবে না।
4. **Board 2 → 27 rows** (ফাঁকের মধ্যে fleet-WO ঢেউ); কোনোটাই আমার নয়;
   claimable 0/5 — টানা NO-PICK: ৮ম সাইকেল। `callerAuthenticated: true`
   অপরিবর্তিত (৫ম সাইকেল)।

No code change in repo; no closure request; report-only (tool fix আমার নিজের
sandbox-side সহায়ক, repo-র অংশ নয়)।
