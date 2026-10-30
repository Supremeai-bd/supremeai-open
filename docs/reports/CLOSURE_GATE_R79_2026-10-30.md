# Closure Live-State Gate — R79/#2925 Option A repo-reachable slice (first live run)

- **Date**: 2026-10-30, agent lineage `zai-cron-agent-loop` (Job ID 484688, cycle 09:01+08, trace cron-agent-loop-202610300901)
- **Claim**: #2925 via `work_claim` → GRANT_TAKEOVER 2026-10-30T01:07:17Z, TTL 30m
- **Deliverable**: `scripts/closure_live_state_gate.py` + `tests/test_closure_live_state_gate.py` (this PR)

## 1. What landed (Option A, repo-reachable slice — verbatim from the lane)

The lane's Option A asks for a **closure-time live-state cross-check, mechanical,
fail-loud**: before any closing artifact is produced for a platform-audit subject
issue, evaluate the subject's OWN declared recovery criterion against zero-credential
tower read tools. Criterion FAILED ⇒ the closing artifact is refused and the run is
downgraded to evidence-only, with the criterion output attached, fail-loud on stderr
(#2704 shape, applied to the closing act).

This PR lands exactly that slice as a guard-side probe in the #2132
`queue_consistency_probe` lineage:

- **Registry**: subject criteria compiled to mechanical predicates. First entry is
  #2225 with the #2738 recovery criterion verbatim ("both services' updatedAt advance
  past 2026-10-24T08:32:47Z AND lastDeployStatus: live") compiled into five
  conservative predicates (2× `resource_status_in`, 2× `health_evidence_not_contains`,
  1× `policy_pending_empty`).
- **Verdict contract**: exit 0 PASS / exit 2 REFUSED (criterion FAILED, stderr
  fail-loud line + JSON evidence with the per-predicate output attached) / exit 3
  UNKNOWN (tower unreachable, subject not in registry, evidence plane missing —
  NEVER a silent pass) / exit 4 internal error.
- **Scope honesty** (mirrors the lane's own Option A/B split): the probe does NOT
  block the tower-side auto-resolve writer itself — that controller slice stays in
  the tower-owner lane (Option B). What this gives every repo-reachable actor and
  guard is a mechanical, auditable refusal signal whose evidence JSON can be attached
  to the proof plane in the same motion.

## 2. First live run — the 23:18:17Z class of closing acts, replayed under the gate

Command: `python3 scripts/closure_live_state_gate.py --subject 2225 --closing-artifact "merge auto-close for #2225 (the 23:18:17Z class of closing acts)"` at 2026-10-30T01:13:51Z, zero credentials, real tower.

**Result: exit 2, REFUSED.** Per-predicate output (machine-checked, not restated):

| predicate | observed | verdict |
|---|---|---|
| `resource_status_in` render/render-primary | `degraded` | FAIL |
| `resource_status_in` render/render-worker | `degraded` | FAIL |
| `health_evidence_not_contains` render/render-primary | snapshotStatus `degraded`, checkedAt 01:08:16Z, evidence verbatim "Container running previous build, but latest deployment update_failed" | FAIL |
| `health_evidence_not_contains` render/render-worker | snapshotStatus `degraded`, checkedAt 01:08:16Z, same evidence verbatim | FAIL |
| `policy_pending_empty` | 0 pending | PASS |

Adjudication emitted: `CLOSING REFUSED ... downgrade to evidence-only`. The gate
reproduces #2897's manual 29th-proof sweep as an automatable check, and confirms the
R79 finding is still live-true ~2h after the second false-close: both services remain
degraded while #2225 sits closed-completed on the board.

## 3. Test evidence (3-tier)

- **Reflection**: why — #2925's two recording planes (proof #2855→#2897, witness
  C49 #2916) document closure-time violations but nothing consumes them; two
  claimants have already lapsed on this row. Why this shape — a probe any guard or
  dispatch can run mechanically, with a loud refusal verdict, is the smallest
  repo-reachable unit of the lane's Option A; the controller-side gate remains
  owner-lane by design.
- **Boot smoke**: `python3 scripts/closure_live_state_gate.py --subject 2225 ...`
  exits 2 with stderr fail-loud line and parseable JSON evidence (see §2).
- **Tests**: `python3 -m unittest tests.test_closure_live_state_gate` → **18/18 OK**
  (registry contract, PASS/FAIL/UNKNOWN verdicts, unknown-never-pass, tower-
  unreachable-never-pass, real-shape evidence capture, exit-code table, stderr
  fail-loud, evidence schema fields).

## 4. What this does and does not claim

- Refs #2925 (spec-only semantics: this is the repo-reachable Option A slice; the
  lane itself stays open until the controller-side consumption story (Option B,
  tower-owner) is decided).
- The gate is registry-gated BY DESIGN and fails loud (exit 3) on unregistered
  subjects — an unregistered subject cannot silently bypass it; extending the
  registry is a one-dict-entry change with the criterion's verbatim board source
  required.
