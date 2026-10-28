# Queue-plane consistency probe — first standing receipt (#2100 / #2115 / #2123 arc)

**Check**: `scripts/queue_consistency_probe.py` — stdlib-only, anonymous (zero-credential)
tower session; executes exactly two read-only bridge tools (`bridge_work_queue`,
`bridge_read_feedback`) under a hard fail-close allowlist; nothing else runs, so no
secret/destructive-class execution is structurally possible. One snapshot cross-checks
the dispatch plane (queue) against the truth plane (feedback) row by row.

**Rules armed**
- **R1 mirror-stale** — row in queue but feedback says the WO is closed (landed-mirror
  residue at the queue layer).
- **R2 claim-lag** — feedback shows a fresh live claim (≤ TTL 30 min) but the queue row
  still lacks `status:claimed` (double-claim surface for every fleet agent).
- **R3 verdict-lag** — feedback carries a verdict but the row still wears an in-flight
  bridge label (verdict↔label stamp-pipeline lag, #2100 class).
- **R4 reliability** — >50% unresolved feedback calls fail-close the snapshot as
  `unreliable` instead of passing silently.

## First receipt (2026-10-28T12:05:57Z) — status: violation

```json
{
  "at": "2026-10-28T12:05:57Z",
  "status": "violation",
  "queue_rows": 35,
  "rows_checked": 35,
  "rows_unresolved": [],
  "session_rotations": 1,
  "rule_counts": {"R1-mirror-stale": 0, "R2-claim-lag": 2, "R3-verdict-lag": 0}
}
```

## Live findings

1. **R2 claim-lag fires on BOTH claimable P2 rows** — new defect evidence, not yet on
   file anywhere:
   - **#2111**: live claim stamped 11:36:12Z (feedback), yet the 11:55Z queue row still
     read `status:unclaimed` → ≥19 min staleness observed by two independent readers.
   - **#2123**: claimed ~11:50Z (feedback: fresh claim 14–16 min old at probe time),
     queue row still `status:unclaimed` at 12:05:57Z.
   Impact: any agent picking from the queue plane sees both P2s as free; `work_claim`
   then rejects atomically, burning the cycle. The loop-side fix for the sibling class
   landed at b3dfbbe (bridge-state exclusions), but the loop cannot fix *wrong label
   data* — this is Tower-side stamping, same pipeline family as #2100.
2. **R1 armed, 0 fires** — the queue correctly dropped closed WO #2109 (closed ~11:02Z
   with merged PR #2110); no closed mirror was present in any of today's three polls.
   Improvement over the #2123-era invalid triple (closed + queued + no verdict).
3. **R3 armed, 0 fires** — expected: the #2100 blackout means no verdicts exist to lag.
   The rule stays armed for post-blackout regressions.
4. **Session burst budget (new, hypothesis-class)** — an anonymous MCP session stopped
   answering `tools/call` after ~19–20 calls (first-shot runs lost 16–18 tail rows);
   one client-side session rotation restored 35/35 coverage. Needs maintainer
   confirmation; the probe rotates transparently and records the count.
5. **Queue churn continues** — 36 rows @ 11:55Z → 37 @ ~12:04Z → 35 @ 12:06Z across
   three polls inside 15 minutes; consistent with #2115's truncation-instability class
   and #2123's migration-window note.

## Routing (honest lanes)

- **R2/R3 stamping fixes, session budget**: Tower internals — maintainer lane.
- **Agent-side mitigation**: this standing check + the dispatch discipline
  "re-verify claimability via `bridge.read_feedback` immediately before `work_claim`"
  (queue labels are advisory, feedback is truth).
- **Not wired into `scripts/ops/ai/drift_checks.py`**: same reason as the #2076
  deliverable-B refusal — that surface is deterministic/offline by its own contract;
  a network probe would break it. The probe is opt-in CLI, nothing auto-runs it.

## Verification trail

`py_compile` OK; three live runs against the production tower (first-shot: violation
with 16 unresolved → after rotation fix: violation, 35/35 checked, 0 unresolved);
freshness-window sanity: #2122's claim (25 min old at 12:04Z) fired R2, then aged past
TTL and correctly stopped firing at 12:06Z; allowlist fail-close enforced in the call
wrapper (`SystemExit` on any non-allowlisted name). Report-only: two additive files,
no protected paths, no code-path change.
