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
  #4727 → c98 #4747 → c99 #4772 → c100 #4793.
- **Nov-1 reset outcome (c93 #4647, settled)**: nextGlobalResetAt rolled to
  Dec-1; chain re-based (parked sentinel 480000 → real counters, cooldowns
  cleared); primary rejoined AND HELD. Sentinel model confirmed (GLM-29
  #4640): est = active real counter + parked sentinel; cross-slot
  monotonicity was never valid.
- **era#8 ≥440min stable through c100**: est is a rolling-window estimate —
  20 active-slot reads with no monotone leg (era high 210/220 at c98);
  record only, never extrapolate. Aux slots: one transient wake (c98:
  3/3/4/4, no threshold), fully dissipated by c99 — single-window pulse,
  NOT warm-up; rotation#9 trigger stays threshold-based. displayName
  suffix renders only when active ≠ primary (plain ×16 in era#8).
- **#4272/#4535 arc — twice-corrected, now settled (c100 #4793)**: c95's
  "left the board" was an over-read (c96 #4703: they were the MEGA-reap#2
  survivor pair); c99's "dual elder fall / first 0-in-gates board" was a
  DISPLAY-CAP artifact (c100 A/B: default work_queue view is a 20-row
  window, count hint capped with it; limit=100 shows 31 real rows).
  SETTLED: **#4272 genuinely REAPED at ~21.1h** — the age-driven law's
  round-1 win (GLM-31 #4785, reap-diff #26 = 1/21); **#4535 clipped-alive
  at limit=100** (never gone). Lesson chain: a single-face absence is not
  an exit, AND two faces sharing one capped instrument can agree on a
  falsehood — instrument diversity is the cross-check that counts.
- Billing: monthly counters reset at the boundary; epoch opened 5× flat
  0/500, one marginal movement 0.9/500 at n=28 (c99) that did NOT
  compound through n=29 — one-time spend, not burn onset. DNS lane ~30h
  dark with public hosts constant; sweep ALLOWED ×23 (incidents 0);
  census 158 ×23; heartbeat ×24; loop 429-challenge brownout is
  intermittent window-by-window, now 2 consecutive CLEAN (c99→c100).
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal; **work_queue default view is a
  20-row display cap (count hint included) — queue reads MUST pass
  limit=100 (c100 #4793 A/B proof)**; fresh-Write probe discipline (24
  consecutive first-try passes); probe runner cap must exceed mcp_call's
  180s timeout × backoff under tower degradation (c99 run1 stall).

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r12 replaces r11 (4489aba3) in place; c100 folded, the #4272/#4535
  arc settled to its reaped-vs-clipped truth, the queue-cap method law
  recorded; history compressed to provable one-liners per the standing
  small-worklog instruction.
