# GLM Agent 28 — Worklog (Job ID 486832)

> Post-purge restart (2026-11-01). The founder's doc purge wave
> (#4965–#4969, Batches 1–5: 308 bridge/report files / 16,356 lines
> in Batch 1 alone, refs #762 "lean 50–100 files") removed every lane
> worklog, including this lane's 14-revision chain (r1–r14, PRs
> #4658–#4959). Nothing is restored verbatim; full history stays in
> git and the WO archive. This file restarts the small live slot per
> the standing hourly mandate ("keep worklog small, remove old
> worklog and keep only important part"), following the glm19 #4971 /
> glm22 #4973 restart precedent — only the durable facts a fresh
> reader needs.

## Durable facts carried forward

- Identity: GLM Agent 28, Job ID 486832, hourly cron cadence; door =
  raw urllib MCP client (chunk-boundary-safe) → AGENTS.md/bridge
  contract → full census before every receipt; HB slot z.ai-28
  (primary redis).
- #4471 chain (CLOSED pre-purge): fail-open `_INDEX.md` regen
  root-caused; evidence-only PR #4590 (no Closes line); class-killed
  by glm10's committed-blob freshness gate #4612 (25604a3);
  independent third-party mechanical proof by glm25 #4671.
- Payload-corruption class (repaired #4658): a bridge payload landed
  as a raw unified-diff hunk (`--- a/` on L1) → SyntaxError → pytest
  collection error on main → every census ran 0 tests. Repaired
  same-hour (364d4bd/#4658, battery 12/12). Class note: submit
  pipelines must apply-check hunk integrity before diff-mode landing
  or fall back to full_file.
- Census arc (pre-purge): 13 consecutive FLAT red-plane cycles (2F =
  CVE owner duo only) across four board regimes (drain → mass
  land-verification sweep → rebuild → pure accumulation); final
  pre-purge datum 2F/2535P/14S at b46b2ba.
- False-red habit (durable): stale untracked `__pycache__` under
  pruned paths survives on long-lived sandboxes and fires prune
  sentinels — sweep artifacts before reading a census (root-caused
  cycle 43; independently corroborated by glm32 r30).

## Landed cycles (post-restart)

| Cycle | Contribution | Proof |
| - | - | - |
| 44–54 | POST-PURGE RESTART + first greens (r15–r24, PRs #4979 #5006 #5024 #5045 #5064 #5085 #5106 #5132 #5148 #5165): founder purge #4965–#4969 wiped the 14-revision chain incl. fresh r14; restart per glm19/glm22 precedent; collection-broken datum owner-healed (prune #4988, sentinel-sync #5005, 58-SSOT reset #4995); census NEW BASELINE first fully-green in lane history 50P→62P (#5016); board arc: SWEEP #3 + MEGA-DRAIN (22→6) → refill (8→28) → SWEEP #4 late (26→3 #5093) → SWEEP #5 CAUGHT (MEGA-DRAIN #2 27→2, event-coupled reaper 3rd instrument #5100) → refill waves MULTI-LEG (#5109/#5135) with slope HALVED +4.5/h per a97 #5129; zombie arc CLOSED (#4872 closed-UNMERGED per glm14 #5076); fixed ~3.3h sweep cadence retired #5075; TELEGRAM WATCH CLOSED #5047, brain Dockerfile fix #5049; 52: r22 fast-land artifact SOP — raw-branch 404 after same-hour landing, landed-blob diff is the authoritative integrity check (#5132), render-brain watch REOPENED one window after closure #5134, wave #3 SECOND LEG 10→17 all seeds held, tower recovery ≤1h ×3 #5143, 8th green; 53: FIRST ORPHANED LANDING RECOVERED (glm11 PR #5117 open ~3h under 27 later landings, then landed — patience not panic #5160), wave #3 THIRD LEG 17→23 #5153, steady-x10 milestone #5157, brain relapse ×2 #5150, PII 166 8th pin #5163, 9th green; 54: MEGA-DRAIN #3 reported by sentries (23→2 @01:15Z, hint-window HIT cross-witnessed #5173/#5174/#5171), preflight UPGRADE zero open P0 certified #5175, brain relapse ×3 #5169, 10th green | PRs #4979, #5006, #5024, #5045, #5064, #5085, #5106, #5132, #5148, #5165 |
| 55 (11:28+08) | r25 LANDED (4e668e8/#5185); standing verify 205ed6d (+5: FIRST REAL LOOP DISPATCH since purge — #1304 P1 33 stale queued Actions runs assigned #5199, glm04 classified ALL 33 orphaned/stale, zero genuinely pending #5201; WAVE #4 LEG-2 board 9→20 (+11 births incl. 5 ci-failed WOs, re-record path fired) #5196; HOLLOW #10 first in-band face — 503 variant 7.6s hang healed ≤25s #5195; additive burst 10→21 no sweep #5197): census 62 passed / 12 subtests / 0F in 9.13s — 11th consecutive fully-green post-lean; loop tower-429 dark 3rd straight (U2) → queue fallback; queue totalOpen 24 (12→24, truncated); HB brownout timeout→503→OK attempt 3 slot z.ai-28 — 503 face matches HOLLOW #10 in-band capture | PR #5210 |
| 56 (12:28+08) | r26 LANDED (6172332/#5210); FIRST REAL SOLVER DISPATCH to this lane since purge — loop assigned #5192 (ci-fixer, P2-medium); remedy = supremeai-core .github/workflows → OUT OF ENVELOPE twice (satellite #751 + protected .github/) → evidence-only discharge per mandate: WO #5236/PR #5237 (U3 re-check honestly dark — private repo + REST rate limit; Agent 05 claim→release #621 corroboration; remediation sketch one-for-one with acceptance criteria; no Closes line); #5189 skipped anti-stampede (receipt in flight #5207); census 67 passed / 12 subtests / 0F in 9.27s — 12th consecutive green on NEW BASELINE 67P (+5P bridge_intake_pagination join); pick pre-verify dark (landing cross-scan + feedback 503) | this worklog |
