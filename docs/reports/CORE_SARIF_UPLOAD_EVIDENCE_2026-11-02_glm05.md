# Evidence — #5192 [core] SARIF upload fails when GitHub Advanced Security is unavailable

- **Agent**: GLM Agent 05 (Job 486719)
- **Task ID**: `audit-20261102-core-sarif-capability`
- **Claim**: GRANT_NEW at 2026-11-02T04:14:32Z (TTL 30m, expires 04:44:32Z)
- **Lane**: evidence (not auto-close). The remedy lives in a private satellite repo (`Supremeai-bd/supremeai-core`) inside `.github/` protected paths and requires a repository-capability policy decision (HITL/admin). Refs #5192 — no `Closes` line (false-closure guard, #2211/#2225 family).

## Root cause (mechanism)

The scheduled Core CI workflow reaches its `Upload SARIF to GitHub code scanning` step. On a repository where GitHub Advanced Security / code scanning is not enabled, the upload API rejects the SARIF submission with "Advanced Security must be enabled for this repository to use code scanning." The step treats this as a hard failure, the job goes red, and downstream reporting (code-scanning dashboard) never receives the result. The scanner and the application tests did not fail; only the publish step's capability assumption did.

This is a **capability-assumption defect in the workflow**, not an application defect: the workflow assumes GHAS is enabled without checking, and has no fallback path for repositories where it is not.

## Decision tree (per acceptance criteria)

**Path A — GHAS is approved for `supremeai-core`:**
1. Enable GitHub Advanced Security / code scanning for the private repo (admin setting).
2. Ensure the workflow job has `permissions: security-events: write`.
3. Re-run the scheduled workflow; confirm the SARIF upload step succeeds and findings appear under Security → Code scanning.

**Path B — GHAS is not approved (plan/policy limit) — recommended default given current state:**
1. Publish the SARIF file as a workflow artifact (`actions/upload-artifact`) so the scan result is preserved per run.
2. Make the GitHub upload step non-fatal: `continue-on-error: true` on the upload step (or a capability pre-check that skips the step with a clear warning line in the log).
3. Keep the rest of the job unchanged: Core Pytest & Lint continues to run on its normal push/PR triggers.
4. Document the operator review path (below).

Suggested step shape for Path B (illustrative, to be adapted to the real workflow file, which lives in the private repo and is outside this agent's read scope):

```yaml
- name: Upload SARIF to GitHub code scanning
  continue-on-error: true          # capability not guaranteed on private repos
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results.sarif

- name: Publish SARIF artifact
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: pyerrorfix-sarif
    path: results.sarif
```

## Operator review path

With Path B, per-run scan reports live under the workflow run's **Artifacts** section (`pyerrorfix-sarif`), downloadable from the run page: `https://github.com/Supremeai-bd/supremeai-core/actions/runs/<run_id>` → Artifacts → `pyerrorfix-sarif`. If Path A is chosen later, findings additionally appear under the repo's Security → Code scanning alerts view, and the artifact step can be kept as a belt-and-braces fallback.

## Impact assessment

- The red scheduled run is a **visibility defect** (scan findings unpublished, workflow red), not evidence of an application vulnerability — matching the WO's own impact statement.
- Leaving it red risks masking future genuine failures in the same workflow (alert fatigue), so the fix has real operational value.

## Verification limits (stated honestly)

- `supremeai-core` is private; this agent's environment has no authenticated GitHub read for it (tower `github.*` tools are RBAC-dark for this lane; anonymous REST probed → HTTP 403 for both repo and run endpoints). The referenced run 41290416574 could therefore not be re-inspected live.
- Compensating premise evidence: the WO was minted fresh on 2026-11-02 (same-day intake audit), carries a concrete run/job pair and verbatim log line; the feedback plane had `latestVerdict: null` and no prior evidence row for #5192 at claim time (no duplicate work in flight).

## Boundaries

- No `.github/` files were modified in this open repo (protected paths → admin review).
- No satellite repo was touched.
- Claim released after this receipt; closure/enable-decision left to the verdict plane/admin per the false-closure guard.
