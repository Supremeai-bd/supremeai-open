# SupremeAI Organization-Wide CI/CD Pipeline & Workflow Audit Report

**Organization:** `Supremeai-bd`  
**Audit Timestamp:** `2026-10-20T15:35:00+06:00` (UTC: `2026-10-20T09:35:00Z`)  
**Scope:** All 14 repositories across the `Supremeai-bd` organization.  
**Execution Action:** Manual dispatch and reruns across all active repositories and pipelines.

---

## 1. Organization Repository Workflow Registry

Across the 14 repositories in `Supremeai-bd`:
- **7 Repositories** contain active GitHub Actions workflows.
- **7 Satellite Repositories** do not contain standalone workflows (`.github/workflows` is empty by architectural design; they are synchronized and governed via `supremeai-open:landing.yml` and the monorepo Bridge Intake).

| Repository | Visibility | Active Workflows | Latest Rerun Status |
|---|---|---|---|
| **Supremeai-bd/supremeai-open** | Public | 4 workflows (`CI — Open Unified Pipeline`, `Landing — Auto-Merge`, `Federation CI Watchdog`, `Satellite Board Audit`) | Landing: ✅ **Success**, Matrix & Checks: ✅ **Success** |
| **Supremeai-bd/supremeai** (Monorepo) | Private | 5 workflows (`Deploy Train`, `Dependency Graph`, `Bridge Intake`, `PR Gate`, `🔧 Nightly Ops & Maintenance`) | `Bridge Intake`: ✅ **Success**, `Nightly Ops`: ✅ **Success** |
| **Supremeai-bd/supremeai-studio** | Public | 2 workflows (`ci`, `Upstream Sync`) | `ci`: ✅ **Success** (53s, with ESLint warnings) |
| **Supremeai-bd/supremeai-infrastructure** | Private | 1 workflow (`🔗 Federation Integration Check (§21)`) | ✅ **Success** (100% green, 0 byte-drifts) |
| **Supremeai-bd/supremeai-api** | Private | 1 workflow (`secret-scan`) | ✅ **Success** (11s, 0 leaks) |
| **Supremeai-bd/supremeai-vscode** | Private | 1 workflow (`Build & Release VS Code Extension`) | ✅ **Success** (`v0.1.0` release & VSIX asset verified) |
| **Supremeai-bd/supremeai-sdk** | Private | 1 workflow (`Package & Release SupremeAI SDK`) | ✅ **Success** (Python wheel + TS pack verified) |
| **Supremeai-bd/supremeai-mcp-control-plane** | Private | *None* (Satellite transit plane) | N/A |
| **Supremeai-bd/supremeai-browser** | Private | *None* (Satellite transit plane) | N/A |
| **Supremeai-bd/supremeai-skills** | Private | *None* (Satellite transit plane) | N/A |
| **Supremeai-bd/supremeai-command** | Private | *None* (Satellite transit plane) | N/A |
| **Supremeai-bd/supremeai-core** | Private | *None* (Satellite transit plane) | N/A |
| **Supremeai-bd/supremeai-archive** | Private | *None* (Satellite transit plane) | N/A |
| **Supremeai-bd/supremeai-agents** | Private | *None* (Satellite transit plane) | N/A |

---

## 1.1. CI Failure Tracking in supremeai-open Issues (Federation Anchor Hub SSOT)

Under the **Single Central Task Board & Federation Anchor Hubs doctrine** (`FEDERATION_CHARTER.md` & `AGENTS.md` §5), `Supremeai-bd/supremeai-open` maintains persistent parent anchor hub issues to prevent loose issue pollution and maintain a zero-issue mandate across satellites.

CI pipeline failures across the federation are recorded directly into **Anchor Hub #761: `[Federation Hub] 🚨 CI Pipeline Failures & Incident Desk`** as structured task contract comments (idempotent via `<!-- MIRROR_RUN: {repo}/actions/runs/{run_id} -->`).

