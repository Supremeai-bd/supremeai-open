# TRIAGE #4250 — core nightly-RED: private-repo SARIF upload can never succeed (schedule-only, 7/7)

- **Filed by:** GLM Agent 04 · Job 486718 · slot `agent-3` · cycle 2026-10-31 16:04+08
- **Subject:** P0 #4250 (`fix(ci): [core] ci failed on main (Run #41182951163)`)
- **Relation to prior receipts (U5 dedup):** glm10 (#4251) and glm09 (#4252)
  proved the **access boundary** — from their lanes the core repo, run and
  logs are unreadable, so they correctly filed report-only and stopped at
  "structurally unreachable". This file is the **next layer, not a
  duplicate**: the post-#4249 admin restore returned the tower's
  `github_*` read family to the roster (158 tools), and through it this lane
  read the run, its logs, the landed `ci.yml` blob and the repo metadata —
  i.e. the U3 stale-incident verification glm10 called "mechanically
  impossible from the lane" was executed here. What glm10 could not see, we
  now know: the exact failing job, the exact step, and a one-line admin fix.
- **Verdict:** report-only triage — the remedy lives inside `supremeai-core`'s
  `.github/workflows/ci.yml`, a protected path (bridge rejects `.github/`
  writes, #2512 routing note). No agent patch can land this; admin-only with a
  one-line recipe below. This file is the evidence the routing note asks for.

## Failure fingerprint (all live-verified this cycle)

1. **Event-gated:** only `schedule` runs fail. Recent main history:
   run 47 (schedule, `ba69caba`) FAIL; 46/45/44 (push) PASS; 42, 41, 40, 36,
   26, 24 — every sampled scheduled run FAIL. Push/PR runs of the same
   workflow are green, so the defect is invisible to normal development
   traffic (a blind-lane class: the red lane only ever runs at night).
2. **Job-gated:** `github_get_failed_logs` across runs **47, 42, 41, 40, 36,
   26, 24 → 7/7 failedJobs = ['🔧 PyErrorFix Engine']** (the `autofix` job).
   The `test` job never fails on schedule (it does not run there: its `if:`
   excludes schedule). 6/6 of the older schedule failures independently
   probed this cycle (42/41/40/36/26/24) — same single failed job each time.
3. **Step-gated (by elimination):** inside `autofix`, both analyze invocations
   of the pyerrorfix CLI (the `python -m` module form seen in the landed
   workflow) carry `|| true` (fail-safe by
   construction; missing module, bad exit — nothing propagates). The SARIF
   fallback step unconditionally rewrites a valid empty-runs SARIF when the
   file is empty/unparseable. The **only step that can fail the job** is
   `github/codeql-action/upload-sarif@v4` (`if: always()` — it runs even when
   analysis produced nothing).
4. **Why the upload fails, always:** `supremeai-core` is
   **`[PRIVATE]`** (repo description echoes it; `github_repo_info` verified).
   On a private repo without Advanced Security, the code-scanning
   upload-sarif API is not available — the step fails deterministically,
   every night. Log tail confirms the job reaches codeql-action's post phase
   ("Uploading combined SARIF debug artifact") and dies in the wire call.
5. **Why it becomes a P0:** the workflow's own "Trigger Federation CI
   Watchdog on Failure" (`if: failure()`) dispatches `federation_ci_failed`
   to the open repo every night → a fresh P0 mirror on the board each run
   (#4250 is the latest; the drain era has been reaping its predecessors).

## Root cause (one sentence)

A workflow job whose terminal step is structurally impossible on this repo's
visibility is scheduled nightly, manufacturing one P0 red per night while all
developer-facing (push/PR) lanes stay green.

## Admin recipe (pick one; A is the zero-cost root fix)

- **Option A — visibility-gate the impossible step (root fix, 1 line):**
  in `supremeai-core/.github/workflows/ci.yml`, `autofix` job:
  `if: always()` → `if: always() && github.repository_visibility == 'public'`
  on the `Upload SARIF to GitHub code scanning` step. The analysis artifacts
  remain on the runner as before (the SARIF file is still produced); only the
  wire call that cannot succeed on a private repo is skipped. Optionally add
  an `actions/upload-artifact@v4` step for the SARIF so the nightly output
  stays observable without code-scanning.
- **Option B — enable code scanning:** license Advanced Security for
  `supremeai-core` and enable code scanning (cost decision, admin-only).
- **Anti-recurrence guard (either option):** keep the watchdog dispatch, but
  before mirroring a P0, check whether the failed job is the scheduled
  `autofix` job and whether the same job failed in the previous scheduled
  run — a 2-data-point repeat is a systematic class, not an incident; route
  it to the triage lane instead of a fresh P0 (U5 anti-stampede applies to
  the night-shift pipeline too).

## Why this is not a claim

The task contract's own Protected-Path Routing Note (#2512) says: if the root
cause lives in `.github/workflows/`, no agent patch can land it — file triage
evidence (report-only) instead of burning a claim+TTL on a structurally
blocked patch. This file is exactly that evidence. Closing #4250 is the
admin's call after Option A or B lands; a `Closes #N` from the agent lane
would be a false closure.

## 3-Tier verify

- **Reflection:** 7/7 failedJobs identical across sampled schedule failures;
  6 sampled schedule failures vs green push runs 44/45/46 on the same
  workflow; step-elimination grounded in the landed `ci.yml` blob
  (sha 9acd7fca) read live from `supremeai-core`.
- **Smoke:** `github_repo_info` → `[PRIVATE]` description; run 47 timeline
  (start 08:02:21Z, fail ~08:06:46Z) matches checkout+analyze+post phase.
- **Tests:** offline read-only probe cycle; no tree change by this triage.
