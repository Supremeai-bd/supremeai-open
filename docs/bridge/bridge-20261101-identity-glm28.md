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
| 44–48 | POST-PURGE RESTART + first greens (r15–r18, PRs #4979 #5006 #5024 #5045): founder purge #4965–#4969 wiped the 14-revision chain incl. fresh r14 (2da4560/#4959, purged 12 min post-landing); restart per glm19/glm22 precedent; collection-broken datum (12 orphan tests, no delete ingress → owner lane) → owner-healed (prune #4988, sentinel-sync #5005, 58-SSOT reset #4995); census NEW BASELINE: first fully-green in lane history 50P → 62P (glm26 re-land #5016); SWEEP #3 + MEGA-DRAIN (board 22→6) then refill regime (8→21): sentry reports re-landed, TELEGRAM WATCH CLOSED #5047, brain Dockerfile fix #5049, a94 dupguard restart #5062 | PRs #4979, #5006, #5024, #5045 |
| 49 (04:28+08) | r19 LANDED (d0e43ba/#5064); standing verify 75fc26c (+12: board 21→28 pure additive (oldest queued #4991 4.1h unharvested); SWEEP-4 no-show cross-confirmed + zombie arc CLOSED #5083 — pre-purge orphan PR #4872 closed per glm14 evidence #5076; GLM11 r48 retires the fixed ~3.3h sweep period #5075; PII plateau 166 third pin per glm22 #5080): census 62 passed / 12 subtests / 0F in 9.31s — 5th consecutive fully-green post-lean; loop claimable 0/5, PR plane 0 open; HB first-attempt OK slot z.ai-28 | PR #5085 |
| 50 (05:28+08) | r20 LANDED (ec18df9/#5085); standing verify eced592 (+9: SWEEP #4 HITS LATE (26→3, ~5.5h, signature beats clock #5093) then SWEEP #5 CAUGHT — MEGA-DRAIN #2 board 27→2, sentry c114 pins 20:31–20:43Z, event-coupled reaper 3rd instrument #5100; #4872 confirmed closed-UNMERGED ~9.5h post-open, not landed #5090; queue re-read totalOpen 7 — refill restarting from near-zero): census 62 passed / 12 subtests / 0F in 9.00s — 6th consecutive fully-green post-lean; loop claimable 0/5; HB first-attempt OK slot z.ai-28 | this worklog |
