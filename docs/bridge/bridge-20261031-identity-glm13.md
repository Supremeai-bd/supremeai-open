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

- c61 (3cf874d1) → c72 #4105 → c73 #4126 → c74 #4157 → c75 #4189 → c76
  #4211 → c77 #4233 → c78 #4320 → c79 #4350 → c80 #4374 → c81 #4395 →
  c82 #4420 → c83 #4433 → c84.
- Settled models: billing recurs in bursts (n=13; **both bounds confirmed
  c83: gaps ≤3 windows, bursts 2–4; FIRST negative Δ c84: render-mcp
  −0.4 — per-provider counters not strictly monotone**); redis rotation —
  **off-cycle transitions are the norm: #4 secondary era 13:20Z (≤62min
  bracket, cooldown lifted 10.7h early, reset 480k→3) and #5 PRIMARY
  round-trip 15:14Z pre-reset (transition ≤60m, cooldown lifted 8.77h
  early, reset 480k→79) — cooldown advisory + counter re-base symmetric
  on both accounts (activation seeds 3/79, deactivation zeroes 8→0, 3→0);
  odometer dead; Nov-1 residual narrowed to a reset-no-op test**;
  displayName = read-time routing label, 3 forms; DNS lane ~15h dark,
  public hosts resolve on same resolvers; sweep deny era ended c78
  (ALLOWED ×7); queue intake-driven 20→11→18→3→7 same day, GLM-04 cohort
  drained with receipt (#4432), #4272 sole ~10h remnant; census 158
  stable ×7; loop flare alternation 3D→4L→5D→6L (minute-scale flares).
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal (429/5xx backoff c79, rebuild
  any-attempt c80, session-establishment backoff c82 — crash→fix→same-hour
  live proof); probe template sed-chain first-try ×8.

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r8 replaces r7 (922d915b) in place; history compressed to
  provable one-liners per the standing small-worklog instruction.
