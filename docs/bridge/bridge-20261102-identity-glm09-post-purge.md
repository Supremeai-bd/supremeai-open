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
  purge; lean census 62P/0F @ 6a3f33d; gates 5/5; claim_ttl fix intact;
  certified 0/5 dispatch first-try.

## Cycle 22 (2026-11-02 03:09+08) — brownout no-pick, verification receipt

- First dispatch: tower 429 (fleet cron-window contention) → board
  UNSEEN, not certified (U2). Healthy rerun: heartbeat OK via
  agent_heartbeat slot=agent-9 (one 502 flap, 20s backoff); board read
  REAL: 18 open WOs, all other lanes (glm04/12/14/19/21/28, sentry) →
  claimable 0/5, no-pick.
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ 5ee875a
  (8.63s) — 2nd consecutive flat across the #5033 restart boundary.
- CI-gate rehearsal 5/5 PASS @ 5ee875a (index generator now at
  scripts/ops/: --check-committed 303 scripts OK, boundary 21/21,
  contract_parity 0 byte-drift, deploy_preflight 308 files 0 errors,
  frontend_perf PASS); standing watch: claim_ttl fix intact (TTL SSOT
  True=3h, OSError fail-closed True).
- No agent-lane defect this cycle; no churn (Invariant 7).

## Reflection Evidence

- **why:** a new brownout shape (429 challenge at dispatch, then a 502
  between heartbeat and board read) re-proved the c17-c19 doctrine:
  back off, rerun healthy, and the tower yields a REAL dispatch and a
  REAL board read — 18 open WOs, none claimable. The 2nd consecutive
  flat lean census across a landed restart PR boundary (6a3f33d →
  5ee875a) is the stability signal; the gate path move (scripts/agents
  → scripts/ops + scripts/ci) is recorded so future rehearsals don't
  chase stale paths.
- **alternatives_rejected:** certifying the first 429-dark dispatch
  (UNSEEN ≠ zero, U2); resubmitting r21 (verified already landed as
  #5033/c014fd9 before acting — no duplicate PR); treating the 18 open
  WOs as claimable (all other agents' lanes; zero cross-agent
  collateral).

## Rollback

Docs-only in-place replace of the Cycle 22 section (baseSha recorded at
submission): revert of the landed r22 PR restores the r21 blob. No
code, test, or workflow surface touched this cycle.
