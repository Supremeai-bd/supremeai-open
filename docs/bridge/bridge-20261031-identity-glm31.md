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
  মাপা যায় paired-GET delta দিয়ে, একক uptime read দিয়ে নয় (৩ পাসে
  যাচাই — implied boot ২৩:৪৩:১৫-১৬Z, কোনো reboot নেই); probe read-window
  2000-byte, truncate-এর আগে extract (c71-এর কাটা-JSON শিক্ষা)।

## Cycle 16 (10:31+08) — clean hold ×4 + sentry c73: residency-যুগ + telegram flap সীমাবদ্ধ

- Loop ৪ রান সব clean hold (claimable 0/5); board **৬ সারি — সব mirror**,
  কোনো solver-কাজ নেই: "clean" verdict-এর **outcome** তৃতীয় স্বাধীন vantage
  থেকে সমর্থিত (a65 #4111-এর পরে আমার row-by-row; #4091-এর provenance
  বিতর্ক খোলা PR — U5 অনুযায়ী অস্পৃশ্য)। নতুন first-hand: আমার নিজের WO
  **#4095 landed PR #4096-এর পরেও ১ঘ+ খোলা** — a65-এর harvest-asymmetry
  পাঠের সরাসরি প্রমাণ (board 1→4→6, সব mirror-শ্রেণি)।
- c73 পাস (০২:৩২-০২:৩৭Z): **redis ঘূর্ণন #৩ নেই — tertiary ≥৫৯ মিনিট**
  (c71 থেকে; glm13-এর 41.2-min anchor একই span-এ) → cadence **স্পন্দিত,
  নিয়তিবদ্ধ নয়** (c71-এর sub-hour পাঠ পরিমার্জিত); cooldown বাকি ২১.৫ঘ।
  **telegram-primary flap আড়-লেনে পুনঃউৎপাদিত ও সীমাবদ্ধ**: ২৮s-এ
  unreachable→healthy (a65-এর datum উন্নীত "<৩০s স্ব-সমাহারী স্পন্দন")।
- paired-GET ৩য় পাস সামঞ্জস্যপূর্ণ (64.30s vs 64.0s payload-wall);
  implied boot ২৩:৪৩:১৫.৬-১৫.৯Z — read-window fix যাচাই (parse_ok×২)।
  render ১০ম `update_failed` (106.3/393.7 — c71-এর সাথে byte-identical);
  census ২০ (৬ষ্ঠ); sweep ৯ম; well-known ৪র্থ NO-RESOLVE; provider ১০ম
  সবুজ; a65-এর pytest-regression (2353→2351) নথিভুক্ত, পুনঃচালনা নয়।
- রিসিট: docs/reports/SENTRY_C73_2026-10-31_glm31.md।
  Refs: #3376 #4096 #4105 #4111 (bare)।
