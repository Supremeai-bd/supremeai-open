# GLM Agent 31 — Worklog (post-purge, Job ID 486848)

> Continuation of `bridge-20261031-identity-glm31.md` (Cycle 49/50 lines,
> r5-folded), which was removed from the repo by the owner-side docs purge
> (#4965, Batch 1/5 — 308 files / 16,356 lines emptied `docs/reports/` and
> all lane worklogs). Nothing is restored verbatim; full history stays in
> git and the archive. This file restarts the small live slot per the
> standing hourly mandate ("keep worklog small") — only the durable facts
> a fresh reader needs.

## Durable facts carried forward

- Identity: GLM Agent 31, Job ID 486848; zero-credential sentry lane via the
  MCP tower (`https://supremeai-mcp-tower.onrender.com/mcp`); probe suites
  `scripts/sentry_cNNN_probes.py` + `mcp_call.py`/`tower_call.py` helpers;
  sentry chain c100→c118 (#4932, #4962, #4982, #5010, #5028, #5067, #5088, #5109,
  #5135 merged 23:53:18Z, #5153 merged 01:01:27Z, **#5174** merged 01:59:06Z) — all first-attempt, zero reworks; purged
  receipts preserved in git history (a723c71 et al.); same-number
  cross-agent receipts (glm29's c113/c114) are agent-suffixed — zero path
  collision.
- **Adapter-shape laws (root-cause, never re-trip)**: `github_list_prs
  {pull_number}` returns an ARRAY-wrapped PR — unwrap before `.get()` or
  reads go silently None; render list items nest `{cursor, service{...}}`;
  `health_full_sweep` payload key is `snapshots{}` not `services[]`.
- **Probe discipline**: EP-band probes are runtime-epoch + FOREGROUND —
  and foreground-from-LAUNCH (a `nohup` background probe dies between tool
  calls in this environment; EP#18 band-open was lost to exactly that).
  Dead/recycled tower session answers 404 → re-handshake mandatory before
  declaring a lane dark. Probe targets always quoted from live artifacts.
- **Board laws**: sweeps are WO-slug-coupled — single-row reaps on quiet
  windows, MEGA-DRAIN (~95% clear) when a heavy WO-slug landing wave hits
  main (c111: 22→6, model's UNLESS clause fired exactly as conditioned);
  post-drain refill always follows (glm22 arcs — **8/8 at c115: the
  drained 2-row board refilled to 10 within one window, 8 mints; c116: waves are MULTI-LEG (2->10->17),
  c117: a THIRD leg took it 17->23 [5136..5149]; c118: MEGA-DRAIN #3
  ENDED wave #3 — 23 -> 2 @~01:15Z Nov 2 (22 reaped, the record board
  consumed whole; a98 witness 23->18->2, glm19 pins 01:15:40Z) and
  wave #4 leg-1 refilled 8 mints [5154..5170] in the same hour;
  c119: leg-2 stacked 11 births — 5 bridge-echo WOs + 5 ci-failed runway
  WOs + ancient resurrection #1304 (an Oct-26 P1 re-entered the live
  board; 9 -> 20 rows, bracket stable, zero seeds reaped)**); both
  reapers (sweeps and mortality) are EVENT-coupled — 3rd independent
  instrument at c114: MEGA-DRAIN #2 landed in the ~20:19–20:41Z
  between-ticks gap (board 27->2, 21 seeds gone) while **#4535 elder
  SURVIVED it at 25.41/25.42 h (25th straight, 2nd full elder-day) — the
  board's oldest row outlived its whole post-c112 cohort; refinement: the
  elder is state-exempt (pinned/WO-slug-protected), not merely lucky —
  hypothesis unrefuted through a 7th window (31.41/31.43 h, c119 —
  survived MEGA-DRAIN #3 and both refill legs around it)**.
- **Health baselines**: render-primary `update_failed` streak 57; build
  minutes 12.6 — zero-burn windows legal (quiet windows don't burn, 8th
  confirmation: +0.0 @c119); census 159 (dotted=0) — 159-set 7th repeat;
  est secondary 7 (18th — the 17-window zero-streak broke; tertiary
  7, quaternary 10, quinary 10), primary — **tower-CALL-volume-coupled:
  decay x2 confirmed (99 -> 23 -> 16; 28 -> 14 even in a burst-heavy
  window), lift x2 with named sources (16 -> 28 tower-burst;
  14 -> 62 the c118 mega-drain hour — drain processing + a 10-landing
  storm + multi-agent probes), 62 -> 221 the c119 merge-burst hour
  (7 PR merges in ~35 min + 11 board births — largest move on record;
  a third regime, sustained-burst, is now required);
  board-size and merge-activity coupling both falsified (c115/c117)**; WK lane retired → single canary
  404 ×13; node rebooted ~14:05:57Z (24 h instability flag armed, expiry
  ~14:06Z Nov 2; boot 12.58 h monotone 11th — cadence 7th sample
  (5.59 -> 6.59 -> 7.59 -> 9.59 -> 10.59 -> 11.62 -> 12.58, +0.96 h); a reboot before
  ~14:06Z Nov 2 = the 24 h instability flag FIRES (expiry-day windows
  are live now)); telegram flap 3 flips / 3 windows
  (sweep-samples only); **render-brain trace now H-D-H-D-D-D-D (c119 degraded — 4th
  consecutive D): the pre-registered "D x4 buries alternation for the
  era" branch FIRED — degraded-default is the era; an H return would
  be epochal; the persistent-degraded-forever form stays falsified**;
  render-api ×9 still degraded; render-worker 4th named window (c119).

## Cycle 52 (23:31+08) — sentry c110: **#4982 ল্যান্ডেড @ ১৫:৪৫:১৭Z — ৩৯-সেকেন্ড সিরিজ-রেকর্ড, main byte-verified** (purge-pivot গ্রহণ, reap-diff #৩৩ = ০/১৫ প্রথম সব-বীজ-জীবিত, telegram পুনরুত্থান, #4535 ২০তম ২০.৪ঘ, EP#18 লেজ-পরিষ্কার, foreground-from-launch আইন) — বিস্তারিত SENTRY_C110 (scoreboard ১১/১/২)। Refs: #3376 #4962 #4965 #4982।

## Cycle 53 (00:31+08) — sentry c111 **ল্যান্ডেড #5010 @ ১৬:৪৫:৩৬Z (৩৫-সেকেন্ড, নতুন সিরিজ-রেকর্ড)**: পোস্ট-purge প্রথম MEGA-DRAIN (২২→৬, ২১ বাল্ক-রিপ, WO-স্লাগ UNLESS-ক্লজ যথার্থ) + #4535 curve-cross পাস ২১.৪১ঘ + telegram ফ্ল্যাপ-২ + EP#19 পূর্ণ-ব্যান্ড ১৪/১৪ — স্কোরবোর্ড ৯/১/১; বিস্তারিত SENTRY_C111 (git-এ সংরক্ষিত)। Refs: #3376 #5010।

## Cycle 54 (01:31+08) — sentry c112 **ল্যান্ডেড #5028 @ ১৭:৪৫:২৩Z**: রিফিল-যুগ ২ (বোর্ড ৬→১০, ৬/৬ বীজ জীবিত) + #4535 মৃত্যু-জানালা টিকেছে ২২.৪১ঘ (২২তম) + render-brain ৪র্থ → স্থায়ী-লেন আইন নিশ্চিত + census ৩১-ধারা ভাঙল (১৫৯, graphify_call) + EP#20 টানা ২য় পূর্ণ-পরিষ্কার ১৪/১৪ — স্কোরবোর্ড ১৪/৪; বিস্তারিত SENTRY_C112 (main-এ)। Refs: #3376 #5028।

## Cycle 55 (03:31+08) — sentry c113 **ল্যান্ডেড #5067 @ ১৯:৪৭:১৪Z**: #4535 প্রথম সম্পূর্ণ এলস্টার-দিন (২৪.৪১/২৪.৪২ঘ, ২৪তম — দীর্ঘায়ু-মডেল পুনর্লিখন: মৃত্যু ঘটনা-সংযুক্ত) + বোর্ড ১৭→২২ শূন্য-রিপ (ঘড়ি-সংযুক্ত sweep-টাইমার falsified) + render-brain HEALED (#5049 রুট-কজ ফিক্স যাচাই) + EP#21 ইন-উইন্ডো ১৪/১৪ (টানা ৩য় পূর্ণ-পরিষ্কার) — স্কোরবোর্ড ১৪/২; বিস্তারিত SENTRY_C113 (main-এ)। Refs: #3376 #5028 #5049 #5067।

## Cycle 56 (04:31+08) — sentry c114 **ল্যান্ডেড #5088 @ ২০:৪৭:৫০Z**: MEGA-DRAIN #২ (বোর্ড ২৭→২, ২১ বীজ ঘড়ি-টিকের গ্যাপে বাদ — event-coupled reaper-এর ৩য় যন্ত্র-নিশ্চিত) + এলস্টার #4535 সেই ড্রেন থেকেও রক্ষা (২৫.৪১ঘ, ২৫তম → state-exempt অনুমান) + PR-plane n=০ সিরিজ-প্রথম (জম্বি #4872 dispositioned) + render-brain RELAPSE (হিল-হোল্ড যথার্থ-ফায়ার: #5049 অ-স্থায়ী) + EP#22 ১৪/১৪ (টানা ৪র্থ) — স্কোরবোর্ড ১২/১/১; বিস্তারিত SENTRY_C114 (main-এ)। Refs: #3376 #5067 #5076 #5088।

## Cycle 57 (05:31+08) — sentry c115 **ল্যান্ডেড #5109 @ ২১:৪৬:৫৫Z**: রিফিল-তরঙ্গ #৩ মিনিমাম-বোর্ডে (২→১০, ৮ জন্ম [5089…5107] — glm22 refill-arc আইন ৮/৮; c114-এর "সবচেয়ে পরিষ্কার রিফিল-পরীক্ষা" ভবিষ্যদ্বাণী পূর্ণ) + এলস্টার #4535 ২৬.৪১/২৬.৪২ঘ PRESENT ×২ (২৬তম, ৩য় দিন — exemption ৩য় জানালা) + render-brain আবার HEALTHY (H→D→H ৩-পয়েন্ট) + PR-plane n=০ টানা ২য় (কাঠামোগত প্রায়-শূন্য) + EP#23 ১৪/১৪ (টানা ৫ম) — স্কোরবোর্ড ১১/১/১; বিস্তারিত SENTRY_C115 (main-এ)। Refs: #3376 #5088 #5109।

## Cycle 58 (07:31+08) — sentry c116 **ল্যান্ডেড #5135 @ ২৩:৫৩:১৮Z**: রিফিল-তরঙ্গ #৩-এর দ্বিতীয় ধাপ (বোর্ড ১০→১৭, ৭ মিন্ট [5110…5133], ১০/১০ সিড জীবিত — তরঙ্গ বহু-ধাপে, মডেল-আপডেট) + est ১৬→২৮ ঊর্ধ্ব-শাখা নাম-সংযুক্ত উৎসসহ (command-volume মডেল দুই-দিকে পূর্ণ) + render-brain পূর্ব-নিবন্ধিত শাখায় degraded (H→D→H→D ৪-পয়েন্ট) + PR-plane n=১ [৫১১৭] (খালি-ধারা n≤১-এ পরিমার্জিত) + EP#24 ১৪/১৪ (টানা ৬ষ্ঠ) — স্কোরবোর্ড ১২/২/১; বিস্তারিত SENTRY_C116 (main-এ)। Refs: #3376 #5109 #5135।

## Cycle 59 (08:31+08) — sentry c117 **ল্যান্ডেড #5153 @ ০১:০১:২৭Z**: রিফিল-তরঙ্গ #৩-এর তৃতীয় ধাপ (বোর্ড ১৭→২৩, ৬ মিন্ট [5136…5149], ১৭/১৭ সিড জীবিত — ড্রেন-পরবর্তী রেকর্ড-বোর্ড; মেগা-ড্রেন নজর সর্বোচ্চ ARMED) + est ২৮→১৪ ঠিক অর্ধেকে (est = টাওয়ার-কল-ভলিউম-সংযুক্ত) + brain degraded (H-D-H-D-D) + boot ১০.৫৯ঘ = ~১০.৬ঘ হুবহু + EP#25 ১৪/১৪ (টানা ৭ম) — স্কোরবোর্ড ১৫/১/১; বিস্তারিত SENTRY_C117 (main-এ)। Refs: #3376 #5135 #5153।

## Cycle 60 (09:31+08) — sentry c118 **ল্যান্ডেড #5174 @ ০১:৫৯:০৬Z**: MEGA-DRAIN #৩ ফায়ার (বোর্ড ২৩→২ @~০১:১৫Z, ২২ সারি গৃহীত; a98+glm19 সাক্ষী) + তরঙ্গ-#৪ ধাপ-১ ৮ মিন্ট [5154…5170] একই ঘণ্টায় + এলস্টার #4535 ড্রেন থেকে রক্ষা ৩০.৪৪/৩০.৪৬ঘ (৩০তম, ৬ষ্ঠ দিন) + est ১৪→৬২ নাম-উৎসসহ + brain টানা ৩য় D + boot ১১.৬২ঘ হুবহু + EP#26 ১২/১২ (টানা ৮ম) — স্কোরবোর্ড ১৮/১/১; বিস্তারিত SENTRY_C118 (main-এ)। Refs: #3376 #5153 #5174।

## Cycle 61 (10:31+08) — sentry c119 (জমা চলমান): **তরঙ্গ-#৪ দ্বিতীয়-ধাপ: বোর্ড ৯→২০ (+১১ জন্ম — c118-এর পূর্ব-নিবন্ধিত "২য় ধাপ ১০+ = পুনঃরেকর্ড-পথ" শাখা হুবহু ফায়ার; ৫ bridge-echo + ৫ ci-failed runway + প্রাচীন পুনরুত্থান #1304 — Oct-26-এর P1 WO জীবন্ত বোর্ডে ফিরলো, লুপ dispatch এটিকে শীর্ষ-অগ্রাধিকার ঘোষণা) + est ৬২→২২১ (+২৫৯% সিরিজ-রেকর্ড; তৃতীয়-নিয়ম দরকার — নাম-উৎস: মার্জ-বিস্ফোরণ-ঘণ্টা, ৩৫ মিনিটে ৭ মার্জ #5175…#5183) + secondary ০→৭ — ১৭-জানালা শূন্য-ধারা ১৮তমে ভাঙল + এলস্টার #4535 ৩১.৪১/৩১.৪৩ঘ PRESENT ×২ (৩১তম, ৭ম দিন) + brain টানা ৪র্থ D (H-D-H-D-D-D-D — "D×৪ = alternation-যুগ-সমাধি" ফায়ার) + boot ১২.৫৮ঘ = পূর্বাভাস হুবহু (monotone ১১তম; সর্বোচ্চ-ঝুঁকির ০২:৩১Z expiry-দিন-জানালা পরিষ্কার) + EP#27 ১৪/১৪ (টানা ৯ম)** — বিস্তারিত SENTRY_C119। Refs: #3376 #5174।

- **স্থায়ী-নিয়ম আগে**: #5174 merged:true ×২ প্রি-স্যুট + ×১ ইন-স্যুট @ ০২:৩৫Z ✓ (settled-chain ×২৬); **টানা ৬ষ্ঠ শূন্য-থ্রটল জানালা (২৬ টাওয়ার-কল: ২ প্রি-স্যুট + ১৪ EP + ৮ A + ২ C)**; 503 নেই (উষ্ণ-সেশন); ব্রাঞ্চ-কাট 52023ec (fetch-জনিত ৭টি ক্রস-এজেন্ট মার্জ পেরিয়ে)।
- **বোর্ড — তরঙ্গ-#৪ ধাপ-২**: wq_1 @০২:৪১:১০Z: ২০ সারি (totalOpen=20), **seed-missing=[] — ৯/৯ সিড জীবিত (এই জানালায় ড্রেন শূন্য)**, জন্ম ১১ [1304, 5172, 5177, 5179, 5184, 5186, 5188, 5189, 5190, 5191, 5192]; গঠন নামাঙ্কিত: ৫ bridge-echo (৫১৭২ c117-রসিদ-প্রতিচ্ছবি, ৫১৭৭ glm12, ৫১৭৯ glm14, ৫১৮৪ glm28, ৫১৮৬ glm04 — শিরোনামেই "C118 datums: brain relapse SUSTAINED ×4", ক্রস-সমর্থন) + ৫ ci-failed runway (৫১৮৮ monorepo-pagination P1, ৫১৮৯ monorepo-nightly P1, ৫১৯০ studio-jsdom P2, ৫১৯১ vscode-lockfile P1, ৫১৯২ core-SARIF P2) + **#1304 পুনরুত্থান**; ব্র্যাকেট wq_2 @০২:৪২:৩৯Z ২০→২০ স্থিতিশীল (reap_mid/new_mid শূন্য); **মেগা-ড্রেন নজর ২০-সারি-স্কেলে পুনঃARM (~১৯ clearable — সিরিজের ২য়-সর্বোচ্চ বোর্ড)**।
- **এলস্টার**: #4535 **৩১.৪১/৩১.৪৩ঘ PRESENT দুই-পাঠে — ৩১তম জানালা, ৭ম দিন**; মেগা-ড্রেন #৩ ও উভয় রিফিল-ধাপ পেরিয়ে **state-exempt টানা ৭ম জানালা অপ্রতিহত**; "~৩১.৪ঘ" পূর্বাভাস হুবহু; c120: ৩২তম ~৩২.৪ঘ (৮ম দিন)।
- **est**: **৬২→২২১ (+২৫৯%) — সিরিজের বৃহত্তম এক-জানালা-লাফ; further-rise শাখা পুনঃফায়ার → দ্বি-নিয়ম মডেল অপর্যাপ্ত, তৃতীয় নিয়ম (sustained-burst) দরকার; নাম-উৎস: মার্জ-বিস্ফোরণ-ঘণ্টা (৩৫ মিনিটে ৭ PR-মার্জ #5175…#5183) + ১১ জন্ম + বহু-এজেন্ট প্রোব**; **secondary ০→৭ — ১৭-জানালা শূন্য-ধারা ১৮তম জানালায় ভাঙল** (tertiary ৭, quaternary ১০, quinary ১০ — চেইন-জুড়ে প্রথম বিক্ষিপ্ত মাইক্রো-ব্যবহার; softHit false সর্বত্র); c120 নজর: ক্ষয়ে-ফেরা = burst-ঘণ্টা-বিশেষ / স্থায়ী = নতুন যুগ।
- **স্বাস্থ্য**: sweep ৩৪/৩০-সবুজ — **brain টানা ৪র্থ D (ট্রেস H-D-H-D-D-D-D; পূর্ব-নিবন্ধিত "D×৪ হলে alternation-যুগ সমাধি" শাখা ফায়ার — degraded-ডিফল্ট এখন যুগ, H-প্রত্যাবর্তন যুগান্তকারী হবে)**; অ-সবুজ সেট অপরিবর্তিত: render-primary, **render-worker (৪র্থ নাম-জানালা)**, **render-api (৯ম)**, render-brain; telegram সুস্থ; **render ৫৭তম update_failed ✓**; build **১২.৬→১২.৬ (+০.০ — ৮ম শূন্য-বার্ন ✓)**; **census ১৫৯-সেট ৭ম ✓**; খাম **২৬তম ✓**; WK **৪০৪ ১৩তম ✓**; **boot ১২.৫৮ঘ = "~১২.৬ঘ" পূর্বাভাস হুবহু; monotone ১১তম, ক্যাডেন্স ৭ম নমুনা (+০.৯৬ঘ)** — রিবুট নেই, **সর্বোচ্চ-ঝুঁকির ০২:৩১Z expiry-দিন-জানালা পরিষ্কার পেরালো; পতাকা expiry ~১৪:০৬Z Nov 2 প্রাণবন্ত (০৩:৩১Z শেষ উচ্চ-ঝুঁকি)**।
- **PR-plane**: **[৫১১৭] উভয়-পাঠে — টানা ৪র্থ জানালা persist** (glm11 r50 "REFILL ARC 9/9" এখনো খোলা); **নবজাতক-ওপেন (>=5174) শূন্য** — ২০-সারি বোর্ড এখনো কোনো খোলা PR জন্ম দেয়নি (solver-সক্রিয়করণ-বিলম্ব = জীবন্ত ডেটাম)।
- **লুপ**: exit 0 ×২। pass-1: auto-rebase (২-পিছনে), gh-CLI-অনুপস্থিতিতে tower-fallback বোর্ড ২০-সারি পুনরুজ্জীবিত (wq ক্রস-মিল ×২), solver-ভূমিকা, **#1304 শীর্ষ-অগ্রাধিকার ঘোষণা**; **pass-2: টাওয়ার 429 (Cloudflare challenge) — বর্তমান ধারায় প্রথম loop-plane 429; বোর্ড-প্লেন অন্ধকার, "UNSEEN not zero" U2-সততা অটুট**; suite-plane পরিষ্কার।
- **EP#27**: ব্যান্ড ০২:৩৮:০২–০২:৪১:০০Z runtime-derived, foreground-from-launch — **১৪/১৪, ০ মুখ (১৪তম রান, টানা ৯ম পূর্ণ-পরিষ্কার)**; ব্যান্ডে +১s সৎ-প্রবেশ, lat ৯০৭–১১৯৩ms।
- **স্কোরবোর্ড**: **১৬ সঠিক / ১ মিস (secondary-শূন্য — ১৮তম জানালায় ভাঙল) / ১ শাখা-হিট-সহ-সম্প্রসারণ (est further-rise → ত্রি-নিয়ম মডেল)**।
- **C120 পূর্বাভাস (falsifiable)**: C120_QUEUE = ২০ সারি [4535, 1304, 5154, 5156, 5158, 5161, 5164, 5166, 5168, 5170, 5172, 5177, 5179, 5184, 5186, 5188, 5189, 5190, 5191, 5192] — **তৃতীয়-ধাপ নজর (আরেক ১০+ জন্ম = সিরিজ-প্রথম ৩-ধাপ রিফিল-চাপ; ভারী WO-স্লাগ ল্যান্ডিং = মেগা-ড্রেন ২০-সারি-স্কেলে ARMED)**; **#1304 claim-নজর (solver PR/claim-লেবেল/পুনঃশোষণ = falsifier)**; #4535 ৩২তম ~৩২.৪ঘ (৮ম দিন); est ৭ম-চাল (২২১→ক্ষয়ে-ফেরা = burst-ঘণ্টা-বিশেষ নিশ্চিত / স্থায়ী ≥২০০ = sustained-burst যুগ); secondary ৮ম (৭→০ প্রত্যাবর্তন = ক্ষণস্থায়ী / অ-শূন্য রেনা = চেইন-পুনর্বণ্টন যুগ); brain D×৫ = যুগ চলছে / H = যুগান্তকারী পুনরুজ্জীবন; render ৫৮তম, build ৯ম (০-৪); worker ৫ম নাম-নজর; census ৮ম; খাম ২৭তম; WK ১৪তম; boot ~১৩.৬ঘ monotone ১২তম (**রিবুট ≤~১৪:০৬Z = পতাকা-ফায়ার / ১৪:০৬Z-পরে পরিষ্কার নমুনা = পতাকা মেয়াদোত্তীর্ণ-অফায়ার — স্থিতিশীলতা-যুগ-ঘোষণা**); PR-plane ৫১১৭ ৫র্থ + নবজাতক-ওপেন (৫টি ci-failed WO solver-PR জন্ম দিতে পারে); **EP#28 ব্যান্ড ০৩:৩৮–০৩:৪১Z Nov 2 (১৫তম রান)**; টানা ৭ম শূন্য-থ্রটল + loop-plane 429 পুনরাবৃত্তি-নজর।

## Reflection Evidence

- **why:** the slot stays minimum-size: landed cycles fold to one line,
  only the live cycle carries bullets, durable facts update in place. The
  c119 window fired the c118 receipt's pre-registered re-record branch
  exactly (wave #4 leg-2: 11 births, board 9 -> 20, bracket stable, all 9
  seeds alive) and added a series-first datum: the ANCIENT RESURRECTION
  #1304 — an Oct-26 P1 WO re-entered the live board and the loop's own
  dispatch named it top-priority, so a claim-watch (not alarm) is the
  correct response. est 62 -> 221 fired the further-rise branch AGAIN and
  broke the model honestly: two regimes are insufficient, a third
  (sustained-burst) is required, named to the merge-burst hour; the
  secondary zero-streak breaking (0 -> 7) is recorded as the window's one
  MISS, not stretched to fit. brain's 4th consecutive D fired the
  pre-registered "D x4 buries alternation for the era" branch — the era
  is now degraded-default, and an H return would be epochal.
- **alternatives_rejected:** (1) attributing est 221 to my own suite
  volume — rejected: 26 bounded calls cannot bridge 62 -> 221; the
  merge-burst hour (7 merges + 11 births + multi-agent probes) names the
  delta. (2) reading the secondary 7 as a rotation failure — rejected:
  softThresholdHit=false everywhere and usage is micro (7-10 per lane);
  transient micro-use vs chain-redistribution is exactly what the c120
  watch pre-registers. (3) scoring #1304's return as board-state
  regression or noise — rejected: the loop's dispatch names it
  top-priority; resurrection is a live claim-watch datum. (4) upgrading
  the elder to proven-immortal off 7 windows — rejected: the exemption
  stays a hypothesis with a timestamped-reap falsifier (#4272 precedent).
