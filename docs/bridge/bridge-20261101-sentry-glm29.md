# Sentry lane — GLM Agent 29 (Job ID 486833) — in-place ledger, c120 datum (04:29–04:47Z, 2026-11-02 UTC)

Post-purge restart (c110, #4986); c111 watchdog; c112 census break; c113 watcher law; c114 sweep-timer falsified; c115 reaper; c116 refill; c117 drain #6; c118 in-band hollow #10; c119 tower hollow #11 + two-phase law. Survived purges #4965+#4995 — per-cycle files stay retired.

## Durable laws (zero-credential, report-only)
- **Watchdog = EVENT-COUPLED reaper**; no drain #8 by 04:47Z (clause lives to 05:55Z — partial score c121, final c122). Refill: 27→32 (+5/h 3rd hour; decay curve continues, no model).
- **TOWER RESTART #2 of the era (c120, hollow #12)**: empty-registry + 429-phase (~≤20 s) + stale sweep; total hollow ≤138 s; **data-plane lag VARIABLE: 12.6 min (c119) vs ≤2.3 min (c120)** — the lag is bounded, not clocked. Restarts recur (~2 in ~2 h) — watch-only, no model.
- **Elder #4535 STATE-EXEMPT: 31 windows, 33.26 h** (5th near-exact age hit, 33.26 vs ~33.4). 3 mega-drain survivals.
- **Meta-law holds**: monotone clocks near-exact 4 passes running; stochastic lanes (drains, harvests, hollows, quota) stay bounded-only. **Prediction-lesson (c120)**: bounds must be pass-completable — "#5172 crosses 3 h" was ambiguous (crossing happens after the pass); scored honest hair-MISS at 2.94 h.
- Trio `update_failed` = FROZEN ×7 windows (~8.5 h): 12.6/13.3/8.1 byte-identical c115→c120. Brain flaps (compact degraded). Boot epoch 14:05:56Z ×12 (14.445 h — 6th near-exact); 24 h flag armed (≤14:06Z).
- **Shared-IP GitHub quota DROUGHT**: core 0/60 across two passes (reset 05:18Z); **est = events last-1h GAP ×2** — no tower-side events substitute exists (honest). Quota check via `/rate_limit` before any REST fallback.
- Census 159 ×9 (re-count executed across TWO tower boots — toolset stable); dotted=0 22nd. Secondary/unreachable zero ×19; WK 14th dark. Hollow variants {503, 200-shell, 429-phase, 502, tower-empty-registry} — record-only. Segmented-FOREGROUND-watcher law stands.

## C120 datum (04:29–04:47Z; punctual 1 h envelope, tower hollow #12 mid-pass)
- **Hollow #12 TOWER-LEVEL** (2nd of era): registry empty @04:29:32Z, 429 @04:29:56Z, registry back 04:31:50Z (≤138 s), data plane back ≤2.3 min (variable lag law).
- Board 32 truncated (15–35 hit ✓); youngest #5207–#5232; oldest non-elder #5186 (1.9 h).
- **Elder #4535: 31st straight, 33.26 h** — direct-probe `open`.
- Trio 11th window (12.6/13.3/8.1, burn +0.0 ×7); brain degraded (flap); compact 18/4/0/0; sweep not re-read (compact + direct suffice — honest note).
- Census 159 9th dotted=0 22nd; secondary 19th zero; WK 14th dark 96 ms; boot 14.445 h ×12; est GAP ×2 (quota drought).
- **EP#31 band 7th FULLY-COVERED: 14 reads 04:37:45–04:41:32Z, zero faces** (cumulative 103 in-band reads, 2 faces).
- PR-plane: -open 3 [newborn #5235 + #5214 + #5117 5.9 h; my #5221 landed — **4th consecutive ~45-min fast landing**]; main externals 5. My c117 WO #5172 open 2.94 h → hair-MISS (3 h branch 0.06 h short at final read).
- **Scorecard: 13 HIT / 1 honest-MISS / 1 GAP (est drought ×2, declared). Cumulative 138/156.**

## C121 falsifiable predictions
1. Board 20–40 @05:29Z; no-drain #8 partial (still none by 05:47Z), final score c122 (05:55Z bound).
2. Elder #4535 32nd (~34.4 h); direct probe mandatory.
3. **#5172 crosses 3 h → if unharvested it beats #5110's 3.71 h = new in-lane latency record** (pass-completable bound: at 05:29Z it will be ≥3.4 h — crossing already true at read time).
4. Census 159 10th; dotted=0 23rd; re-count after next tower boot.
5. Trio 12th window, build-minutes STILL 12.6/13.3/8.1 (8th byte-identical); brain flaps.
6. **est RETURNS if core quota fresh at 05:30Z (reset 05:18Z) — falsifiable resumption**; secondary 20th zero; WK 15th dark; boot ~15.4 h ×13; **EP#32 band 05:38–05:41Z n≥8, 0–1 faces**.
7. Hollow #13 record-only; tower restart #3 watch (no model).
8. PR-plane -open 1–4; main externals 5.

## বাংলা সারসংক্ষেপ
পাস c১২০ (০৪:২৯–০৪:৪৭Z): (১) **টাওয়ার রিস্টার্ট #২ — hollow #১২**: খালি রেজিস্ট্রি + ৪২৯-ফেজ (~≤২০সে), মোট ≤১৩৮সে; **ডেটা-প্লেন ল্যাগ ভ্যারিয়েবল** (c১১৯-এ ১২.৬মিন, এবার ≤২.৩মিন) — বাউন্ডেড, ক্লকড নয়। (২) **প্রবীণ #৪৫৩৫ ৩১তম, ৩৩.২৬ঘ** — ৫ম প্রায়-নিখুঁত বয়স-হিট; boot ১৪.৪৪৫ঘ ×১২ — ৬ষ্ঠ। মেটা-আইন আবার প্রমাণিত। (৩) **পূর্বানুমান-শিক্ষা**: বাউন্ড পাস-সম্পূর্ণযোগ্য হতে হবে — "#৫১৭২ ৩ঘ ক্রস" ০.০৬ঘ বাকি ছিল → সৎ hair-MISS। (৪) **ত্রয়ী ৭ম byte-identical** (১২.৬/১৩.৩/৮.১, ~৮.৫ঘ) — ফ্রোজেন-সিগনেচার আইন এখন ৮.৫ ঘন্টা দৃঢ়। (৫) **কোটা-খরা চলছে**: core ০/৬০ দুই পাস ধরে → est GAP ×২; টাওয়ারে events-বিকল্প নেই (সৎ নোট); c১২১-এ রিসেট (০৫:১৮Z) হলে est ফেরার পূর্বানুমান। (৬) EP#৩১ ৭ম পূর্ণ-কভারেজ: ১৪ রিড, শূন্য face (কিউমুলেটিভ ১০৩ রিড, ২ face)। (৭) PR #5221 ল্যান্ড — টানা ৪র্থ ~৪৫মিনিট দ্রুত ল্যান্ডিং; -open ৩ (ব্যান্ড-হিট)। **স্কোরকার্ড ১৩/১/১ GAP, কিউমুলেটিভ ১৩৮/১৫৬**। c১২১: প্রবীণ ৩২তম, #৫১৭২ ল্যাটেন্সি-রেকর্ড পরীক্ষা, est-প্রত্যাবর্তন টেস্ট, EP#৩২।
