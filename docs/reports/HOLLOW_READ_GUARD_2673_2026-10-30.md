# Hollow-Read Guard — #2673 standing assertions (first live run + baseline)

- **Date**: 2026-10-30, agent lineage `zai-cron-agent-loop` (Job ID 484688, cycle 10:01+08, trace cron-agent-loop-202610301001)
- **Claim**: #2673 via `work_claim` → GRANT_NEW 2026-10-30T02:09:49Z, TTL 30m
- **Deliverable**: `scripts/ci/hollow_read_guard.py` + `tests/test_hollow_read_guard.py` (this PR)

## 1. What landed (the #2673 class-absorption slice)

#2673 files the silent-empty class (six 200-but-hollow reads across five planes)
with a five-item Unified remedy: "emptiness assertions at the consumption
boundary". Its falsification clause states the absorption condition verbatim:
**"If a standing guard (not an ad-hoc probe) catches the NEXT hollow-read
occurrence before an agent's manual census does → the class is being absorbed;
close as implemented."** This PR lands that standing guard.

Implemented (remedy numbering from #2673):

| # | assertion | catches |
|---|---|---|
| 1 | `assert_non_empty` | n=0 where domain semantics imply data; semantic floor is decided by a **workflow_runs side-channel cross-check**, not hardcoded (#2609 roster row) |
| 2 | `assert_live_implies_fresh` | timestamp advanced + content identically empty across two snapshots (#2665 signature: live stamp decorating hollow data) |
| 3 | `assert_truncation_flagged` | paginated face with no first-class truncation signal returning exactly page size (#2609); work_queue flag/data divergence (#2190 miscalibration) |
| 5 | `assert_ci_coverage` | green run with zero executed jobs — green-but-blind (#2529 class) |

Verdict contract (#2704 shape): exit 0 CLEAN / 1 HOLLOW_DETECTED (stderr
fail-loud + JSON evidence) / 2 usage-internal. Live probe reads three roster
planes zero-credential (list_prs + workflow_runs side-channel, work_queue,
health_full_sweep) and emits per-plane findings — an UNREADABLE plane is
labeled UNREADABLE, never laundered into CLEAN.

## 2. First live run — baseline (2026-10-30T02:13:34Z)

Command: `python3 scripts/ci/hollow_read_guard.py --probe live`, zero
credentials, real tower. **Result: exit 0 CLEAN, 0 hollow signatures.**

| plane | observed | verdict |
|---|---|---|
| github.list_prs (open, per_page=30) | 3 rows | CLEAN |
| github.list_prs truncation | 3 < 30 page size | CLEAN |
| bridge.work_queue (limit=120) | totalOpen 99, windowTruncated=false, limit≥total → flag correctly false | CLEAN |
| health_full_sweep.snapshots | 33 provider snapshots | CLEAN |

The CLEAN run is the baseline the guard will be judged against: at this same
hour the fleet had witnessed list_prs silent-empty bursts (previous cycles' ×3
hollow) and a failed-logs blind read — none were firing at probe time. The
guard stays standing; its next HOLLOW_DETECTED run on one of these planes is
the #2673 falsification clause firing in the class's favor.

Side observation attached to evidence: totalOpen moved 123 → 99 within the
hour (queue drain in progress), consistent with the reconciler work referenced
by #2587/#2628.

## 3. Test evidence (3-tier)

- **Reflection**: why — every member of the #2673 roster was caught by a
  *different ad-hoc method*; none of the standing guards would catch the next
  member. Why this shape — assertions at the consumption boundary are
  repo-reachable, mechanical, and falsifiable; the tower-side plane fixes
  remain owner-lane and are explicitly out of scope (scope-honesty note in the
  module docstring).
- **Boot smoke**: the §2 live run (exit 0, parseable JSON evidence, per-plane
  findings attached).
- **Tests**: `python3 -m unittest tests.test_hollow_read_guard` → **21/21 OK**
  (non-empty floor semantics incl. floor-0 honesty, live≠fresh three-state,
  truncation calibration #2190 + blind-page #2609, green-but-blind #2529,
  live-probe composition with side-channel floor, evidence schema, exit
  contract, UNREADABLE-never-laundered). Full suite: **89/89 OK**
  (50 pre-existing + 18 closure-gate + 21 hollow-guard).

## 4. What this does and does not claim

- Refs #2673 (report-only class filing): this is the standing guard the
  filing's remedy section calls for; the class row itself stays with its
  filer and the owner — closure is governed by the falsification clause, not
  by this PR.
- Does not modify any tower plane; cannot false-close anything; registry-free
  (assertions are parameterized at call sites, documented inline).
