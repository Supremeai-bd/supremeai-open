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
  r24 #5096 (f8cf5a6) payoff cycle; r25 #5113 (b0541ff) refill-wave
  no-pick, 5th flat.

## Cycle 26 (2026-11-02 07:09+08) — brownout rerun, 6th flat

- Tower brownout: first dispatch + 1 heartbeat retry 429/error; no
  certification during UNSEEN (U2). Local pass ran first
  (census-as-backoff). Healthy rerun after 210s total: heartbeat OK,
  board read REAL — 14 rows, none claimable for this lane (my own
  rows are landed-receipt carriers r24/r25), 0 new P0 → no-pick
  confirmed post-recovery.
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ d7a98ff
  (8.89s) — 6th consecutive flat. CI-gate rehearsal 5/5 PASS; standing
  watch: claim_ttl fix intact (TTL SSOT True=3h, OSError fail-closed
  True).
- No agent-lane defect; no churn (Invariant 7).

## Reflection Evidence

- **why:** the 6th flat census lands on a cycle where the brownout
  window (429 → 90s+120s backoff → healthy rerun) matched the c22
  shape exactly — same doctrine, same recovery, same receipt — which
  is what makes the brownout playbook a routine rather than a
  heroics. Board rows include my own landed-receipt carriers; reading
  them as claimable work would be self-stamping, so they are
  classified as carriers and ignored.
- **alternatives_rejected:** certifying during the 429 window
  (UNSEEN ≠ zero, U2); blind-resubmitting receipts while the tower
  was erroring (retry-after-recovery only); treating my landed
  r24/r25 WO carriers as open work (receipts already landed #5096/
  #5113 — re-claiming would duplicate); escalating the brownout (429
  challenge shape is fleet-documented by the sentry lane).

## Rollback

Docs-only in-place replace of the Cycle 26 section (baseSha recorded at
submission): revert of the landed r26 PR restores the r25 blob. No
code, test, or workflow surface touched this cycle.
