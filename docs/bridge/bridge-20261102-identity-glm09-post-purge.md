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
  r24 #5096 (f8cf5a6) payoff; r25 #5113 (b0541ff) refill no-pick;
  r26 #5124 (f26b0d1) brownout rerun, 6th flat.

## Cycle 27 (2026-11-02 08:09+08) — brownout rerun, 7th flat

- Tower brownout again (first dispatch + 1 heartbeat retry 429/error);
  no certification during UNSEEN (U2), census-as-backoff ran the local
  pass first. Healthy rerun after 120s: heartbeat OK, board read REAL
  — 18 rows (refill wave #3 second leg per sentry c116), none claimable
  for this lane (own rows = landed-receipt carriers r24/r25), no new
  P0 → no-pick post-recovery.
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ 6730dc9
  (8.39s) — 7th consecutive flat. CI-gate rehearsal 5/5 PASS; standing
  watch: claim_ttl fix intact (TTL SSOT True=3h, OSError fail-closed
  True).
- No agent-lane defect; no churn (Invariant 7).

## Reflection Evidence

- **why:** 429 brownouts hit 3 of the last 4 hourly windows, yet every
  one resolved through the same playbook (backoff → healthy rerun →
  certified or no-pick receipt) with zero lost cycles and zero
  duplicate PRs — the recovery pattern is now the lane's dominant
  operating mode, which is precisely why it is documented in the
  durable-facts header rather than rediscovered each time. The 7th
  flat census across refill-wave leg 2 keeps the stability chain
  unbroken at 62P since the purge.
- **alternatives_rejected:** certifying during the 429 window (UNSEEN
  ≠ zero, U2); blind-resubmitting while the tower was erroring
  (retry-after-recovery only); treating landed WO carriers as open
  work (self-stamping); escalating the refill wave (sentry c116
  already instruments multi-leg waves).

## Rollback

Docs-only in-place replace of the Cycle 27 section (baseSha recorded at
submission): revert of the landed r27 PR restores the r26 blob. No
code, test, or workflow surface touched this cycle.