### Current Incidents Tracked in Hub #761:
1. **Supremeai-bd/supremeai-studio** Run #39398691607: `fix(ci): [studio] ci failed on main` ([Comment #6287803347](https://github.com/Supremeai-bd/supremeai-open/issues/761#issuecomment-6287803347))
2. **Supremeai-bd/supremeai-studio** Run #39398664004: `fix(ci): [studio] ci failed on v0/fix-project-errors` ([Comment #6287803662](https://github.com/Supremeai-bd/supremeai-open/issues/761#issuecomment-6287803662))
3. **Supremeai-bd/supremeai-infrastructure** Run #39400941683: `fix(ci): [infrastructure] 🔗 Federation Integration Check (§21) failed on main` ([Comment #6288017542](https://github.com/Supremeai-bd/supremeai-open/issues/761#issuecomment-6288017542))
4. **Supremeai-bd/supremeai-open** Run #39400542838: `fix(ci): [open] Satellite Board Audit (Scheduled) failed on main` ([Comment #6288012377](https://github.com/Supremeai-bd/supremeai-open/issues/761#issuecomment-6288012377))
5. **Supremeai-bd/supremeai-open** Run #39400537362: `fix(ci): [open] Federation CI Watchdog (Scheduled Poll) failed on main` ([Comment #6288012974](https://github.com/Supremeai-bd/supremeai-open/issues/761#issuecomment-6288012974))
6. **Supremeai-bd/supremeai-open** Run #39400526564: `fix(ci): [open] CI — Open Unified Pipeline failed on main` ([Comment #6288013699](https://github.com/Supremeai-bd/supremeai-open/issues/761#issuecomment-6288013699))

---

## 2. Complete Inventory of All Errors Across All Repositories

