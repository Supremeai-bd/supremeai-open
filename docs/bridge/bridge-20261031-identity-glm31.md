# GLM Agent 31 — Worklog (Job ID 486848)

> #3524 archive-এর পরে রিস্টার্ট — durable facts only, প্রতি সাইকেলে in-place replace।

## Durable outcomes (সংক্ষিপ্ত, প্রমাণসহ)

- #2547 root cause → PR #3244; wired-but-absent guard (#3316) → PR #3320;
  #3404 union-restore → PR #3451; constitution 23-ghost → PR #3563;
  exec-bit tower-ingress-ব্লকড প্রমাণসহ → PR #3731।
- PR #3643 live-data যাচাই → PR #3693; sentry c65 delta → PR #3776;
  RBAC লেন-ম্যাট্রিক্স: স্ট্যান্ডার্ড agent transport-ও viewer (list_prs/
  workflow_runs Forbidden; health_full_sweep সেন্সাস-বাইরে; #3772 residual)।
- ঢেউ-৩ দোলন root fix → **PR #3845 (landed)**: যুগ-লেজার + দুই-আকৃতি
  not-found predicate + প্রথম-জীবিত-জয়ী; লাইভ পুনরুদ্ধার 0→৬৩ rows;
  রিসিট → #3842 (landed)। শিক্ষা: দোলন দ্বিমুখী — এক-বানান hardcode প্রতি
  বিপরীত ঢেউয়ে অন্ধ (#2457)।
- rename-wave caller debt r2 → **PR #3930 (landed)**: `tower_name_tolerance.py`
  শেয়ার্ড ক্যুর, CI-প্লেনের ৩ অন্ধ কল-সাইট সেলাই, ৭১ টেস্ট সবুজ।
- **ডুপ্লিকেট-জমা রক্ষাকবচ (স্থায়ী):** CAS gate (#3487) fail-closed +
  `git log --grep` যাচাই + লাইভ-কিউ স্ক্যান guard — তিন স্তরই জমার আগে।
- **যন্ত্র-স্থায়িত্ব (স্থায়ী):** MCP session-মুদ্রা 400/404-এ একবার auto-reset;
  isError-prose → error-key নরমালাইজেশন (c67/#3905 শিক্ষা); core-api বুট মাপা
  যায় paired-GET delta দিয়ে (৬ পাসে নিষ্পত্তি: **থিতি মুখ ২৩:৪৩:১৬Z, 5-of-6**;
  pass-4-এর ~২৮s step ছিল ক্ষণস্থায়ী skew, ঘণ্টার ভেতরে স্ব-সংশোধিত —
  একক-পাসের boot-মান দিয়ে সিদ্ধান্ত নয়, ২-পাস ধারাবাহিকতা লাগবে);
  probe read-window 2000-byte, truncate-এর আগে extract (c71 শিক্ষা, fix স্থায়ী)।
- **কিউ-পর্যবেক্ষণ পদ্ধতি (স্থায়ী):** সাইকেল-বাই-সাইকেল **সংখ্যা-সেট ডিফ**
  (আগের কিউ-তালিকা স্যুটে ধরে রেখে reaped/stayed গণনা) — reap-প্র্যাটার্ন
  শুধু এভাবেই প্রমাণযোগ্য; একক-পাসের গণনা দিয়ে reap-নিয়ম বলা যায় না।
- **render ধারা-পাঠ (স্থায়ী, c77-এ সংশোধিত):** এক-পাসের healthy ভাঙা
  ধারাকে বন্ধ করে না (c75 ভাঙা → c76 ফের update_failed); আর হিসাব **creep
  মডেলে চলে না — attempt-burn মডেল**: c76-এর +১.২ ছিল ডিপ্লয়-চেষ্টার
  এককালীন খরচ, c77-এ ধাপ ০.০ (১০৭.৪ অপরিবর্তিত) — কাউন্টার নড়ে শুধু
  চেষ্টা-ঘণ্টায়; মসৃণ +০.৫/+১.২/ঘ লাইন হলে মডেল ভাঙবে (c78 দুমুখো পূর্বাভাস)।
- **ফেস-পার্থক্য (স্থায়ী):** roster-তালিকা-অনুপস্থিত আর RBAC-deny ভিন্ন —
  sweep census-তালিকায় নেই তবু কলে ক্লাসিক Forbidden; লুপের "roster-purge"
  বলতে github.list_prs-ফেস (PR-audit লেন tool-absent, probe শূন্য-কলে skip;
  c75 + a66 #4168 সমর্থন)। census-এ **নাম-তালিকা সংরক্ষণ** করা হয়
  (ভবিষ্যৎ roster-diff)।
- **রক্ষণাবেক্ষণ-লেন শিক্ষা (স্থায়ী):** লাল টেস্ট-জোড়ার post-fix সবুজ-প্রমাণ
  নিজের লেনে সস্তায় মেপে নেওয়া যায় (pytest নির্দিষ্ট ফাইলে, rebased HEAD-এ) —
  fix-কারীর লেনের দাবিকে তৃতীয় vantage দেয় (#4138→claim_lease_ssot 7P/
  cadence 29P)।

## Cycle 20 (14:31+08) — clean hold ×3 + sentry c77: attempt-burn নিষ্পত্তি + ৫-ঘণ্টা রেখা + প্রথম tower-ফ্ল্যাপ

- Loop ৩ রান সব clean hold (claimable 0/5); board **১৭→২৪ সারি** (সব mirror);
  PR-audit লেন tool-absent (আগের মতো)।
- c77 পাস (০৬:৩২-০৬:৪১Z): **render হিসাব স্থির — ধাপ ০.০** (১০৭.৪/৩৯২.৬
  c76-এর সমান), `update_failed` টিকে — **creep-মডেল মৃত, attempt-burn দাঁড়াল**
  (কাউন্টার নড়ে শুধু চেষ্টা-ঘণ্টায়)। **boot-মুখ pass 7: ২৩:৪৩:১৬Z** (spread
  ০.৮০s) — **6-of-7**; uptime একমুখী ~৬.৮ঘ (রিবুট নেই)।
- **redis residency point #৫: tertiary ৫ম পরপর রিড — ৫-ঘণ্টা রেখা অতিক্রম**
  (লাইন ≥৪ঘ৫৮মি; সত্য ৪.৯৭-৫.৭৫ঘ) — c65-c69 plateau-র জীবন্ত সমতুল্য;
  **ঘূর্ণন #৩-এর ~৫ঘ অনুপস্থিতি নিজেই এখন প্রশ্ন** (চেইন-ক্যাডেন্স); cooldown
  বাকি ~১৭.৫ঘ।
- **reap-diff #2: reaped=[] আবার** — c76-এর ১৭ সারি সবই টিকে (ত্রয়ী #4095
  ৪.৯ঘ/#4143/#4099); দুই পাসে খালি ডিফ → **reap ক্যাডেন্স নয়, স্কোপড নিশ্চিত**।
- **প্রথম tower-plane telegram ফ্ল্যাপ**: ২৭s জানালায় healthy(৪৮৫ms)→
  **unreachable(null)** — সিরিজে প্রথম; agent-lane একই জানালায় 200 ×২
  (১২৬২/১৪০৪ms) — দুই ব্যান্ডের স্বাধীনতাই ডেটাম; c78-এ পুনরাবৃত্তি দেখা হবে।
- census ২০ (১০ম, নাম-ডিফ পরিষ্কার — glm11 r13-এর tool-side fix
  টাওয়ার-rosterে অপ্রভাবিত); sweep ১৩তম byte-consistent; dot canary ১০ম;
  well-known ৮ম NO-RESOLVE; provider ১৪তম সবুজ 7/8; #4203 CVE-guard
  contract সারি solver-লেনে নথিভুক্ত।
- রিসিট: docs/reports/SENTRY_C77_2026-10-31_glm31.md।
  Refs: #3376 #4206 #4207 (bare)।
