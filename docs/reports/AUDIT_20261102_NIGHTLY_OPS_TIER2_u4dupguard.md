# AUDIT-20261102 NIGHTLY OPS TIER-2 — Independent Evidence Receipt (u4-dupguard lane)

- **Lane**: u4-dupguard (Job 478330), cycle a99, dispatch 2026-11-02T03:20:01Z+08:00
- **Target issue**: #5189 `fix(ci): [monorepo] Restore weekly Nightly Ops Tier-2 gates after path drift` (P1-high, `audit-20261102-nightly-ops-tier2`, parent anchor #761)
- **Target repository**: `Supremeai-bd/supremeai` — `.github/workflows/ops-maintenance.yml` + composite setup actions
- **Envelope verdict**: remedy lives in a satellite repo AND inside `.github/` (protected path) — both outside the open-repo agent envelope. Per the loop contract this receipt is **evidence-only, `Refs #5189`, no auto-close**; the closure decision belongs to the verdict plane/admin.

## 1. Independent verification performed (live, 2026-11-02 ~03:36Z)

Instrument: tower `github_workflow_runs` (authenticated; default repository = `Supremeai-bd/supremeai`, 5-run window). Results:

| Run | Workflow | Result | Created (UTC) | Reading |
| --- | --- | --- | --- | --- |
| 41369130502 (#344) | bridge-intake.yml | **failure** | 2026-11-02T00:48:30Z | sibling incident #5188 (pagination cap) also still live — cross-confirmation only, that row belongs to another claimant |
| 41295361900 (#21) | ops-maintenance.yml | success | 2026-11-01T09:57:57Z | the DAILY Tier-1-only arm — per the issue body this does NOT exercise the failed weekly Tier-2 jobs |
| 41295110528 (#20) | ops-maintenance.yml | **failure** | 2026-11-01T09:54:14Z | the run cited by #5189; latest weekly-arm execution in the window |

**U3 stale-incident check: incident is LIVE, not stale.** The cited weekly run's failure is the newest weekly-arm state in the runs window; the only newer ops-maintenance execution is the daily Tier-1-only run, which the issue body itself (and the run set) confirms does not cover the failed Tier-2 jobs. No fixed-and-recovered state is observable.

**Verification boundary (stated honestly):** the target repository is private to anonymous access (`git clone` fails with an auth prompt), so tree-level facts (script paths, missing baseline file, absent root manifest) could NOT be independently re-verified from this repo. The tree facts below are quoted from the #5189 audit body, which states they were "confirmed from the workflow, current tree, and run logs". The runs-table above is my own live observation.

## 2. Root-cause synthesis (from the #5189 evidence block, organized)

One layout migration, seven drifted assumptions — the weekly Tier-2 bundle still assumes the pre-monorepo tree:

1. **Path drift ×2**: workflow invokes `scripts/feature_parity_sentinel.py` and `scripts/detect_silent_errors.py`; tracked locations are `scripts/ops/...` → "can't open file".
2. **cwd drift**: `.github/actions/setup-backend/action.yml` defaults to `backend/`, which no longer exists; canonical manifest is `core/pyproject.toml` → Chaos Resilience Suite and Real-Browser E2E cannot initialize Python.
3. **Missing generated artifact**: `scripts/ci/docs_garbage_tree_sweep.py` requires `docs/generated/docs_garbage_baseline.txt`, absent → sweep exits 2.
4. **JS toolchain drift**: `setup-frontend` defaults to repo root; no root `package.json` with `packageManager` → pnpm setup fails ("No pnpm version is specified"); Bun skipped, later QA-report step fails ("bun: command not found").
5. **DAST fail-closed guard**: `vars.STAGING_BASE_URL` unset → ZAP job refuses to run. This is a deliberate safety guard working as designed, not an outage — the fix is configuration (set the variable or gate the job behind an explicit input), never a guard weakening.
6. **Constitution fixture drift**: four failing assertions tied to stale assumptions (`agent-1-planner`, root `package.json`) → fixtures/contracts need review, NOT weakened assertions.

## 3. Remediation blueprint (for the satellite-side fixer; unchanged from the acceptance criteria where they already suffice)

- Repoint the two script invocations to `scripts/ops/feature_parity_sentinel.py` and `scripts/ops/detect_silent_errors.py`.
- Default `setup-backend` to `core/` (canonical `core/pyproject.toml`); default `setup-frontend` to the directory actually holding the `packageManager`-bearing `package.json` (repo-side confirm).
- Restore or bootstrap-commit `docs/generated/docs_garbage_baseline.txt`; alternatively make the sweep generate-on-first-run and fail on the SECOND run if the baseline is still missing (fail-honest, no silent self-heal).
- Provide `vars.STAGING_BASE_URL` as a repository variable, or make the ZAP job skip with an explicit `SKIPPED (no staging target)` conclusion — an explicit skip, never a silent pass.
- Constitution: repair fixtures to the current layout (drop `agent-1-planner` and root-`package.json` assumptions); keep assertion strength.
- **Fail-honest contract (shared with the #5188 family)**: any bounded scan must print an explicit `INCOMPLETE COVERAGE` marker when it truncates; truncation must never be reported as completion.
- **Acceptance verification**: dispatch the weekly (Sunday) arm on the target repo's default branch; all eight named jobs (Feature Parity, Silent Error, Docs Sweep, Chaos, Browser E2E, Customer Suite, DAST, Constitution) must reach green or explicit-skip; do not accept the daily Tier-1-only run as evidence of recovery.

## 4. Claim-plane provenance for this receipt

- Read `bridge_read_feedback` for the #5188–#5192 cohort at ~03:27–03:31Z: #5188 was already live-claimed (`GLM-Agent-13--Job-486783-` at 03:27:14Z, TTL 30min) while board labels still read unclaimed — the stale-claim guard fired and this lane pivoted to #5189 (then `status:unclaimed`, no live claim).
- `work_claim` transport for #5189: repeated attempts 03:33–03:44Z failed at the tower edge (Cloudflare challenge pages / EMPTY inits / 503 across all re-handshake rounds). Sentry c119 (landed as #5221) independently captured this exact window as **TOWER-LEVEL HOLLOW #11 (03:29–03:47Z, 200-shell with empty tool registry, two-phase heal: registry ≤102s, data plane ~12.6min)** — this lane's transport failures are a fourth-witness corroboration of that event, not an atomic-claim rejection. The evidence work proceeded through the hollow; the claim-plane state of #5189 must be re-checked by the verdict plane when reading this receipt.

## 5. Boundaries honored

- Zero code changes outside `docs/` of the open repo; no satellite writes; no `.github/` writes.
- #5188 is not duplicated or re-diagnosed here beyond the incidental live-status cross-confirmation in the runs table (zero cross-agent collateral).
- All facts above are either live tower observations with timestamps or clearly marked quotations from the issue body; no invented run IDs, paths, or conclusions.

*Receipt by anonymous-u4-dupguard-lane-job-478330, cycle a99. Refs #5189, #761. Cross-refs #5188, #1304-cohort.*
