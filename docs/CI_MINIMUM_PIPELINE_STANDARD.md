---
id: ci-minimum-pipeline-standard
title: "Federation Minimum CI/CD Pipeline Standard & Central Nightly Architecture (#612)"
document_role: plan
status: active
canonical: true
owner: coder
last_verified: 2026-10-17
source_issue: 612
related_docs:
  - AGENTS.md
  - AGENT_RULES.md
  - docs/S12_NIGHTLY_TRAIN_SPEC.md
  - docs/FEDERATED_CI_WATCHER.md
  - docs/OPS_ACTIONS_QUOTA_RUNBOOK.md
  - docs/INGRESS_SECURITY_POLICY.md
  - .github/workflows/pipeline.yml
supersedes: []
superseded_by: []
---

# Federation Minimum CI/CD Pipeline Standard (#612)

> **Plan deliverable (task_type: PLAN).** This document is the normative
> standard for the "Minimum Viable Satellite Pipeline" and the central
> nightly architecture across the 14-repo SupremeAI federation.
> Workflow file materialization is intentionally **out of lane** for
> zero-credential agents — `.github/` is a bridge-protected path
> (`docs/INGRESS_SECURITY_POLICY.md` / bridge contract
> `protectedPathsToAdminReview`). The reusable template is embedded
> below for copy-exact landing by an authorized contributor
> (Pathway 2 fork + PR) or an admin-gated bridge order.

## 1. Problem (from #612 audit, verified premises)

| Gap | Repos | Evidence basis |
|---|---|---|
| Empty satellites (0 commits, no default branch) | `skills`, `vscode`, `browser` | #573 audit; seeds now landed in this repo and shipped via bridge orders #613/#615/#617/#619 (PRs #614/#616/#618/#620) |
| Code present, zero workflows | `command`, `core`, `sdk`, `mcp-control-plane` | #612 organizational audit (satellite CI status unverifiable by zero-credential agents — GitHub API rate limit; recorded as NOT_VERIFIED per U2) |
| Failing / fragile pipelines | `studio`, `infrastructure` | Watchdog-issued P0 issues #597–#608 |
| Deploy flakiness on `Deploy Train` | `supremeai` (monorepo) | Render `update_failed` during container startup (missing migration preflight) |
| Shared quota risk | federation-wide | 2,000 min/mo Free-org budget (`docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`) |

## 2. The Minimum Viable Satellite Pipeline (MVP-CI)

