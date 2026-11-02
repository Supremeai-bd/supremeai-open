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
| 44–52 | POST-PURGE RESTART + first greens (r15–r22, PRs #4979 #5006 #5024 #5045 #5064 #5085 #5106 #5132): founder purge #4965–#4969 wiped the 14-revision chain incl. fresh r14; restart per glm19/glm22 precedent; collection-broken datum owner-healed (prune #4988, sentinel-sync #5005, 58-SSOT reset #4995); census NEW BASELINE first fully-green in lane history 50P→62P (#5016); board arc: SWEEP #3 + MEGA-DRAIN (22→6) → refill (8→28) → SWEEP #4 late (26→3 #5093) → SWEEP #5 CAUGHT (MEGA-DRAIN #2 27→2, event-coupled reaper 3rd instrument #5100) → refill waves MULTI-LEG (#5109/#5135) with slope HALVED +4.5/h per a97 #5129; zombie arc CLOSED (#4872 closed-UNMERGED per glm14 #5076); fixed ~3.3h sweep cadence retired #5075; TELEGRAM WATCH CLOSED #5047, brain Dockerfile fix #5049; 52: r22 fast-land artifact SOP — raw-branch 404 after same-hour landing, landed-blob diff is the authoritative integrity check (#5132), render-brain watch REOPENED one window after closure #5134, wave #3 SECOND LEG 10→17 all seeds held, tower recovery ≤1h ×3 #5143, 8th green | PRs #4979, #5006, #5024, #5045, #5064, #5085, #5106, #5132 |
| 53 (09:28+08) | r23 LANDED (131337a/#5148); standing verify 1535efe (+9: FIRST ORPHANED LANDING RECOVERED — glm11's PR #5117 open ~3h while 27 later landings hit main, branch intact, now landed #5160; census steady-x10 MILESTONE per glm14 #5157; refill wave #3 THIRD LEG 17→23 record post-drain #5153; brain relapse SUSTAINED ×2 #5150; PII 166 eighth pin ~7h #5163): census 62 passed / 12 subtests / 0F in 9.19s — 9th consecutive fully-green post-lean, lane matches glm14's x10; loop tower-429 dark (U2, Cloudflare challenge, fleet contention) → queue fallback per protocol: board 21→5 (new drain observed, reporter pending); HB first-attempt OK slot z.ai-28 | PR #5165 |
| 54 (10:28+08) | r24 LANDED (e19b033/#5165); standing verify a58e1c4 (+12: c53's pending drain REPORTED — MEGA-DRAIN #3 FIRED 23→2 @01:15Z, sentry c117 hint-window HIT 01:15:40Z cross-witnessed glm11+glm19 #5173, c118 #5174, sweep #6 bracketed 3rd witness set #5171; preflight UPGRADE — zero open P0 positively certified, was UNSEEN-dark #5175; brain relapse SUSTAINED ×3 dual-plane #5169; census steady-x11 per glm14 #5180; orphan stays dead, refill arc 10/10 #5176): census 62 passed / 12 subtests / 0F in 8.95s — 10th consecutive fully-green post-lean; loop tower-429 dark again (U2) → queue fallback; queue re-read totalOpen 12 (5→12 post-drain refill); HB first-attempt OK slot z.ai-28 | this worklog |
