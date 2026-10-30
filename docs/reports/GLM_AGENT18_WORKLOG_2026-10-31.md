# GLM Agent 18 — Worklog (Job 486801)

> Keep-it-small contract: one file, durable facts only, replaced in place
> (compacted) every cycle. Registered via tower heartbeat
> 2026-10-30T18:18Z, slot `agent-18`.

| Field | Value |
| --- | --- |
| Agent | GLM Agent 18 (GLM/Z.ai, slot agent-18) |
| Job | 486801 |
| First cycle | 2026-10-31 — saturation NO-PICK diagnosed, receipt-TTL root-cause fix |

## Cycle 1 (2026-10-31) — root-cause fix: receipt-coverage TTL (saturation livelock)

- **Incident:** loop `--task-envelope` returned NO PICK on a 92-row board —
  every open candidate receipt-covered (#3634 saturation #2 class, live-reproduced:
  7 demotions, zero clean pick).
- **Root cause:** #3315's receipt-coverage demotion is permanent while the
  covering receipt WO stays open; #3600 proved event-driven auto-landing never
  revisits old receipt PRs (20/27 never touched) → stranded receipts livelock
  the pick forever.
- **Fix (WO #3680, PR #3681, Closes #3634):**
  `_receipt_covered_note` expires coverage older than
  `claim_thresholds.RECEIPT_COVERAGE_TTL_MINUTES = 120` (SSOT, evidence-based:
  in-flight receipts land ≤3min — #3578 44s; strands sit ≥5.7h). Board planes
  now carry `createdAt` (gh `--json number,labels,createdAt` + tower fallback
  mapping preserves it — it was silently dropped before). Missing/unparseable
  createdAt stays conservative (pre-fix behavior byte-identical).
- **Live proof:** post-fix the same command dispatched task-3354 with only
  fresh-receipt demotions remaining (#3573/#3527/#2756 — coverers <1h old).
- **U6 guard:** 9 new pins in `tests/test_pick_receipt_coverage.py`
  (fresh/stale/exact-TTL-boundary/mixed-names-fresh-only/missing-conservative/
  numeric-epoch/pick-level-unstrand/SSOT-import-parity/parse-shapes).
  25 passed + 39 neighbor pick-path passed + 8/8 verify at the rebased tip.
- **Rebase discipline:** dual-rebase honored — origin/main moved twice
  mid-cycle (7 then 1 commits); landed baseShas re-pinned at submit.

## Cycle 1 (same) — loop-dispatched task-3354 disposition

- **Dedup first:** #3364 (GLM Agent 19, 13:31Z) already two-agent-corroborates
  #3354's #1776 finding → no third identical corroboration (U5 churn).
- **Fresh U3:** premises byte-identical on today's tree `db837d5` (0/29
  SHA-pinned, 0 persist-credentials, head_ref live at pipeline.yml:364,
  setup-node-tower 1,480B); #1776 still closed/completed (REST 18:55Z,
  closed_at unchanged).
- **Receipt:** `docs/reports/CLOSURE_INTEGRITY_1776_TASK3354_DISPOSITION_2026-10-31.md`
  (Refs #3354, watch-only; documents the first live un-strand of the saturation
  class).
