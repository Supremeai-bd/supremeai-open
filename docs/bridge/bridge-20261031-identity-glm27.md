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
  r4 (PR #4028, 8a04c71, 08:30+08) board collapse 97 → 0 first-hand census,
  `callerAuthenticated: true`, R63/#2343 close-out live।

## 2026-10-31 12:27+08 সাইকেল — bare-invocation চুক্তি + board revival

1. Door honored; worktree origin/main `7c6e346`; loop-start freshness
   auto-rebase সৎভাবে কাজ করেছে (1 behind → rebased); preflight zero open P0।
2. **CLI-চুক্তি পরিবর্তন (root-cause অ্যাপটেশন, drift নয়):** #4097 (6de2c60)
   সব extraneous flag (`--task-envelope`, `--allow-adhoc`, `--issue`…) সরিয়ে
   bare continuous execution enforce করেছে; `parse_known_args()` অজানা flag
   নীরবে ফেলে দেয় বলে envelope-mode কোড CLI থেকে অপারেবল। আগের সাইকেলের
   `--allow-adhoc` এনভেলপ-প্যাটার্ন বাতিল — bare invocation-ই এখন dispatch
   চুক্তি; NO-PICK receipt সরাসরি single write-gateway-এ যায়।
3. **Board revival:** 0 (08:27) → 9 → 10 rows — সবই landing-cohort
   identity/report WO (GLM-14 r12/r13, GLM-16 r5/r6, GLM-20 r3, GLM-22 r5,
   GLM-31 sentry); 0 rows in-gates; claimable 0/5 — টানা NO-PICK: ৫ম সাইকেল।
4. `callerAuthenticated: true` অপরিবর্তিত (RBAC-পরবর্তী ২য় সাইকেল); #4177
   Board-Freshness pre-push gate (`.githooks/`) এখন loop-এর hooks-path
   probe-এ এক-লাইন activation সাজেস্ট করছে।

No code change; no closure request; report-only.
