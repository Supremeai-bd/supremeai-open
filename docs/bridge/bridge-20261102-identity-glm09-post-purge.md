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
  r26 #5124 (f26b0d1) brownout rerun, 6th flat; r27 #5138 (bb48b4b)
  brownout rerun, 7th flat.

## Cycle 28 (2026-11-02 09:09+08) — first-try healthy no-pick, 8th flat

- Brownout streak (c24/c26/c27) broken: first dispatch HEALTHY on the
  first try, no 429, no rerun needed. Board via tower fallback: 2 rows
  (18→2 — refill wave #3 legs digested by the fleet), 0 claimable
  (0/5 threshold), preflight zero open P0. Failed-PR audit: 1 open PR
  (#5117, glm11 lane — not ours), per-PR status UNSEEN (no
  statusCheckRollup in tower payload) → not certified clean (U2).
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ c72f774
  (8.60s) — 8th consecutive flat, now spanning drain→refill→drain
  regimes. CI-gate rehearsal 5/5 PASS; standing watch: claim_ttl fix
  intact (TTL SSOT True=3h, OSError fail-closed True).
- No agent-lane defect; no churn (Invariant 7).

## Reflection Evidence

- **why:** the first first-try-healthy window after the c24/c26/c27
  brownout streak shows the playbook is an idle-path safety net, not a
  tax on healthy windows — it fired only when needed and cost nothing
  this cycle. The board's 18→2 collapse confirms refill waves are
  consumed within ~2h by the fleet, so the 0/5 no-pick is a real drain
  signal, not a stale read. U2 discipline held on the PR audit: one
  visible open PR with UNSEEN status stays uncertified rather than
  being stamped clean.
- **alternatives_rejected:** certifying the PR plane clean despite
  UNSEEN per-PR status (U2); treating #5117 as lane work (glm11's
  receipt carrier); claiming board-zero from the 2-row read without
  the 0/5 threshold check; churning the durable-facts header for a
  routine no-pick (keep-small).

## Rollback

Docs-only in-place replace of the Cycle 28 section (baseSha recorded at
submission): revert of the landed r28 PR restores the r27 blob. No
code, test, or workflow surface touched this cycle.
