# Triage (report-only, consolidated) — auto-landing base-policy cohort: #3402 + #3413 (with #3401)

- **Agent:** GLM Agent 07 (Job 486733), cycle-3 addendum, 2026-10-30T15:2xZ
- **Classification:** PR-lane failures, workflow-internal class → protected path `.github/` (#2512) → admin-only fix. No claims taken; default Refs semantics (a triage does not resolve its subjects).
- **Why consolidated:** all rows share one root cause and one fix; peer pattern #3453 established the consolidated report-only receipt. Row A is covered by `docs/bridge/bridge-20261030-3401-autolanding-triage-glm07.md` (PR #3473, in-flight); this receipt adds Rows B and C so the whole cohort is on the board.

## Cohort (each row live-verified, U3 stale-guard, 15:1x–15:2xZ)

| Row | Task | PR lane | Run | Auto-landing failure | PR liveness |
| --- | --- | --- | --- | --- | --- |
| A | #3401 | `3395/merge` | 41065145695 | 13:41:20Z | open, untouched since 13:40:09Z |
| B | #3402 | `3398/merge` | 41065217412 | 13:41:54Z | open, untouched since 13:40:43Z |
| C | #3413 | `3411/merge` | 41066432193 | 13:49:57Z | open, untouched since 13:49:16Z |

- Identical failure signature on all three rows (tower `github.get_failed_logs`, re-read live per row):
  1. `✅ All verification tests and constitutional guards passed! Executing autonomous squash-merge...`
  2. `X Pull request Supremeai-bd/supremeai-open#<N> is not mergeable: the base branch policy prohibits the merge.`
  3. `To have the pull request merged after all the requirements have been met, add the --auto flag.`
  4. `##[error]Process completed with exit code 1.`
- Liveness: no successor runs on any of the three lanes (PRs untouched since creation; newest-300 run window scanned); `main` itself green (run 8154). Board scan (43 open rows, untruncated) shows exactly these three Unified Pipeline PR-lane rows — the cohort is complete.
- Board check: #3402 and #3413 both had `latestClaim: null` and no triage comments before this receipt.

## Root cause (class-level, applies to all rows)

The auto-landing step treats a transient base-branch-policy state as a hard job failure: bare `gh pr merge --squash` (no `--auto`) races main's branch protection, gh exits 1, the healthy PR's lane goes red, and the `federation_ci_failed` mirror spawns a task issue per PR (#3401/#3402/#3413 are those mirrors). Nothing in the three PRs' content is broken — each PR's own verification passed.

## Admin-lane recommendation (unchanged from the Row A receipt — one fix kills all rows)

1. `gh pr merge --squash --auto` in the auto-landing step (gh's own error text prescribes it): policy-blocked merges enqueue and land when base policy is satisfied instead of exiting 1.
2. Classify `base branch policy prohibits the merge` as retryable/enqueue (exit 0 + notice); reserve exit 1 for genuine content failures.
3. Ops: re-attempt the merges on PRs #3395, #3398, #3411 (or close/reopen) so the healthy lanes re-run.

## Why report-only (alternatives rejected)

1. Claim + patch — structurally impossible: the fix is a `.github/` write (protected path, intake rejects) and the three merge refs belong to other lanes; claims would only burn TTL (explicitly warned against by each task body).
2. Stale-skip — rejected: every row verified live (PRs open/untouched, no supersession); skipping discards log-verified findings.
3. Three separate receipts — rejected: same root cause and fix; consolidation keeps the evidence lane small (operator instruction) and matches peer precedent (#3453).
4. Re-run/retry the merges — admin/author action, out of zero-credential reach; handed to the admin lane as above.

## Reflection Evidence (why + alternatives_rejected)

- **Why:** the loop dispatched Row B (#3402) this cycle; the board scan revealed Row C (#3413) shares the class, and Row A was already triaged — so a single consolidated receipt gives the admin lane the complete cohort picture (3 red lanes, 1 cause, 1 fix) with minimal receipt traffic. Default Refs linkage keeps the task issues open until the admin fix lands, per the receiptClosureConvention.
- **alternatives_rejected:** enumerated above (claim+patch impossible; stale-skip contradicts live evidence; per-row receipts violate worklog economy; merge retries out of reach).

## Rollback

git revert-safe: delete this single new receipt file; no code, config, or claim state is touched.
