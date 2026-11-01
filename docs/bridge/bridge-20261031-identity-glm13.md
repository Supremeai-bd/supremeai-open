# GLM Agent 13 — Worklog (Job ID 486783)

> Post-#3524 archive restart — old lane history lives in supremeai-archive per
> the founder mandate (5fec348). Small durable-facts file, replaced in place
> every cycle (keep-it-small contract).

## Durable facts (compressed; PR proof inline)

- Identity: GLM Agent 13, tower slot agent-13; mcp_call.py session helper
  v3 (CLI truncates at 12k — module import + json-dump for large payloads).
- Receipts lane: #3195 (#3214), #3093 (#3279), ARW three-layer (#3496),
  failed-PR audit tower fallback (#3602), #3649 shadow-guard root cause,
  sentry c61 series-first all-green (3cf874d1), RBAC census 158->18 (#3751),
  task-3354 closure-integrity (#3763), U6 registry discipline (#3805, #3828),
  task-3855 stale-base triage receipt #3882 (035ba868).
- **P0 #4250 triage (PR #4257, 38646872)**: "[core] ci failed on main" lives
  in the PRIVATE satellite supremeai-core; scheduled job red on the IDENTICAL
  commit (environment class); unguarded upload-sarif@v4 isolated; remedies
  admin-only. Converging triage: GLM Agent 09 (#4258) — independent agreement.

## Sentry chain (task-3376, report-only parallel passes; all landed)

- c61 (3cf874d1) → c72–c84 folded (rotation#4/#5 off-cycle eras; mega-reap
  era) → c89 #4553 (est non-monotone first proof) → c90 #4574 (downward
  re-sync default) → c91 #4604 (#4471 dispatch receipt, stale-claim guard
  held) → c92 #4628 (secondary pre-reset re-arm; post-mega queue 4) →
  **c93 #4647 DECISIVE: the Nov-1 00:01Z reset FIRED — arc closed**.
- **Rotation arc CLOSED at the Nov-1 reset (c93 #4647)**: the scheduled
  global reset rolled nextGlobalResetAt to Dec-1, re-based every slot
  (parked sentinel 480000 → real counters, cooldowns cleared), and primary
  rejoined AND HELD (est 2→12 monotone in 20s; ≥18min hold vs rotation#8's
  <6.5min rehearsal). Sentinel model confirmed (GLM-29 #4640): est = active
  real counter + parked sentinel; activation re-floors; cross-slot
  monotonicity was never valid — the c89 series is explained. Off-cycle
  transitions (c83), pre-reset re-arm (c92) and the 3-activePrimaries-in-
  8min oscillator (#4640) were all pre-reset phenomena of a bounded monthly
  oscillator.
- Other settled models: billing monthly counters RESET at the boundary
  (0/500 both providers; n=22 closes the era — bursts 2–4 / gaps ≤3
  windows and the first negative Δ at c84 were era-bound); displayName
  "[auto-rotated: X]" suffix renders only when active ≠ primary (c92 vs
  c93 faces); DNS lane ~23h dark with public hosts constant; sweep ALLOWED
  ×16; census 158 ×16; #4272 survives every reap + the epoch boundary
  (12th window ~17.5h); #4471 arc closed (class-kill #4612; closure-gap
  #4634 stays admin-lane); loop 429-challenge brownout recurs in cron
  windows (4th shape, GLM-32 r14) while the PR plane revives hourly.
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal; fresh-Write probe discipline
  (17 consecutive first-try passes after the sed-chain era).

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r9 replaces r8 (5a665fbb) in place; the Nov-1 reset outcome is
  folded and the rotation/billing series are closed; history compressed to
  provable one-liners per the standing small-worklog instruction.
