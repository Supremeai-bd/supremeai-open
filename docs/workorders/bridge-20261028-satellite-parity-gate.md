# Bridge Work Order — guard(federation): scheduled satellite-dispatch parity gate (#1792, R38)

**Lane**: coder → admin (`.github/` apply only). **Classification**: `adapt` — adapts the
proven #1689 sentinel SHA-256 method into a scheduled, report-only detection gate.
**Delivered**: 3 files (`scripts/ci/satellite_parity_gate.py`, `tests/test_satellite_parity_gate.py`,
this runbook). `.github/workflows/satellite-parity-gate.yml` is carried VERBATIM in §3 below —
agents cannot write protected paths (#1643 precedent), so the admin applies it exactly as printed.

## Why

#1689 proved a satellite dispatch drift could sit in production for days until a human
byte-level audit found it (unsanitized gateway entrypoint served live while the hardened
mirror fix sat undispatched). The verification kernel exists in-tree
(`federation_satellite_sync.py --verify-only`, run 7, landed via PR #1720) but only fires
when a human or admin re-runs the sync — there is no scheduled detection. This WO adds the
missing schedule: **detection latency drops from "until the next manual audit" to ≤6 h 15 m**
(schedule + jitter), with zero auto-push and zero auto-merge — dispatch authority stays with
humans/admins per the bridge contract.

## §1 Live baseline (evidence, dated)

Run 9 live probe of all 7 manifest pairs via authenticated contents-API reads,
2026-10-28 07:32+08 (= 2026-10-27T23:32Z), `git blob SHA` identity on both sides:

```
CLEAN  gateway/main.py          <-> Supremeai-bd/supremeai-api:main.py
CLEAN  core/main.py             <-> Supremeai-bd/supremeai-core:main.py
CLEAN  browser/main.py          <-> Supremeai-bd/supremeai-browser:main.py
CLEAN  studio/package.json      <-> Supremeai-bd/supremeai-studio:package.json
CLEAN  vscode/package.json      <-> Supremeai-bd/supremeai-vscode:package.json
CLEAN  api-schemas/gateway.openapi.yaml <-> Supremeai-bd/supremeai-api:contracts/openapi.yaml
CLEAN  examples/gateway_client.py       <-> Supremeai-bd/supremeai-api:scripts/clients/gateway_client.py
```

7/7 clean — the #1689 heal is holding. First scheduled run must report clean; any later
drift then auto-files its own evidence (§3), which is the entire point of the gate.

## §2 Admin apply — checklist (2 minutes)

1. **Secret**: `SAT_SYNC_PAT` already exists on this repo (verified via
   `github_list_secrets`, 2026-10-27T23:33Z, total_count 13). Confirm its scope is
   least-privilege READ-ONLY contents on the five satellite repos
   (`supremeai-api`, `-core`, `-browser`, `-studio`, `-vscode`). The gate never writes.
2. **Label**: `audit:finding` exists in this repo (in active use on #1791/#1785/#1804 …).
   The auto-WO step uses it; no setup needed.
3. **Workflow**: create `.github/workflows/satellite-parity-gate.yml` with EXACTLY the §3
   content (copy the fenced block, nothing else).
4. **Enable**: `workflow_dispatch` lets you trigger a first run immediately from the
   Actions tab to prove the wiring (expect exit 0, `7/7 clean`).

## §3 Verbatim workflow (admin applies as-is)

```yaml
name: satellite-parity-gate

on:
  schedule:
    # every 6 h at :17 UTC — off the top of the hour to avoid contention
    - cron: "17 */6 * * *"
  workflow_dispatch: {}

permissions:
  contents: read
  issues: write

jobs:
  parity:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout open monorepo mirror
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2 (SHA-pinned per #1776/R35 zizmor discipline)

      - name: Set up Python
        uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c # v5.3.0
        with:
          python-version: "3.11"

      - name: Run satellite parity gate (report-only)
        id: gate
        env:
          SAT_SYNC_PAT: ${{ secrets.SAT_SYNC_PAT }}
        run: |
          set -o pipefail
          python scripts/ci/satellite_parity_gate.py --json --issue-body drift_body.md | tee gate_report.json
          code=$?
          echo "exit_code=$code" >> "$GITHUB_OUTPUT"
          exit $code   # 0 clean / 1 drift / 2 infra — failing on drift is intentional (red-CI double-signal)

      - name: File report-only drift work order
        if: steps.gate.outputs.exit_code == '1'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue create \
            --title "federation: satellite parity drift detected (auto, report-only)" \
            --body-file drift_body.md \
            --label "audit:finding"
```

## §4 Behavior contract (what admin should expect)

- **Exit 0** — all sentinels byte-identical; job green; nothing filed.
- **Exit 1** — drift. Job red ON PURPOSE (double-signal) AND a report-only issue is filed
  with the `api_drift_detail.py` template: per-pair byte-size delta + sha256 pairs + capped
  unified hunks + remediation pointing at the #1689 runbook (re-dispatch sync to heal, or
  revert satellite surface to the mirror blob SHA).
- **Exit 2** — infra (auth/network/rate-limit/manifest unreadable). Job red, NO issue filed
  (a gate that cannot see must not vote clean, and must not spam issues either — inspect logs).
- **Never**: no push, no merge, no dispatch, no satellite writes. The script's only
  filesystem side effect is the issue-body file you explicitly name via `--issue-body`.
- GitHub caveat: scheduled workflows auto-pause after 60 days of repo inactivity — if the
  repo goes quiet, re-enable from the Actions tab.

## §5 Validation performed (this submission)

- `py_compile` PASS on both scripts.
- unittest runner, module `tests.test_satellite_parity_gate` — 25/25 PASS (offline, fetch layer
  injected; covers clean/drift/error classification, fail-closed infra semantics, exit-code
  mapping, hunk caps + delta signs, issue-body contract markers, token env chain, 404→None,
  base64 decode, manifest-missing/empty refusal).
- `scripts/ci/satellite_parity_gate.py --self-test` — PASS.
- Secret scan: no literals, no tokens, no URLs with credentials; token referenced by env
  name only (`SAT_SYNC_PAT`).
- `.github/` untouched by this PR (§3 is the only workflow source of truth, printed above).

## §6 Rollback

Delete `.github/workflows/satellite-parity-gate.yml` (reverts schedule instantly; the
script is inert without it) — the standalone script + tests can stay harmlessly in-tree.
