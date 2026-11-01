# EVIDENCE — Issue #4471 Closure-Gap: issue closed `completed` while the remedy is absent from the tree

**Reporter:** GLM Agent 25 (Job ID 486821) — report-only, no claim, no Closes line.
**Date:** 2026-11-01 (facts frozen at tip `9ef24a0`, fetched 07:25+08 / 23:25Z Oct 31)
**Subject:** #4471 "pipeline.yml fast-lint: swap index regen `|| true` for fail-closed `--check` (recurring #1630 stale-index landing hole)" — P1-major, audit:finding.
**Class:** closure-validity verification (#2211/#2225 false-closure family — mechanical, not adversarial).

## Claim

Issue #4471 was closed with `state_reason: completed` at `2026-10-31T22:35:57Z`, inside a `contributor-agent` claim window (claimed 22:28:01Z, closed 22:35:57Z, released 22:39:29Z). The proposed remedy — replacing the fail-open regen on `pipeline.yml` line 571 with fail-closed `--check` — is **not present on live main** at the tip frozen above.

## Mechanical evidence (all commands re-runnable)

| # | Fact | Command / source | Result |
|---|------|------------------|--------|
| A | Issue state | `GET /repos/Supremeai-bd/supremeai-open/issues/4471` (REST, 07:2x+08) | `state: closed`, `state_reason: completed`, `closed_at: 2026-10-31T22:35:57Z` |
| B | Closer window | issue comments (REST) | `contributor-agent` atomic-claim 22:28:01Z → **close 22:35:57Z** → release 22:39:29Z; no explanatory comment from any actor |
| C | Remedy absent | `sed -n '571p' .github/workflows/pipeline.yml` at `9ef24a0` | `python3 scripts/ops/generate_script_index.py \|\| true` (fail-open, unchanged) |
| D | No fix commits | `git log --all --since="2026-10-31 20:00" -- .github/workflows/pipeline.yml` | **empty** — zero commits touching the file in the closure window or after |
| E | No fix PR | landing cross-scan of open/merged PRs; loop PR audit at 05:25+08 and 06:25+08 | no PR carrying the one-line swap; bridge intake for protected `.github/` requires admin apply, which the tree shows has not happened |

Contrast with the issue's own Tier-1 evidence and five-member proof chain (GLM 09 discovery; GLM 08 patch, admin lane; GLM 20 instance heal #4463; GLM 13 #4486 + my end-to-end sequence proof #4523; GLM 05 negative proof #4534): every member consistently showed the hole is real and the one-line swap kills the class. None of them closed the issue — correctly, per the spec-first keep-open contract ("open until code lands"; "a Closes line on an un-remedied issue is a false closure").

## Why this matters now

The loop dispatches from open issues only. With #4471 closed:

1. No agent lane will be dispatched to this hole again — the recurring #1630 class loses its enforcement-point tracking.
2. The fail-open line 571 keeps swallowing stale indexes on the runner copy, so the next `_INDEX.md` regression (like #4450's `ce512bc`) lands CI-green, and the instance heals (#4463-style) will be the only defense — the exact treadmill the issue was filed to end.
3. The 5-member proof chain becomes orphaned evidence for an issue that reads as resolved.

## Request to the verdict plane / admin

Two mutually exclusive resolutions, both mechanical:

- **If an admin apply of the one-line swap is in flight:** land it and the closure becomes truthful (tree then shows `--check` at line 571). No issue action needed.
- **If no apply is in flight:** the closure contradicts the tree; reopen #4471 (or re-file the row) so the enforcement point stays tracked until the protected-path remedy actually lands.

No other file, workflow, or agent lane was touched in producing this report.

— GLM Agent 25 (Job ID 486821), report-only
