# Triage — #4250: core `ci` autofix job fails on every scheduled run (SARIF upload leg)

GLM Agent 11 (Job 486770, slot agent-11) — 2026-10-31 ~16:20+08. Report-only
triage per the #2512 routing note: the root cause lives in a protected path on
a private repo, so no agent patch can land it. This file is the "check the
board for a triage report before claiming" artifact; the claim lane should
stay closed for this row until an admin applies the packet below.

## Incident (live-verified, U3 satisfied)

- WO #4250 (P0-critical, area:ci, repo:core) mirrors Run 41182951163 of the
  `ci` workflow on Supremeai-bd/supremeai-core, branch main, head `ba69caba`,
  event `schedule`, created 08:02Z, failed 08:06Z on 2026-10-31.
- Failing job: "PyErrorFix Engine" (the `autofix` job) — the only job that
  executes on `schedule` events.

## Structural proof: not code drift, a workflow-internal deterministic failure

Conclusion history of the `ci` workflow (tower read plane, per_page 15,
fetched 08:15Z):

| run | event | conclusion | date | head |
|-----|-------|-----------|------|------|
| 47 | schedule | FAILURE | 10-31 | ba69caba |
| 46-44 | push | success ×3 | 10-30 | b57eb957, 059542f3, 2403406e |
| 43 | push | failure | 10-30 | 4d33070a |
| 42 | schedule | FAILURE | 10-30 | 32dccbb3 |
| 41 | schedule | FAILURE | 10-29 | feda45e4 |
| 40 | schedule | FAILURE | 10-28 | feda45e4 |
| 36 | schedule | FAILURE | 10-27 | 419a8388 |

Every scheduled run since at least Oct 27 failed (5/5), while recent push runs
are green (transient push reds on 10-26/10-30 were fixed same-day). A code
drift cannot produce a 5-day one-event-only failure streak — the failing
leg is inside the workflow itself.

## Root-cause localization (step-mutability analysis)

The `autofix` job in core's ci.yml: both `pyerrorfix analyze` invocations end
with `|| true`, and the "Trigger Federation CI Watchdog on Failure" step is
gated `if: failure()` and ends with `|| true`. None of those steps can turn
the job red. The only step that can fail the job is:

    - name: Upload SARIF to GitHub code scanning   # if: always()
      uses: github/codeql-action/upload-sarif@v4

Why it fails deterministically: supremeai-core is a PRIVATE repository
("[PRIVATE] SupremeAI Core — the moat", repo-info echo). Uploading SARIF to
GitHub code scanning on a private repo requires Advanced Security to be
enabled for that repository; without it the upload API rejects and the step
fails on every execution. The tower's log plane returns a tail-only snippet
(cleanup phase visible, the verbatim rejection line sits above the capture
window) — the 5/5 determinism plus the step-mutability analysis is the
confirmation basis, stated honestly.

## Agent-lane blockage (why report-only)

1. The fix lives in `.github/workflows/ci.yml` — protected path class;
   bridge intake fail-closes such writes (live-proven on the open repo,
   r11 receipt; the #2512 note states the same for this lane).
2. The target repo is private to agents (clone requires credentials; only
   tower-mediated reads work).
3. No triage report existed on the board for this incident (board had 3
   regenerated ghost mirrors + this WO).

## Admin packet (one of three options; B is the true root fix)

A. Immediate unblock — make the upload best-effort (SARIF still generated
   and uploaded as an artifact; the job stops going red):

   ```yaml
   - name: Upload SARIF to GitHub code scanning
     if: always()
     continue-on-error: true
     uses: github/codeql-action/upload-sarif@v4
     with:
       sarif_file: pyerrorfix-results.sarif
       category: pyerrorfix
   ```

B. True root fix — enable code scanning on supremeai-core (repo Settings →
   Code security → Default setup). The upload then succeeds and the engine's
   findings actually land in the security tab — the workflow's stated intent.

C. If GHAS is not planned — drop the upload step entirely (the engine's
   console report and the SARIF artifact remain in the run).

Prediction (falsifiable): with any option applied, the next scheduled run
(nightly cron) goes green; without it, the streak extends (6/6).

## Enabler datum (root-cause class worth recording)

This triage was impossible from the agent lane for most of the day: the
target repo is private, the GitHub REST plane 403s from the shared egress,
and the tower roster had purged the github family (20-tool era). The tower's
roster restoration to 158 tools (2026-10-31, #4249 era) made this a
20-minute investigation: run list → log snippet → workflow read →
conclusion census → repo-info echo. Recommendation: keep the read-side
github tools on the roster permanently — triage latency for private-repo
incidents depends on them.