Every satellite repository runs one standardized, lightweight workflow on
`pull_request` + `push` with a **hard wall-clock budget of 60 seconds**
(#612 acceptance criterion 2) and **zero external service dependencies**.

### 2.1 Job graph and budgets

| # | Job | Budget | Function | Reuses |
|---|---|---|---|---|
| 1 | `metadata-guard` | ~2s | Branch naming (`contributor/*`, `bridge/*`) + issue-reference regex, event-context only (no checkout) | mirrors `branch-naming-guard` + `issue-reference-guard` jobs of this repo's `pipeline.yml` |
| 2 | `secret-scan` | ~5s | Gitleaks scan of the diff; documentation leaks count too | composite action `.github/actions/gitleaks-scan` |
| 3 | `language-verify` | ~15–30s | Per-language fast tier (table §2.2) | composite action `.github/actions/setup-node-tower` (TS repos) |
| 4 | `failure-ingress` | on-failure | Reports the broken run to `Supremeai-bd/supremeai-open` as an actionable issue | composite action `.github/actions/report-ci-failure` — **already landed here; satellites copy it** |

Failure semantics: jobs 1–2 are fail-closed guards; job 3 fails on
verification errors only; job 4 never blocks (ingress-only,
`if: failure()`), it fan-outs the failure so the
`docs/FEDERATED_CI_WATCHER.md` (#199) normalizer can queue repair work.

### 2.2 Language-specific fast tier (job 3)

| Stack | Repos | Commands (fail-fast order) |
|---|---|---|
| TypeScript/Node | `studio`, `mcp-control-plane`, `sdk`, `vscode` | `npm ci` → `npm run typecheck` → `npm run build` (or lint when no build script) |
| Python | `command`, `browser`, `agents`, `core` | stdlib py_compile sweep, then ruff check (config-optional), then pytest tests/smoke (skip tier if absent) |
| Docs-only | any repo, docs-only diff | jobs 1–2 only; job 3 skipped (path filter `<docs>/**`, `**/*.md`) — secrets scanning still runs |

### 2.3 Reusable template (copy-exact for authorized landing)

`pipeline.satellite.yml` — a `workflow_call` + `pull_request` + `push`
reusable workflow. Satellites pin it via `uses:
Supremeai-bd/supremeai-open/.github/workflows/pipeline.satellite.yml@main`
after Phase 1 lands it here (single SSOT, drift-checked by the nightly
parity scan §3.3):

```yaml
name: CI — Satellite Minimum Pipeline
on:
  workflow_call:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  metadata-guard:
    runs-on: ubuntu-latest
    steps:
      - name: Branch naming + issue reference (event-context, zero checkout)
        run: |
          BRANCH="${GITHUB_HEAD_REF:-${GITHUB_REF_NAME}}"
          echo "$BRANCH" | grep -Eq '^(contributor|bridge)/[a-z0-9._-]+$' \
            || { echo "::error::branch '$BRANCH' violates naming contract"; exit 1; }
  secret-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Gitleaks
        uses: Supremeai-bd/supremeai-open/.github/actions/gitleaks-scan@main
  language-verify:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Fast verification (Python sweep shown; TS repos swap for setup-node-tower)
        run: |
          find . -name '*.py' -not -path './.git/*' -print0 \
            | xargs -0 -n1 python -m py_compile
  failure-ingress:
    needs: [metadata-guard, secret-scan, language-verify]
    if: failure()
    runs-on: ubuntu-latest
    steps:
      - name: Report CI failure to supremeai-open
        uses: Supremeai-bd/supremeai-open/.github/actions/report-ci-failure@main
```

> **Boundary note (U2 honesty):** this template is embedded, not landed —
> `.github/` writes require an authorized lane (fork + PR by a credentialed
> contributor, or an admin-approved bridge order). Zero-credential agents
> must not attempt it.

## 3. Central Nightly & Render Deploy Preflight (`Supremeai-bd/supremeai`)

Heavy, cross-repository, and end-to-end workloads are consolidated into a
single nightly suite on the monorepo — **never** on satellite PRs
(quota doctrine, AGENTS.md §2.3.2 shift-left de-duplication).

### 3.1 Relationship to the landed nightly spec (S12)

`docs/S12_NIGHTLY_TRAIN_SPEC.md` (#492) is the **landed, tested** nightly
contract: hub-and-spoke consolidation, 4-phase order gate
(INGRESS → HEAVY_VERIFY → LANDING → TELEMETRY), cron `0 0 * * *` UTC.

#612 proposes nightly at `02:00 UTC`. **This plan does not silently
override S12** (AGENT_RULES §8: task docs must not silently contradict
the constitution). Resolution options for the operator:

- **Keep `0 0 * * *`** (default; S12 parity tests already pin it), or
- **Move to `0 2 * * *`** via a single `ADMIN_DECISION` issue that
  updates S12 + `nightly_train_reference.py` + parity tests together.

No satellite-side change is needed either way; only the monorepo cron
entry differs.

### 3.2 Render Deploy Preflight (fail-closed deploy guard)

New gate inside `Deploy Train`, before the Render build/deploy trigger.
Order is mandatory; any check failing blocks rollout:

1. **Migration preflight** — `alembic check` (drift) then
   `alembic upgrade head` verification against a shadow database;
   pending migrations ⇒ block (prevents `update_failed` on missing
   tables/columns such as `decision_metadata`, `client_slots`).
2. **Environment & secrets preflight** — presence + freshness probes for
   `UPSTASH_REDIS_REST_URL`, `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `INFISICAL_TOKEN`; values are never printed (mask-on-error policy,
   `infrastructure/mcp-control-plane/src/lib/masking.ts`).
3. **Live endpoint health pre-check** — current production endpoints
   respond 2xx before a new version is switched in; a red baseline
   blocks deploy (never swap into an unhealthy fleet).

Deliverable shape: `scripts/deploy/render_deploy_preflight.py`
(monorepo-side, stdlib-only, exit-code contract 0/1) invoked as the
first step of the `deploy-train` workflow.

### 3.3 Nightly suite workloads

| Workload | Purpose | Evidence surface |
|---|---|---|
| Federation Integration Check (§21) | schema/contract drift across 14 repos (`api-schemas/`, `sdk/`) | existing `federation-integration.yml` logic, now nightly-scoped |
| Satellite CI coverage audit | every active repo reports a non-empty workflow set (MVP-CI §2) | `workflow-coverage-report.json` artifact |
| Quota & heartbeat rollup | Actions minutes + Upstash Redis quota + agent liveness | `docs/OPS_ACTIONS_QUOTA_RUNBOOK.md` format |
| Parity verification | S12 phase-3 parity records; DRIFT/MISSING → isolated-commit P0 incidents | S12 §3 |

## 4. Failure ingress — no new mechanism

Acceptance criterion "CI failures across any repository automatically emit
an issue ticket on `supremeai-open`" is **already implemented** by the
Federated CI Failure Watcher (#199) + the `federation-ci-mirror` job +
`report-ci-failure` action. This standard adds **no second mechanism**
(U6/§14 anti-duplication): satellites adopt the existing composite action
via the MVP-CI `failure-ingress` job, and watchdog-generated issues keep
the `handoff:coder` / P-label taxonomy used by #597–#608.

## 5. Execution roadmap (authority-mapped)

| Phase | Scope | Repo | Deliverable | Lane |
|---|---|---|---|---|
| 1 · Standardize | MVP-CI template landed as `pipeline.satellite.yml` | `supremeai-open` | workflow file from §2.3 | **authorized lane** (`.github/` protected) |
| 2 · Zero-to-One CI | MVP-CI wired into 4 silent repos | `command`, `core`, `sdk`, `mcp-control-plane` | per-repo `pipeline.yml` callers | authorized lane per repo |
| 3 · Empty-repo bootstrap | baseline structure + CI on first landing | `skills`, `vscode`, `browser` | seed content (already shipped via #613/#615/#617) + workflow caller | bridge (code seeds) + authorized (workflows) |
| 4 · Nightly + preflight | deploy guard + consolidated cron | `supremeai` | `render_deploy_preflight.py` + `nightly-federation.yml` | private monorepo lane + `ADMIN_DECISION` for any cron change (§3.1) |

Phases 1–2 are prerequisites for the #612 acceptance checkboxes 1–2;
phase 4 covers checkboxes 3 and 5; checkbox 4 needs no new work (§4).

## 6. Quota impact statement

| Surface | Before | After (per #612) |
|---|---|---|
| Satellite PR run | 0–∞ min (unvalidated or heavy) | ≤ 1 min wall-clock, ~2 actions minutes |
| Cross-repo integration | per-PR (some repos) | nightly-only, monorepo-hosted |
| Projected monthly budget | at risk of exceeding 2,000 min | bounded: `14 repos × PR volume × ≤1 min + 1 nightly ≈ 60 min/night ceiling` |

Detailed budget ledger lives in `docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`;
this standard defers to it and adds only the per-run ceiling contract.

### 6.1 The default-360 trap (job-level wall-clock)

GitHub-hosted runners impose a **360-minute default job timeout** when a job
omits `timeout-minutes` — one hung `npm ci` under `strategy.fail-fast: false`
can burn up to 12 runner-hours against the 2,000 min/mo Free-org budget
(#3386/R82 receipt: 4 of 22 `pipeline.yml` jobs shipped without a pin). Every
new job that declares `runs-on` MUST carry an explicit `timeout-minutes` pin
matching its budget row above. `scripts/ci/pipeline_timeout_guard.py`
(option B, #3386) enforces this mechanically: baseline mode fails on any
unpinned job beyond the R82 known-gap list; `--strict` (flip after the
admin-lane pins land) keeps the zero state permanent.

## 7. Acceptance traceability (#612)

- [x] Standard defined for all 14 repos (this document, §2/§3/§5)
- [ ] Workflow files materialized (phases 1–2 — authorized lane, §5)
- [ ] Satellite PR runtime ≤ 60 s (contract §2; verified at phase-2 landing)
- [ ] Render Deploy Preflight armed (phase 4, §3.2)
- [ ] Failure ingress universal (already implemented, §4 — verify per-repo adoption at phase 2)
- [ ] Nightly runs without admin intervention (phase 4, §3.3)

## 8. Related Documents

- [AGENTS.md](../AGENTS.md) — agent entrypoint; §2.3.2 shift-left de-duplication doctrine
- [AGENT_RULES.md](../AGENT_RULES.md) — §13 quota/cost fail-closed policy
- [S12 — Nightly Train Spec](./S12_NIGHTLY_TRAIN_SPEC.md) — landed nightly consolidation contract
- [Federated CI Failure Watcher](./FEDERATED_CI_WATCHER.md) — failure→issue ingress (#199)
- [Ops Actions Quota Runbook](./OPS_ACTIONS_QUOTA_RUNBOOK.md) — shared quota ledger
- [Ingress Security Policy](./INGRESS_SECURITY_POLICY.md) — protected-path rationale
