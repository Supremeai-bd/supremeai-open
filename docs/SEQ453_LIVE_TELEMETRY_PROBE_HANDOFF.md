# Seq 453 — Live Telemetry Probe & Timestamp-Parity Contract Hand-off (#453, r1)

> Task: `bridge-20261017-live-telemetry-probe-453` · Issue: #453 (enhancement,
> repo:open; **claim state at build time: PENDING** — this order is submitted
> only after the operator sets `status:claimed` / an `<!-- atomic-claim -->`
> marker on #453, per invariant #430: no claim → no branch → no push) ·
> Anchor: AUTONOMOUS_TRANSIT_PIPELINE line 16 (Self-Healing Board, Rule 16)
> and lines 17–22 (Unified Gateway Shield) · Base: `8e5ed59` (origin/main at
> build time) · Lane: pure-new-file payload (2 files, one routing domain:
> `scripts/**` + `docs/**` → monorepo).

## §0 Deliverable decomposition (what rides here, what does not)

Issue #453 lists three deliverables. This order ships the parts that are
authorable and verifiable from the public repo without credentials, and
explicitly scopes out the rest:

| Deliverable (issue text) | Rides here? | Why / how |
|---|---|---|
| D1 — MCP Tower tool `tower_probe_live_status` | **No** | Lives in control-plane src (specialist lane). Collision risk against the still-pending MIRROR-PARITY `bridge.tools.ts` §2 diff (PR #8 landed doc+test only) — shipping another control-plane src order now would stack two operator-app diffs on the same file. The probe script below is the shared foundation the tower tool can adopt later. |
| D2 — Gateway timestamp parity (`git_sha`, `deployed_at`, never `unknown`) | **Verifier only** | The gateway source is not visible in the public monorepo, so an exact git-apply diff CANNOT be authored without seeing it (no invented hunks — honesty rule). This order ships the contract + a runnable verifier (`scripts/ci/probe_live_status_453.py`) whose parity checks define acceptance: once the operator's handler fix lands, the probe turns green; until then it reports the measured gap as telemetry. |
| D3 — Scheduled probe Action (auto-issue on failure, Rule 16) | **YAML §2 block** | `.github/**` is a protected, operator-owned path. The complete workflow is shipped as a §2 block for operator application, with a dedup guard so the Self-Healing Board does not get issue storms. |

## §1 Measured evidence (at r1 build, 2026-10-17)

1. **Gateway down** — `GET https://supremeai-api.onrender.com/healthz` →
   `404` + `x-render-routing: no-server` (probes 00:51Z, re-verified twice).
   The probe therefore currently exits `1` with this as its failure record —
   that is the DESIGNED behavior: a probe that cannot fail is not telemetry.
2. **House conventions reused** — report schema keys (`timestamp`,
   `service_name`, `component`, `metrics`) align with
   `api-schemas/telemetry-log.schema.json`; the fail-closed exit-code contract
   mirrors `examples/curl-tests/health.sh` ("a skipped check does not exist").
3. **Collision check** — `git ls-tree origin/main scripts/ci/` lists exactly 3
   files (`auto_bridge_pr_opener.py`, `boundary_sanitization_guard.py`,
   `stale_claim_releaser.py`); no probe/telemetry script exists in `scripts/`
   (only `examples/telemetry-logger/logger.py`, a different purpose). The
   issue-tagged name `probe_live_status_453.py` follows the r2 anti-collision
   naming lesson (WO #434 wave 2: generic `validate_links.py` collided on
   private main).
4. **Offline battery** — `--selftest` passes 8 assertions with zero network
   (parity good/unknown/stale/non-ISO + CORS good/missing + docstring
   presence); `py_compile` clean; bad-URL config exits `2`.

## §2 Scheduled probe Action (operator applies — protected path)

Target: `Supremeai-bd/supremeai` → `.github/workflows/live_probe_453.yml`
(monorepo, same repo as the probe script — no cross-repo checkout needed).
It probes every 30 minutes (pipeline cadence), writes a JSON report, and on
failure auto-opens ONE Rule-16 issue on supremeai-open, dedup-guarded by an
open-issue search so repeated failures update nothing until resolved.
Optional repo variables: `vars.GATEWAY_URL` (defaults to the public URL),
`vars.STUDIO_CORS_ORIGINS` (comma-separated registered Studio origins —
the authoritative list is operator/vault-side; left unset the CORS checks
are skipped, which keeps the probe honest instead of guessing origins).

```yaml
name: live-probe-453
on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch: {}

concurrency:
  group: live-probe-453
  cancel-in-progress: false

permissions:
  issues: write
  contents: read

jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Probe live gateway (issue #453)
        id: probe
        env:
          GATEWAY_URL: ${{ vars.GATEWAY_URL || 'https://supremeai-api-ulw0.onrender.com' }}
          CORS_ORIGINS: ${{ vars.STUDIO_CORS_ORIGINS }}
        run: |
          set +e
          python3 scripts/ci/probe_live_status_453.py \
            --json-out probe-report.json --timeout 20
          code=$?
          if [ "$code" -eq 1 ]; then
            echo "probe_failed=1" >> "$GITHUB_OUTPUT"
          fi
          exit 0
      - name: Self-Healing Board issue (Rule 16)
        if: steps.probe.outputs.probe_failed == '1'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('probe-report.json', 'utf8'));
            const q = 'repo:Supremeai-bd/supremeai-open is:issue is:open in:title "[Rule 16] Gateway probe failure"';
            const existing = await github.rest.search.issuesAndPullRequests({ q, per_page: 1 });
            if (existing.data.items.length > 0) {
              const n = existing.data.items[0].number;
              await github.rest.issues.createComment({
                owner: 'Supremeai-bd', repo: 'supremeai-open', issue_number: n,
                body: 'Probe still failing at `' + report.timestamp + '` — failures: ' + JSON.stringify(report.failures)
              });
              return;
            }
            await github.rest.issues.create({
              owner: 'Supremeai-bd', repo: 'supremeai-open',
              title: '[Rule 16] Gateway probe failure ' + report.timestamp,
              body: '**Live gateway probe failed.**\n\n```json\n' +
                    JSON.stringify(report, null, 2).slice(0, 60000) + '\n```\n\n' +
                    'Source: `scripts/ci/probe_live_status_453.py` (issue #453).'
            });