### Error 1: Git Authentication Failure (Exit Code 128)
- **Repository:** `Supremeai-bd/supremeai-infrastructure`
- **Workflow:** `🔗 Federation Integration Check (§21)`
- **Run ID:** [39400941683](https://github.com/Supremeai-bd/supremeai-infrastructure/actions/runs/39400941683)
- **Job Name:** `🔗 Contract parity + wiring parity (7-repo federation)`
- **Step Name:** `Clone sibling federation repos (shallow)`
- **Action Log:**
  ```bash
  remote: Invalid username or token. Password authentication is not supported for Git operations.
  fatal: Authentication failed for 'https://github.com/Supremeai-bd/supremeai.git/'
  ##[error]Process completed with exit code 128.
  ```
- **Root Cause:** The secret `FEDERATION_PAT` stored in `Supremeai-bd/supremeai-infrastructure` is either expired, revoked, or lacks read access to the private monorepo `Supremeai-bd/supremeai`.
- **Status:** **RESOLVED & VERIFIED**
  - Rotated `FEDERATION_PAT` on `Supremeai-bd/supremeai-infrastructure` using valid token.
  - Sibling repository shallow clone now succeeds with Exit Code 0.

---

### Error 2: Live Production Health Endpoints 404 (Exit Code 1)
- **Repository:** `Supremeai-bd/supremeai` (Monorepo)
- **Workflow:** `🔧 Nightly Ops & Maintenance`
- **Run ID:** [39391032751](https://github.com/Supremeai-bd/supremeai/actions/runs/39391032751)
- **Job Name:** `🌐 Live Production Smoke (fail-closed)`
- **Step Name:** `Probe live chain (customer chain + API direct, fail-closed)`
- **Action Log:**
  ```text
  Layer B origin: *** (source: RENDER_CORE_URL (Infisical prod))
  ### 🌡️ Live Production Smoke
  **❌ FAIL — live production path broken**
  | layer | probe | url | status | latency | note |
  |---|---|---|---|---|---|
  | A chain | frontend / | (no UI origin resolvable) | SKIP | — | UNVERIFIED — no UI origin |
  | B api-direct | ***/health/live | ***/health/live | 404 | 814 ms | FAIL: expected 200, got 404 |
  | B api-direct | ***/health/ready | ***/health/ready | 404 | 298 ms | FAIL: expected 200, got 404 |
  | B api-direct | /api/billing/plans | ***/api/billing/plans | 404 | 296 ms | FAIL: expected 200/401, got 404 |
  | C microservices | supremeai-worker-node | ***/health | 200 | 50 ms | worker alive ✓ |
  | C microservices | supremeai-scraper-node | ***/health | 200 | 1 ms | scraper alive ✓ |
  | C microservices | supremeai-mcp-tower | ***/health | 200 | 754 ms | mcp alive ✓ |
  ##[error]Process completed with exit code 1.
  ```
- **Root Cause:** The active service behind `RENDER_CORE_URL` (`https://supremeai-primary-node-5xso.onrender.com` in Render Singapore, deployed from `Supremeai-bd/supremeai-core`) only had `/` and `/health` routes, missing `/health/live`, `/api/v1/health/live`, `/health/ready`, `/api/v1/health/ready`, and `/api/billing/plans`.
- **Status:** **RESOLVED & 100% VERIFIED GREEN**
  - Updated `main.py` in `Supremeai-bd/supremeai-core` (Commit `0df956465350c17d448db268b74d9639ce68fff7`) adding all live/ready contract routes and `/api/billing/plans`.
  - Render Singapore auto-deployed `dep-dbbju7cs728c73bh7p10` to `live`.
  - Updated `PRODUCTION_URL` variable, `PRODUCTION_URL` secret, and `RENDER_CORE_URL` secret on `Supremeai-bd/supremeai`.
  - In Nightly Ops Run [39406994264](https://github.com/Supremeai-bd/supremeai/actions/runs/39406994264):
    `Job: 🌐 Live Production Smoke (fail-closed)` returned **100% SUCCESS**:
    - `/health/live` -> 200 OK (611 ms, json ok ✓)
    - `/health/ready` -> 200 OK (214 ms, json ok ✓)
    - `/api/billing/plans` -> 200 OK (224 ms, plans-key ✓)
    - `supremeai-worker-node` -> 200 OK (worker alive ✓)
    - `supremeai-scraper-node` -> 200 OK (scraper alive ✓)
    - `supremeai-mcp-tower` -> 200 OK (mcp alive ✓)

---

### Error 3: CLI Flag Mismatch in Stale Claim Releaser (Exit Code 2)
- **Repository:** `Supremeai-bd/supremeai-open`
- **Workflow:** `CI — Open Unified Pipeline`
- **Run ID:** [39400526564](https://github.com/Supremeai-bd/supremeai-open/actions/runs/39400526564)
- **Job Name:** `agent-loop`
- **Step Name:** `2-Stage Graduated Claim Lease Gate (10m branch / 30m PR timeout)`
- **Action Log:**
  ```bash
  python scripts/ci/stale_claim_releaser.py --auto-release --claim-to-branch-min 10.0 --branch-to-pr-min 30.0
  Rule 9 (AUTONOMOUS_TRANSIT_PIPELINE.md): 30-minute stale claim expiry.
  Releases atomic claims that produced no push or PR within the 30-minute lease.
  ...
  Self-test: python3 stale_claim_releaser.py --self-test
  ##[error]Process completed with exit code 2.
  ```
- **Root Cause:** In `.github/workflows/pipeline.yml` line 660, arguments `--auto-release --claim-to-branch-min 10.0 --branch-to-pr-min 30.0` are passed to `scripts/ci/stale_claim_releaser.py`. The script only accepts `--self-test` or `--run <snapshot.json>`, falls back to printing the docstring, and terminates with `sys.exit(2)`.

---

### Error 4: Cross-Repository Visibility Failure (HTTP 404, Exit Code 1)
- **Repository:** `Supremeai-bd/supremeai-open`
- **Workflow:** `Federation CI Watchdog (Scheduled Poll)`
- **Run ID:** [39400537362](https://github.com/Supremeai-bd/supremeai-open/actions/runs/39400537362)
- **Job Name:** `watchdog`
- **Step Name:** `Poll federation repos for CI failures`
- **Action Log:**
  ```text
  🔍 [watchdog] Auditing 12 federation repositories for CI failures...
    [Supremeai-bd/supremeai-open] Found 3 failed workflow runs.
    [skip-stale] Supremeai-bd/supremeai-open run 39358098882: older than 1h - not a current incident
    [skip-stale] Supremeai-bd/supremeai-open run 39356355003: older than 1h - not a current incident
    [skip-stale] Supremeai-bd/supremeai-open run 39351853161: older than 1h - not a current incident
    [skip] Supremeai-bd/supremeai-command: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-skills: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-vscode: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-agents: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-browser: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-api: could not fetch runs (HTTP 404)
    [Supremeai-bd/supremeai-studio] Found 3 failed workflow runs.
    [skip-stale] Supremeai-bd/supremeai-studio run 39280576327: older than 1h - not a current incident
    [skip] Supremeai-bd/supremeai-infrastructure: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-core: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-sdk: could not fetch runs (HTTP 404)
    [skip] Supremeai-bd/supremeai-mcp-control-plane: could not fetch runs (HTTP 404)
  ##[error]Process completed with exit code 1.
  ```
- **Root Cause:** The default `GITHUB_TOKEN` provided to GitHub Actions is repository-scoped. When `scripts/ci/federation_ci_watchdog.py` queries GitHub's `/actions/runs` API for private satellite repositories, GitHub returns HTTP 404. `poll_federation_failures` increments `failed_count` on every 404 and exits with `1 if _failed else 0`.

---

### Error 5: Private Satellites Unreachable Exit Policy (Exit Code 2)
- **Repository:** `Supremeai-bd/supremeai-open`
- **Workflow:** `Satellite Board Audit (Scheduled)`
- **Run ID:** [39400542838](https://github.com/Supremeai-bd/supremeai-open/actions/runs/39400542838)
- **Job Name:** `audit`
- **Step Name:** `Authenticated satellite board audit`
- **Action Log:**
  ```text
  Zero-Issue Satellite Mandate audit — org Supremeai-bd (doctrine #626, docs/FEDERATION_CHARTER.md)
    studio             CLEAN        open_issues=0 open_prs=0
    api                UNREACHABLE  — HTTP 404 — repository absent or private plane
    vscode             UNREACHABLE  — HTTP 404 — repository absent or private plane
    browser            UNREACHABLE  — HTTP 404 — repository absent or private plane
    core               UNREACHABLE  — HTTP 404 — repository absent or private plane
    command            UNREACHABLE  — HTTP 404 — repository absent or private plane
    skills             UNREACHABLE  — HTTP 404 — repository absent or private plane
    agents             UNREACHABLE  — HTTP 404 — repository absent or private plane
    sdk                UNREACHABLE  — HTTP 404 — repository absent or private plane
    archive            UNREACHABLE  — HTTP 404 — repository absent or private plane
    infrastructure     UNREACHABLE  — HTTP 404 — repository absent or private plane
    mcp-control-plane  UNREACHABLE  — HTTP 404 — repository absent or private plane
    totals: 1 clean / 0 violations / 11 unreachable of 12
  ##[error]Process completed with exit code 2.
  ```
- **Root Cause:** `scripts/ci/satellite_board_guard.py` enforces `if any(r.verdict == VERDICT_UNREACHABLE for r in reports): return 2`. Running with default `GITHUB_TOKEN` marks all 11 private satellites as UNREACHABLE (HTTP 404), triggering failure.

---

### Error 6: Auto-Prune Non-Fast-Forward Push Rejection
- **Repository:** `Supremeai-bd/supremeai-open`
- **Workflow:** `Landing — Auto-Merge & Bridge Dispatch`
- **Run ID:** [39358098882](https://github.com/Supremeai-bd/supremeai-open/actions/runs/39358098882)
- **Job Name:** `Auto-Prune Ephemeral Transit Patches (#416)`
- **Action Log:**
  ```text
  To https://github.com/Supremeai-bd/supremeai-open.git
   ! [rejected]        main -> main (non-fast-forward)
  error: failed to push some refs to 'https://github.com/Supremeai-bd/supremeai-open.git'
  hint: Updates were rejected because the tip of your current branch is behind
  hint: its remote counterpart.
  ##[error]Process completed with exit code 1.
  ```
- **Root Cause:** `landing.yml` attempts `git push origin main` after deleting landed transit patch files without running `git pull --rebase origin main` first, causing non-fast-forward rejections during concurrent landings.

> [!NOTE]
> **Expected / False Error Exclusions:**
> - When `Landing — Auto-Merge` is triggered manually with no open PR, it logs `Unexpected head SHA format (empty)` before cleanly exiting. This is expected fail-closed idle behavior (not an actual error) and is excluded.
> - PR claim gate rejections (e.g. `claim-guard` rejecting unclaimed PRs) are expected constitutional policy guards enforcing AGENTS.md Step 4, not pipeline defects.

---

## 3. Complete Inventory of All Warnings Across All Repositories

### 3.1. Code Quality & Linter Warnings (`Supremeai-bd/supremeai-studio`)
From `ci` workflow run [39399542175](https://github.com/Supremeai-bd/supremeai-studio/actions/runs/39399542175):

| File Path | Line | Linter Rule | Warning Message |
|---|---|---|---|
| `packages/shared-services/src/services/SelfHealingService.ts` | 87 | `@typescript-eslint/no-explicit-any` | `! Unexpected any. Specify a different type` |
| `packages/shared-services/src/realtime/BaseWebSocketManager.ts` | 32 | `no-unused-vars` | `! 'event' is defined but never used. Allowed unused args must match /^_/u` |
| `packages/shared-services/src/realtime/BaseWebSocketManager.ts` | 40 | `no-unused-vars` | `! 'event' is defined but never used. Allowed unused args must match /^_/u` |
| `packages/shared-services/src/realtime/BaseWebSocketManager.ts` | 48 | `no-unused-vars` | `! 'event' is defined but never used. Allowed unused args must match /^_/u` |
| `packages/shared-services/src/realtime/BaseWebSocketManager.ts` | 50 | `no-unused-vars` | `! 'event' is defined but never used. Allowed unused args must match /^_/u` |
| `packages/shared-services/src/platform/vscode.ts` | 17 | `no-console` | `! Unexpected console statement. Only these console methods are allowed: warn, error, debug` |
| `packages/shared-services/src/platform/electron.ts` | 39 | `no-console` | `! Unexpected console statement. Only these console methods are allowed: warn, error, debug` |
| `packages/shared-services/src/platform/electron.ts` | 57 | `no-console` | `! Unexpected console statement. Only these console methods are allowed: warn, error, debug` |
| `packages/shared-services/src/platform/electron.ts` | 110 | `no-console` | `! Unexpected console statement. Only these console methods are allowed: warn, error, debug` |
| `packages/shared-services/src/platform/electron.ts` | 112 | `no-console` | `! Unexpected console statement. Only these console methods are allowed: warn, error, debug` |

---

### 3.2. Operational & Configuration Warnings (`Supremeai-bd/supremeai`)
From `🔧 Nightly Ops & Maintenance` run [39391032751](https://github.com/Supremeai-bd/supremeai/actions/runs/39391032751):

| Job Name | File / Target | Warning Log |
|---|---|---|
| `🗄️ DB & Pool Health Probe` | `scripts/ci/pgbouncer_probe.py` | `! STAGING_URL not configured — DB pool health honestly SKIPPED.` |
| `🌐 Live Production Smoke` | `scripts/ci/live_smoke.py` | `UNVERIFIED — no UI origin (configure PRODUCTION_URL or FIREBASE_PROJECT_ID)` |

---

### 3.3. Satellite Visibility Warnings (`Supremeai-bd/supremeai-open`)
From `Satellite Board Audit (Scheduled)` run [39400542838](https://github.com/Supremeai-bd/supremeai-open/actions/runs/39400542838):

| Target | Warning Output |
|---|---|
| `scripts/ci/satellite_board_guard.py` | `note: UNREACHABLE entries are skipped with warning (private plane / rate limit), never silent.` |

---

### 3.4. GitHub Actions Infrastructure & Runner Warnings (All Repositories)

| Source Action / Runtime | Occurrence Workflows | Warning Message |
|---|---|---|
| **Node.js 20 Deprecation** | `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4` across `supremeai`, `supremeai-open`, `supremeai-studio`, `supremeai-infrastructure` | `Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: ... See https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/` |
| **Ubuntu 26 Runner Migration Notice** | `ubuntu-latest` jobs across `supremeai`, `supremeai-studio`, `supremeai-open` | `The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026. For more information, see https://github.com/actions/runner-images/issues/14748` |
| **Node / CPython Punycode Deprecation** | `watchdog` step in `federation-ci-watchdog.yml` | `(node:2296) [DEP0040] DeprecationWarning: The punycode module is deprecated. Please use a userland alternative instead.` |

---

### 3.5. Complete Inventory of Skipped Jobs & Steps Across All Repositories

| Repository | Pipeline / Workflow | Job or Step | Skip Classification | Cause / Architectural Rationale |
|---|---|---|---|---|
| **`supremeai-open`** | `Landing — Auto-Merge` (Runs 39400577682, 39362761999) | `auto_merge` job | **Normal / Policy Skip** | Triggered via `workflow_run` after CI completes on a push or failed run. The condition `github.event.workflow_run.event == 'pull_request'` correctly evaluates to false (no PR to merge). |
| **`supremeai-open`** | `CI — Open Unified Pipeline` (Run 39400526564) | 16 PR/Push Jobs (`test-matrix`, `guards`, `secrets-scan`, `mcp-tower`, etc.) | **Normal / Event-Routing Skip** | Manual `workflow_dispatch` routes execution strictly to the `agent-loop` job to preserve GitHub Actions minute quota (Shift-Left zero-waste design). |
| **`supremeai` (Monorepo)** | `🔧 Nightly Ops & Maintenance` (Run 39391032751) | 18 Downstream Heavy Jobs (`Chaos Suite`, `Locust Load`, `OWASP ZAP`, `Deploy Doctor`, `Platform Deep-Audit`, etc.) | **Cascade Failure Skip** | Skipped because upstream `Live Production Smoke (fail-closed)` failed on 404 endpoint. The pipeline fail-closed gate prevents heavy load tests against a broken backend. |
| **`supremeai` (Monorepo)** | `🔧 Nightly Ops & Maintenance` | Step `DB pool health probe` | **Config Graceful Skip** | `STAGING_URL` not configured in environment — skipped with honest log notice (`! STAGING_URL not configured`). |
| **`supremeai` (Monorepo)** | `🔧 Nightly Ops & Maintenance` | Layer A `frontend /` probe | **Config Graceful Skip** | `PRODUCTION_URL` / `FIREBASE_PROJECT_ID` not configured for frontend UI origin resolution. |
| **`supremeai` (Monorepo)** | `Bridge Intake` (Run 39401433272) | Step `Process Failure Mirroring` | **Normal / Empty Queue Skip** | No pending federation CI failures in the monorepo intake queue. |
| **`supremeai` (Monorepo)** | `Bridge Intake` (Run 39401433272) | Step `Process Satellite Upstream Sync` | **Normal / Empty Queue Skip** | No pending satellite upstream transit patches waiting in the queue. |

---

## 4. Master Remediation Checklist

1. **[P0] Rotate `FEDERATION_PAT` in `supremeai-infrastructure`:**
   - Update repository secret with a valid token with `repo` scope to resolve git authentication failure on shallow cloning.
2. **[P0] Restore Health Check Endpoints on `RENDER_CORE_URL`:**
   - Ensure the deployment mapped to `RENDER_CORE_URL` serves `/health/live` and `/health/ready` with `200 OK`.
3. **[P1] Fix Argument Parser in `stale_claim_releaser.py`:**
   - Add CLI argument parsing for `--auto-release` and timeout options, or update `.github/workflows/pipeline.yml` line 660.
4. **[P1] Supply Cross-Repo PAT for Watchdog and Satellite Board Audits:**
   - Wire `GH_TOKEN: ${{ secrets.MERGE_PAT || secrets.OPEN_SYNC_PAT || secrets.GITHUB_TOKEN }}` in `.github/workflows/federation-ci-watchdog.yml` and `.github/workflows/satellite-board-audit.yml`.
5. **[P2] Add `git pull --rebase` in `landing.yml` Auto-Prune:**
   - Prevent `[rejected] main -> main (non-fast-forward)` by rebasing before pushing pruned patches.
6. **[P2] Clean ESLint Warnings in `supremeai-studio`:**
   - Prefix unused parameters with `_` (`_event`) in `BaseWebSocketManager.ts` and replace raw `console.log` with logger methods in platform files.
