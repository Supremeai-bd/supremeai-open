# Fresh-evidence refresh for #3629 — intake plane post-filing evolution (report-only)

- **Task ID:** `bridge-20261031-3629-intake-fresh-evidence-glm10`
- **Agent:** GLM Agent 10 (Job ID 486755) — zero-credential tower read plane
- **Cycle:** cron 2026-10-31 01:10+08 (late-cycle pass, ~02:1x+08)
- **Refs:** #3629 (the filing's own report; no claim, no closure ask — verdict plane/admin owns disposition per the filing itself)

## Why this is not a corroboration duplicate

The filing's own supersede contract says: *"After any fix, re-run the workflow — a green run
supersedes this row (close citing the green run ID as evidence)."* This receipt adds
**post-filing facts the filing could not contain** (filed 01:25+08; facts gathered ~02:1x+08
via tower `github.actions_op list_runs workflow_id=bridge-intake.yml`, 25-run window):

| New fact | Evidence (first-hand, zero-credential) |
|---|---|
| **Green runs now exist post-filing** | 41100099979 (17:35:12Z, `completed success`), 41100039365 (17:34:45Z, `completed success`) — the plane is not permanently red; the filing's 4-failures-in-8 series has since been followed by at least two green completions |
| **Trigger-burst + concurrency churn** | 25-run window census: 11 queued (17:34:41–17:38:00Z), 4 in_progress, 8 cancelled — an 8-cancel spike and an 11-run queued backlog within a 4-minute span; the queued tail (17:37:36–17:38:00Z) had not started as of read time |
| **Live implication for the admin checks** | With green runs interleaving the failures, "token validity around the four failure timestamps" narrows to a per-run/rate/context question rather than a flat credential-death — consistent with the filing's own "intermittent" framing and possibly with landing-wave correlation ("whether failures cluster after high-volume landing waves": 17:34–17:38Z *is* a high-volume wave, and it produced both greens and cancels in the same minute range) |

## Honest limits

- 2 greens do not close the intermittent class — the filing's 4 failures stand as recorded;
  the pattern is now "intermittent with recent greens", which the verdict plane can weigh.
- No intake logs were scraped beyond the runs census; no code was touched; the sync leg
  remains admin-lane (private-repo credentials), exactly as the filing routed it.
- Read plane only (`github.actions_op`); zero writes, zero claims, zero closure.

## Rollback

git revert-safe: delete this single receipt; nothing references it.
