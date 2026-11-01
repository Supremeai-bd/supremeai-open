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
| 44–47 | POST-PURGE RESTART (r15/#4979 … r18/#5045) after founder purge wave #4965–#4969 (Batches 1–5) wiped the 14-revision chain incl. fresh r14 (2da4560/#4959, purged 12 min post-landing); durable facts re-anchored; collection-broken datum (12 orphan tests of purged modules; bridge probed live: no delete ingress → owner lane) → owner-healed (test prune #4988, sentinel-sync #5005, lean reset to 58 SSOT files #4995); census NEW BASELINE: first fully-green in lane history 50P → 62P (glm26 tower429 re-land #5016); SWEEP #3 + MEGA-DRAIN cross-confirmed (board 22→6, ~95% bulk-reap); refill regime began (board 8→15, sentry reports re-landed, owner wave #2 left docs/bridge intact — 15 files kept) | PR #4979, #5006, #5024, #5045 |
| 48 (03:28+08) | r18 LANDED (a539ebc/#5045); standing verify b5c2583 (+11: refill regime — board 15→21 (20 WOs in queue window); TELEGRAM WATCH CLOSED after 4 open windows #5047; brain Dockerfile build fix #5049; sentry c113 hollow #7 healed ≤95s #5051; a94 u4-dupguard restart #5062): census 62 passed / 12 subtests / 0F in 9.23s — 4th consecutive fully-green post-lean, baseline stable; loop claimable 0/5, PR plane 1 open (#4872 orphan); HB first-attempt OK slot z.ai-28 | PR #5064 |
| 49 (04:28+08) | r19 LANDED (d0e43ba/#5064); standing verify 75fc26c (+12: board 21→28 pure additive (oldest queued #4991 4.1h unharvested); SWEEP-4 no-show cross-confirmed + zombie arc CLOSED #5083 — pre-purge orphan PR #4872 closed per glm14 evidence #5076; GLM11 r48 retires the fixed ~3.3h sweep period #5075; PII plateau 166 third pin per glm22 #5080): census 62 passed / 12 subtests / 0F in 9.31s — 5th consecutive fully-green post-lean; loop claimable 0/5, PR plane 0 open; HB first-attempt OK slot z.ai-28 | this worklog |
