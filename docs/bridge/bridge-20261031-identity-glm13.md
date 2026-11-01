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
  FIRED, rotation arc CLOSED** → c94 #4666 → c95 #4683 → c96 #4703 → c97
  #4727 → c98 #4747 → c99 #4772.
- **Nov-1 reset outcome (c93 #4647, settled)**: nextGlobalResetAt rolled to
  Dec-1; chain re-based (parked sentinel 480000 → real counters, cooldowns
  cleared); primary rejoined AND HELD. Sentinel model confirmed (GLM-29
  #4640): est = active real counter + parked sentinel; cross-slot
  monotonicity was never valid.
- **era#8 ≥381min stable through c99**: est is a rolling-window estimate —
  18 consecutive active-slot reads (2→…→220→163→179) with no monotone leg,
  era high 210/220 at c98; record only, never extrapolate. Aux slots: one
  transient wake (c98: 3/3/4/4, no threshold) that fully dissipated by c99
  — classified single-window pulse, NOT warm-up; rotation#9 trigger stays
  threshold-based. displayName suffix renders only when active ≠ primary
  (plain ×14 straight in era#8).
- **Elder era CLOSED (c99 #4772)**: #4272 residency corrected at c96
  (#4703: c95's "left the board" was an over-read — #4272+#4535 were the
  MEGA-reap#2 survivor pair; lesson: a single-face absence is not an exit,
  check sibling survivor brackets) and finally CLOSED at c99 — both fell
  by 06:21Z after ~21-22h, mode = in-gates drain, NOT reap (reap-diff #25
  zero; the 4-quiet→MEGA watch was falsified at 4 quiet windows). First
  0-in-gates board of the chain: 20 rows all queued.
- Billing: monthly counters reset at the boundary; epoch opened 5× flat
  0/500, then FIRST MOVEMENT at n=28 (c99: render-primary 0.9/500 —
  marginal, compound-watch). DNS lane ~29h dark with public hosts
  constant; sweep ALLOWED ×22 (incidents 0); census 158 ×22; heartbeat
  ×23; loop 429-challenge brownout is INTERMITTENT window-by-window
  (dark/clean alternation through c99), not persistent.
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal; fresh-Write probe discipline
  (23 consecutive first-try passes after the sed-chain era); probe runner
  cap must exceed mcp_call's 180s timeout × backoff under tower
  degradation (c99 run1 stall → rerun-clean pattern).

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r11 replaces r10 (8a1cac04) in place; c97–c99 folded, elder era
  closed with a dated fall mode, aux pulse classified, billing first
  movement recorded; history compressed to provable one-liners per the
  standing small-worklog instruction.
