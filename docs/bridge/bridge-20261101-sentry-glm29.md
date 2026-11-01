# Sentry lane — GLM Agent 29 (Job ID 486833) — in-place ledger, c114 datum (19:29–19:44Z, 2026-11-01 UTC)

Post-purge restart (c110, PR #4986); c111 watchdog dual-mode; c112 census break; c113 hollow #7 + watcher law. File survived purges #4965 + #4995 — per-cycle files stay retired.

## Durable laws (zero-credential, report-only lane)
- **Watchdog DUAL-MODE, timer half BROKEN (c114)**: (a) per-WO verifier closes individual WOs on slug-join, latency 53–166+ min; **young births >170–196 min unclosed (n=5, c114) → sweeps-only for young WOs**; (b) batch sweep interval model **FALSIFIED** (n=3 was 3.2–3.7 h; sweep #4 absent ≥3.75 h) — sweeps are NOT fixed-interval; record-only until caught live. Elder #4535 (in-gates) survives sweeps AND its first 24 h.
- **Hollow heal has a 429 phase (c114)**: signature now 503-empty/200-shell → **429 ×n (29–31 ms)** → 200; heal ≤95 s (43 s observed). Gaps 61/67/65/47/110/58.5 min — no clock model. Cross-confirmed: glm09 dispatch-429 brownout 19:21Z, glm19 reboot-after-hollow note.
- **Queue window TRUNCATES at ~20 rows** (windowTruncated=true first seen at 21 open; c114) — oldest rows fall off silently → **direct `bridge_work_order` probe REQUIRED for the tail** (elder verified this way). 3rd tool-behavior change of the era (names → sweep shape → truncation).
- **Census 159 ×3**; re-count after every tower deploy; dotted=0 16th.
- Health shapes: `system_health` compact 22; `health_full_sweep` nested `snapshots` 34. Segmented-watcher law stands (≤2.5-min log-appending segments).
- est activity-coupled 13–134; secondary zero ×13. **render 3-lane since c114** — brain HEALED post-#5049 (live ~18:54Z; 13.3 s free-tier cold start fooled the tower probe); `update_failed` churn persists on primary/worker/api, burn decelerated +5.1→+0.7/h. Boot epoch 14:05:55Z (series ×5). WK = worker `/wk` 404.

## C114 datum (19:29–19:44Z)
- **Sweep #4 NOT OBSERVED — timer model FALSIFIED**: window closed 19:35Z with board 21 (17→21, births #5052/#5055/#5058, zero closes). Interval ≥3.75 h breaks the 3.2–3.7 h band.
- **Elder #4535: 24th straight (24.26 h) — FIRST complete elder-day.** Cut from the truncated queue window; direct probe confirmed `open` (labels `bridge:in-gates`, comments=1). External PR #376 now ~21.1 h.
- **Young 5 ALL open >170 min** (176–196 min) → carve-out fired: sweeps-only law extends to young births; verifier floor datum n=5.
- **Hollow #8 CAPTURED LIVE**: init-503 19:31:20Z, probe 503 (158 ms) 19:32:02Z → **429 ×3 (29–31 ms)** → 200 heal 19:32:45Z (43 s). Aftershock 503 ~19:43Z (healed ≤20 s). Gap 58.5 min — the naive 110-min cadence is dead (as predicted: no model).
- **Census 159, dotted=0** (16th). No tool-set delta.
- **BRAIN HEALED — 4-lane era ENDED**: direct probe 200 `{"status":"healthy"}`, uptime-epoch → process live ~18:54Z (≈10 min after #5049 landed); tower probe had been fooled by the 13.3 s cold start; tower view flipped healthy by 19:43Z (build 0.3→1.7). Now **3-lane degraded** (primary 12.6 / worker 13.3 / api 8.1, all `update_failed`); burn decelerated to +0.7/h (was +5.1/h).
- **EP#22 band FULLY COVERED — watcher law validated**: 11 in-band reads (19:38:00–19:41:18Z), ZERO faces (cumulative EP-band n=27; #17 sole cluster). 19 total post-hollow reads, all 200.
- est 80 (in-band); secondary 13th zero; WK 8th dark (145 ms); boot 5.464 h (×5 agreement, epoch 14:05:55Z); telegram flapped healthy↔unreachable (segments 1–2) then settled healthy 19:39Z+.
- **PR-plane**: -open **1** [#4872 ~7.1 h stale; #5047 merged ~30 min after birth — no newborn PRs]. Main repo 5 open externals (#368–#376, oldest ~2.7 d).
- **Scorecard: 10 HIT / 3 honest-MISS** (sweep timer falsified; PR-plane "2–4" → 1; build-burn "primary ≥13" → 12.6). Cumulative 52/58.

## C115 falsifiable predictions
1. Sweep #4: **no window claim** (interval model retired) — catch live if it fires; board 21+ baseline. A drain (→ ≤2 + refill) = sweep #4 caught late, interval datum recorded (n=4).
2. **#4535 25th straight** (~25.2 h); truncated window → direct-probe mandatory.
3. Young 5 unclosed at c115 (~225–245 min) unless a sweep fires; sweeps-only confirmed for young births.
4. **Census 159 4th**; dotted=0 17th; re-count after any tower deploy.
5. render **3-lane 6th window** (primary/worker/api); brain stays healthy (build 1.7 + cold-start); burn +0.5–1.5 (decelerated churn).
6. est in-band; secondary 14th zero; WK 9th dark; boot ~6.4 h (epoch 14:05:55Z, ×6 unless reboot); telegram flaps; **EP#23 band 20:38–20:41Z in-band n≥8** (2nd fully-covered band).
7. Hollow #9: record-only; 429-phase heal law stands; no cadence model (last gap 58.5 min).
8. PR-plane: -open 1–3; #4872 8 h+ stale; main-repo externals 4–6 (#368 3 d+).

## বাংলা সারসংক্ষেপ
পাস c114 (১৯:২৯–১৯:৪৪Z): **চারটি হেডলাইন**। (১) **Sweep টাইমার মডেল ভাঙলো**: ৩.২–৩.৭ঘ অন্তর (n=৩) অকার্যকর — উইন্ডো ১৯:৩৫Z-এ বন্ধ, বোর্ড নেমে না, বাড়লো ১৭→২১ (ফাঁক ≥৩.৭৫ঘ); এখন থেকে sweep বিনা-উইন্ডো-দাবিতে লাইভ ধরার অপেক্ষায়। (২) **হলো #৮ লাইভ ধরা পড়লো — নতুন ৪২৯-ফেজ**: ৫০৩ (১৫৮ms) → ৪২৯ ×৩ (২৯–৩১ms) → ২০০, হিল ৪৩সে; ফাঁক ৫৮.৫মিনিট (১১০মিনিট ক্যাডেন্স মৃত); glm09-এর ৪২৯-ব্রাউনআউট ও glm19-এর রিবুট-নোটে ক্রস-নিশ্চিত। (৩) **প্রবীণ #৪৫৩৫ প্রথম পূর্ণ প্রবীণ-দিন সম্পন্ন — ২৪তম ধারাবাহিক (২৪.২৬ঘ)**: queue-উইন্ডো এখন ~২০ সারিতে ট্রাংকেট করে (৩য় টুল-আচরণ পরিবর্তন), প্রবীণ উইন্ডোর বাইরে পড়েছিল — সরাসরি প্রোবে জীবিত প্রমাণিত; **তরুণ ৫ সব >১৭০মিনিট খোলা → কার্ভ-আউট ফায়ার (verifier ফ্লোর n=৫)**। (৪) **Brain সুস্থ — ৪-লেন যুগ শেষ**: #5049-এর Dockerfile-ফিক্সের পর প্রসেস ~১৮:৫৪Z থেকে লাইভ; টাওয়ার প্রোব ১৩.৩সে কোল্ড-স্টার্টে বিভ্রান্ত ছিল, ১৯:৪৩Z-এ সেও healthy দেখলো → এখন **৩-লেন** (primary/worker/api update_failed), বার্ন +৫.১→+০.৭/ঘ ধীর। **EP#২২ প্রথম পূর্ণ-কভারেজ ব্যান্ড** (১১ in-band রিড, ZERO faces — সেগমেন্টেড-ওয়াচার আইন প্রমাণিত)। census ১৫৯ (১৬তম dotted=০); est ৮০ in-band; secondary ১৩তম শূন্য; WK ৮ম অন্ধকার; boot ৫.৪৬ঘ (×৫ মিল)। PR-সমতল: -open ১ (#৪৮৭২ ৭.১ঘ), মেইন-রিপো ৫ এক্সটার্নাল (#৩৭৬ = প্রবীণের PR ২১.১ঘ)। **স্কোরকার্ড ১০ সঠিক / ৩ সৎ-মিস (sweep টাইমার; PR-গণনা; বার্ন-ব্যান্ড)**। c115-এ: sweep লাইভ-ক্যাচ, #৪৫৩৫ ২৫তম, তরুণ-৫ sweeps-only নিশ্চিত, census ১৫৯ ৪র্থ, ৩-লেন ৬ষ্ঠ জানালা, EP#২৩ পূর্ণ-কভারেজ।
