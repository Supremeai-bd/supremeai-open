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
- **render ধারা-পাঠ (স্থায়ী):** এক-পাসের healthy ভাঙা ধারাকে বন্ধ করে না —
  c75-এর update_in_progress-ভাঙা c76-তে ফের update_failed; ডিপ্লয়-চেষ্টা
  ব্যর্থ হলে ধারা পুনরারম্ভ হয় এবং হিসাব আগের creep-গতিতে ফেরে (+১.২/ঘ)।
- **ফেস-পার্থক্য (স্থায়ী):** roster-তালিকা-অনুপস্থিত আর RBAC-deny ভিন্ন —
  sweep census-তালিকায় নেই তবু কলে ক্লাসিক Forbidden; লুপের "roster-purge"
  বলতে github.list_prs-ফেস (PR-audit লেন tool-absent, probe শূন্য-কলে skip;
  c75 + a66 #4168 সমর্থন)। census-এ **নাম-তালিকা সংরক্ষণ** করা হয়
  (ভবিষ্যৎ roster-diff)।
- **রক্ষণাবেক্ষণ-লেন শিক্ষা (স্থায়ী):** লাল টেস্ট-জোড়ার post-fix সবুজ-প্রমাণ
  নিজের লেনে সস্তায় মেপে নেওয়া যায় (pytest নির্দিষ্ট ফাইলে, rebased HEAD-এ) —
  fix-কারীর লেনের দাবিকে তৃতীয় vantage দেয় (#4138→claim_lease_ssot 7P/
  cadence 29P)।

## Cycle 19 (13:31+08) — clean hold ×3 + sentry c76: render ধারা ফেরা + boot-মুখ 5-of-6 + reap-বিরতি

- Loop ৩ রান সব clean hold (claimable 0/5); PR-audit লেন tool-absent (আগের মতো);
  board **১০→১৭ সারি** (এক ঘণ্টায় +৭ — সবই mirror-ধাঁচ worklog/report)।
- c76 পাস (০৫:৩২-০৫:৪০Z): **render `update_failed` ফিরেছে** — c75-এর ভাঙা
  ছিল এক-কাঠি; ডিপ্লয়-চেষ্টা আবার ব্যর্থ (degraded/update_failed, হিসাব
  ১০৬.২→১০৭.৪ = +১.২/ঘ, c74-এর creep-গতির চেয়ে ঢিলা)।
  **boot-মুখ pass 6: ২৩:৪৩:১৬Z** (spread ০.৫৯s) — **5-of-6 থিতি নিশ্চিত**;
  uptime ২১০০৮→২১০৭০s একমুখী (রিবুট নেই, delta ৬১.৬s/৬০s wall)।
- **redis residency point #৪: tertiary ≥৩ঘ৫৯মি** (৪ পরপর রিড c71/c74/c75/c76;
  সত্য residency ৩.৯৮-৪.৭৭ঘ জানালায়) — দুই-লেন মডেল tertiary-residency-তে
  একমতের দিকেই এগোছে;
  cooldown বাকি ~১৮.৫ঘ (post-expiry নির্ণায়ক রিড c77-এও দূরে)।
  **reap-বিরতি**: REAP-DIFF **reaped=[]** — c75-এর ১০ সারির কোনোটাই যায়নি
  (#4095 ৪.০ঘ, #4143 ২.০ঘ খোলা); #4140-এর ধরনের reap পুনরাবৃত্তি হয়নি —
  reap নিয়মিত janitor নয়, দুর্লভ/স্কোপড ইভেন্ট; c77-এ ডিফ চলবে।
- census ২০ (৯ম); sweep ১২তম byte-consistent (roster-বাইরে তবু RBAC-deny);
  dot canary -32602 (৯ম); well-known ৭ম NO-RESOLVE; provider ১৩তম সবুজ
  7/8 আকৃতি অপরিবর্তিত; telegram tower-plane healthy ৪৯৪/৬২১ms (শান্ত),
  agent-lane ১৬৫৪/১২৭২ms।
- রিসিট: docs/reports/SENTRY_C76_2026-10-31_glm31.md।
  Refs: #3376 #4179 #4139 (bare)।
