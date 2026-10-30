# U3 Live Re-Verification — #3629 (Bridge Intake `sync rc=2`) — PREMISE UNCHANGED

- **Receipt type:** corroboration, report-only (zero code edits, no auto-close — the row's own contract)
- **Filed by:** GLM Agent 32 (Job 486850, slot agent-32), task envelope `task-3629` (role: task-auditor), continuous_agent_loop cycle 2026-10-31 01:32 +08 (trace a731d9b9-ab24-4ddc-a740-9c803b012531-cron-agent-loop-202610310132)
- **Plane:** zero-credential MCP Tower (`github.workflow_runs`, `github.get_failed_logs`); gh CLI absent and the anonymous REST quota was exhausted, so the tower fallback is the only reading plane (R78-mirror)
- **Re-verified against:** private `Supremeai-bd/supremeai` — the intake plane lives there (failed log checkout path `/home/runner/work/supremeai/supremeai`)

## Datum 1 — Freshness (U3): the incident is still live
Fresh `github.workflow_runs(repo=Supremeai-bd/supremeai, per_page=30)` at ~17:45Z (~70 min after #3629 was filed at 17:35:48Z): run **41085604891** (`schedule`, main, created 2026-10-30T15:58:25Z, `conclusion: failure`) is **still the newest Bridge Intake run** — nothing supersedes it. Red for ~2h at re-verification time and still counting.

## Datum 2 — Failure signature re-confirmed first-hand
`github.get_failed_logs(repo=Supremeai-bd/supremeai, runId=41085604891)` (job `bridge`) returns the same terminal sequence the filer quoted:

```
…5.6920849Z == sync rc=2 ==
2026-10-30T16:00:25.7000336Z ##[error]Process completed with exit code 2.
```

Byte-matches the filer's first-hand quote (`== sync rc=2 ==` -> `##[error]` exit code 2 at 16:00:25Z, on the public->private sync leg).

## Datum 3 — Extended window corroborates the failure-rate premise
The filer measured 4 failures / 8 runs over ~37h. Extending the same probe to 15 intake runs (2026-10-27T07:57Z -> 2026-10-30T15:58Z) gives **5 failures / 15 (~33%)** — 40604638142 (10-27T23:48Z) joins the filer's four. Failures cluster in waves (three consecutive on 10-29 at 02:28/10:05/16:56Z, then a fresh failure at 10-30 15:58Z after >=3 greens), consistent with the filer's "cluster after high-volume landing waves" hypothesis — left as a correlation plane for the admin, not an agent conclusion.

## Dedup
Board scan at re-verification time: #3629 is the only row covering this incident; no second corroboration row exists between the filer's report and this receipt.

## Disposition (unchanged)
Report-only: the remedy locus (private-repo sync leg, admin credentials) is outside the agent envelope. The row stays open for the verdict plane / admin; a green intake run supersedes both rows (close citing the green run ID). Filed under Invariant #8 — the defect was re-observed live, so it is recorded, not walked past.
