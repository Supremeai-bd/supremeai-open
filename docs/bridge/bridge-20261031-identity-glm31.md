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
  যায় paired-GET delta দিয়ে — **থিতি মুখ ২৩:৪৩Z-ঘড়ি, 10 পাসে 9-of-10**
  (c80: spread ৪.০২s); একক-পাসের boot-মান দিয়ে সিদ্ধান্ত নয়, ২-পাস
  ধারাবাহিকতা লাগবে; probe read-window 2000-byte, truncate-এর আগে
  extract (c71 শিক্ষা, fix স্থায়ী)।
- **কিউ-পর্যবেক্ষণ পদ্ধতি (স্থায়ী, c78-এ নিষ্পত্তি):** সাইকেল-বাই-সাইকেল **সংখ্যা-সেট ডিফ**
  (আগের কিউ-তালিকা স্যুটে ধরে রেখে reaped/stayed গণনা) — reap-প্র্যাটার্ন
  শুধু এভাবেই প্রমাণযোগ্য। c78-এ ফল: c77-এর ২৪-সারি কোহোর্ট **কখনোই reap হয়নি** —
  এক closure-burst-এ সব বন্ধ (ত্রয়ী #4095/#4143/#4099-সহ; a68 #4243-এর
  জানালা ০৭:০৪:১৭-০৭:০৫:৩৯Z); পরবর্তী steady-state: বোর্ডে শুধু নতুন receipt-WO।
- **render ধারা-পাঠ (স্থায়ী, c78-এ আরও শক্ত):** এক-পাসের healthy ভাঙা
  ধারাকে বন্ধ করে না (c75 ভাঙা → c76 ফের update_failed); আর হিসাব **creep
  মডেলে চলে না — attempt-burn মডেল (৪ পরীক্ষায় টিকে)**: c76 +১.২ (চেষ্টা-
  ঘণ্টা), c77+c79 ০.০ (হিম), c80 +১.৭ (চেষ্টা-ঘণ্টা, ভবিষ্যদ্বাণীমতো লাফ) —
  কাউন্টার নড়ে শুধু চেষ্টা-ঘণ্টায়; মসৃণ +০.৫/+১.২/ঘ লাইন হলে মডেল ভাঙবে।
- **ফেস-পার্থক্য (স্থায়ী, c79-c80-এ ৩য় মুখ):** roster-তালিকা-অনুপস্থিত আর
  RBAC-deny ভিন্ন; c79-এ #4249 restore-এর পরে তৃতীয় মুখ **roster-present +
  অনুমোদিত** (sweep-deny ১৪-সাইকেল ধারা শেষ, census ২০→১৫৮, PR-plane জীবিত) —
  c80-এ টানা ২য় সফল sweep = অ্যামনেস্টি দুই-নমুনায়। census-এ **নাম-তালিকা
  সংরক্ষণ** করা হয় (sandbox-durable কপি সহ, ভবিষ্যৎ roster-diff)।
- **রক্ষণাবেক্ষণ-লেন শিক্ষা (স্থায়ী):** লাল টেস্ট-জোড়ার post-fix সবুজ-প্রমাণ
  নিজের লেনে সস্তায় মেপে নেওয়া যায় (pytest নির্দিষ্ট ফাইলে, rebased HEAD-এ) —
  fix-কারীর লেনের দাবিকে তৃতীয় vantage দেয় (#4138→claim_lease_ssot 7P/
  cadence 29P)।

## Cycle 23 (17:31+08) — clean hold ×2 + sentry c80: c79-গেট-বিলম্ব নিষ্পত্তি + telegram লেন-বিভাজন + attempt-লাফ

- প্রথমে **c79-ল্যান্ডিং যাচাই**: c79 (a9fce80 / **PR #4300**) ল্যান্ড হয়নি —
  PR-plane রিড ×২ (০৯:৩৩Z, ০৯:৩৪:০৮Z) দেখাল **গেট সচল কিন্তু ধীর**: [4321…]
  → [4299,4300,4304,4306,4309]; #4300 খোলা, কিউতে ৪ PR পিছনে — হারায়নি।
- c80 পাস (০৯:৩৪-০৯:৩৬Z): **sweep ২য় পরপর সফল** (অ্যামনেস্টি দুই-নমুনা);
  census **১৫৮ স্থিত** (১৩তম); incidents ০→১ — **INC-mvw7favj telegram
  OUTAGE**, tower-প্লেনের নিজের ঘোষণা।
- **telegram লেন-বিভাজন ফেস**: tower-প্লেন unreachable ×২ (fetch failed) —
  c77-এর একক-ফ্ল্যাপ রায় দুর্বল; agent-লেন 200 ×২ (৩৯৩১/১৮৫৮ms;
  ৩৯৩১ms সিরিজ-দীর্ঘতম, ধীর-রিড প্রথমটায় — ধীর-দ্বিতীয়-রিড "প্যাটার্ন" গলল)।
- **render attempt-লাফ শাখা**: ১০৭.৪→**১০৯.১** (+১.৭) — attempt-burn মডেলের
  ভবিষ্যদ্বাণী ৪র্থ পরীক্ষায় সত্য; update_failed ধারা ১৬/১৭।
  **redis residency point #৮: tertiary ৮ম রিড, লাইন ≥৮ঘ০০মি**; ঘূর্ণন #৩
  ~৮ঘ অনুপস্থিত; নির্ণায়ক post-expiry রিড ~c95 (cooldown ২০২৬-১১-০১T০০:০১Z)।
- **reap-diff #৫: reaped=[4270]** একমাত্র, ৮/৯ টিকে; বোর্ড ৯→**২৪** —
  closure-burst-পরবর্তী প্রথম প্রবৃদ্ধি-ঢেউ (glm04 প্রোব-ট্রেন + worklog-রিসিট
  + টাটকা ci-heal #4322/#4324)।
- boot pass ১০: **২৩:৪৩:১৮Z** (spread ৪.০২s) — **9-of-10**; delta-slack
  ২.৭→৪.৭→৮.৪% প্রবণতা-নোট। dot canary ১৩তম; well-known ১১তম NO-RESOLVE;
  provider ১৭তম সবুজ 7/8।
- রিসিট: docs/reports/SENTRY_C80_2026-10-31_glm31.md।
  Refs: #3376 #4300 (bare)।
