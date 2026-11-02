# Evidence receipt — #5192 (SARIF upload vs GitHub Advanced Security, supremeai-core)

> Filed by GLM Agent 32 (Job 486850), c120 window (2026-11-02 12:32+08 = 04:32Z).
> Dispatch: continuous_agent_loop assigned #5192 (solver / ci-fixer; P2-medium,
> status:unclaimed, handoff:coder, area:ci, repo:core, status:runway, ci-failed).
> **Verdict: evidence lane — NOT claimed, NO auto-close.** Grounds below.

## Premise verification (stale-incident guard — PASSED, incident CURRENT)

- Referenced run `supremeai-core` **41290416574** (scheduled `ci.yml`, run #49,
  created 2026-11-01T09:48:49Z): status `completed`, conclusion **`failure`** —
  re-verified live via tower `github_workflow_runs` this window.
- It is still the **latest main run** (newest-first list, total_count 57): no
  newer main run exists → the incident is current, not stale.

## Boundary verdict — remedy outside the agent envelope (three independent grounds)

1. **Satellite repo**: target repository is `Supremeai-bd/supremeai-core`, not
   the open repo this slot is contracted to (`supremeai-open`). The loop's own
   contract lists satellite repos under "remedy lives outside the agent
   envelope".
2. **Protected path**: the remedy lives in `.github/workflows/ci.yml`; `.github/`
   is a `protectedPathsToAdminReview` entry in the bridge contract.
3. **Owner/policy decision**: acceptance criterion 1 is "decide whether GitHub
   Advanced Security / code scanning is an approved capability for this
   repository"; suggested owner "Core CI / security-maintainer"; label
   `status:runway` agrees.

## Remedy map (for the core owner — mechanical options, no decision made here)

- **If GHAS not approved**: publish the SARIF as a workflow artifact and guard
  the upload step to skip with a clear warning (capability check /
  continue-on-error semantics) instead of failing the whole job.
- **If GHAS approved**: enable the feature + required workflow permissions,
  then confirm the upload succeeds.
- **Either way**: restore the Core Pytest & Lint job triggers — in run #49 that
  job was SKIPPED; the only red step is the SARIF upload, so the scanner and
  the application tests did not fail.

## Plane discrepancy on record (UNSEEN discipline)

`bridge_work_order` reported state **open** (updatedAt 2026-11-02T04:25:15Z) vs
`bridge_read_feedback` reported state **closed** (@ ~04:39Z, same window). No
third transport was available (gh CLI absent; anonymous REST `/pulls` dark per
the loop's own pre-verify scan). Discrepancy filed UNRESOLVED; the claim was
skipped on either reading, so the boundary verdict above is unaffected. Row
closure authority stays with the verdict plane / admin.

Refs #5192 — spec-first keep-open: **no Closes line**; this receipt does not
resolve its subject (the GHAS capability decision and the core workflow edit
belong to the core owner).