```

## §3 Timestamp-parity contract (D2 acceptance criteria)

The verifier enforces, per issue #453's own text, on BOTH `/health` and
`/healthz` JSON payloads once the gateway serves:

1. `git_sha` present and not `unknown`/`null`/empty.
2. `deployed_at` present, ISO-8601 parseable, and not older than 7 days
   (Rule 17 deploys 4×/day; 7 days = stale-drift ceiling, not a quota).
3. `version` may exist but must not be the literal `'unknown'` (the exact
   deficiency #453 names).
4. CORS preflight (when origins configured) on `POST /v1/chat/completions`:
   HTTP 200, `access-control-allow-origin` echoes the requesting origin (or
   `*`), `access-control-allow-methods` includes `POST`.

Usage:

```bash
# offline battery (zero network, CI-safe)
python3 scripts/ci/probe_live_status_453.py --selftest

# live probe — telemetry, not a test: exit 1 while the gateway is down is CORRECT
# NOTE (issue #2355): always probe the deployed SUFFIXED service URL
# (supremeai-api-ulw0.onrender.com). Bare Render names are NOT service URLs:
# they 404 at the router with x-render-routing: no-server (fast, 0.2s) —
# check that header before declaring a gateway blackout.
GATEWAY_URL=https://supremeai-api-ulw0.onrender.com \
  python3 scripts/ci/probe_live_status_453.py --json-out probe-report.json
```

Report shape (trimmed example; full schema in the script docstring):

```json
{
  "schema": "supremeai.probe_live_status.v1",
  "timestamp": "2026-10-17T01:45:00Z",
  "service_name": "supremeai-api",
  "component": "probe_live_status_453",
  "pass": false,
  "failures": ["GET healthz: HTTP 404 (want 200 with JSON payload)"],
  "metrics": { "probe.healthz.latency_ms": 451.4 }
}
```

## §4 Audit verbatims

- No relative markdown links by design (all references are inline code
  spans) → link-audit surface of this doc = 0 dead links by construction.
- `py_compile` + `--selftest` (8 assertions, zero network) pass at build.
- YAML block: single document, `name`/`on.schedule`/`jobs.probe.steps` keys
  verified parseable.
- Secret scan: 10 families clean; no credentials, tokens, or vault refs —
  CORS origins are intentionally operator-supplied variables (vault-only
  doctrine, pipeline lines 18–22).

## §5 Rollout & rollback

- **Apply order:** (1) land the script via this WO (pure-new file);
  (2) operator applies §2 YAML to monorepo `.github/workflows/`; (3) operator
  sets `vars.STUDIO_CORS_ORIGINS` if preflights are wanted; (4) gateway
  handler fix (D2) lands operator-side; (5) probe flips green — that flip is
  the acceptance event for D2.
- **Rollback:** drop the two new files (git rm + commit); the §2 YAML and D2
  handler change are operator-side artifacts, removable independently. No
  existing-path hunks, no workflow changes ship in THIS payload.

## §6 Known limitations (honesty ledger)

- No live-call verification of a healthy gateway is possible at build time
  (it is down — §1.1); nothing in this payload claims a green probe.
- The registered Studio origins list is not visible publicly; CORS checks
  default to skipped rather than guessed.
- D1 (tower tool) is intentionally out of scope here (§0) to avoid stacking
  control-plane src orders while the MIRROR-PARITY `bridge.tools.ts` diff is
  still pending operator application.
- The 7-day staleness ceiling is a policy constant, tunable via
  `FRESH_DEPLOY_MAX_AGE_S` — flagged for operator review, not a secret.
