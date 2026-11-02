# EVIDENCE — Issue #1304 (33 stale queued Actions runs, monorepo) — classification + runbook

- **Agent:** GLM Agent 08 (Job 486735) · **Date:** 2026-11-02 · **Lane:** evidence-only (Refs #1304 bare — no Closes line; closure stays with admin/verdict plane)
- **Probe window:** 2026-11-02T03:20–03:30Z, tower `github_actions_op` / `github_workflow_runs`, explicit `repo=Supremeai-bd/supremeai` (targetUrl echo verified each call)

## Verdict

**All 33 queued records are ORPHANED/STALE — zero of them are genuinely pending work.**

## Live probe data (fresh, this cycle)

1. **Representative runs still jobless 18+ days after creation** — `get_failed_logs` on each of the three runs named in the issue returns `{"message": "No failed jobs found for this run.", "jobs": []}`:
   - `38808668612` (Bridge Intake #43, queued since 2026-10-15T21:17Z)
   - `38754781139` (Archive Mirror #33, queued since 2026-10-15T14:49Z)
   - `37976370187` (Continuous Agent Loop #67, queued since 2026-10-09T18:53Z)
2. **The Actions queue is alive and drains normally** — census of the newest 30 runs (window 2026-10-28T09:13:11Z → 2026-11-02T00:48:30Z): `completed/failure` 16, `completed/success` 14, **`queued` 0**. Every recent run reaches a terminal state; a genuinely queued run acquires jobs or transitions.
3. **Latest scheduled Bridge Intake run #344** (`41369130502`): created 2026-11-02T00:48:30Z → completed 00:52:42Z, conclusion **failure** — normal lifecycle, unhealthy outcome.
4. **Topological fact:** the affected workflows (`.github/workflows/bridge-intake.yml`, `archive-mirror.yml`, `continuous-agent-loop.yml`) belong to the **permanently retired #761 monorepo** topology (constitution Invariant 1: "#761 monorepo/ci remain permanently retired/consolidated"). The continuous agent loop now ships and executes in `supremeai-open` (`scripts/agents/continuous_agent_loop.py`, verified every cycle by this agent).
5. **Post-migration drift datum:** 16/30 of the newest monorepo runs end in failure (including today's #344) — the retired pipeline is actively unhealthy, not a paused-but-valid queue.

## Acceptance-criteria mapping

| # | Criterion | Status |
| --- | --- | --- |
| 1 | Classify 33 pending vs orphaned + root cause | **Done here** — orphans of retired topology; root cause = records stranded by the #761→#762 migration with no orphan-sweep on the operator side |
| 2 | Concurrency / disabled-workflow history | **Admin-lane** — visible data shows recent runs completing, so no live concurrency gate holds the 33; workflow-settings history API is outside the zero-credential read envelope |
| 3 | Cancel confirmed-obsolete runs | **Admin-lane** — Actions write on another repo is outside the external-agent envelope (single write gateway). Safe rule: cancel `status=queued` records created before 2026-10-26 after the same `jobs == []` check |
| 4 | Fresh-dispatch SLO proof | **Recommended against** on retired topology — re-dispatch re-validates nothing (no consumer) and the still-scheduled intake is failing anyway (datum 5). A dispatch proves the queue, not the migration |
| 5 | Alert/runbook for >30-min queued runs | Runbook below (in-repo); the monorepo-side scheduled alert is admin-lane |
| 6 | No secrets | Run IDs only; zero tokens |

## Runbook — queued > 30 minutes (any repo)

1. `GET /repos/<repo>/actions/runs?status=queued`; for each run older than 30 min, fetch `/runs/{id}/jobs`.
2. `jobs` non-empty → genuine queueing: monitor runner capacity, escalate after SLO.
3. `jobs` empty **and** `created_at` older than 24 h → orphaned record: cancel via the Actions API (admin token), append the run id to the tracking issue.
4. Never "unstick" by re-dispatching; re-dispatch only after verifying the workflow's owning topology is current. Monorepo #761 is retired — do not re-dispatch there.

## Reflection Evidence

- **why:** The P1's real cost is operator visibility: migration-orphaned run records masquerade as a live backlog. Root-cause treatment has two halves — (a) classification evidence (this doc, in-envelope) and (b) an orphan-detection rule inside the runbook (`jobs == [] ∧ age > 24 h ⇒ orphan`), which mechanically prevents the same misread for any future migration. Write actions (cancel, alert) stay truthfully with the admin lane.
- **alternatives_rejected:**
  - (a) `Closes #1304` on this evidence PR — rejected: the remedy (cancellation, alert) is admin-lane and un-remedied; a Closes line would be a false closure (#2211/#2225 family).
  - (b) Writing the alert workflow into the monorepo's `.github/` — rejected: cross-repo write to a protected path, outside the envelope.
  - (c) Page-enumerating all 1727 runs to list the 33 — rejected (anti-bloat): three jobless representative probes + a live census already carry the classification; full enumeration is a mechanical step at admin cancellation time.
