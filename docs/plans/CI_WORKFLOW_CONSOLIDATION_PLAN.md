---
id: ci-workflow-consolidation-plan
subject: "CI Workflow Consolidation — 38 Workflows → 5 Smart Workflows (Runtime Waste Elimination)"
document_role: architecture
planning_authority: Planning & Audit Circle (Agent-1)
canonical: true
status: implementing
evidence_state: verified_live_api
disposition: retain
last_verified: 2026-09-26
supersedes: []
superseded_by: []
target_scope: supremeai_ci
related_docs:
  - docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md
  - docs/master_docs/OPS-06-MULTI-AGENT-BRANCHING-LIFECYCLE.md
  - docs/agents/AGENT_WORK_BOUNDARIES_CHARTER.md
  - AGENTS.md
source_issue: 1850
---

> **STATUS (2026-09-27, epic #1850 Phase F truth-sync):** historical planning document.
> The final locked architecture (19 workflow files: 6 pipelines + 2 retained + 11
> libraries) landed via epic #1850 — see `integration-gate.yml`, `pr-gate.yml`,
> `nightly-ops.yml`, `ci.yml`, `ops-console.yml`, `issue-ops.yml` for the live state.
> Workflow names referenced below may differ from the final state.

# 🏗️ CI Workflow Consolidation — 38 → 5

> **Status:** `implementing` · **Owner:** Planning & Audit Circle (Agent-1) · **Source:** Issue #1850 (founder directive)
> **Implementation lane:** CI agents (`handoff:ci`) · **Planner boundary:** this document plans; it does not modify workflow files (CRITICAL protected scope).

---

## 1. Executive Summary

The repository runs **38 GitHub workflow files** (~470 KB of YAML) that generated **2,500 workflow runs in the last 7 days** (~10,700/month projected). The workflows have accreted organically — one guard, one watchdog, one suite at a time — until the CI surface itself became the largest source of runtime waste, duplicated work, and dead logic in the repo.

This plan consolidates all 38 files into **5 workflows + a library of composite actions**, cutting run volume by an estimated **70–80%** while making every check **faster** (path filtering, caching, fast-fail staging, event-driven escalation) and preserving every existing guarantee (required checks, environment gates, single-flight merge train, failure-memory re-runs).

**The core insight from live API evidence:** the repo's worst "waste" — sub-hourly cron watchdogs — *already do not work as designed*. `deploy-doctor` is configured `*/5` but actually executes ~5×/day at 4–5 hour gaps (GitHub throttles scheduled runs under load; 41 runs ever). The 5-minute detection it promises is dead in production. Consolidation is therefore not a sacrifice of responsiveness — it is the only way to *actually get* fast detection, via event-driven steps that fire the moment a deploy fails.

---

## 2. Evidence Base (all verified 2026-09-26)

### 2.1 Live GitHub API measurements

| Metric | Value | Source |
|---|---|---|
| Workflow files | 38 (+2 dependabot dynamic) | `.github/workflows/` |
| Runs, last 7 days | **2,500** | `/actions/runs?created=>=` (API total_count) |
| Sampled 1,000 of those runs | 626 wall-clock minutes | same |
| Per-PR-event workflow fan-out | up to **6** | trigger map (§2.2) |
| `deploy-doctor` actual cadence | ~5 runs/day at 4–5h gaps (despite `*/5`) | runs API, all statuses |
| `rate-limit-monitor` actual cadence | ~5/day (despite hourly) | runs API |
| `auto-approve` actual cadence | ~8/day (despite `*/10`) | runs API |
| Queue delay for interactive runs | ~0 min | `run_started_at − created_at` (12-run samples) |

### 2.2 Trigger fan-out map (what one event fires today)

- **One PR update (opened/synchronize/reopened/ready_for_review):** `pr-pipeline` + `branch-naming-guard` + `cross-pr-collision-guard` + `merge-train-rollup` (on label events) + `constitution-governance` (paths: 3) + `e2e-suites` (paths: 3) → **up to 6 workflows, 6 runners, 6 logs**.
- **One push to main:** `ci.yml` (29 jobs) + `artifact-regen` + `auto-update-pr-drift` + `merge-train-rollup` → **4 workflows**. Then `auto-update-pr-drift` PUTs `update-branch` on every behind PR → each becomes a `synchronize` event → re-fires the whole PR storm per PR (CI amplifier).
- **Any of 9 named workflows finishing:** `ci-doctor` fires via `workflow_run` (269 runs to date).

### 2.3 Structural findings (three parallel deep audits, file:line verified)

1. **A typical backend PR costs 8 full checkouts (4 full-history) + 2 complete Poetry installs + 2 service-container pairs — with zero PR-side caching** (`pr-helper` step1 base+head matrix; no cache directives).
2. **Nightly duplicates:** `mission_passk` ×2 jobs = 6 suite executions/night; `pip-audit` ×2 (02:00 `audit-release` + 03:00 deep-audit `auto_vulnerability_scanner`); backend ruff ×2 inside ci.yml (tooling-quality L470 + backend-prepare L669, same ruleset); artifact-drift generators ×3 (advanced-checks gate / artifact-regen heal / ci-doctor auto-fix); health probes ×4 variants.
3. **Dead / vestigial:** `05/06/07-e2e-*.yml` shims (pure pass-throughs, zero callers); `dry-gate.yml` `disabled_manually` **yet still executed via ci.yml `workflow_call`** (live runs 36272820443, 36270676758 — deleting the file without unwiring ci.yml would break every CI run); ci-doctor "Auto-Merge Verified PR" step has an impossible condition (`event_name == 'pull_request'`, no PR path exists); audit-release PR-arm conditions permanently false (no pull_request trigger); 5 workflows expose `workflow_call` with zero callers; `vercel-deploy-preflight` outputs consumed by nobody; `merge-train-rollup` plan job does a **full-history checkout ×72 ticks/day ≈ 1.5–2 runner-hours/day of idle waste**.
4. **Bugs:** `hold:merge-conflict` label used (merge-train-rollup L298) but never created by the label bootstrap → conflicted PRs are not visibly quarantined; merge-train pins `checkout@v5.0.0` while every other workflow uses `v7.0.1` (a documented hosted-runner fix it never received); `pr-pipeline` concurrency group falls back to `github.ref` (concurrent manual dispatches cancel each other); deploy-doctor's comment says "old run cancelled" but `cancel-in-progress: false` queues instead; `deploy_doctor.py` hardcodes Render service IDs (violates zero-hardcode doctrine).
5. **Cross-file contracts (must move in lockstep):** `detect-previous-failures.py` PACKAGE_MAP (job-name patterns), ci-doctor's `workflow_run` 9-name list (exact `name:` matches — the "Scheduled Deep Audit" rename bug precedent is documented in ci-doctor L68), dorny filter sets in ci.yml, branch protection required checks (`Branch Naming Guard`, `🚦 Unified PR Gate (Security, Scope & Policy Orchestrator)`), `security/policies/protected-scopes.yml` CRITICAL gate on `.github/workflows/**`, `regen_all_artifacts.sh` mirror-order contract with ci-advanced-checks.

---

## 3. Current-State Map

**38 files → categories:**

| Category | Count | Files |
|---|---|---|
| PR-triggered | 6 | pr-pipeline, branch-naming-guard, cross-pr-collision-guard, merge-train-rollup (PR arm), constitution-governance (PR arm), e2e-suites (PR arm) |
| Push-main-triggered | 4 | ci, artifact-regen, auto-update-pr-drift, merge-train-rollup (push arm) |
| Scheduled | 13 | scheduled-deep-audit, qa-live-smoke, db-retention, stale-mutex, branch-retention, dast-zap, audit-release (3 crons), rate-limit-monitor, platform-agent-check, deploy-doctor, auto-approve, merge-train-rollup (cron arm), constitution-governance (weekly) |
| Reusable-only (workflow_call) | 11 | ci-deploy-production, ci-docker, ci-mcp-build, ci-advanced-checks, dry-gate, qa-contract, 08-preflight, 09-smoke, staging-deploy, reusable-e2e-runner, (+pr-helper dispatch/call) |
| Manual/dispatch-only | 4 | cors-sync, deploy-firebase-hosting, issue-labeler, (+pr-helper manual arm) |
| Dead shims | 3 | 05-e2e-guest, 06-e2e-customer, 07-e2e-admin |

---

## 4. Target Architecture — 5 Workflows + Composite Actions

### W1 — `pr-gate.yml` · "PR Gate" (absorbs 6)

**Trigger:** `pull_request` [opened, synchronize, reopened, ready_for_review, labeled, unlabeled] → branches [main, develop]. **Concurrency:** `pr-gate-<PR#>`, cancel-in-progress: true (fixes the `github.ref` fallback bug).

```
Stage 0  branch-naming            (NO checkout, ~10 s)   ← job name stays "Branch Naming Guard"
Stage 1  collision-guard ∥ pr-gate-core ∥ e2e-guest
         (checkout+merge-base)     (risk classify,        (paths-filter self-skip:
                                    guardian lite/deep,     frontend/qa only)
                                    dependabot classify,
                                    contract, labels,
                                    merge-train enqueue)
Stage 2  pr-helper lifecycle: guard → step1 matrix ∥ step1.5 learning-guards ∥ step2 audit → step3 delta
         (job name stays "🚦 Unified PR Gate (Security, Scope & Policy Orchestrator)" for the core;
          backend stage self-skips when paths-filter says no backend change)
```

**Guarantees preserved:** required check names byte-identical (branch protection needs no change); draft/fork skip logic; SG-11 self-mod guard set updated in lockstep; merge-train skip condition (#1776) carried on the Stage-2 gate.

**Files deleted:** pr-pipeline.yml, branch-naming-guard.yml, cross-pr-collision-guard.yml, pr-helper.yml + PR arms of constitution-governance.yml & e2e-suites.yml.

### W2 — `main-pipeline.yml` · "Main Pipeline" (absorbs 13)

**Trigger:** `push` [main, develop] (paths-ignore unchanged) + `workflow_dispatch` (force flags preserved). **Concurrency:** cancel-in-progress: true per ref (as today).

Everything ci.yml orchestrates today via `uses:` becomes inline jobs with `needs:` chains — the deploy chain is already 100% `workflow_call` (zero dynamic `gh workflow run` edges), so inlining is mechanical:

```
fast-lane:   changes (dorny) → stub-blocker ∥ plan-governance ∥ constitution-audit ∥ tooling-quality ∥ security → security-gate
backend:     backend-prepare → backend-test-planner → backend-tests (matrix) → backend-aggregate ∥ backend-contract ∥ integration-test
frontend:    frontend-tests → build → deploy-frontend (environment: production)
deploy:      render-preflight → docker (core/scraper/worker-alias/budget-guard) ∥ mcp-build
             → production-deploy (migration-gate → deploy-core/worker/scraper/mcp/cloudflare → db-schema-check → notify-failure)
             → post-deploy-smoke ∥ production-preflight → staging-deploy (STAGING_ENABLED)
quality:     advanced-checks ∥ dry-gate ∥ qa-contract (unchanged logic, inline)
heal:        artifact-regen (NEW: guarded by changes.backend||infra — today it runs on EVERY non-docs push)
             deploy-doctor-on-failure (NEW: if: failure() on deploy jobs — instant classification,
                                       replaces the throttled */5 cron for CI-triggered deploys)
tail:        ci-doctor (inline final job, exactly as ci.yml calls it today) + pr-drift-update
             (rate-limited: only PRs with queue:pending-rollup or >6h stale — kills the CI amplifier)
```

**Files deleted:** ci.yml, artifact-regen.yml, auto-update-pr-drift.yml, ci-deploy-production.yml, ci-docker.yml, ci-mcp-build.yml, ci-advanced-checks.yml, dry-gate.yml, qa-contract.yml, 08-production-preflight.yml, 09-post-deploy-smoke.yml, staging-deploy.yml, ci-doctor.yml (workflow_run arm retired — each workflow gets a doctor tail; scheduled survivors keep one listener, see W3).

### W3 — `nightly-ops.yml` · "Nightly & Weekly Ops" (absorbs 10)

**Trigger:** schedule `0 3 * * *` (nightly core) + weekly crons as separate entries (`30 5 * * 1` dast-zap, `17 3 * * 1` branch-retention, `17 6 * * 1` constitution, `0 3 * * 0` self-audit, `0 4 * * 1` silent-error) + `workflow_dispatch` with per-suite boolean inputs.

```yaml
# Day-guard pattern (established repo convention, audit-release L230/L266/L279):
nightly-core:  if: github.event_name != 'schedule' || github.event.schedule == '0 3 * * *'
dast-weekly:   if: github.event_name != 'schedule' || github.event.schedule == '30 5 * * 1'
```

**Jobs (parallel, no shared DB/mutex conflicts — verified):** deep-audit (deduped) · ai-safety · **pass^k ×1 job** (gate 0.8 + scoreboard 0.7 from one run — today 2 jobs/6 executions) · qa-live-smoke · db-retention · stale-mutex · pip-audit **×1** (today ×2) · e2e-customer (nightly arm) · platform-sweep (3h→nightly; CF Worker keepalive + qa-live-smoke already backstop liveness) · rate-limit trend snapshot · weekly: dast-zap / branch-retention / constitution / self-audit / silent-error.

**Files deleted:** scheduled-deep-audit.yml, qa-live-smoke.yml, db-retention.yml, stale-mutex-cleanup.yml, branch-retention-cleanup.yml, dast-zap.yml, audit-release.yml (cron arms), rate-limit-monitor.yml, platform-agent-check.yml, constitution-governance.yml (weekly arm), (+ deploy-doctor fallback slot: `0 * * * *` hourly with `--window-minutes 90`).

### W4 — `integration-gate.yml` · "Merge Train" (absorbs 2, slimmed)

Kept as its own workflow **by design**: different trigger surface (PR labeled/closed), single-flight `cancel-in-progress: false` semantics that must not share a group with per-PR cancelling, 120-min gate watch. Slimming:

- plan job: `fetch-depth: 1` (script-only job — kills ~1.5–2 runner-hrs/day idle clone), label bootstrap behind `selected_count > 0`, checkout pin fixed to v7.0.1
- **auto-approve watchdog folded** into the tick (same permissions class, actions:write) → one cron instead of two; fix `per_page=100` single-page scan
- cron reduced `*/20` → `*/30` (PR-labeled events are the primary trigger; cron is the missed-event safety net)
- create the missing `hold:merge-conflict` label in bootstrap

**Files deleted:** merge-train-rollup.yml, auto-approve-internal-workflows.yml.

### W5 — `ops-console.yml` · "Ops Console" (absorbs 4, dispatch-only)

**Trigger:** `workflow_dispatch` with `action` string input (`cors-sync | firebase-deploy | issue-ops | deploy-doctor-scan | scraper-ci | release-build`) — GitHub has no choice-type; the enum is documented in the input description. Per-action jobs gated `if: inputs.action == '...'`, each with job-level least-privilege permissions. Bodies extracted to composite actions (`.github/actions/cors-sync`, `firebase-hosting-deploy`, `issue-ops`) so they stay testable and reusable.

**Safety semantics preserved:** cors-sync stays dry-run-default (`apply=true` opt-in); firebase deploy keeps its fail-closed FIREBASE_TOKEN guard; deploy-doctor manual arm keeps `dry_run`/`window_minutes` inputs.

**Files deleted:** cors-sync.yml, deploy-firebase-hosting.yml, issue-labeler.yml, deploy-doctor.yml (manual arm → here; cron arm → event-driven step in W2 + hourly fallback in W3).

### Deleted without absorption

- `05/06/07-e2e-*.yml` shims (zero callers; PR body notes supersession by e2e-suites for Preservation Guard compliance; branch protection verified to not require them)
- `reusable-e2e-runner.yml` → composite action `.github/actions/e2e-suite` (no services, no strategy → composite-compatible)

### Composite actions library (`.github/actions/`)

`setup-backend`, `setup-frontend` (exist today) **+ new:** `resolve-pr-meta`, `guardian-lite`, `dependabot-classify`, `approve-internal-runs`, `pr-comment-upsert`, `render-deploy-status` (NEW: polls deploy to terminal state — the event-driven deploy-doctor primitive), `e2e-suite`, `cors-sync`, `firebase-hosting-deploy`, `issue-ops`. This kills the copy-paste drift documented in §2.3 (branch regex ×2, dependabot classifier ×3, approve loop ×2, PR-meta resolve ×3, comment-upsert ×3, label bootstrap ×3).

---

## 5. Speed Playbook (fast but effective)

| # | Technique | Effect |
|---|---|---|
| 1 | One workflow per event | one bill, one log, no duplicated setup (6→1 on PRs, 4→1 on main) |
| 2 | Stage-0 fast-fail (`needs:` chains, naming check = 0 checkout) | bad branches rejected in ~10 s, before any expensive stage starts |
| 3 | `dorny/paths-filter` on PR side | backend PRs skip frontend stages and vice-versa (today most PR jobs are unfiltered) |
| 4 | Uniform `cancel-in-progress` per PR# | superseded runs die instantly (fixes pr-pipeline's `github.ref` fallback bug) |
| 5 | PR-side caching: Poetry venv, pnpm, Playwright browsers, pip | today: 2 cold Poetry builds per PR (~4–8 min each) → cache hit seconds |
| 6 | Lazy base-leg pytest | run pr-helper step1 base matrix leg only when head fails → halves the most expensive PR job |
| 7 | **Event-driven escalation** | deploy fails → `if: failure()` doctor step fires in seconds (vs 4–5 h actual today); rate-limit → pre-flight step before agent-heavy jobs; auto-approve folded + root-caused (internal pushes use SELF_HEAL_PAT) |
| 8 | Merge-train batching (keep) | N queued PRs tested by ONE CI run — the repo's best anti-burn feature |
| 9 | `fetch-depth` discipline | depth-1 for script-only jobs; full history only where merge-base/diff needs it |
| 10 | Dedupe same-work | ruff ×2→1, pip-audit ×2→1, pass^k 6→3 runs/night, drift generators 3→1 canonical, health probes consolidated |
| 11 | Failure-memory re-runs (keep) | `detect-previous-failures.py` re-runs only previously-failed lanes — smart, keep + PACKAGE_MAP lockstep |
| 12 | Rate-limited PR-drift updates | only `queue:pending-rollup` or >6h-stale PRs → kills the update→synchronize→refire amplifier |

**Projected result:** ~2,500 runs/week → **~550–650/week** (−72–78%); PR-event runs 640→~215; push-main 4→1 per event; scheduled ~504 ticks/day configured → ~40/day (nightly 1 + weekly + W4 `*/30` + hourly deploy fallback); idle clone hours eliminated; per-backend-PR runner cost roughly **halved** (8→3 checkouts, 2→1 Poetry builds via cache, lazy base leg).

---

## 6. Migration Phases (each = 1 issue = 1 branch = 1 PR)

> **Constraint governing every phase:** `.github/workflows/**` is a CRITICAL protected scope (`security/policies/protected-scopes.yml` L45) → every phase PR carries `needs-human-review` by policy. Order = risk-ascending, reward-early.

### P1 — Quick wins & dead-code removal (no architecture change)
- ci.yml: drop one of the duplicate ruff jobs (backend-prepare copy — tooling-quality keeps the centralized gate); delete ci-doctor's impossible auto-merge step + dead test-failure-trend upload; delete backend-contract's dead Infisical staging import; wire or gate vercel-preflight outputs; fix stale "[CI-OPT] Redundant" comment location
- merge-train: create `hold:merge-conflict` in bootstrap; fix checkout pin v5.0.0→v7.0.1; plan job `fetch-depth: 1`; labels behind `selected_count > 0`; fix `github.ref`→`run_id` concurrency fallback in pr-pipeline
- artifact-regen: fix `GITHUB_STEP_SUMMARY_FILE`→`GITHUB_STEP_SUMMARY` bug
- deploy-doctor: fix comment/config contradiction (pick no-cancel + document), move hardcoded service IDs to secrets-only
- **Risk:** minimal (behavior-preserving fixes + deletions of provably-dead code) · **Reward:** idle-clone hours/day + honest states

### P2 — W5 ops-console + shim deletion (dispatch-only, zero branch-protection coupling)
- Build `.github/actions/cors-sync`, `firebase-hosting-deploy`, `issue-ops` + `ops-console.yml`; delete cors-sync.yml, deploy-firebase-hosting.yml, issue-labeler.yml; delete 05/06/07 shims (verify branch protection first — only 2 required contexts exist today, neither is a shim)
- **Risk:** low (manual surfaces only)

### P3 — W3 nightly-ops (biggest scheduled win)
- Merge 10 scheduled workflows with day-guards; dedupe pass^k (6→3) + pip-audit (×2→1); add hourly deploy-doctor fallback slot; platform-agent 3h→nightly; keep per-job concurrency where semantics demand (dast no-cancel)
- **Risk:** low-medium (no required checks; crons are already throttled so observation window is short) · **Reward:** −~700 scheduled runs/week configured; nightly duplicate work halved

### P4 — W4 integration-gate slim + event-driven deploy-doctor
- merge-train slim (P1 items are pre-reqs) + auto-approve fold + cron */30 + `render-deploy-status` composite (poll to terminal state) + `if: failure()` doctor step wired into W2's deploy jobs (can land as a ci.yml patch before W2 exists — the composite is forward-compatible)
- **Risk:** medium (touching the merge train — must be landed on a quiet queue day; rollback = revert one PR)

### P5 — W2 main-pipeline (largest blast radius)
- Inline the 13 (§4 W2); artifact-regen becomes path-guarded job; pr-drift rate-limited; PACKAGE_MAP updated in lockstep; ci-doctor workflow_run list trimmed as survivors are absorbed
- **Risk:** high (29-job graph + deploy chain) — mitigated by: chain is already 100% `uses:` (mechanical inline), environment gates preserved, one PR = one workflow, revert = one PR

### P6 — W1 pr-gate (last: required check names)
- Merge the 6 (§4 W1) with job names byte-identical to today's required checks → branch protection untouched; e2e-runner → composite action; SG-11 self-mod set updated
- **Risk:** medium-high (most visible surface) — done last so all learnings from P2–P5 apply

### P7 — Cleanup & docs truth-sync
- Delete absorbed files' stale references: `CODEBASE_GUIDE.md` (deploy-firebase-hosting "removed" claim at L1001 — file exists; qa-live-smoke script credit L986; nonexistent `maintenance.yml` L1364), AGENTS.md/OPS-06 references to renamed workflows, `docs/plans/PENDING_APPROVALS.md` entries
- End-state audit: exactly 5 workflow files; grep-clean for orphan `uses:`/names; PACKAGE_MAP final; worklog

**Dependency graph:** P1 → P2 → P3 → P4 → P5 → P6 → P7 (strictly sequential — each phase lands on a stable previous state; P2/P3 may interleave safely if different agents hold them, but PRs must not touch the same files).

---

## 7. Founder Decisions Required (blocking P3/P4/P5)

1. **Watchdog cadence policy:** accept hourly deploy-doctor fallback (event-driven covers CI deploys) + nightly platform sweep, vs. keeping a 30-min critical-subset probe? (recommendation: event-driven + hourly + nightly)
2. **dry-gate disposition:** it is `disabled_manually` yet still executing via ci.yml. Re-enable as an inline W2 job, or formally remove the call + PACKAGE_MAP entry? (recommendation: keep — 2% jscpd threshold is a real gate)
3. **PR-drift rate-limit policy:** restrict auto-update-branch to `queue:pending-rollup` + >6h-stale PRs? (recommendation: yes — kills the CI amplifier)
4. **Protected-scope exception:** bulk workflow deletions across P2–P6 will each need human review by policy — confirm the founder wants to review each phase PR, or delegates a one-time exception for the series. (recommendation: review each; the PRs are small and individually revertible)
5. **merge-train cron */20 → */30:** acceptable added drain latency (≤10 min) for half the tick burn? (recommendation: yes — labeled events remain the primary trigger)

---

## 8. Epic Acceptance Criteria

1. `.github/workflows/` contains **exactly 5** workflow files (`pr-gate`, `main-pipeline`, `nightly-ops`, `integration-gate`, `ops-console`)
2. Branch protection required checks pass on a test PR without protection edits (job names preserved)
3. `environment: production` gates, per-service Render concurrency, and merge-train single-flight semantics all intact (verified on first post-consolidation deploy + batch merge)
4. `detect-previous-failures.py` PACKAGE_MAP and ci-doctor naming lists final and consistent (grep audit in P7)
5. Zero orphan references repo-wide (P7 grep gate)
6. Run-volume check 2 weeks post-completion: ≤700 runs/week sustained
7. Deploy failure → doctor issue opened **within one workflow run** (event-driven), not on a cron tick

---

## 9. Planner Boundary Compliance

Agent-1 authored this plan from read-only audits + live API measurement. No workflow file was modified. All implementation work is delegated to the CI lane (`handoff:ci`) as atomic phase issues; `.github/workflows/**` changes go through human review per protected-scope policy. Single-merge-door discipline: planner does not merge.
