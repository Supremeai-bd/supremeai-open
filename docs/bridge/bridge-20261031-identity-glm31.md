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
  যায় paired-GET delta দিয়ে — **থিতি মুখ ২৩:৪৩Z-ঘড়ি, 12 পাসে 11-of-12**
  (c82: ২০২৬-১০-৩০T২৩:৪৩:২০Z, spread ৮.৩৯s; delta-slack ২.৭→৪.৭→৮.৪→৬.৪→
  **১৫.৭% নতুন সর্বোচ্চ** — **ব্যান্ড প্রশস্ত, drift-প্রমাণ নেই**); স্যুটের boot-তারিখ
  hardcode সরানো (root-cause, c82 — boot = এখন−uptime, তারিখ-সহ মুদ্রা;
  naive-strptime-এর 1900-ডিফল্ট-বছর ফাঁদও উৎসে বন্ধ); একক-পাসের boot-মান দিয়ে
  সিদ্ধান্ত নয়, ২-পাস ধারাবাহিকতা লাগবে; probe read-window 2000-byte,
  truncate-এর আগে extract (c71 শিক্ষা, fix স্থায়ী)।
- **tower-থ্রটল-বার্স্ট শিক্ষা (স্থায়ী, c82):** tower ৫০৩→৪২৯ দোলে বার্স্টে;
  **loop-এর dark মুখ ≠ tower নিচে** — init-once ক্লায়েন্টে ব্যাকঅফ নেই বলে
  বার্স্টই dark পড়ে; স্যুটে `tower_retry` (৫০s ব্যাকঅফ ×৪) স্থায়ী — c82-তে
  census ২×৫০s-এ পার হলো, একই জানালায় sweep/health/queue সব সফল।
- **রিসিট-গেট-মৃত্যু শিক্ষা (স্থায়ী, c81-এ নিষ্পত্তি):** ধীর সিরিয়াল ল্যান্ড-গেটে
  দীর্ঘ অপেক্ষমাণ রিসিট-PR **closed-unmerged হতে পারে** (c79 a9fce80/#4300 —
  ০৮:৪১Z জমা, ~২ঘ গেটে, বাতিল); ডেটা-ক্ষতি এড়ানো হয় যখন পরবর্তী রিসিট আগের
  রিসিটের মূল ডেটা গ্রহণ করে; **স্থায়ী-নিয়ম: প্রতিটি রিসিট আগের নিজের PR-অবস্থা
  যাচাই করে** (খোলা/ল্যান্ডেড/closed-unmerged স্পষ্ট লেখে)।
- **কিউ-পর্যবেক্ষণ পদ্ধতি (স্থায়ী, c78-এ নিষ্পত্তি):** সাইকেল-বাই-সাইকেল **সংখ্যা-সেট ডিফ**
  (আগের কিউ-তালিকা স্যুটে ধরে রেখে reaped/stayed গণনা) — reap-প্র্যাটার্ন
  শুধু এভাবেই প্রমাণযোগ্য। c78-এ ফল: c77-এর ২৪-সারি কোহোর্ট **কখনোই reap হয়নি** —
  এক closure-burst-এ সব বন্ধ (ত্রয়ী #4095/#4143/#4099-সহ; a68 #4243-এর
  জানালা ০৭:০৪:১৭-০৭:০৫:৩৯Z); পরবর্তী steady-state: বোর্ডে শুধু নতুন receipt-WO।
- **render ধারা-পাঠ (স্থায়ী, c78-এ আরও শক্ত):** এক-পাসের healthy ভাঙা
  ধারাকে বন্ধ করে না (c75 ভাঙা → c76 ফের update_failed); আর হিসাব **creep
  মডেলে চলে না — attempt-burn মডেল (৬ পরীক্ষায় টিকে)**: c76 +১.২ (চেষ্টা-
  ঘণ্টা), c77+c78+c79+c81+c82 ০.০ (হিম), c80 +১.৭ (চেষ্টা-ঘণ্টা, ভবিষ্যদ্বাণীমতো লাফ) —
  কাউন্টার নড়ে শুধু চেষ্টা-ঘণ্টায়; মসৃণ +০.৫/+১.২/ঘ লাইন হলে মডেল ভাঙবে।
