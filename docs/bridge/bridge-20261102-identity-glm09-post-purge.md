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

## Cycle 21 (2026-11-02 02:09+08) — lean-era re-anchor, no-pick

- Restart file created (this PR) after the docs purge removed the old
  worklog. Dispatch first-try CERTIFIED: claimable 0/5, "System is clean
  and healthy"; heartbeat healthy after one 503 flap + 60s backoff.
- Lean census: 62 passed / 0 failed / 12 subtests EXIT=0 @ 6a3f33d
  (8.3s) — matches glm32's c111 report (62P/0F/9.4s); the old
  CVE-guard ignore flags are obsolete (files pruned).
- CI-gate rehearsal 5/5 PASS @ 6a3f33d (--check-committed 303 scripts,
  boundary self-test, contract_parity 0 byte-drift, deploy_preflight
  step1 0 errors, frontend_perf PASS); standing watch: claim_ttl fix
  intact (TTL SSOT True, OSError fail-closed True).
- No agent-lane defect this cycle; no churn (Invariant 7).

## Reflection Evidence

- **why:** the purge removed the worklog lane file, not the slot —
  restarting at minimum size with only durable facts honors the
  keep-it-small contract and re-anchors the receipt chain (r21) without
  resurrecting pruned history. The claim_ttl_expirer survival check
  matters because that is the only code fix of mine inside the purged
  tree's neighborhood.
- **alternatives_rejected:** re-creating the full receipts table
  (resurrects pruned content against owner intent); filing an issue
  about the purge (deliberate owner action, refs #762, not a defect);
  touching the CVE-guard or maintainer lanes (forbidden to this lane).

## Rollback

Single docs-only new file (brand-new path, no baseSha) — revert this one
PR; no code paths touched this cycle.
