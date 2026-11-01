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
- **Landed**: r21 re-anchor #5033 (c014fd9) — restart file after the
  purge; r22 #5053 (9bcac54) — brownout no-pick receipt, 2nd flat
  census across the restart boundary.

## Cycle 23 (2026-11-02 04:09+08) — certified clean + zombie-PR housekeeping

- Dispatch CERTIFIED clean: board revived via tower fallback (23 rows,
  0 open P0, claimable 0/5) after gh CLI absence — first certified read
  in the lean era; heartbeat first-try OK.
- Found a zombie in my own lane: stale PR #4872 (old r20 worklog) still
  open while its target file was removed by the docs purge — merging
  would resurrect purged content. Escalated via github_create_issue:
  **#5068** requests close-as-superseded (r20 already landed 843a8d0/
  #4870; chain continues in #5033/#5053) and proposes the class-kill:
  auto-close bridge PRs whose target blob no longer matches main.
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ d09d0c2
  (8.64s) — 3rd consecutive flat. CI-gate rehearsal 5/5 PASS; standing
  watch: claim_ttl fix intact (TTL SSOT True=3h, OSError fail-closed
  True).
- No agent-lane defect; no churn (Invariant 7) — the only lane write is
  this receipt plus the #5068 escalation.

## Reflection Evidence

- **why:** the first certified board read of the lean era turned up a
  real piece of housekeeping in my own lane: a zombie PR whose target
  file a fleet-wide purge had removed. Closing my own PR is outside
  bridge-lane tool reach, so the root-cause-minded move is an
  escalation that both retires the zombie AND names the class-kill
  (target-blob watchdog) so other agents' purged PRs stop inflating
  the open-PR count sentry watches. Filing it keeps the open count
  honest without touching pr_lifecycle_guard (documented fail-open,
  out of scope).
- **alternatives_rejected:** merging PR #4872 as-is (resurrects
  purged content against owner intent, refs #762); editing
  pr_lifecycle_guard to auto-close such PRs myself (documented
  fail-open, forbidden to this lane, and a code churn without a
  solver task); staying silent about the zombie (the open-PR count is
  a fleet health signal — sentry c114 tracks its growth).

## Rollback

Docs-only in-place replace of the Cycle 23 section (baseSha recorded at
submission): revert of the landed r23 PR restores the r22 blob. Issue
#5068 is filed but harmless if closed unused; no code, test, or
workflow surface touched this cycle.
