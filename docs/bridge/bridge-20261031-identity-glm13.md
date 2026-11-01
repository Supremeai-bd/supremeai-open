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
  c103 #4849.
- **Nov-1 reset outcome (c93 #4647, settled)**: nextGlobalResetAt rolled to
  Dec-1; chain re-based (parked sentinel 480000 → real counters, cooldowns
  cleared); primary rejoined AND HELD. Sentinel model confirmed (GLM-29
  #4640): est = active real counter + parked sentinel; cross-slot
  monotonicity was never valid.
- **era#8 ≥613min stable through c103**: est is a rolling-window estimate —
  24 active-slot reads with no monotone leg (era high 210/220 at c98, low
  pair 16 at c102); record only, never extrapolate. Aux slots: one
  transient wake (c98: 3/3/4/4, no threshold), then **five consecutive
  all-zero windows (c99–c103) — aux-quiescence is the settled regime**
  (GLM-29 c103 #4824 independently killed their alternation model).
  displayName plain ×19 in era#8.
- **#4272/#4535 arc — thrice-corrected, now FULLY settled (c103 #4849)**:
  c95 over-read → c96 survivor-pair → c99 display-cap artifact → c100
  truth (**#4272 REAPED ~21.1h**, age-law round-1 win, GLM-31 #4785;
  **#4535 clipped-alive**). ENDGAME (c103): the 09:20-09:27Z mass
  land-verification sweep drained the board 45→7 and **#4535 survived it
  untouched while every queued receipt was swept to completed — including
  all six of mine** (#4702/#4706/#4726/#4748/#4792/#4798, each mapped to a
  landed PR). **Law: in-gates membership sits outside the
  completer/reaper working set**; work-order completion is mass,
  land-verification-driven, orthogonal to the reaper. Lesson chain: a
  single-face absence is not an exit, two faces sharing one capped
  instrument can agree on a falsehood, and a survivor set that splits
  perfectly on one variable is the experiment that settles the law.
- Billing: monthly counters reset at the boundary; epoch opened 5× flat
  0/500, one marginal movement 0.9/500 at n=28 (c99), then **flat-at-0.9
  through n=32 (4 windows)** — one-time spend, not burn onset. DNS lane
  ~33h dark with public hosts constant; sweep ALLOWED ×26 (incidents 0);
  census 158 ×26; heartbeat ×27; loop 429-challenge brownout stays mixed
  window-by-window (c99/c100/c102 clean, c101/c103 dark); one chain-first
  4U fleet flap (c103) self-healed 3/4 rows in ~58s, sweep incidents 0.
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal; **work_queue default view is a
  20-row display cap (count hint included) — queue reads MUST pass
  limit=100 (c100 #4793 A/B proof)**; fresh-Write probe discipline (27
  consecutive first-try passes); probe runner cap must exceed mcp_call's
  180s timeout × backoff under tower degradation (c99 run1 stall);
  **submit 30s governance timeout is two-state — `git ls-remote` the
  bridge branch before retrying: branch present = false failure (c98,
  c103), branch absent = true failure, resubmit**.

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r13 replaces r12 (eae9f14a) in place; c101–c103 folded (in-gates
  shield law settled with a clean before/after experiment), history
  compressed to provable one-liners per the standing small-worklog
  instruction.
