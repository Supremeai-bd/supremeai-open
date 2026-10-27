# Admin Work Order — Satellite Sentinel Gate (#1689)

**Task ID:** `bridge-20261028-satellite-sentinel`
**Filed by:** zai-mcp-tower-agent (cron Job 477795, run 7) · 2026-10-28 05:35 +08:00
**Carrier PR:** bridge/bridge-20261028-satellite-sentinel — lands the sync-script mapping, the sentinel verifier, the manifest, and this doc. The CI gate below is `.github/` (protected path) and is NOT in the PR diff — admin applies it verbatim.

## 1. Verified finding (audit #1689, re-verified live this run)

| Surface | Size | sha256(16) | Status |
|---|---|---|---|
| `supremeai-open:gateway/main.py` | 38,818 B | `8fa890e8442c39ab` | hardened (sanitization imports + `sanitize_error_message` + `payload.update(sanitize(extra))`) |
| `supremeai-api:main.py` (satellite **root**) | 35,428 B | `680da93d6c6dabf7` | **STALE** — 956-line revision, missing all sanitization hardening (90 lines behind) |
| `supremeai-api:gateway/main.py` (in-package) | 38,818 B | `8fa890e8442c39ab` | hardened — byte-identical to mirror |

**Impact correction (honesty first):** the audit's headline ("live api satellite is running the unsanitized error path") is **overstated**. The in-package `gateway/main.py` on the satellite — the surface the sync maintains and that `service/`/module imports resolve through — already carries the full hardening. The drifted surface is the satellite **root** `main.py`, a legacy mirror artifact that (a) uses relative imports (`from .config import ...`) and therefore cannot execute standalone from the satellite root, and (b) is no longer mapped by `sync_satellite()` — so *no re-dispatch of the current sync can ever fix it*. The residual risks are: humans/runbooks/tools copying or executing the stale root file, and the mirror↔satellite parity invariant being violated on a visible surface. Both are real; neither is a live leak.

**Root cause:** the `Supremeai-bd/supremeai-api` block of `sync_satellite()` maps `gateway/` → `gateway/`, `gateway/service` → `service/`, `admin_auth.py` → root, `api-schemas/` → `contracts/schemas/` — but never `gateway/main.py` → root `main.py`. The audit's remediation 1 ("re-run `federation_satellite_sync.py --all`") alone would leave this drift in place forever.

## 2. What the carrier PR already lands (no admin action needed)

1. **`scripts/ci/federation_satellite_sync.py`** — (a) api satellite now syncs `gateway/main.py` → root `main.py` (admin_auth.py precedent, #1689 comment); (b) new `--verify-only` sentinel mode comparing open-side checkout bytes vs live satellite heads (GitHub contents API, stdlib only) with exit contract `0` clean / `1` drift / `2` verification errors (fail-closed — a network or auth failure fails the gate rather than silently passing); (c) observational post-sync sentinel check in normal sync runs (never flips the sync exit code — API freshness can lag a just-pushed ref); (d) self-test extended with the sentinel contract (defaults↔manifest alignment, mandatory api root pair).
2. **`scripts/ci/satellite_sentinels.json`** — config-driven manifest of 7 sentinel pairs (the auditor's 7-point sweep). All 7 pairs were re-verified live this run: 6 byte-identical, 1 drifted (the pair this PR fixes). Ops can extend the sweep by editing the manifest — no code change.
3. **`tests/test_federation_sentinels.py`** — 12 offline unit tests (manifest load/fallback/corruption, clean/drift/absent/infra-error/malformed/filter paths, source-level regression pin for the root mapping). All passing; `--self-test` passing.

## 3. Admin action 1 — heal the live drift (after PR lands)

```bash
# Re-dispatch sync for the api satellite with the patched script.
# This copies gateway/main.py -> satellite root main.py and pushes it.
python scripts/ci/federation_satellite_sync.py \
  --targets Supremeai-bd/supremeai-api \
  --commit-msg "sync(open->api): heal root main.py sanitization parity (#1689)"

# Then confirm the gate is green:
python scripts/ci/federation_satellite_sync.py --verify-only
# expect: 7 clean / 0 drift / 0 errors, exit 0
```

## 4. Admin action 2 — CI sentinel gate (protected path, apply verbatim)

Create **`.github/workflows/satellite-sentinel-gate.yml`** in `Supremeai-bd/supremeai-open`:

```yaml
name: satellite-sentinel-gate
on:
  workflow_dispatch: {}
  schedule:
    - cron: "23 * * * *"   # hourly, offset from other crons
  workflow_run:
    workflows: ["satellite-dispatch-and-sync"]  # rename if the sync workflow is named differently
    types: [completed]
permissions:
  contents: read
jobs:
  sentinel-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Wait for push propagation (skip on manual runs)
        if: github.event_name == 'workflow_run'
        run: sleep 60
      - name: Verify mirror<->satellite sentinel parity (#1689)
        env:
          SAT_SYNC_PAT: ${{ secrets.SAT_SYNC_PAT }}
        run: python scripts/ci/federation_satellite_sync.py --verify-only
```

The job fails (exit 1 drift / exit 2 infra) → gate red → the drift class of #1689 can no longer silently recur. If the sync workflow has a different `name:` than `satellite-dispatch-and-sync`, adjust the `workflow_run.workflows` value (the schedule + dispatch triggers make the gate independent of that name).

## 5. Admin action 3 — investigate the original skip

Audit remediation 3 asks *why* `satellite-dispatch-and-sync` skipped `Supremeai-bd/supremeai-api` on the sanitization landing. The sync script's api block has multiple graceful-degradation paths (clone/push permission errors print `[GRACEFUL-DEGRADATION]` and return success). Review those workflow logs around the sanitization commit; if degradation-during-incident is confirmed, consider making `[GRACEFUL-DEGRADATION]` post a Telegram notification so silent skips become visible. The sentinel gate from §4 makes any future skip detectable within an hour regardless.

## 6. Rollback

The PR is revert-safe: the mapping addition is one guarded copy (`if root_main.exists()`), `--verify-only` is opt-in (nothing in existing flows changes behavior — the observational post-sync check prints but never fails), the manifest is a new file, the tests are a new file. Reverting the PR restores the previous blobs byte-for-byte; the CI gate in §4 is admin-owned and removable independently.
