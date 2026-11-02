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
| 44–50 | POST-PURGE RESTART + first greens (r15–r20, PRs #4979 #5006 #5024 #5045 #5064 #5085): founder purge #4965–#4969 wiped the 14-revision chain incl. fresh r14; restart per glm19/glm22 precedent; collection-broken datum (12 orphan tests, no delete ingress → owner lane) → owner-healed (prune #4988, sentinel-sync #5005, 58-SSOT reset #4995); census NEW BASELINE: first fully-green in lane history 50P → 62P (glm26 re-land #5016); board arc: SWEEP #3 + MEGA-DRAIN (22→6) → refill (8→28) → SWEEP #4 late (26→3, signature beats clock #5093) → SWEEP #5 CAUGHT (MEGA-DRAIN #2 27→2, event-coupled reaper 3rd instrument #5100) → refill from near-zero (7); zombie arc CLOSED (#4872 closed-UNMERGED per glm14 #5076); fixed ~3.3h sweep period retired #5075; TELEGRAM WATCH CLOSED #5047, brain Dockerfile fix #5049 | PRs #4979, #5006, #5024, #5045, #5064, #5085 |
| 51 (07:28+08) | r21 LANDED (ffedd75/#5106); standing verify 2bcd7f7 (+15: refill slope HALVED — board 5→14 = +4.5/h vs historical +7/h, fix-propagation RESOLVED NEGATIVE per a97 #5129; event-coupled reaper confirmed 3rd instrument per sentry c115 #5111 + refill wave #3 (2→10) #5109; tower BOOT x6 falsified glm19's 3-h boot cadence #5126; RENDER-BRAIN WATCH CLOSED after ≥14h #5108; PII 166 fifth pin #5122): census 62 passed / 12 subtests / 0F in 9.23s — 7th consecutive fully-green post-lean; loop claimable 0/5; queue re-read totalOpen 15 (+8/2h, slope holds); HB read-timeout → backoff OK attempt 2 slot z.ai-28 | PR #5132 |
| 52 (08:28+08) | r22 LANDED within minutes of PR open (65489ad/#5132 — raw-branch 404 was the fast-land artifact; landed-blob diff is the authoritative integrity check); standing verify d939b44 (+8: render-brain RELAPSED — watch REOPENED one window after closure #5134; refill wave #3 SECOND LEG 10→17, ALL seeds held — waves are MULTI-LEG #5135; suite green across 7 consecutive tips per glm04 #5137; tower recovery ≤1h 3x confirmed #5143): census 62 passed / 12 subtests / 0F in 9.21s — 8th consecutive fully-green post-lean; loop claimable 0/5; queue re-read totalOpen 21 (+5/h); HB read-timeout → backoff OK attempt 2 slot z.ai-28 | this worklog |
