# OPS RUNBOOK — Private Actions quota & scheduler freeze (`Supremeai-bd/supremeai`)

One findable operational record for every agent/admin. Filed as **issue #68**
(P1-high, `infra-ops`). Zero secrets in this document — tokens stay in the
vault; run IDs are harmless numeric metadata.

## 1. Scheduler-freeze signature (know it when you see it)

A GitHub-side scheduler defect freezes run scheduling **per repo**. Signature
(verified 2026-10-15, onset ~14:48 UTC):

- New run (dispatch AND rerun) is created with **`jobs: 0`** and stays
  `queued` forever — it never enters GitHub's internal scheduling queue.
- `POST .../runs/<id>/cancel` → **409** `"Cannot cancel a workflow run that
  has not been queued yet"` (GitHub's own API admits the run was never
  queued). Delete-run → 403.
- Dispatch returns 204 and rerun returns 201, but both still yield 0 jobs.
- Same-minute CI on a **different repo stays green** → the freeze is
  repo-scoped, not global.

**NOT the cause:** workflow YAMLs (same files ran green hours earlier),
concurrency groups (all distinct), billing quota (see §3), global outage
(statuspage operational), dispatching actor (bot + human both affected).

Historic batches: Oct 9, Oct 10, Oct 13, Oct 15 (2026). Recurrent.

## 2. Current limbo inventory (as of 2026-10-15)

29 runs stuck in uncancellable limbo (all 0-jobs, all cancel→409):

```
38757670162 38754788775 38754781139 38733477639 38731410353 38729592396
38728720184 38486594219 38478222433 38473043852 38473037451 38451086231
38451075841 38444426369 38420941808 38419812324 38419034037 38418782444
38415473620 38404255585 38017400855 38017395370 38000861169 37980151219
37976430079 37976370187 37976357646 37976343041 37971998922
```

Workflows affected: bridge-intake, archive-mirror, continuous-agent-loop.

## 3. Quota context & monitoring (AC4)

- Org plan: **Free** → private repos share **2,000 Actions minutes/month**.
- Burn 2026-10-15: **≈353 min (17.6%)** via billing usage API — quota was
  NOT the freeze trigger.
- Volume pathology signal: 1,117 runs created in ~2.5 days (watchdog
  re-dispatching intake+archive on every CI cycle) — keep burn + run-count
  low; the E11 guard (§5) stops the dispatch storm.

### Check the burn (any agent, read-only)

```bash
GH_TOKEN=<PAT> python scripts/ops/actions_quota_check.py --year 2026 --month 10
# exit 0 = below threshold, exit 1 = ≥80% ALERT
```

Alert threshold: **80% (1,600/2,000 min)** per issue #68 AC4. CI/cron owners
should run this weekly (org-owner PAT with `admin:org` billing read).

## 4. Recovery procedure (when scheduling resumes)

1. Watch for the first new run expanding to real jobs
   (`GET /repos/Supremeai-bd/supremeai/actions/runs?status=queued` shows
   `jobs_count > 0` or the run leaves `queued` within minutes).
2. **Cull immediately** — up to 29 limbo runs may fire **at once**:
   ```bash
   for id in <run ids from §2>; do
     curl -X POST -H "Authorization: Bearer $GH_TOKEN" \
       "https://api.github.com/repos/Supremeai-bd/supremeai/actions/runs/$id/cancel"
   done   # expect 202 per fresh-queued run; 409 = still limbo
   ```
3. Verify: `gh run list --repo Supremeai-bd/supremeai --status queued` → 0.
4. Cancelled limbo runs are then deletable (DELETE run) to unclutter the UI.

## 5. Mitigations already landed

