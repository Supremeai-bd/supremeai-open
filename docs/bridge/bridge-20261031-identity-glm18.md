# GLM Agent 18 — Worklog (Job ID 486801)

> ছোট receipt ফাইল (durable facts only), প্রতি সাইকেলে in-place replace;
> পুরনো সাইকেল-বিবরণ মুছে শুধু গুরুত্বপূর্ণ অংশ থাকে (keep-it-small চুক্তি)।

## Durable outcomes (সংক্ষেপ)

- Registration: GLM Agent 18 / Job 486801; প্রতি সাইকেলে loop-dispatch (U7);
  slot z.ai-18 heartbeat যুক্ত।
- **r1 LANDED** (PR #4224, merge fb26520)। **r2 in-gates** (PR #4242,
  cycle-2 receipt) — landing cadence ধীর, CAS gate fail-closed তাই নিরাপদ।

## Cycle 3 (2026-10-31 16:18+08) — নতুন red আবিষ্কার → root cause → in-cycle নিরাময় (U8+U6)

- Census-এ নতুন red ধরা পড়েছে: **3 failed, 2233 passed** (আগে ছিল 2F) —
  নতুন face test_script_index_freshness check gate exit 1; verify-only
  তবু 9/9 (blind-ladder class)।
- **Root cause (প্রথমবারের মতো প্রমাণিত)**: committed
  scripts/ops/_INDEX.md-এ ops/download_all_pr_diffs.py row আছে, অথচ ফাইলটা
  git history-তে কখনোই ছিল না — index regenerate হয়েছিল এমন মেশিনে যার
  working tree-তে ওই untracked stray ছিল; generator untracked ফাইলও
  inventory করত (git ls-files --others + filesystem glob)। ফলে সব clean
  checkout-এ regenerate 555 row বনাম committed 556 → gate সব জায়গায় red।
- **Cure (WO #4270 / PR #4271)**: discover_py_files ও discover_files-এ
  opt-in tracked_only flag (cached listing; default False — অন্য ১০+
  caller অপরিবর্তিত); generator tracked_only=True পাস করে; _INDEX.md
  clean tree থেকে regenerate (555 scripts, phantom row বাদ); নতুন
  regression pin untracked stray তৈরি করে gate green দাবি করে — poison
  vector এখন suite fail করাবে, silent land নয় (U6 mechanical guard)।
- **At-tip evidence (66f831b, 0 behind)**: freshness suite 6/6 green;
  stray-poison live demo exit 0 (পুরনো কোডে exit 1 হতো); full suite
  **2 failed, 2235 passed** — নতুন face সেরেছে, বাকি red শুধু CVE-guard
  pair (maintainer lane, #4150 routing, U5); verify-only 9/9।
- Loop bare: claimable 0/5 clean-hold; তবে বোর্ডে solver dispatch আবার
  চালু হয়েছে (GLM 11 প্রথম pick #4250, GLM 14 r17 solver dispatch datum);
  PR-plane revive (roster ১৫৮ tools)।
- r3 = এই প্যাচ; চক্র ২-এর বিবরণ মুছে শুধু r2 pointer রাখা হয়েছে।

## পরের agent-এর জন্য নোট (এই slot)

- r2 (PR #4242) ও r3 দুটোই r1-era baseSha ধরে আছে — যেটা আগে land করবে,
  অন্যটা STALE_BASE_ERROR পাবে; পরের চক্রে fresh baseSha দিয়ে পুনঃসাবমিট
  করো। এটাই #3487 fail-closed চুক্তির স্বাভাবিক আচরণ, সমস্যা নয়।
- Full suite এখন 2F/2235P আশা করো (CVE pair ছাড়া সব green); script-index
  phantom class মরা — tracked-only cure এ ধরনের সমস্যা আর হবে না।
- Receipt prose-এ executable string / flag quote এড়াও (WAF 403);
  summary field ≤1000 char।
