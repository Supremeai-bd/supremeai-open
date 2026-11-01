# GLM Agent 09 — Worklog (post-purge restart, Job ID 486738)

> Continuation of `bridge-20261031-identity-glm09.md` (chain r12→r20, 9
> landings there: #4520→#4870; r1-r11 live in
> `bridge-20261030-identity-glm09.md`; last landing = 843a8d0/PR #4870),
> removed by the owner-side docs purge (Batch 1 of 5, refs #762). This
> file restarts the slot receipt at minimum size (r21 re-anchor). Total
> merged landings across both files: 20. Compressed durable facts:

- **Root-cause fixes shipped (r1-r12)**: parity reds (27 tests), tower
  tool-name drift, clock-coupled fixture bomb class, no-secret-logs FP
  class, shield whole-tree precision 58 FP→0, stale-branch pruner
  fail-open→fail-closed (#4470), ingress opener divergence lie (#4502),
  claim watchdog fail-closed + #57 TTL SSOT (#4516 — scripts/agents/
  claim_ttl_expirer.py SURVIVED the code purge, re-verified below).
- **Watch closed**: #4471 (pipeline.yml regen `|| true` defeating the
  index gate) class-killed upstream by 25604a3/#4612 `--check-committed`;
  verified locally rc=0 before the purge.
- **Brownout doctrine (c17-c19)**: 429 challenge = fleet cron-window
  contention, not tower-down; census-as-backoff; UNSEEN never certified
  (U2); the healthy rerun always yielded a REAL dispatch.
- **Census across eras**: pre-purge 2358/13/0 flat ×8 → lean era after
  owner prunes #4984/#4988/#4995: 62P/0F (below); scripts/ops/_INDEX.md
  559→303 scripts, 6→2 hand sections.
- **Landed**: r21 re-anchor #5033 (c014fd9); r22 #5053 (9bcac54)
  brownout receipt; r23 #5072 (28f519b) first certified dispatch +
  zombie-PR escalation #5068 (stale PR #4872 → closed-unmerged,
  cross-confirmed glm04 r4 #5090, end-to-end resolved glm14 u5 #5094);
  r24 #5096 (f8cf5a6) — #5068 payoff cycle, 4th flat census.

## Cycle 25 (2026-11-02 06:09+08) — refill-wave no-pick, 5th flat

- Dispatch first-try CERTIFIED: board 11 rows (refill wave #3 — 8
  fresh mints 5089..5107 after the 27→2 MEGA-DRAIN, per sentry c115),
  0 open P0, claimable 0/5; 0 open PRs visible (zombie era over);
  heartbeat first-try OK.
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ 37f900b
  (9.04s) — 5th consecutive flat across all board regimes (drain →
  minimum → refill). CI-gate rehearsal 5/5 PASS; standing watch:
  claim_ttl fix intact (TTL SSOT True=3h, OSError fail-closed True).
- No agent-lane defect; no churn (Invariant 7).

## Reflection Evidence

- **why:** the 5th flat census now spans three different board
  regimes in three cycles (MEGA-DRAIN → 4-row minimum → 11-row refill
  wave), which is the strongest evidence yet that the lean suite's
  stability is regime-independent — the mint cadence refilling the
  board is the system working, not noise. The zombie-PR era closing
  (0 open PRs) completes the #5068 arc started in c23: escalate what
  you cannot fix, verify the fix, record the payoff.
- **alternatives_rejected:** reading the 8 fresh mints as claimable
  work for this lane (mint cadence serves solvers with matching
  scope; none addressed this lane); escalating the refill wave as an
  event (sentry c115 already instruments it — duplicate observation
  adds no value); touching pr_lifecycle_guard while its zombie class
  is quiet (documented fail-open, no defect to fix).

## Rollback

Docs-only in-place replace of the Cycle 25 section (baseSha recorded at
submission): revert of the landed r25 PR restores the r24 blob. No
code, test, or workflow surface touched this cycle.
