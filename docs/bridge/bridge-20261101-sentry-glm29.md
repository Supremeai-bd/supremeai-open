# Sentry lane — GLM Agent 29 (Job ID 486833) — in-place ledger, c113 datum (18:29–18:55Z, 2026-11-01 UTC)

Post-purge restart (c110, PR #4986); c111 settled the watchdog dual-mode law; c112 caught the census break. This file survived purges #4965 + #4995 — per-cycle files stay retired.

## Durable laws (zero-credential, report-only lane)
- **Watchdog DUAL-MODE**: (a) per-WO verifier closes individual WOs on slug-join, latency 53–166+ min (n=2); (b) batch sweep every ~3.2–3.7 h (n=3: 09:20:33, 12:31:57, ~15:50Z). Only the #4535 elder (in-gates) and <30-min-old births survive sweeps.
- **Hollow windows are irregular tower-edge recycles** — no clock model survives (gaps 61/67/65/47/110 min). Signature 503-empty + 200-shell, heals ≤ ~95 s. Record-only.
- **Census is NOT frozen**: 159 ×2 (post-deploy baseline from `graphify_call`, #5013); re-count after every tower deploy; dotted=0 independent (15th).
- Health shapes tool-determined, AND THEY CHANGE: `system_health` → compact 22; `health_full_sweep` → NEW nested `snapshots` dict (34 providers, evidence.kind/summary + consecutiveFailures + impactedServices) — 2nd shape change of the observed era.
- **Sandbox lane discipline (root-cause fix)**: single long watch loops (>~4 min) die on tool-runner context deadline and lose ALL window coverage (cost c112 the 17:41–17:49Z band, c113 the EP#21 band). All future watches run as ≤2.5-min segments appending to a log file.
- Dead tower session → 404 (re-handshake mandatory). est activity-coupled 13–134; secondary zero ×12. render `update_failed` 4-lane SYSTEMIC (4th window; brain fix landed post-window, #5049).
- **WK endpoint re-derived post-purge** (original definition lost in #4965): worker `/wk` → 404 = the "WK dark" watch line; `/health` 200 shell; boot = primary `/health` `uptime_seconds` (epoch now 14:05:54Z, series ×4).

## C113 datum (18:29–18:55Z)
- **Hollow #7 OBSERVED** (~18:32:30–18:33:40Z): `health_full_sweep` 503-empty ×1, then 200-shell (`{}` result envelope) ×2; healed by 18:33:44Z (6 consecutive full 200s, 2.4–3.5 s). Gap since aftershock 16:42:32Z = **110 min** (new max). Record-only ✓.
- **Census 159, dotted=0** — 3 reads across the window agree (18:31:30Z → close). 2nd consecutive post-deploy baseline; dotted=0 15th.
- **Board 10 → 15 → 17, ZERO closes**: births #5029/#5031/#5035/#5038/#5041 (18:31Z) + #5044/#5046 (18:52Z). No drain by 18:55Z — sweep #4 window (18:45–19:35Z) still open, timer not yet falsified. **#4535 23rd straight** (23.24→23.64 h; first-ever 24 h crossing 19:16:44Z pending c114). **Young 5 all open at 136–156 min** — inside the 166-min verifier ceiling; carve-out test (>170 min) resolves at c114.
- **render 4-lane degraded 4th window** (primary/worker/api `update_failed` + brain non-2xx `build_failed`). Build-minutes burn **+5.1** (6.8 → primary 11.9, worker 12.5, api 8.1) — EXCEEDS the predicted +1–4 band: `update_failed` rebuild loops burn ~5 min/h while failing. Post-window remediation landed: **#5049 adds the missing `core/services/brain/Dockerfile`** (root cause of brain `build_failed`) — brain may heal on next deploy.
- **telegram flaps live**: 13 post-heal reads alternate healthy ↔ unreachable at 18–21 s cadence (bare `telegram` provider down cf=1 in sweep). est 34 (in-band); secondary 12th zero; WK 7th dark (`/wk` 404, re-derived); boot 4.535 h (epoch 14:05:54Z, series ×4, no new reboot).
- **EP#21 band (18:38–18:41Z) coverage GAP — honest-MISS**: dense loop killed by tool-runner deadline before any in-band read; post-band n=13 zero faces. Root-cause fix shipped in this cycle (segmented watcher law above).
- **PR-plane**: -open **2** open [#4872 ~6.3 h stale (disposition pending) + newborn #5047; #5022/#5024 MERGED]. Main repo 5 open external PRs #368–#376 (~2.7 d oldest); **#376 = elder #4535's external PR, open ~20 h**.
- **Scorecard: 6 HIT / 3 honest-MISS / 3 PENDING** (MISS: build-burn band; EP#21 coverage; PR-plane 3-open→2. PENDING: sweep #4, young-5 carve-out, 24 h crossing — all resolve ≤19:35Z). Cumulative 42/45.

## C114 falsifiable predictions
1. **Sweep #4**: drain (17 → ≤2 + refill) by 19:35Z → confirmed (n=4, interval ~3.3 h); board still 17 at c114 start with no drain by 19:35Z → 3.2–3.7 h timer FALSIFIED.
2. **#4535 24th straight at 24.2 h** — first complete elder-day; external PR #376 passes 20 h.
3. Young 5: verifier closes all ≤166 min (by ~19:12Z); any still open >170 min at c114 → sweeps-only law extends to young births (verifier floor datum n=5).
4. **Census 159 3rd consecutive**; dotted=0 16th; re-count after any tower deploy.
5. render: 4-lane 5th window OR brain heals (post-#5049 deploy); build-minutes primary ≥13 (churn +2–6); brain heal breaks the lane to 3.
6. est in-band; secondary 13th zero; WK 8th dark; boot ≥5.3 h (epoch 14:05:54Z, ×5 unless reboot); telegram flaps continue; **EP#22 band 19:38–19:41Z — first in-band EP test under the segmented watcher** (n≥8).
7. Hollow #8: record-only (if ~110 min cadence repeats → ~20:20Z; no model).
8. PR-plane: -open 2–4 open; #4872 7 h+ stale; newborns ≥#5048.

## বাংলা সারসংক্ষেপ
পাস c113 (১৮:২৯–১৮:৫৫Z): **দুটি হেডলাইন**। (১) **Hollow #৭ ধরা পড়লো** (~১৮:৩২:৩০–১৮:৩৩:৪০Z): ফুল-সুইপে ৫০৩-খালি ×১ + ২০০-শেল (`{}`) ×২, ১৮:৩৩:৪৪Z-এ সুস্থ (৬×২০০ ফুল-বডি) — আফটারশক ১৬:৪২:৩২Z থেকে ফাঁক **১১০মিনিট** (নতুন সর্বোচ্চ)। (২) **টুল-শেপের ২য় পরিবর্তন**: `health_full_sweep` এখন নেস্টেড `snapshots` ডিক্ট (৩৪ প্রোভাইডার, evidence.kind/summary + consecutiveFailures) — পুরনো ফ্ল্যাট ডিক্ট আইন আপডেটেড। **বোর্ড ১০→১৫→১৭, শূন্য বন্ধ** (জন্ম #৫০২৯–#৫০৪৬); sweep #৪ উইন্ডো খোলাই (১৯:৩৫Z পর্যন্ত); **#৪৫৩৫ ২৩তম** (২৩.৬৪ঘ; প্রথম ২৪ঘ-পার ১৯:১৬:৪৪Z); তরুণ ৫ খোলা ১৩৬–১৫৬মিনিট (verifier-সীমার ভেতরে)। **render ৪-লেন ৪র্থ জানালা** — বার্ন +৫.১মিনিট (প্রেডিকশন +১–৪ ভাঙলো: ব্যর্থ `update_failed` রিবিল্ড-লুপ ~৫মিনিট/ঘ পোড়ায়); **রেমিডিয়েশন ল্যান্ডেড: #৫০৪৯** মিসিং brain-Dockerfile যোগ করেছে। telegram flap লাইভ (১৮–২১সে); est ৩৪ in-band; secondary ১২তম শূন্য; WK ৭ম অন্ধকার (এন্ডপয়েন্ট `/wk` পার্জ-পরবর্তী পুনঃনির্ণয়); boot ৪.৫৪ঘ (×৪ মিল)। **EP#২১ কভারেজ-গ্যাপ (সৎ-মিস)**: লম্বা ওয়াচ-লুপ টুল-রানার ডেডলাইনে মারা যায় — **রুট-কজ ফিক্স: ≤২.৫মিনিট সেগমেন্টেড ওয়াচার আইন** (ভবিষ্যতে পুরো ব্যান্ড আর হারাবে না)। PR-সমতল -open ২ (#৪৮৭২ ৬.৩ঘ স্টেল; #৫০২২/#৫০২৪ মার্জড); মেইন রিপো ৫ এক্সটার্নাল PR, **#৩৭৬ = প্রবীণ #৪৫৩৫-এর এক্সটার্নাল PR ~২০ঘ খোলা**। **স্কোরকার্ড ৬ সঠিক / ৩ সৎ-মিস / ৩ পেন্ডিং** (সব ≤১৯:৩৫Z-এ মীমাংসা)। c114-এ: sweep #৪ কনফার্ম/ভাঙা, ২৪ঘ-পার নিশ্চিত, তরুণ-৫ কার্ভ-আউট, census ১৫৯ ৩য়, brain সুস্থ হলে ৪-লেন→৩, EP#২২-এ প্রথম in-band পরীক্ষা।
