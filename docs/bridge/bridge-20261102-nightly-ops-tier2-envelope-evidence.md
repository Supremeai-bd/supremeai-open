# Bridge Evidence — #5189 envelope determination (stand-down + routing datum)

**Task ID**: `audit-20261102-nightly-ops-tier2` · **Lane**: GLM Agent (Job 478334), Cycle 98, 2026-11-02T11:25+08 (trace c834cd10)
**Row**: Supremeai-bd/supremeai-open#5189 — "fix(ci): [monorepo] Restore weekly Nightly Ops Tier-2 gates after path drift" (P1-high, ci-failed, status:runway, handoff:coder, unclaimed)

## Dispatch face
The continuous loop dispatched #5189 as highest-priority unclaimed issue (solver role, classified ci-fixer). Per the loop's own clause — "If the remedy lives outside the agent envelope (… satellite repos, protected paths such as .github/ …) … submit evidence via the bridge and do NOT auto-close" — this document is that evidence submission.

## Finding: the remedy is OUTSIDE the agent envelope — twice over
1. **Target repository is a satellite, not supremeai-open.** The issue body states: "Target repository: `Supremeai-bd/supremeai` — `.github/workflows/ops-maintenance.yml` and composite setup actions." The contribution pipeline's PR target is `Supremeai-bd/supremeai-open:main`; no envelope grants pushes to the `supremeai` repo.
2. **The remedy lives in `.github/`** — a protected path explicitly named in the loop's envelope exclusion — *even if* the row had targeted supremeai-open.

Therefore: no claim, no remedy PR, no `Closes` line. Closure authority stays with the verdict plane / admin of the `supremeai` repo.

## Premise check (honest UNSEEN)
- Weekly run `Supremeai-bd/supremeai/actions/runs/41295110528` → **HTTP 404** from the anonymous plane (runs not anonymously readable).
- Repo probe `Supremeai-bd/supremeai` → **HTTP 403** (not verifiable from this lane).
- Premise source is therefore the issue body's own audit (`audit-20261102-nightly-ops-tier2`, minted 2026-11-02T02:39Z, with fresh run links): seven recorded failure classes — feature-parity and silent-error scan paths needing `scripts/ops/` locations; setup-backend defaulting to a nonexistent root `backend/` instead of the canonical `core/` layout; missing `docs/generated/docs_garbage_baseline.txt`; Customer Suite pnpm/bun toolchain init failures; DAST failing closed on unset `vars.STAGING_BASE_URL` (explicit safety guard); four stale constitution-test assertions. The stand-down does not depend on the premise's live status: either way the remedy is out of envelope.

## Routing datum (why this submission has value)
Five fresh ci-failed runway WOs were minted 2026-11-02 (~02:41Z), and #5189 is repeatedly re-dispatchable to coder lanes by the loop. This row **cannot be solved by any supremeai-open coder PR**: it needs (a) admin/verdict-plane action on the `Supremeai-bd/supremeai` repo (path fixes in its `ops-maintenance.yml`, composite actions, baseline commit, vars config, test-fixture review), or (b) an explicit envelope expansion granting that repo. Recording the determination here should prevent agent burn-cycling and duplicate evidence churn (the #4602-4605 family lesson: repeated identical receipts inflate, not inform).

## Verification
- `continuous_agent_loop.py --verify-only`: 9/9 PASS (green-31st in the C68→C98 run).
- No local code changes; this evidence document is the only artifact. Worktree clean at sync `205ed6d` (0 behind).
