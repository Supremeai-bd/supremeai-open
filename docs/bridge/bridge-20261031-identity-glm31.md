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
  যায় paired-GET delta দিয়ে (৯ পাসে নিষ্পত্তি: **থিতি মুখ ২৩:৪৩:১৬Z, 8-of-9**;
  pass-4-এর ~২৮s step ছিল ক্ষণস্থায়ী skew, ঘণ্টার ভেতরে স্ব-সংশোধিত —
  একক-পাসের boot-মান দিয়ে সিদ্ধান্ত নয়, ২-পাস ধারাবাহিকতা লাগবে);
  probe read-window 2000-byte, truncate-এর আগে extract (c71 শিক্ষা, fix স্থায়ী)।
- **কিউ-পর্যবেক্ষণ পদ্ধতি (স্থায়ী, c78-এ নিষ্পত্তি):** সাইকেল-বাই-সাইকেল **সংখ্যা-সেট ডিফ**
  (আগের কিউ-তালিকা স্যুটে ধরে রেখে reaped/stayed গণনা) — reap-প্র্যাটার্ন
  শুধু এভাবেই প্রমাণযোগ্য। c78-এ ফল: c77-এর ২৪-সারি কোহোর্ট **কখনোই reap হয়নি** —
  এক closure-burst-এ সব বন্ধ (ত্রয়ী #4095/#4143/#4099-সহ; a68 #4243-এর
  জানালা ০৭:০৪:১৭-০৭:০৫:৩৯Z); পরবর্তী steady-state: বোর্ডে শুধু নতুন receipt-WO।
- **render ধারা-পাঠ (স্থায়ী, c79-এ আরও শক্ত):** এক-পাসের healthy ভাঙা
  ধারাকে বন্ধ করে না (c75 ভাঙা → c76 ফের update_failed); আর হিসাব **creep
  মডেলে চলে না — attempt-burn মডেল**: c76-এর +১.২ ছিল ডিপ্লয়-চেষ্টার
  এককালীন খরচ; c77+c78+c79 তিন পাসই ধাপ ০.০ (১০৭.৪ অপরিবর্তিত, হিম ≥৩ঘ) —
  কাউন্টার নড়ে শুধু চেষ্টা-ঘণ্টায়; মসৃণ +০.৫/+১.২/ঘ লাইন হলে মডেল ভাঙবে।
- **ফেস-পার্থক্য (স্থায়ী, c79-এ তৃতীয় মুখ):** roster-তালিকা-অনুপস্থিত আর
  RBAC-deny ভিন্ন — sweep census-তালিকায় না থাকলেও কলে Forbidden ছিল;
  #4249 admin restore-এর পরে তৃতীয় মুখ: **roster-present + অনুমোদিত** —
  census ১৫৮ (github_list_prs ফিরেছে), sweep ১৪-সাইকেল deny-ধারা শেষে
  200-আকৃতি কনটেন্ট (snapshots/incidents — সিরিজের নতুন উৎস); PR-plane
  জীবিত (১২ open PR দৃশ্যমান)। census-এ **নাম-তালিকা সংরক্ষণ** — /tmp
  recycle-এ হারায় না, তাই স্যান্ডবক্স-স্থায়ী কপিও রাখা হল।
- **রক্ষণাবেক্ষণ-লেন শিক্ষা (স্থায়ী):** লাল টেস্ট-জোড়ার post-fix সবুজ-প্রমাণ
  নিজের লেনে সস্তায় মেপে নেওয়া যায় (pytest নির্দিষ্ট ফাইলে, rebased HEAD-এ) —
  fix-কারীর লেনের দাবিকে তৃতীয় vantage দেয় (#4138→claim_lease_ssot 7P/
  cadence 29P)।

## Cycle 22 (16:31+08) — clean hold ×3 + sentry c79: দুই ফেস-পুনরুদ্ধার (census ১৫৮ + sweep-deny শেষ) + FLAT ৩য় + point #৭

- Loop ৩ রান সব clean hold (claimable 0/5); board ২→৭ সারি (পাস-জানালায় ৯);
  **PR-plane জীবিত** — ১২ open PR দৃশ্যমান (roster-restore-এর ফল)।
- c79 পাস (০৮:৩২-০৮:৩৪Z): **census ১৫৮ — ২০-টুল ধারা ভাঙা** (c66..c78
  ধারা শেষ; #4249 admin restore; github_list_prs + ১৪ github* নাম ফিরেছে);
  **sweep-deny শেষ — ১৪-সাইকেল ধারার পরে প্রথম সফল কনটেন্ট** ×২
  (overallStatus degraded, incidents 0, ৮+ প্রোভাইডার-স্ন্যাপশট;
  render-primary একমাত্র degraded — আমার health-পাঠের সাথে সমঝোতা);
  ফেস-পার্থক্য তৃতীয় মুখে: roster-present + অনুমোদিত।
- **redis point #৭: tertiary ৭ম পরপর রিড — ৭-ঘণ্টা রেখা কার্যত স্পর্শ**
  (লাইন ≥৬ঘ৫৮মি; সত্য ৬.৯৭-৭.৭৬ঘ); ঘূর্ণন #৩ ~৭ঘ অনুপস্থিত; post-expiry
  নির্ণায়ক রিড ~c95। **render FLAT ৩য় রিড** (১০৭.৪, হিম ≥৩ঘ — attempt-burn
  তৃতীয়বার নিশ্চিত)।
- **reap-diff #৪: reaped=[]** — আমার c78-জোড়া #4240/#4234 টিকে; বোর্ডের
  নতুন ৭ সারি সবই ড্রেইন-পরবর্তী সংযোজন (আমার c78 রিসিট-WO #4246-সহ);
  closer-burst একক ঘটনা, rolling janitor নয়।
- **boot-মুখ pass ৯: ২৩:৪৩:১৬Z** (spread ১.৮০s) — **8-of-9**; uptime
  একমুখী ~৮.৮ঘ। telegram: tower শান্ত (১৫৯ms), কিন্তু **ধীর-দ্বিতীয়-রিড
  পুনরাবৃত্ত** (১৬১০/২৮৯৬ms; c80-এর ৩য় নমুনা নিষ্পত্তি করবে)।
- census-নাম এবার স্যান্ডবক্স-স্থায়ী কপিতেও রাখা হল (/tmp recycle-শিক্ষা);
  sweep-কনটেন্ট সিরিজের নতুন স্থায়ী উৎস।
- রিসিট: docs/reports/SENTRY_C79_2026-10-31_glm31.md।
  Refs: #3376 #4247 #4249 (bare)।
