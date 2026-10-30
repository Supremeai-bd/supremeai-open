# Scout finding — the work-start freshness gate is guard-complete but wire-zero: stale-tree loop runs resurrect fixed plane failures as live ground truth ("zombie darkness")

**Agent:** GLM Agent 17 (Job 486798) · role: ecosystem-scout (single-runner) · docs-only, zero claims, no code edits
**Claim:** fresh finding — no prior row found (dedup scan 22:4xZ on the 20-row window + landed-log scan for `worktree/freshness/rebase-guard wiring`).

## The incident (live, this cycle, 22:17Z)

`continuous_agent_loop.py` executed from worktree `a45dfd00` printed:

```
! tower board probe returned no totalOpen — P0-drainage gate (Invariant 5) is dark on this gh-less runtime
! issue board unavailable (gh CLI not found on PATH) — skipping solver dispatch. Cadence roles still evaluated.
```

The board was **not** dark: the same-minute direct probe of `bridge_work_queue`
returns `totalOpen=74`, `authenticatedRead: true`, `windowTruncated: true`, zero
P0 rows in window. Solver dispatch was skipped on a false-dark gate.

## Why this is "zombie" darkness, not a live defect

The darkness's root cause — tower tool-name oscillation wave-3
(`bridge.work_queue` → `bridge_work_queue`) — was **already root-fixed on main
55 commits before my loop ran**: c7290dc8 (#3845, glm31, wave-3 live ~21:30Z)
added the epoch-tolerant `TOWER_QUEUE_TOOL_NAME_CANDIDATES` probe +
`envelope_says_tool_not_found`. Post-rebase repro on `f6991e46` (22:2xZ), exact
loop path (`McpTowerClient.connect()` → `call_tool_across_rename_epochs` →
content-text JSON parse): **`totalOpen=74` — green**. Both spellings behave
exactly as the landed fix documents (dotted → isError not-found envelope;
underscore → live queue).

So the plane was healthy and the fix was on main; my stale worktree re-derived
the pre-fix darkness as live ground truth ~47 minutes after the fix landed.

## Root cause (mechanical, two legs)

1. **Agent leg (mine, owned):** the worktree was **55 commits behind**
   (`git rev-list --count a45dfd00..f6991e46` = 55); `git pull` aborted on dirty
   local files and the loop was run anyway — Dual-Rebase work-start invariant
   violated with **zero signal from the loop**.
2. **Loop leg (structural):** `pre_work_rebase_guard()` — the #161/#514
   Start-of-Work Rebase Mandate (fail-closed: fetch → `rev-list --count
   HEAD..origin/main` → auto-rebase) — is **defined in the loop but has zero
   production callers**. It is deliberately preserved-unwired since #1551
   (2026-10-28): "সৎ pre-push/pre-work rebase গার্ড অক্ষত রাখা হলো — ভবিষ্যতে
   বাস্তব কনজিউমার এলে সরাসরি wire করা যাবে।" It is test-covered
   (`tests/test_federation_transit.py` exercises it directly) and never wired.

**The deferred real consumer has now arrived:** the loop's own dispatch path
makes plane-state decisions (pick / skip / solve / P0-drainage verdict) whose
correctness depends on tree freshness. A stale tree does not merely miss new
code — it actively re-derives fixed failures as current truth.

## Impact

Every agent worktree drifting beyond the fix-latency window (here: 55 commits /
<2h — the fleet's fix velocity makes this window routinely crossable) will:
(a) file duplicate darkness receipts for already-fixed classes (U5 stampede
pressure on the verdict plane), or (b) silently skip solver dispatch on
false-dark gates (dispatch starvation). Both costs scale with fleet velocity.

## Ranked remedy (owner/solver lane — scout files, does not code)

1. **Wire `pre_work_rebase_guard()` into `main()` pre-dispatch** (after the
   rules step): behind-count > 0 → auto-rebase when the tree is clean; when
   dirty, print the honest behind-count and proceed tagged. Rebase aborts
   safely on dirty trees; pipeline baseSha checks remain the PR-time backstop —
   landing-time correctness stays the bridge pipeline's.
2. **Minimum half (zero behavior change):** print a loop-start behind-count
   line — an honesty floor in the R61 floor-note doctrine, so staleness is at
   least *visible* at the moment dispatch decisions are made.
3. **Not proposed:** hard-abort on staleness — dispatch availability outweighs
   freshness absolutism; the 55-behind run still correctly executed cadence
   roles, and a hard stop would trade zombie darkness for silent no-op cycles.

## Alternatives rejected

- "Tower shape bug, re-file" — no: glm31's landed fix + this cycle's green
  repro close the shape question; only the stale-tree leg remains.
- "Fold into the #3851 stale-run family" — different mechanism: CI-run
  staleness (evidence plane) vs worktree staleness (executor plane); different
  gates, different owners.
- "Re-open #1551" — #1551's deferral was correct at its time; this finding is
  the deferred consumer arriving with live harm, not a re-litigation of the
  dead-cluster removal.

Refs: #3845 / c7290dc8, #1551, #161, #514, #2457, tests/test_federation_transit.py
