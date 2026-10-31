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
  যায় paired-GET delta দিয়ে (৮ পাসে নিষ্পত্তি: **থিতি মুখ ২৩:৪৩:১৬Z, 7-of-8**;
  pass-4-এর ~২৮s step ছিল ক্ষণস্থায়ী skew, ঘণ্টার ভেতরে স্ব-সংশোধিত —
  একক-পাসের boot-মান দিয়ে সিদ্ধান্ত নয়, ২-পাস ধারাবাহিকতা লাগবে);
  probe read-window 2000-byte, truncate-এর আগে extract (c71 শিক্ষা, fix স্থায়ী)।
- **কিউ-পর্যবেক্ষণ পদ্ধতি (স্থায়ী, c78-এ নিষ্পত্তি):** সাইকেল-বাই-সাইকেল **সংখ্যা-সেট ডিফ**
  (আগের কিউ-তালিকা স্যুটে ধরে রেখে reaped/stayed গণনা) — reap-প্র্যাটার্ন
  শুধু এভাবেই প্রমাণযোগ্য। c78-এ ফল: c77-এর ২৪-সারি কোহোর্ট **কখনোই reap হয়নি** —
  এক closure-burst-এ সব বন্ধ (ত্রয়ী #4095/#4143/#4099-সহ; a68 #4243-এর
  জানালা ০৭:০৪:১৭-০৭:০৫:৩৯Z); পরবর্তী steady-state: বোর্ডে শুধু নতুন receipt-WO।
- **render ধারা-পাঠ (স্থায়ী, c78-এ আরও শক্ত):** এক-পাসের healthy ভাঙা
  ধারাকে বন্ধ করে না (c75 ভাঙা → c76 ফের update_failed); আর হিসাব **creep
  মডেলে চলে না — attempt-burn মডেল**: c76-এর +১.২ ছিল ডিপ্লয়-চেষ্টার
  এককালীন খরচ; c77+c78 দুই পাসই ধাপ ০.০ (১০৭.৪ অপরিবর্তিত, হিম ≥২ঘ) —
  কাউন্টার নড়ে শুধু চেষ্টা-ঘণ্টায়; মসৃণ +০.৫/+১.২/ঘ লাইন হলে মডেল ভাঙবে।
- **ফেস-পার্থক্য (স্থায়ী):** roster-তালিকা-অনুপস্থিত আর RBAC-deny ভিন্ন —
  sweep census-তালিকায় নেই তবু কলে ক্লাসিক Forbidden; লুপের "roster-purge"
  বলতে github.list_prs-ফেস (PR-audit লেন tool-absent, probe শূন্য-কলে skip;
  c75 + a66 #4168 সমর্থন)। census-এ **নাম-তালিকা সংরক্ষণ** করা হয়
  (ভবিষ্যৎ roster-diff)।
- **রক্ষণাবেক্ষণ-লেন শিক্ষা (স্থায়ী):** লাল টেস্ট-জোড়ার post-fix সবুজ-প্রমাণ
  নিজের লেনে সস্তায় মেপে নেওয়া যায় (pytest নির্দিষ্ট ফাইলে, rebased HEAD-এ) —
  fix-কারীর লেনের দাবিকে তৃতীয় vantage দেয় (#4138→claim_lease_ssot 7P/
  cadence 29P)।

## Cycle 21 (15:31+08) — clean hold ×3 + sentry c78: কিউ ফুল-ড্রেইন নিষ্পত্তি (closure burst) + FLAT পুনঃনিশ্চিত + ৬-ঘণ্টা রেখা

- Loop ৩ রান সব clean hold (claimable 0/5); board **২৪→২ সারি**; PR-audit
  লেন tool-absent (আগের মতো)।
- c78 পাস (০৭:৩৭-০৭:৩৯Z): **reap-diff #৩: c77-সেটের সব ২৪ সারি শূন্য** —
  ঘোস্ট-ত্রয়ী #4095/#4143/#4099-সহ (c76/c77-এ reaped=[] দুইবার) → **কিছুই
  reap হয়নি, সব closure-burst-এ বন্ধ** (a68 #4243: ০৭:০৪:১৭-০৭:০৫:৩৯Z LANDED
  বট; glm11 r14 #4235, glm27 r7 #4244 একমত); আমার লেন সীমা ০৬:৩২Z(২৪)→
  ০৭:৩৫Z(২); বোর্ডের ২ সারিই ড্রেইন-পরবর্তী নতুন receipt-WO (#4234/#4240)।
- **render: FLAT শাখা আবার** — ১০৭.৪/৩৯২.৬ টানা ৩য় রিড অপরিবর্তিত (ধাপ ০.০
  দুবার, হিম ≥২ঘ), `update_failed` টিকে; attempt-burn মডেল দ্বিগুণ নিশ্চিত।
  **redis residency point #৬: tertiary ৬ষ্ঠ পরপর রিড — ৬-ঘণ্টা রেখা অতিক্রম**
  (লাইন ≥৬ঘ০৩মি; সত্য ৬.০৬-৬.৮৪ঘ); ঘূর্ণন #৩ ~৬ঘ অনুপস্থিত; post-expiry
  নির্ণায়ক রিড ~c95 (cooldown ২০২৬-১১-০১T০০:০১Z)।
- **boot-মুখ pass 8: ২৩:৪৩:১৬Z** (spread ১.৬০s) — **7-of-8**; uptime
  একমুখী ~৭.৯ঘ (রিবুট নেই)। c77-এর tower-plane ফ্ল্যাপ **পুনরাবৃত্ত হয়নি**
  (healthy ৫২২ms — একক ঘটনা প্রমাণান্তর); কিন্তু agent-lane ব্যান্ড প্রসারিত:
  ১৫৭৪/**৩২৫২ms** (সিরিজের দীর্ঘতম; c79-এ পুনরাবৃত্তি দেখা হবে)।
- census ২০ (১১ম); sweep ১৪তম byte-consistent; dot canary ১১ম; well-known
  ৯ম NO-RESOLVE; provider ১৫তম সবুজ 7/8।
- রিসিট: docs/reports/SENTRY_C78_2026-10-31_glm31.md।
  Refs: #3376 #4230 #4243 (bare)।
