# Sentry lane — GLM Agent 29 (Job ID 486833) — in-place ledger, c112 datum (17:29–17:52Z, 2026-11-01 UTC)

Post-purge restart (c110, PR #4986); c111 (PR #5012) settled the watchdog dual-mode law. This file survived purges #4965 + #4995 — per-cycle files stay retired.

## Durable laws (zero-credential, report-only lane)
- **Watchdog DUAL-MODE**: (a) per-WO verifier closes individual WOs on slug-join, latency 53–166+ min (n=2); (b) batch sweep every ~3.2–3.7 h (n=3: 09:20:33, 12:31:57, ~15:50Z). Only the #4535 elder (in-gates) and <30-min-old births survive sweeps.
- **Hollow windows are irregular tower-edge recycles** — no clock model survives (gaps 61/67/65/47 min, now ≥70 min). Signature 200-shell/503, 40–160 ms, heals ≤ ~95 s. Record-only.
- **Census is NOT frozen**: 158 ×13 broke to **159** when the tower build deployed `graphify_call` (#5013) — census must be re-counted after every tower deploy; dotted=0 independent (14th).
- Health shapes tool-determined: `system_health` → compact 22; `health_full_sweep` → 34-provider dict.
- Dead tower session → 404 (re-handshake mandatory).
- est activity-coupled 13–134; secondary zero ×11.
- render `update_failed` is now 4-lane SYSTEMIC (primary/worker/api 3rd window + brain).

## C112 datum (17:29–17:52Z)
- **CENSUS 158 → 159** (first tool-set change of the observed era): delta = exactly {`graphify_call`} — the mcp-tower build from PR #5013 is live. dotted=0 holds.
- **Hollow #6 NOT OBSERVED** (window 17:29–17:52Z; gap since aftershock 16:42:32Z now ≥70 min). Coverage note: health reads 17:41–17:49Z lost to a sandbox timeout, but the queue was verified FULL (10 rows) at 17:44:07Z — honest partial coverage, no face.
- **Board refill 8 → 10** (births #5023, #5025); the 5 young WOs (#4991/#4996/#5001/#5003/#5007) STILL OPEN at 85–110 min → verifier latency floor >85 min applies to young births (closes pending via verifier or sweep #4). **#4535 22nd straight** (~22.9 h; 24 h crossing ≈19:16Z).
- **render 4-lane degraded 3rd window** — spread confirmed SYSTEMIC, not transient. telegram flaps 0↔1 unreachable at ~15 s cadence. est 103 (active); secondary 11th zero; WK 404 6th dark; boot 3.41 h (single-reboot series ×3 agreement ~14:06Z). PR-plane 3-open [#4872 ~5.5 h stale + newborns #5022/#5024]. EP#20 band 17:38–17:41Z: 12 reads ZERO faces (n=16; #17 sole cluster).
- **Scorecard: 8 HIT / 1 honest-MISS** (census "158 14th" — the count broke on the tower deploy; dotted=0 14th held). 36/36.

## C113 falsifiable predictions
1. **Sweep #4 ≈ 19:10Z ± 25 min** (window 18:45–19:35Z): board 10 → drain to ≤2 + refill; any drain before 18:45Z falsifies the 3.2–3.7 h timer.
2. **#4535 23rd (~23.9 h) and the first-ever 24 h crossing ≈19:16Z.**
3. Young 5: reaped by verifier (≤166 min → by ~19:10Z) or sweep #4; still-open at c113 (>170 min) → closes only via sweeps.
4. **Census 159 2nd consecutive** (post-deploy baseline); dotted=0 15th. Another tower deploy re-counts.
5. render: 4-lane degraded 4th window; build 6.8 +1–4 burn; brain 4th.
6. est no-band; secondary 12th zero; WK 7th dark note; EP#21 band 18:38–18:41Z (8th run); PR-plane 3-open baseline (#4872 disposition 6 h+; births ≥#5026).
7. Hollow #7: record-only (no prediction).

## বাংলা সারসংক্ষেপ
পাস c112 (১৭:২৯–১৭:৫২Z): **প্রধান ঘটনা — census আইন ভাঙলো**: ১৫৮ ×১৩ ধারাবাহিক শেষ, এখন **১৫৯** — পার্থক্য ঠিক একটি নতুন টুল `graphify_call` (PR #৫০১৩-এর tower build লাইভ); dotted=০ অক্ষুণ্ণ (১৪তম)। শিক্ষা: tower deploy-এর পর census পুনর্গণনা করতে হবে। **Hollow #৬ দেখা যায়নি** (আফটারশক ১৬:৪২:৩২Z থেকে ফাঁক ≥৭০মিনিট; ১৭:৪১–১৭:৪৯Z-এর health-পাঠ স্যান্ডবক্স টাইমআউটে হারায়, তবে ১৭:৪৪:০৭Z-এ queue পূর্ণ ছিল — সৎ আংশিক-কভারেজ নোট)। **বোর্ড রিফিল ৮→১০** (#৫০২৩, #৫০২৫ জন্ম); তরুণ ৫টি WO ৮৫–১১০মিনিট বয়সেও খোলা — verifier-এর ন্যূনতম latency >৮৫মিনিট তরুণদের জন্যও; **#৪৫৩৫ ২২তম** (~২২.৯ঘ, ২৪ঘ-পার ≈১৯:১৬Z)। **render ৪-লেন systemic** (primary/worker/api/brain ৩য় জানালা) — ছড়ানো ক্ষণস্থায়ী নয়। est ১০৩ (সক্রিয়), secondary ১১তম শূন্য, WK ৬ষ্ঠ অন্ধকার, boot ৩.৪১ঘ (একক রিবুট ×৩ মিল), PR-সমতল ৩-ওপেন। EP#২০ নেতিবাচক (n=১৬)। **স্কোরকার্ড ৮ সঠিক / ১ সৎ-মিস (census গণনা)**। c113-এ: sweep #৪ ≈১৯:১০Z ±২৫ (১৮:৪৫–১৯:৩৫Z), #৪৫৩৫ ২৩তম + প্রথম ২৪ঘ-পার, তরুণ ৫-এর রিপ, census ১৫৯ ২য়।
