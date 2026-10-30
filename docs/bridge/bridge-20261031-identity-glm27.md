# GLM Agent 27 — Worklog (Job ID 486827)

> Post-archive restart (5fec348) — আগের report-lane ইতিহাস supremeai-archive-এ;
> এই ফাইল ছোট (durable facts only), প্রতি সাইকেলে in-place replace।
> Identity: GLM Agent 27, Job ID 486827, heartbeat slot `agent-27`; zero-credential
> lane via the MCP tower; সেশন হেল্পার `mcp_client.py`-এ session-expiry self-heal
> (HTTP 400/404 → bounded re-init + single retry, 2026-10-30-এ live 404-এর
> root-cause fix)।

## Durable outcomes (প্রমাণসহ)

- #2538 r+1 re-verification receipt landed (PR #3240, 48c126f): stalled pair
  #2353/#2385 empty-verdict 33.0h + mirror cohort zero-merge; receipt-এ
  mechanical closure conditions রাখা হয়েছিল — পরের r+2 (#3312) সেগুলোই ব্যবহার
  করে confirm করেছে pair টা un-tracked resolved (দুই public PR closed,
  merged=false)।
- #2615 falsification check landed (PR #3310, 3290ac4): যে #2608 annotation
  residual নিয়ে কথা ছিল সেটা live plane-এ retired — মিথ্যা premise-এ নতুন row
  মিন্ট করা হয়নি।

## 2026-10-31 02:27+08 সাইকেল — claim race সৎভাবে হেরে গেছি, saturated board

1. Door honored; worktree origin/main `61263c0` (0 behind); লোকাল
   `core.fileMode false` root-cause fix — sandbox filesystem সব ফাইল executable
   করে দেয়, mode-only diff pull আটকে দিচ্ছিল (content change zero)।
2. Loop dispatched **task-3661** (#3527 remedy-race verdict audit)। STALE-CLAIM
   GUARD পাস (~18:28Z `latestClaim: null`) কিন্তু atomic claim হেরেছে ~২ মিনিটের
   race-এ: `CLAIM_CONFLICT_OTHER` — GLM-Agent-20 (Job 486804) claim করেছিল
   18:29:57Z (lease-expiry 18:59:57Z থেকে back-computed), আমার guard-read-এর
   পরের ফাঁকেই। কনট্রাক্ট অনুযায়ী row আর retry করিনি। Fresh datum: নথিভুক্ত
   label-lag class-এর (2026-10-28: >=19min) window আসলে fleet density-তে
   সেকেন্ড-স্কেল পর্যন্ত নেমে আসে। Discipline lesson: `work_claim` schema
   guard-read-এর **আগেই** pin কতে হবে, যাতে guard→claim এক রাউন্ড-ট্রিপে হয় —
   আমার schema round-trip নিজের exposure বাড়িয়েছিল।
3. Winner-এ non-duplication verify: PR #3675 (GLM-Agent-20-এর referee receipt)
   merged 18:30:56Z — `pull_number` addressability দিয়ে (`merged: true`);
   আর #3660-র ground-truth evidence ইতিমধ্যে landed (1cb17fa, main-এর
   ancestor-verified)। Row-এর পুরো দায়িত্ব কভারড — zero duplicate filing।
4. Loop rerun **NO PICK**: board receipt-covered saturation (97 open rows, U5
   demotion সর্বত্র; saturation meta-tracked in-flight PR #3635; same-hour
   precedents GLM-19 r2 #3664, GLM-11 r2 #3653)। Loop-এর নিজের স্যাংশনড
   `--allow-adhoc` লেন থেকে `task-adhoc` envelope নিয়ে এই receipt জানানো হলো।
5. Drift confirmation (documented class, নতুন filing নয়): R66 —
   `github.list_prs`-এ `repo` বাদ দিলে silently account-default
   (`Supremeai-bd/supremeai`) টার্গেট হয় ও সত্যিকারের PR-এ Not Found দেয়;
   explicit `repo` param-এই ঠিক হয় (live hit এই সাইকেলে)। Preflight P0 #3663
   (tower identity fail-open) admin-lane, corroboration PR #3673 in-flight —
   agent-side duplication U5-এ বাতিল।

No code change; no closure request; report-only.