| Guard | Where | Effect |
|---|---|---|
| **E11 check-before-dispatch** | `scripts/ci/schedule_watchdog.py` (PR #169) | watchdog skips compensation dispatch when a queued/in_progress run exists → no more dispatch storms (log: `comp=skipped(already-queued-or-running)`) |
| **cancel-in-progress: true** | `archive-mirror.yml` (PR #169) | pure mirror is newest-wins — superseded runs cancel cleanly |
| **concurrency v3 bump** | both workflows (PR #169) | group-rename escape hatch — fresh groups bypass poisoned group state |
| **cancel-in-progress stays false** | `bridge-intake.yml` (PR #169) | E4 dedup race: mid-run cancel would push the branch without writing the dedup marker → later false-rejects |
| **shift-left guards** | `supremeai-open` `.github/workflows/pipeline.yml` (PR #64, consolidated by #155) | invalid contributions fail on the free public runtime (~5s) instead of burning private minutes |

## 6. Federation Workflow Diet (#155) — the structural quota fix

Volume pathology (§3) is treated at the root, not with per-run patches: the
public boundary and the private monorepo each run the **minimum safest
workflow set**, and every check that the free public runtime already proves is
eliminated from private CI (shift-left de-duplication).

| Surface | Before | After (2 files) |
|---|---|---|
| `supremeai-open` | 5 workflows (`open-guards`, `ci`, `continuous-agent-loop`, `merge-gate`, `auto-bridge-dispatcher`) | `pipeline.yml` (validation + cron engine) + `landing.yml` (auto-merge + bridge dispatch) |
| `supremeai` (private) | 18 workflows | 4 (`pr-pipeline`, `deploy-train`, `bridge-intake`, `ops-maintenance`) — private-side change, tracked there |

Eliminated from private CI because `supremeai-open` proves them first (free
runtime, unlimited minutes): branch naming, issue reference, anti-duplicate PR,
full Python matrix (3.10–3.13; private pins 3.11), Tower TS typecheck/tests,
gitleaks full-history scan, boundary sanitization audit, docs/link checks,
lint/format passes, dependency vulnerability scans, AI PR evaluation.

Contributor rule: because landed public work is auto-bridged into
`Supremeai-bd/supremeai`, **never open a duplicate manual PR on the private
repository** for work handled at the public boundary (AGENT_RULES.md U4,
zero-duplicate mandate).

## 7. Support-ticket checklist (org owner, AC1)

Include: repo `Supremeai-bd/supremeai`; onset `2026-10-15T14:48Z` (+ prior
batches Oct 9/10/13); run IDs from §2; one raw 409 response body for cancel;
jobs=0 evidence for a stuck run; note that dispatch+rerun both accepted but
never scheduled while other repos stayed green; request purge of limbo runs.

Link the ticket back into issue #68 when filed.

## 8. References

- Issue #68 (this runbook's tracking issue) · PR #169 (E11 + concurrency v3)
- PR #64 (task envelope + open guards) · Issue #63 (taxonomy drift fix)
- Issue #155 (Federation Workflow Diet — public 5→2 workflows, private 18→4)
- `docs/AGENT_LOOP_SPEC.md §4b` (CONTRACT_VERSION parity contract)

## 9. Satellite main CI red — first triage (added 2026-10-28, audit #2111)

Row: **satellite repo main CI RED → check here first, before touching product code.**

1. **Event plane.** Pull the run's `event` field. On `Supremeai-bd/supremeai-core`, schedule
   runs execute ONLY the PyErrorFix autofix job (ci.yml job-split: `test` = push/PR only,
   `autofix` = schedule-only). Same-sha push-green + schedule-red = disjoint job planes,
   not a product regression (live proof: runs 35 success vs 36 failure on sha 419a838).
2. **Trigger filter.** Read `.github/workflows/ci.yml` at HEAD. A corrupted `push.branches`
   silently kills push-CI (observed 2026-10-28: literal `ain]` at bot commit feda45e →
   product CI dark on core main until admin fixes it).
3. **Watchdog plane.** Both core CI jobs dispatch `federation_ci_failed` to supremeai-open
   on failure — check the open repo for the filed issue (e.g. #2053) before declaring a
   detection blind spot; the residual gap is closed-lane invisibility, not absence of
   detection.

Full RCA: `docs/reports/AUDIT_2111_CORE_CI_SCHEDULE_POLARITY_2026-10-28.md`.
