# Federation Dispatch — Operator Appendix (protected path)

Status: OPERATOR/ADMIN-APPLIED INTEGRATION (`.github/` is a protected path
for zero-credential agent writes; this appendix ships the hunk for the
maintainer to apply). Issue class: `ADMIN_DECISION`.

## Why this exists

`landing.yml` is PR-centric: direct `push to main` never dispatches. The
"Universal Federation Dispatch Engine" closes that gap and adds multi-domain
splitting, while reusing the SSOT routing matrix in
`scripts/ci/hourly_satellite_batcher.py` (ECOSYSTEM_MAP.md §3.1).

The Python core lives in `scripts/ci/federation_dispatch.py` (offline,
testable, I/O-free). This appendix provides the workflow that invokes it.

## Apply step (operator lane)

Create `.github/workflows/federation-auto-sync.yml` with the content below.
Requires secret `FEDERATION_DISPATCH_PAT` (contents:write on all 12
satellites) — admin lane, master keys stay in the vault.

## Workflow hunk

```yaml
name: Federation — Auto-Sync (Universal Dispatch)

on:
  push:
    branches: [main]
  pull_request:
    types: [closed]
    branches: [main]
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Dry run (print plan, no push)"
        type: boolean
        default: true
      resync_all:
        description: "Resync every satellite from current main HEAD"
        type: boolean
        default: false

permissions:
  contents: read

concurrency:
  group: federation-auto-sync
  cancel-in-progress: false

jobs:
  dispatch:
    name: "Universal Federation Dispatch"
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      DRY_RUN: ${{ github.event.inputs.dry_run || 'true' }}
      RESYNC_ALL: ${{ github.event.inputs.resync_all || 'false' }}
    steps:
      - name: Checkout supremeai-open (full history)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Compute dispatch plan
        id: plan
        env:
          BASE_SHA: ${{ github.event.before || github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.sha }}
        run: |
          set -euo pipefail
          if [ "${RESYNC_ALL}" = "true" ]; then
            FILES=$(git ls-tree -r --name-only HEAD)
          elif [ "${{ github.event_name }}" = "pull_request" ]; then
            FILES=$(git diff --name-only "${BASE_SHA}" "${HEAD_SHA}")
          else
            if git cat-file -e "${BASE_SHA}^{commit}" 2>/dev/null; then
              FILES=$(git diff --name-only "${BASE_SHA}" "${HEAD_SHA}")
            else
              FILES=$(git ls-tree -r --name-only HEAD)
            fi
          fi
          printf '%s\n' "$FILES" > /tmp/changed.txt
          python scripts/ci/federation_dispatch.py --paths-file /tmp/changed.txt --json > /tmp/plan.json
          cat /tmp/plan.json
          echo "plan_file=/tmp/plan.json" >> "$GITHUB_OUTPUT"

      - name: Dispatch to satellites (live gate)
        if: env.DRY_RUN != 'true'
        env:
          FEDERATION_DISPATCH_PAT: ${{ secrets.FEDERATION_DISPATCH_PAT }}
        run: |
          set -euo pipefail
          if [ -z "${FEDERATION_DISPATCH_PAT}" ]; then
            echo "::error::FEDERATION_DISPATCH_PAT missing — cannot live-dispatch."
            exit 1
          fi
          echo "::notice:: live push to satellite main branches is performed by the operator lane;"
          echo "::notice:: Python core stays I/O-free. Wire git push here once PAT is provisioned."
```

## Relationship to the existing transit pipeline

This engine is a **complement**, not a replacement:

- `landing.yml` + `hourly_satellite_batcher.py` remain the authoritative
  transit path (freshness guards, 3-way conflict checks, urgent fast-lane,
  consolidated batching).
- This engine closes the `push to main` detection gap and provides the
  multi-domain split plan; the live push to satellite `main` branches stays
  in the admin lane behind `FEDERATION_DISPATCH_PAT`.

Protected paths (`.github/`, `.env`, `*.pem`) are quarantined by
`route_path` (returns `None`) and never ride a dispatch.

- Default `dry_run=true` — no pushes unless explicitly opted in.
- Never force-pushes; satellite writes are additive and go through the existing
  hourly batcher freshness/3-way guards before application.
- Live dispatch requires `FEDERATION_DISPATCH_PAT` (admin lane).
- Routing SSOT is `ECOSYSTEM_MAP.md §3.1`; drift is caught by
  `tests/test_federation_dispatch.py` and `tests/test_federation_transit.py`.
