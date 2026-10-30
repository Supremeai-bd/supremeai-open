# bridge-20261031-3656-gateway-parity-r1 — GLM Agent 04 (Job 486718)

Row: #3656 (scout, self-filed this cycle after atomic claim on dispatch row #3649 returned
CLAIM_CONFLICT — holder: contributor-agent, per stale-claim guard no retry).
Landing: remedy A of #3656 — parity manifest now covers the Dockerfile-load-bearing
`gateway/` package. closesOriginalIssue=3656 (remedy fully inside this repo).

## Why (root cause chain, all live-verified 18:05–18:17Z 2026-10-30 UTC)

1. `Supremeai-bd/supremeai-api@main` Dockerfile step `COPY gateway/ gateway/` (#1772
   package-true layout) requires a `gateway/` package that is ABSENT on satellite main —
   tower reads with positive control (`mcp/src/lib/env.ts` ~19KB, `runtime/infisical_bootstrap.py`,
   `requirements.txt` all read fine; `gateway/__init__.py`, `gateway/main.py`, `gateway/app.py`
   all Not Found). This is the confirmed satellite-side root cause of #3649's five failed
   Render builds (13:02–16:23Z) — still unremediated, admin/satellite lane owns the re-sync.
2. The one scheduled gate built to catch mirror<->satellite drift
   (`satellite_parity_gate.py`) could not see it: manifest v1 pinned 7 root-artifact pairs,
   none covering the `gateway/` package. #1772 changed the layout contract; the manifest
   never followed — the gate was blind to its own repo's build contract.

## What landed

- `scripts/ci/satellite_sentinels.json` v1→v2: +2 sentinels for Supremeai-bd/supremeai-api —
  `gateway/__init__.py -> gateway/__init__.py` and `gateway/main.py -> gateway/main.py`
  (open side exists for both; provenance `v2Extension` documents the #3656 arc).
- `tests/test_satellite_parity_gate.py`: +`ManifestGatewayCoverageTests` (4 offline pins:
  package sentinels present, package-true paths, manifest open-paths-on-disk rot guard,
  gateway/Dockerfile still COPYs the package).

## Mechanical outcome (simulated against live satellite state)

`gate.classify_pair(new sentinel, mirror bytes, satellite=None)` → **`drift`
("satellite surface absent")**. From the next scheduled run the gate reports exit 1 with the
standard report-only issue body and keeps firing until admin re-syncs the satellite — the
#3649 class can no longer be silent.

## Honest boundaries (verdict-plane notes, no autoclose claimed beyond #3656)

- #3649's Render-plane anchor is unverifiable through the tower: service id
  `srv-dbappass728c7396p580` does not resolve in the tower's render-primary account
  (exactly one service exists — supremeai-primary-node/supremeai-core, lastDeployStatus
  `live`, zero build-error logs 12:50–18:20Z); `health_full_sweep` still shows
  `render-api: degraded` while its snapshots carry `checkedAt` ~47min older than the
  sweep's own timestamp and `incidents: []`. Stale-snapshot trust + unresolvable anchor:
  admin lane.
- Satellite repair (restore `gateway/` via `federation_satellite_sync.py`, then a green
  Render deploy) supersedes #3649 — admin lane, HITL.
