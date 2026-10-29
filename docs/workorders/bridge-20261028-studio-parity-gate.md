# Admin Work Order — studio parity gate (companion to bridge-20261028-studio-mirror-parity / WO #1617)

## Context
Audit Finding F-1 (#1617) asked to re-mirror 15 `studio/**` files from `Supremeai-bd/supremeai-studio`
(SSOT) into the `Supremeai-bd/supremeai-open` mirror, plus a CI parity gate. The companion bridge PR
mirrors the files that actually differ (SHA-verified on 2026-10-28: 7 of the 15 were already
byte-identical, 6 drifted, 1 absent; `cockpit.css` deliberately NOT overwritten because the open side
carries a real improvement — `z-index: var(--z-index-critical)` token single-sourcing — that the
private HEAD lacks; `package.json` was selectively merged, keeping the open-only
`@testing-library/user-event` devDependency).

This document carries the exact `.github/` patch — the protected path the bridge lane cannot touch.

## Patch: add parity gate job to `.github/workflows/pipeline.yml`

Append this job to the `jobs:` map (adjust indentation to the file's 2-space style):

```yaml
  studio-parity-gate:
    name: studio mirror parity (open ⊆ studio SSOT)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout open mirror
        uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - name: Fail when any satellite studio/** file diverges from the studio SSOT
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          # Files that the audit declared mirrored-subset surfaces. Keep in sync
          # with docs/architecture notes; extend as more studio files are mirrored.
          FILES=(
            studio/package.json
            studio/src/components/EmergencyConsole.tsx
            studio/src/components/RunwayVisualizer.tsx
            studio/src/components/SatelliteMatrix.tsx
            studio/src/components/SwarmDefenseGauge.tsx
            studio/src/components/auth/ServiceHealthBar.tsx
            studio/src/components/auth/ServiceHealthBar.test.ts
            studio/src/services/apiClient.ts
            studio/src/services/apiClient.test.ts
            studio/src/services/telemetryClient.ts
            studio/src/utils/api.ts
            studio/src/utils/api.test.ts
            studio/src/types/federation.ts
            studio/tests/telemetryClient.test.ts
          )
          fail=0
          for f in "${FILES[@]}"; do
            if [ ! -f "$f" ]; then
              echo "::error::missing from open mirror: $f"; fail=1; continue
            fi
            blob=$(git hash-object "$f")
            src_blob=$(gh api "repos/Supremeai-bd/supremeai-studio/contents/$f?ref=main" \
              --jq '.sha' 2>/dev/null || echo "unreachable")
            if [ "$src_blob" = "unreachable" ]; then
              echo "::warning::studio SSOT unreachable for $f (skip — fail-open, mirror must never hard-block on upstream flake)"
            elif [ "$blob" != "$src_blob" ]; then
              echo "::error::drift detected: $f (open $blob != studio $src_blob)"; fail=1
            else
              echo "in-sync: $f"
            fi
          done
          exit $fail
```

Notes:
- `git hash-object` computes the same blob SHA GitHub reports for `contents/<path>` (blob format
  `blob <len>\0<content>`), so the comparison is exact and no extra checkout of the studio repo is
  needed.
- The gate is **fail-closed on drift, fail-open on upstream flake** — a mirror must never block the
  pipeline because the SSOT repo had a 5xx; it must block when content actually diverges.
- `cockpit.css` is intentionally NOT in the list until the z-index token single-sourcing is ported
  back to the studio SSOT (recommended follow-up: adopt `var(--z-index-critical)` upstream, then add
  the file here).

## Rollback
Revert the single pipeline.yml commit; the gate is additive and touches no existing job.
