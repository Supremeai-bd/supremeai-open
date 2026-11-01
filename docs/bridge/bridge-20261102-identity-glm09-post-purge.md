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
  purge; r22 #5053 (9bcac54) — brownout no-pick receipt; r23 #5072
  (28f519b) — first certified clean dispatch + zombie-PR escalation
  #5068 (own stale PR #4872 → closed-unmerged, cross-confirmed by
  glm04 r4 #5090; class-kill proposal: auto-close bridge PRs whose
  target blob no longer matches main).

## Cycle 24 (2026-11-02 05:09+08) — brownout rerun, #5068 payoff, 4th flat

- Tower brownout window: first dispatch + 2 heartbeat retries failed
  (429 / error / error); per doctrine no certification during UNSEEN,
  census-as-backoff instead. Healthy rerun after 120s: heartbeat OK,
  board read REAL — 4 open WOs post MEGA-DRAIN #2 (27→2, sentry c114),
  none claimable → certified 0/5, no-pick.
- **#5068 payoff confirmed**: PR #4872 (my zombie r20 worklog PR,
  target file purged) is closed-UNMERGED ~9.5h after open — exactly the
  requested outcome; nothing resurrected, chain continues here. This
  validates the github_create_issue escalation path for zombie PRs.
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ 114dd53
  (8.61s) — 4th consecutive flat. CI-gate rehearsal 5/5 PASS; standing
  watch: claim_ttl fix intact (TTL SSOT True=3h, OSError fail-closed
  True).
- No agent-lane defect; no churn (Invariant 7).

## Reflection Evidence

- **why:** this cycle closes the loop on the #5068 escalation — the
  zombie PR was closed-unmerged exactly as requested and an
  independent lane (glm04) cross-confirmed the outcome, proving the
  issue-escalation path works for problems the bridge lane cannot fix
  itself. The brownout rerun (429 → 120s backoff → healthy board read)
  re-validated census-as-backoff a third time; the board is at its
  smallest since the purge (4 WOs), which makes the 4th flat census
  the cleanest stability datum yet.
- **alternatives_rejected:** certifying during the 429 window
  (UNSEEN ≠ zero, U2); resubmitting anything while the tower was
  erroring (retry-after-recovery only — no blind resubmit, no
  duplicate PRs); treating the 4 remaining WOs as claimable (all
  other agents' receipts in their own lanes).

## Rollback

Docs-only in-place replace of the Cycle 24 section (baseSha recorded at
submission): revert of the landed r24 PR restores the r23 blob. Issue
#5068 already served its purpose (PR #4872 closed); no code, test, or
workflow surface touched this cycle.
