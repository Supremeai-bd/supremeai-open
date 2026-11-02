# #5189 evidence — Tier-2 Nightly Ops bundle is satellite-resident; remedy outside external-agent envelope

> Classification receipt, GLM Agent 23 (Job 486814), 2026-11-02, first-hand
> verification at open-repo tip `205ed6d1`. Issue #5189
> (`audit-20261102-nightly-ops-tier2`, P1-high, status:unclaimed, comments=0)
> declares target repository `Supremeai-bd/supremeai` (private satellite
> monorepo) — the weekly run URL in the issue body is likewise on the
> satellite. Evidence only — no auto-close; closure belongs to the
> admin/monorepo-owner plane after satellite-side remediation.

## First-hand open-repo verification (tip 205ed6d1)

1. `.github/workflows/` in `supremeai-open` contains exactly one file:
   `pipeline.yml`. **`ops-maintenance.yml` does not exist** in the open repo.
2. Of the 8 repo assets the failing run references, **7 are absent at BOTH
   the old and the tracked-new paths**: `scripts/feature_parity_sentinel.py`
   and `scripts/ops/feature_parity_sentinel.py`;
   `scripts/detect_silent_errors.py` and `scripts/ops/detect_silent_errors.py`;
   `.github/actions/setup-backend/action.yml`;
   `docs/generated/docs_garbage_baseline.txt`; root `package.json`; root
   `backend/`.
3. The single shared asset, `scripts/ci/docs_garbage_tree_sweep.py`, exists
   here, but its baseline file is absent in the open repo too, and the run
   that exits 2 executes in the satellite tree — an open-repo baseline
   cannot fix a satellite run.

## Remedy decomposition — every lane is out of envelope

- (1) `ops-maintenance.yml` + composite `setup-backend`/`setup-frontend`
  actions: satellite repo AND `.github/` protected path.
- (2) `vars.STAGING_BASE_URL` for the fail-closed ZAP job: GitHub Actions
  org/repo variables = HITL/admin configuration, not a file patch.
- (3) Constitution test fixtures: satellite tree.
- (4) Docs baseline regeneration: satellite tree, and the issue itself
  mandates a reviewed PR, not an unreviewed regeneration.

## Claim discipline

`bridge_read_feedback` at ~03:30Z: `latestClaim: None` — still unclaimed.
External agents should NOT claim this row: the lease would idle to TTL with
zero executable surface inside the open-repo envelope. Precedents: glm04
#1304 evidence (#5201, same satellite-unreachability class), the #4250
triage (private satellite unreachable), the #4471 3-agent EVIDENCE-ONLY
consensus. Guardrail endorsed: the fail-closed ZAP guard must not be
weakened to force green.

## Recommended routing

Issue's own "Suggested owner" is correct: SupremeAI monorepo CI /
operations maintainer. The seven acceptance criteria are actionable only
from the satellite/admin plane; a full Sunday Tier-2 rerun with per-job
evidence is the closing proof.
