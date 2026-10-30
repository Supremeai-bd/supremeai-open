# Satellite CI Sentinel Surface — install note (Refs #2360, tool #2131)

`.github/` is a protected path on the bridge lane, so this workflow ships as a
template.

## Install (admin, one command)

```bash
git mv docs/ci-templates/satellite-ci-sentinel.yml .github/workflows/satellite-ci-sentinel.yml
```

No edits needed. Optional repo secrets: `TELEGRAM_ALERTS_BOT_TOKEN`,
`TELEGRAM_ALERTS_CHAT_ID` (notification degrades gracefully when absent).

## Why (the gap it closes)

#2360's follow-through finding: satellite CI damage stays invisible until a
manual audit looks. Measured progression across audit cycles — core push-CI
dark 31h → 54h → 68h (corrupted push trigger `branches: ain]`, #2125 lineage)
while vscode main-CI silence grew 104h → 127h → 140h+. The sentinel tool
(`scripts/ci/satellite_ci_sentinel.py`, self-test 19/19, exit codes 0/1/2
fail-closed) is report-only with no scheduled surface (#2360 option C), so
"only the auditor notices". This template gives the sentinel its surface —
this is #2360's guard suggestion 3, prepared in the agent envelope; wiring and
scheduling remain admin decisions (#2082 routed-not-wiring precedent).

## What it does

Every 4 hours (and on manual dispatch):

1. Runs the zero-credential sentinel sweep (report-only, one anonymous Tower
   handshake, read-only `github.workflow_runs` across the 6 satellite mains).
2. Exit 1 (a verified main is RED) or any other non-zero (fail-close) →
   files ONE deduplicated alarm issue (label `ci:sentinel`); later red sweeps
   append a fresh timestamped receipt as comments instead of stampeding new
   issues.
3. Exit 0 (all green) → posts a single green corroboration comment on the open
   alarm issue if none exists yet; repeated greens stay silent.
4. Optional Telegram notification on red/fail-close (non-fatal).

## Design laws honored

- **Carrier-green**: the workflow job itself never fails — a monitoring plane
  must not structurally bleed red (the #2111/#2125 PyErrorFix lesson). The
  alarm surface is the issue lane; the red state is still shown via `::warning::`
  annotations in the run summary.
- **No auto-close**: a green sweep never closes the alarm issue — closure
  authority stays with the verdict plane/admin (#2211/#2225/#2738
  false-closure family).
- **Anti-stampede (U5)**: label + title-prefix dedup, single green comment.
- **Routed-not-wiring (#2082)**: admin owns scheduling; this template only
  makes the landing a one-command act.

## Provenance

Dispatched by the continuous agent loop against #2360 (solver). Sibling
evidence receipt for the same row: #3272 (GLM Agent 11, 12:12–12:15Z live
probes — core RED, dark-push mechanism confirmed live, api/browser crossed the
48h window). Prior lineage: #2111 (red evidence) → #2125 (RCA) → #2131
(sentinel tool) → #2360 (asymmetric-remediation audit) → this template.
