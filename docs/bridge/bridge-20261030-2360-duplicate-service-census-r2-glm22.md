# Duplicate-Service Census — #2360 (audit: CI follow-through gap) — live probes 2026-10-30T14:28Z

- **Task ID:** `bridge-20261030-2360-duplicate-service-census-r2-glm22`
- **Agent:** GLM Agent 22 (Job 486813) — continuous-loop dispatch of audit row 2360
- **Lane:** report-only process evidence (docs-only, zero code, zero protected paths, no closure requested)
- **Method:** atomic claim GRANT_NEW at 14:28:05Z (lease to 14:58Z) → in-tree sentinel live sweep + Tower workflow-runs drill-down + issue-comment timeline census. No fixes attempted (all remedy options are admin-lane).

## Live premise re-verification (14:28:41Z sweep, self-test 19/19 PASS)

Same result as the two receipts already merged this morning: core **RED** (last completed 08:09:25Z, schedule lane), api green-stale 67.0h, browser green-stale 70.5h, vscode green-stale 142.5h; supremeai + studio green fresh. Core push-plane dark 69.6h (last push run 2026-10-27T16:53:58Z). No decision-grade delta vs `bridge-20261030-2360-evidence-refresh-r1` (probes 12:12Z, ~2.2h earlier): every number moved only by linear drift.

## Finding — the row is now in a duplicate-service loop, not an evidence gap

Claim-event census from the issue timeline (10-29 22:42Z → 10-30 14:28Z, ~16h):

| # | agent | claim | release | outcome |
|---|---|---|---|---|
| 1 | contributor-agent | 10-29 22:42:52Z | 22:44:11Z | released in 1.3 min |
| 2 | contributor-agent | 10-30 00:07:25Z | watchdog 11:57:39Z | 11.8h zero-activity hold (3h TTL ceiling exceeded by 8.8h — watchdog lag) |
| 3 | contributor-agent | 10-30 12:13:38Z | 12:16:25Z | released in 2.8 min |
| 4 | glm-agent-17 (486798) | 12:20:08Z | 12:21:54Z | released in 1.8 min |
| 5 | GLM Agent 04 (486718) | 12:23:38Z | 12:26:28Z | produced `r2360-followthrough-r1` (sweep 12:24:48Z) → merged |
| 6 | GLM Agent 27 (486827) | 12:27:52Z | 12:29:32Z | released in 1.7 min |
| 7 | GLM Agent 22 (486813) | 14:28:05Z | this receipt | produced this census |

Key observations:

1. **Parallel duplicate receipts landed.** GLM Agent 11's `evidence-refresh-r1` (probes 12:12-12:15Z) and GLM Agent 04's `r2360-followthrough-r1` (sweep 12:24:48Z) were produced ~10 min apart on the same row with the same findings (freshness gap widened to 4/6 satellites; dark-push ambiguity resolved via the feda45e→32dccbb schedule-head delta; repair still unowned). Two agents burned leases on identical work inside one 15-minute window.
2. **Post-landing re-dispatch is live.** Both receipts merged, yet the loop re-picked #2360 at ~14:24Z — because receipt-coverage demotion (#3332) checks OPEN bridge WOs only; once a receipt merges, coverage is forgotten and the same audit row re-enters the pick. This census receipt itself is the concrete case the in-flight lane-declaration PRs (#3398, #3412) are being written for; reviewers may cite it as a reproduction.
3. **Lease hygiene signal.** Event 2 held the row 11.8h with zero activity, 8.8h past the stated 3h TTL ceiling, before the watchdog released it.

## What would actually move the row (agent view, unchanged options)

- **A (still unowned, still urgent):** core push.branches yml restoration per 2125 — protected path, admin lane. Every push to core main since 10-27 16:53:58Z is unverified at source.
- **Verdict-plane:** consider marking this row report-complete (two merged evidence receipts + this census) or attaching it to an admin owner, so the pick plane stops cycling it into claim-bounce churn (~6 of 7 claim events produced no artifact).

## Reflection Evidence (why + alternatives_rejected)

- **why:** the loop dispatched the row a third time today after two merged receipts already cover it; a fourth findings-repeat receipt would be waste. The churn pattern itself is the remaining decision-grade evidence an agent can produce without touching the hot picker lane.
- **alternatives_rejected:** another findings-refresh receipt (rejected — zero decision-grade delta in 2.2h, duplicates refresh-r1); a picker change adding landed-receipt memory (rejected — six picker PRs landed or open today on the same file, #3246/#3302/#3332/#3404/#3388/#3412; an uninvited change would stampede the lane); claiming and silently releasing (rejected — leaves no trail for the verdict plane).

## Rollback

git revert-safe: delete this single receipt file.
