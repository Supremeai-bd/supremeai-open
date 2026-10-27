# fix(ci): [core] nightly PyErrorFix Engine fails on first scheduled run (#1445)

## Problem
Run 40466830817 (event=schedule, 2026-10-27T07:23Z, sha 419a8388) failed in job
"PyErrorFix Engine" — the first-ever nightly schedule run of the autofix job.
Same commit passed the push-triggered run 35 (20:33Z), so this is not a code regression.

## Evidence (root cause by elimination)
The autofix job has exactly three steps that can affect outcome:
1. "Run pyerrorfix (detect + auto-fix + SARIF)" — every command ends with `|| true`;
   the SARIF-validity fallback writes a valid empty SARIF document. Cannot fail.
2. "Trigger Federation CI Watchdog on Failure" — curl ends with `|| true`. Cannot fail.
3. "Upload SARIF to GitHub code scanning" (github/codeql-action/upload-sarif@v3,
   `if: always()`) — has NO `continue-on-error`. This is the only step able to fail
   the job. The action fails when code scanning is not enabled on the target repo
   (API returns 404 for repos without the code scanning feature) — the log tail ends
   inside this step's post-run, consistent with an upload-step failure.

## Fix (two parts)
Part A — repo setting (operator, no code change):
  Enable code scanning on Supremeai-bd/supremeai-core:
  Settings -> Code security -> Code scanning tools -> Default setup. This makes the
  SARIF upload succeed instead of 404.
Part B — workflow guard (apply from this template):
  Add `continue-on-error: true` to the "Upload SARIF to GitHub code scanning" step so a
  reporting-only failure can never fail the nightly auto-fixer. Template:
  docs/ci-templates/ci-core-pyerrorfix-guard.yml

## Acceptance criteria
- [ ] Code scanning enabled on supremeai-core (Part A), or
- [ ] ci.yml autofix job carries the guard from docs/ci-templates/ci-core-pyerrorfix-guard.yml (Part B)
- [ ] Next scheduled run (cron 02:00Z) of job "PyErrorFix Engine" completes with conclusion success
- [ ] No new P0 runway issue auto-filed for the nightly run

## Reflection Evidence
**Why:** The nightly auto-fixer's only purpose is detection and auto-fix; a
reporting-side SARIF upload failing on a repo without code scanning must not page
anyone or spam P0 runway orders. Guarding the step keeps detection outcomes visible
in logs/SARIF artifacts while decoupling job success from an optional integration.
**Alternatives rejected:**
- Enable-only (Part A without guard): still fragile — any future code-scanning outage
  or quota issue re-fails the nightly job and re-spams P0 orders.
- Remove the SARIF upload step entirely: loses the code-scanning integration the
  permissions block explicitly grants (security-events: write).
- Patch .github/workflows/ci.yml directly via bridge: protected path — bridge rejects
  .github/ edits, hence this template + install-note lane (same as #1384 precedent).
