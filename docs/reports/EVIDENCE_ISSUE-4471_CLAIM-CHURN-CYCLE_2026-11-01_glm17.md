# EVIDENCE — Issue #4471 — claim-churn cycle datum + tip re-verify (GLM Agent 17)

**Agent:** GLM Agent 17 (Job ID: 486798) · **Claim:** GRANT_NEW @ 2026-10-31T22:19:56Z (TTL 30m)
**Row:** #4471 `[status:unclaimed → status:claimed] [audit:finding] [P1-major]` — pipeline.yml fast-lint: swap index regen `|| true` for fail-closed `--check`
**Disposition:** evidence-only, NO auto-close — remedy lives on a protected path (`.github/`), closure belongs to the admin/verdict plane (#2211/#2225 false-closure family respected).

## 1. What this receipt adds (not a duplicate of #4533/#4534)

GLM Agent 05's landed receipt (#4534, tip 2f1268c) proved the premise and the incident-faithful
negative proof as of 03:05+08. This receipt adds the **class-level picture** that no single
receipt has recorded yet: the row is stuck in a **dispatch/demotion churn cycle** where the
loop reaches a *different* verdict on three consecutive cycles, and one of those verdicts is a
false negative caused by **"cite ≠ fix"** matching.

## 2. The three-cycle churn sequence (first-hand, cycle-dated)

| Cycle (+08) | Loop verdict on #4471 | Mechanism | Truth on that tip |
|---|---|---|---|
| 01:17 Nov 1 | skipped — U5 demotion | "open bridge WO receipt already references this row (#4489, #4482) — coverage in flight" | coverage receipts were bookkeeping, premise unapplied |
| 05:17 Nov 1 | skipped — premise-delivered demotion | merged PR #4553 cites '#4528/#4471' in a **Sentry c89 report** receipt | **cite ≠ fix**: `pipeline.yml:571` still `|| true` (first-hand) |
| 06:17 Nov 1 | dispatched solver | STALE-CLAIM GUARD pass (latestClaim=null — prior live claim TTL-expired) | **GRANT_NEW** this claim, 22:19:56Z |

Net effect: every 30-min fleet window re-derives a fresh opinion about the same unremedied row,
burning one candidate slot per cycle while the actual one-line remedy waits on the admin lane.

## 3. Root observation for the picker: "cite ≠ fix" false negative

The `premise-delivered` demotion (landing-receipt cross-scan) triggers on **text citation** of
the row number inside any landed receipt — including **report-only** receipts (Sentry passes,
worklogs) that merely mention the row. That demotes a live, unremedied, dispatchable row on
false evidence. One cycle later the row is dispatched again — the churn in §2.

**Proposed mechanical hardening (for the loop owners, not self-dispatched here):** before the
premise-delivered demotion, run the row's own premise check mechanically when the row names a
checkable artifact. For #4471 that is exactly:

```
rg -n 'generate_script_index\.py \|\| true' .github/workflows/pipeline.yml   # rc=0 → premise still OPEN (do NOT demote)
```

rc=1 (pattern gone) → premise genuinely delivered → demote with evidence. This turns a text
match into an artifact-state match and kills the whole churn class.

## 4. Tip re-verify (this claim's freshness duty)

All first-hand at current tip **de638e6d** (worklog r9 wave, post-#4534):

1. `rg -n 'generate_script_index' .github/workflows/pipeline.yml` →
   `571: python3 scripts/ops/generate_script_index.py || true` — **swap still unapplied** at 06:25+08 Nov 1.
2. Healthy control: `python3 scripts/ops/generate_script_index.py --check` →
   `OK: .../scripts/ops/_INDEX.md is up to date (559 scripts, 6 hand sections)`, exit 0 —
   applying the swap today blocks nothing on the healthy tree; it only fails future staleness.
3. Guard line 572 (`deploy_preflight_guard.py --step1-syntax`) still follows the regen step —
   the ordering defect Agent 05 recorded is intact at this tip.

## 5. Why the remedy stays admin-lane (limits, restated)

- `.github/` is a protected path: the bridge hard-rejects automatic `full_file` writes there
  (GLM Agent 08 first-hand error; Agent 05 alternatives_rejected concurs).
- Fork-and-PR requires credentials agents do not hold.
- Therefore the correct terminal state for an agent claim on this row is: **evidence receipt +
  lease release + issue stays open** for the admin apply. A `Closes #4471` line here would be a
  false closure — the fix would not be on main.

## 6. Claim lifecycle (honest closure of the dispatch)

1. Loop dispatch (solver, #4471) → STALE-CLAIM GUARD: `bridge_read_feedback` → `latestClaim: null`, labels `status:unclaimed` → clean.
2. `work_claim {issueNumber: 4471, agentId: GLM-Agent-17--Job-486798}` → `GRANT_NEW`, ttl 30m, planes `label:status:claimed` + `comment:atomic-claim`.
3. This receipt = the dispatched work product (evidence lane, per the dispatch's own mandate for protected-path remedies).
4. `bridge_work_release` after landing; `closesOriginalIssue: false`.

## Never-do (from this class)

- Never treat a receipt's citation of a row number as proof the row's premise is delivered —
  verify the artifact state.
- Never re-solve a row whose remedy lives on a protected path; close the dispatch lifecycle
  with evidence instead of leaving it unacknowledged.
- Never leave a solver dispatch unacknowledged across cycles — the churn is the cost.
