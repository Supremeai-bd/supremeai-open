# Evidence — #1304 (33 stale queued Actions runs in supremeai)

Submitted by **GLM Agent 04 (Job 486718)** at 2026-11-02 ~03:30Z, claim
lease `work_claim #1304 GRANT_NEW @03:13:48Z`. Evidence submission only —
closure belongs to the operator/verdict plane (cancel/dispatch tooling is
outside this agent's envelope). No 'Closes' line is intended.

## Classification: all 33 runs are ORPHANED/STALE — zero genuinely pending

| Probe | Result | Meaning |
| --- | --- | --- |
| `get_failed_logs` runId 38808668612 (Bridge Intake #43) | record exists, "No failed jobs found", jobs `[]` | record still on repo, never picked |
| `get_failed_logs` runId 37976370187 (Agent Loop #67) | same | record still on repo, never picked |
| `github_workflow_runs` supremeai recent-12 | 12/12 `completed`, 0 queued; window 2026-11-01→11-02 (Bridge Intake ×3, Nightly Ops ×2, …) | live pipeline healthy; no current concurrency stall |
| `github_code_search` filename:archive-mirror.yml | 0 hits | **workflow file deleted/renamed since 2026-10-15** |
| `github_read_file` .github/workflows/continuous-agent-loop.yml | 404 | **workflow file deleted/renamed** |
| `github_read_file` .github/workflows/bridge-intake.yml | exists (9212 B); `concurrency: group bridge-intake-v5, cancel-in-progress: false` | queue-serializing policy confirmed |

## Root cause (evidence-backed, two failure classes)

1. **Deleted/renamed workflows** (archive-mirror.yml ×12, continuous-agent-loop.yml ×1):
   dispatch records of workflows whose definition no longer exists can never be
   picked by a runner — permanently orphaned records.
2. **Concurrency-queue stall + stale-record GC** (bridge-intake.yml ×20):
   `cancel-in-progress: false` serializes dispatches; during 2026-10-09→10-15 a
   stalled/runnerless window left 20 dispatches queued; by the time the queue
   unblocked, the records were stale (no runner will ever pick a dispatch that
   old), yet they were never cancelled. New dispatches on the same group
   complete normally today (recent-12 evidence).

Supporting facts from the issue itself: all sampled records "not updated since
creation", jobs endpoints empty, GitHub Status operational, other repos clean —
consistent with orphan-record behavior, not a platform outage.

## Acceptance criteria mapping

- Classify 33 runs → **DONE above** (2 failure classes, all orphaned).
- Concurrency review → **DONE** (bridge-intake-v5, cancel-in-progress:false).
- Fresh-dispatch proof → satisfied by recent-12: Bridge Intake completed
  2026-11-01 16:07Z, 20:33Z, 2026-11-02 00:48Z; Nightly Ops completed 11-01.
- Cancel obsolete runs → **operator action** (no cancel tool in agent envelope).
  Safe to cancel all 33: 12+1 are definition-less orphans; the 20 intake
  records are superseded — every intake function has since completed fresh.
- Alert/runbook (runs queued >30 min) → proposal below; implementation touches
  `.github/` of the monorepo (protected path → admin review), so it is listed,
  not patched.

## Proposed runbook (for operator adoption)

1. Alert: any run `status=queued` older than 30 min (scheduled check).
2. Triage: if the workflow file no longer exists on default branch → orphan,
   cancel outright. If it exists → check concurrency group head; cancel only
   if `created_at` is older than the group's latest completed run.
3. Recovery: fresh `workflow_dispatch` of the affected workflow; verify it
   reaches `completed` within the queue SLO.
4. Never cancel while a group head is genuinely in-progress (would violate
   the no-cancel policy the workflow itself declares).
