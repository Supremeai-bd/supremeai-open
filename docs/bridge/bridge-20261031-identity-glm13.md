# GLM Agent 13 — Worklog (Job ID 486783)

> Post-#3524 archive restart — old lane history lives in supremeai-archive per
> the founder mandate (5fec348). Small durable-facts file, replaced in place
> every cycle (keep-it-small contract).

## Durable facts (compressed; PR proof inline)

- Identity: GLM Agent 13, tower slot agent-13; mcp_call.py session helper
  v3 (CLI truncates at 12k — module import + json-dump for large payloads).
- Receipts lane (all landed): #3195, #3093, ARW three-layer, failed-PR
  audit tower fallback, #3649 shadow-guard root cause, RBAC census,
  task-3354 closure-integrity, U6 registry discipline, task-3855 stale-base
  triage; P0 #4250 triage (PR #4257, 38646872; GLM-09 #4258 agreement).

## Sentry chain (task-3376, report-only parallel passes; all landed)

- c61 (3cf874d1) → c72–c91 folded (rotation#4/#5 off-cycle eras; mega-reap
  era; est non-monotone first proof; #4471 dispatch receipt) → c92 #4628
  (secondary pre-reset re-arm) → **c93 #4647 DECISIVE: Nov-1 00:01Z reset
  FIRED, rotation arc CLOSED** → c94 #4666 (era#8 first full hour) → c95
  #4683 → c96 #4703.
- **Nov-1 reset outcome (c93 #4647, settled)**: nextGlobalResetAt rolled to
  Dec-1; chain re-based (parked sentinel 480000 → real counters, cooldowns
  cleared); primary rejoined AND HELD. Sentinel model confirmed (GLM-29
  #4640): est = active real counter + parked sentinel; cross-slot
  monotonicity was never valid.
- **era#8 ≥195min stable (c96 #4703)**: est is a rolling-window estimate —
  10 consecutive active-slot reads (2→12→…→44→45→61) with no monotone leg;
  record only, never extrapolate. displayName suffix renders only when
  active ≠ primary (plain ×8 straight in era#8).
- **#4272 residency CORRECTED (c96 #4703)**: c95's "left the board" was an
  over-read — #4272+#4535 are the MEGA-reap#2 survivor pair (reap-diff #22:
  18/20, board 20→3→4 at 02:38-02:41Z; GLM-29 #4697 and GLM-11 #4700
  concur). Lesson: a single-face absence is not an exit — check sibling
  survivor brackets before dating an exit. Residency continuous ~20.5h+.
- Billing: monthly counters reset at the boundary; the new epoch opens 3×
  flat 0/500 through n=25 (first ~3h15m of Nov with zero build-minutes).
  DNS lane ~26h dark with public hosts constant; sweep ALLOWED ×19; census
  158 ×19; heartbeat ×20; loop 429-challenge brownout recurs in cron
  windows (4 consecutive hours through c96) while the PR plane revives
  hourly.
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal; fresh-Write probe discipline
  (20 consecutive first-try passes after the sed-chain era).

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r10 replaces r9 (1776a83d) in place; c94–c96 folded, #4272
  residency corrected, era#8/billing series updated; history compressed to
  provable one-liners per the standing small-worklog instruction.
