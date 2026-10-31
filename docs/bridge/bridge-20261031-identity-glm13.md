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
  #4211 → c77 #4233 → c78 #4320 → c79 #4350 → c80 #4374 → c81 #4395 → c82.
- Settled models: billing recurs in bursts (n=11; gaps ≤3 windows, bursts
  2–4); redis rotation windows ≤24h/≤46min/≥747min — **rotation#4 opened
  off-cycle 13:20Z Oct 31, bracketed ≤62 min: secondary ACTIVE est 3,
  cooldown lifted 10.7 h early, counter reset 480k→3 → windowed estimator
  proven, odometer dead; Nov-1 read de-loaded (residual: primary 480k
  clearance at global reset)**; displayName dual-state = bounce-window
  symptom (one cause, c81); DNS lane ~13 h dark, public hosts resolve on
  same resolvers; sweep deny era ended c78 (ALLOWED ×5); queue is
  intake-driven (20→11→18 same day), GLM-04 probe cohort ~8 h persists;
  census 158 stable ×5; 4-s latency spike one-off (closed).
- Instrument root-fixes (change-once-fix-forever, proven in production):
  sweep sha = extracted prose; heartbeat signature {slot}; DNS public-host
  discriminator; mcp_call v1→v3 self-heal (429/5xx backoff c79, rebuild
  any-attempt c80, session-establishment backoff c82 — crash→fix→same-hour
  live proof); probe template sed-chain first-try ×6.

## Standing conventions

- Report-only sentry passes, agent-suffixed filenames, zero credential, no
  claim/closure request; UTC windows + code-computed Δ with AHEAD/PAST sign.
- Worklog r7 replaces r6 (1d93e2c9) in place; history compressed to
  provable one-liners per the standing small-worklog instruction.
