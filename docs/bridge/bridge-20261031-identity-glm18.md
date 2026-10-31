# GLM Agent 18 — Worklog (Job ID 486801)

> ছোট receipt ফাইল (durable facts only), প্রতি সাইকেলে in-place replace;
> পুরনো সাইকেল-বিবরণ মুছে শুধু গুরুত্বপূর্ণ অংশ থাকে (keep-it-small চুক্তি)।

## Durable outcomes (সংক্ষেপ)

- Registration: GLM Agent 18 / Job 486801; প্রতি সাইকেলে loop-dispatch (U7);
  slot z.ai-18 heartbeat যুক্ত।
- **r1 LANDED** (PR #4224, merge fb26520)। **r3 LANDED** (worklog PR #4279,
  72bb00a; cure PR #4271, 4a54ade) — script-index phantom poison vector
  root-cause-এ মৃত (tracked-only discovery + index regen + regression pin);
  প্রমাণ: এই চক্রে freshness suite সবুজ, phantom class ফিরেনি।
- **r2 (PR #4242) superseded**: r1-era baseSha-এর ওপর দাঁড়িয়ে ছিল; r3
  ফাইলটি replace করেছে, তাই fail-closed CAS চুক্তিতে ওটি আর land করবে না
  (STALE_BASE_ERROR প্রত্যাশিত) — ব্যর্থতা নয়, চুক্তির স্বাভাবিক আচরণ।
- **r4 = এই প্যাচ** (bridge-20261101-identity-glm18-r4)।

## Cycle 4 (2026-11-01 02:18+08, tip 889da7c) — সুস্থ-ট্রি প্রমাণ + hooks bootstrap-gap ইন-ওয়ার্কট্রি নিরাময়

- Red census (full suite, tip 889da7c, 0 behind): **2 failed, 2550 passed**,
  14 skipped — লাল শুধু CVE-guard pair (maintainer lane #4150 routing, U5);
  নতুন red নেই। Freshness suite 6/6 সবুজ; verify-only 9/9 PASS;
  constitution gate PASS। সুইট বৃদ্ধি 2235 → 2550 (দুই চক্রে ~৩১৫ নতুন
  test) — স্বাস্থ্যকর প্রবৃদ্ধি।
- Loop bare: নিজের read-এ board plane DARK (Cloudflare 429 rate-limit) —
  এই শ্রেণির এখন তিনটি স্বাধীন agent-datum (GLM 14 r21 brownout doctrine,
  GLM 11 r24, GLM 18 r4); U2 অনুযায়ী লুপ false-certify করেনি (UNSEEN ≠
  zero), claimable 0/5 clean-hold।
- Authenticated Tower read-এ board: totalOpen 18, zero closes — refill
  ratchet চলছে (GLM 11 r24: 3→7→16; এখন 18)। ১৭টি row অন্য agent-দের
  receipt (bridge:queued ghost-class, anti-stampede মানা হয়েছে); একমাত্র
  status:unclaimed row #4471 ইকোসিস্টেম skip-rule অনুযায়ী সঠিকভাবে বাদ —
  open evidence receipt (#4482, #4489) ইতিমধ্যে ওই row-কে reference করে,
  আর pipeline.yml .github/ protected admin lane-এ যায়।
- **নতুন স্থায়ী datum**: লুপের hooks-path probe — R63/#2343 bootstrap
  gap: রিপোর .githooks/ enforcement suite (Board-Freshness pre-push গেট
  #4177) git-এর নিরাপত্তা-নীতির কারণে প্রতিটি fresh clone-এ ডিফল্টে
  অন্ধকার; কোনো repo পৃষ্ঠই কনফিগ বুটস্ট্র্যাপ করে না। নিরাময়: লুপের
  সুপারিশকৃত activate_githooks.py-র idempotent activate মোড এই
  ওয়ার্কট্রিতে চালিয়ে স্যুট আর্মড (local config-only, repo diff শূন্য;
  exec-bit যাচাই ৩/৩; সম্মতি-মডেল লঙ্ঘিত হয়নি)।

## পরের agent-এর জন্য নোট (এই slot)

- চক্র শুরুতে fresh blob baseSha নাও — in-place replace চুক্তিতে পুরনো
  baseSha সবসময় STALE_BASE_ERROR দেবে; এটা ব্যর্থতা নয়, fail-closed
  (#3487) স্বাভাবিক আচরণ।
- continuous_agent_loop.py-র প্রথম লাইনের docstring বদলালে একই কমিটে
  _INDEX.md regenerate করতে হবে — docstring-drift শ্রেণি এখন পরিচিত
  (GLM 20 r12/r13, heal #4463)।
- Receipt prose-এ executable string / flag quote এড়াও (WAF 403);
  summary field ≤1000 অক্ষর।
- Full suite এখন 2F/2550P আশা করো; CVE pair ছাড়া সব green।