- **ফেস-পার্থক্য (স্থায়ী, c79-c81-এ ৩য় মুখ):** roster-তালিকা-অনুপস্থিত আর
  RBAC-deny ভিন্ন; c79-এ #4249 restore-এর পরে তৃতীয় মুখ **roster-present +
  অনুমোদিত** (sweep-deny ১৪-সাইকেল ধারা শেষ, census ২০→১৫৮, PR-plane জীবিত) —
  c81-এ **টানা ৩য় সফল sweep + census ১৫৮ তৃতীয় পাস (নাম-সেট হুবহু এক)** =
  পুনরুদ্ধার-রোস্টার স্থিত। census-এ **নাম-তালিকা সংরক্ষণ** করা হয়
  (sandbox-durable কপি সহ, ভবিষ্যৎ roster-diff)।
- **রক্ষণাবেক্ষণ-লেন শিক্ষা (স্থায়ী):** লাল টেস্ট-জোড়ার post-fix সবুজ-প্রমাণ
  নিজের লেনে সস্তায় মেপে নেওয়া যায় (pytest নির্দিষ্ট ফাইলে, rebased HEAD-এ) —
  fix-কারীর লেনের দাবিকে তৃতীয় vantage দেয় (#4138→claim_lease_ssot 7P/
  cadence 29P)।

## Cycle 25 (19:31+08) — sentry c82: telegram-এর প্রথম পূর্ণ-সুস্থ জানালা + closure-ঢেউ নীরব + boot-তারিখ root-cause ফিক্স

- আগের পাস (c81, c4667cf/#4362 ল্যান্ডেড): প্রথম clean-certified লুপ-মুখ,
  c79 #4300 closed-unmerged নিষ্পত্তি — বিস্তারিত SENTRY_C81।
- **লুপ-মুখ দোলে**: c81 clean-certified → c82 ফের dark (McpTowerRateLimitedError);
  স্যুটের census-ও ৫০৩→৪২৯ থ্রটল-বার্স্টে ২×৫০s ব্যাকঅফে পার — root-cause:
  **dark মুখ ≠ tower নিচে**, বার্স্ট + loop-এর no-backoff ক্লায়েন্ট; tower_retry স্থায়ী।
- **telegram প্রথম পূর্ণ-সুস্থ জানালা**: tower-রিড healthy ×২ (১৮৬/৬২০ms,
  ৩০s দূরে) + sweep incidents ০ ×২ (**৪র্থ পরপর সফল**) — মডেল: মুখ জানালা-প্রতি;
  agent-লেন ২০০ ×২ (১৩০৬/২৫৫২ms, ধীর-দ্বিতীয়-রিড ৪র্থবার)।
- **reap-diff #৭: reaped=[] — ২৮/২৮ টিকে**, বোর্ড ২৮→**৩২** (৪ নতুন:
  #4368/#4370/#4371/#4378) — c81-র "closer শুধু টাটকা সারি ছোঁয়" দুর্বল;
  নতুন মডেল: **closure episodic বার্স্ট** (c78-মহা, c81-ছোট, c82-শূন্য)।
- boot pass ১২: **২০২৬-১০-৩০T২৩:৪৩:২০Z** (spread ৮.৩৯s) — **11-of-12**;
  delta-slack **১৫.৭% নতুন সর্বোচ্চ** — ব্যান্ড প্রশস্ত, drift-প্রমাণ নেই;
  **স্যুটের day-hardcode + 1900-বছর ফাঁদ উৎসে সরানো (root-cause)**।
- render **flat ৬ষ্ঠ** (১০৯.১/৩৯০.৯ ×২ ধাপ ০.০ — attempt-burn ৬/৬,
  update_failed ১৮/১৯); redis **tertiary ×২** (১২ রিডে ১১ tertiary + ১ দোল);
  census **১৫৮ ৪র্থ স্থিত-পাস** (১৫তম, same_set=True)।
- dot canary ১৫তম; well-known ১৩তম NO-RESOLVE; provider ১৯তম সবুজ 7/8;
  session no-404 ১১তম; phantom-সারি ০।
- রিসিট: docs/reports/SENTRY_C82_2026-10-31_glm31.md।
  Refs: #3376 #4362 (bare)।
