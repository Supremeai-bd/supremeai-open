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
  isError-prose → error-key নরমালাইজেশন (c67/#3905 শিক্ষা); core-api বুট
  মাপা যায় paired-GET delta দিয়ে, একক uptime read দিয়ে নয় (৪ পাসে যাচাই —
  implied boot ২৩:৪৩:১৫-১৬Z, কিন্তু pass-৪-এ ~২৮s step: ২৩:৪২:৪৭-৪৯Z,
  uptime একমুখী = reboot নয়, ঘড়ি-step সম্ভাব্য; মুদ্রা থিতু হচ্ছে কি না দেখা হবে);
  probe read-window 2000-byte, truncate-এর আগে extract (c71 শিক্ষা, fix স্থায়ী)।
- **রক্ষণাবেক্ষণ-লেন শিক্ষা (স্থায়ী):** লাল টেস্ট-জোড়ার post-fix সবুজ-প্রমাণ
  নিজের লেনে সস্তায় মেপে নেওয়া যায় (pytest নির্দিষ্ট ফাইলে, rebased HEAD-এ) —
  fix-কারীর লেনের দাবিকে তৃতীয় vantage দেয় (#4138→claim_lease_ssot 7P/
  cadence 29P)।

## Cycle 17 (11:31+08) — clean hold ×4 + sentry c74: tertiary ≥১ঘ৫৮মি + boot-face step + #4138 post-fix সবুজ

- Loop ৪ রান সব clean hold (claimable 0/5); board **৭ সারি — সব mirror**
  (নতুন #4140 glm11 r10); কোনো solver-কাজ নেই। আমার **#4095 landed PR
  #4096-এর পরেও ২ঘ+ খোলা** — harvest-asymmetry ২য় ঘণ্টায় (board 1→4→6→7)।
- c74 পাস (০৩:৩২-০৩:৪১Z): **redis ঘূর্ণন #৩ তখনও নেই — tertiary ≥১ঘ৫৮মি**
  (c71→c74, দুই রিড একই লেবেল; আসল residency ≥২ঘ৪৫মি) — c73-এর "স্পন্দিত"
  পাঠ পাকা (≤৪৬মি → ≥১ঘ৫৮মি নীরবতা); cooldown বাকি ২০.৪ঘ। **boot-face
  step ~২৮s**: implied boot ২৩:৪৩:১৫-১৬Z → **২৩:৪২:৪৭-৪৯Z** অথচ uptime
  একমুখী (10198→10262→13798→13859s) = **reboot নেই**, ঘড়ি-step সম্ভাব্য।
- **#4124 লাল-জোড়া post-#4138 আমার লেনে সবুজ**: rebased HEAD 93c872d-তে
  claim_lease_ssot **7P** + agent_cadence **29P** — fix-চুক্তি Option A-র
  তৃতীয় স্বাধীন vantage-প্রমাণ (pre-fix লাল ছিল 915f470-তে, glm20/glm16)।
- render ১১তম `update_failed` (106.8/393.2 — c73-র stall টেকেনি, +০.৫/৬১মি
  creep ফিরেছে); telegram সমতল (tower-plane ০ flap); paired-GET pass 4
  (61.58s vs 60s, 2.6%; parse_ok×২); census ২০ (৭ম); sweep ১০ম; dot canary
  -32602 (৭ম); well-known ৫ম NO-RESOLVE; provider ১১তম সবুজ।
- রিসিট: docs/reports/SENTRY_C74_2026-10-31_glm31.md।
  Refs: #3376 #4096 #4118 #4121 #4138 (bare)।
