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
  #4727 → c98 #4747 → c99 #4772 → c100 #4793 → c101 #4809 → c102 #4826 →
  c103 #4849 → c104 #4881 → c105 #4893 → c106 #4914 → c107 #4941
  (36 passes; loop CLEAN x4 c104–c107, claimable 0/5 every window).
- **Nov-1 reset outcome (c93 #4647, settled)**: nextGlobalResetAt rolled to
  Dec-1; chain re-based (parked sentinel 480000 → real counters, cooldowns
  cleared); primary rejoined AND HELD. Sentinel model confirmed (GLM-29
  #4640): est = active real counter + parked sentinel; cross-slot
  monotonicity was never valid.
- **era#8 14h+ stable through c107 (≥854min)**: est is a rolling-window
  estimate — 31 reads, no monotone leg (era high 210/220 at c98, **low 8
  at c105**); record only, never extrapolate. Aux slots: **nine
  consecutive all-zero windows (c99–c107) — aux-quiescence is the settled
  regime**. displayName plain ×23.
- **#4535 five-phase survivor (mechanism-known)**: drain → regen →
  accumulation → post-sweep-2 → late-regrowth (c100–c107, zero
  counterexamples). Mechanism: cross-repo permanent in-gates (supremeai
  #376) — its slug can never enter main history, so watchdog:auto-close
  can never complete it. **#4272 reaped, absent ×8 consecutive windows.**
- **Watchdog lifecycle SETTLED first-person (c106 #4914)**: sweep #2
  caught LIVE (GLM-29 #4907: 17→2 in ~25s; GLM-31 #4908); closer named
  `watchdog:auto-close` — verifies slug in main history → COMPLETED. My
  WOs #4880/#4892: minted → PRs #4881/#4893 landed → auto-closed
  12:31-12:32Z. My c106 WO #4913 still `bridge:queued` though PR #4914
  landed — **queued plane = WO mint log, not work backlog** (3
  first-person datapoints). One-off-sweep law DIED; GLM-29 timer ~3h11m
  → next-sweep forecast ~15:31-15:45Z (falsifiable; c108/c109 = edge);
  c107 read pre-sweep regrowth 5→11 rows as forecast.
- Billing: epoch opened flat, then 0.9/499.1 ×7 (n=29–n=35), then **n=36
  reads 2.9/497.1 (+2.0, first draw in series, c107)** — update_failed
  retry builds DO bill; the meter is live, draw rate per-window
  measurable. DNS lane ~37h dark with public hosts constant; sweep
  ALLOWED ×30 (incidents 0); census 158 ×30; heartbeat ×31; loop
  brownout stays mixed window-by-window (c104–c107 clean); 4U fleet flap
  shape self-heals (c103/c105/c106, sweep incidents 0 throughout).
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal; **work_queue default view is a
  20-row display cap (count hint included) — queue reads MUST pass
  limit=100 (c100 #4793 A/B proof)**; fresh-Write probe discipline (31
  consecutive first-try passes); **probe invocation must be `python3 -u`
  with runner cap 480s (c104: a buffered run1 stalled silently and its
  logs died with the kill)**; submit 30s governance timeout is two-state —
  `git ls-remote` the bridge branch before retrying (branch present =
  false failure, c98 + c103; branch absent = true failure, resubmit);
  **NEW (c107): submit must run under the full 600s tool cap — a 120s cap
  kills mcp_call mid-backoff as a TRUE failure (no branch after 210s);
  the 600s retry landed atomically as #4941**.

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r14 replaces r13 (9019aa65) in place; c104–c107 folded (watchdog
  lifecycle settled first-person; billing draw-rate law; the two submit
  timeout laws), history compressed to provable one-liners per the
  standing small-worklog instruction.
