# 2026-10-31 07:19+08 — auditor (GLM Agent 19, Job 486803): false auto-close of
# WO #3806 — merge-linked ≠ finding-resolved

Dispatch: auditor (single-runner lock). Door honored; worktree reset to
origin/main `8ac4b75`. Preflight: zero open P0. Board (tower, live): 51 open
rows, 16 in-gates. U2 PR plane still dark (viewer RBAC; `github.list_prs` not
found this wave) — board-plane partial assurance only.

## Headline: #3806 was auto-closed as completed while its subject is still live-broken

- WO #3806 (my scout finding, 21:26Z) documented: the A2A v1.0.0 Agent Card
  published by R23-V (PR #2779, a1a7fbd) declares tower URLs `/a2a`,
  `/a2a/v1`, `/a2a/v1/message:send` — all 404 on live tower AND gateway at
  21:24:21Z, plus spec `/.well-known/agent-card.json` and legacy
  `/.well-known/agent.json` 404 on both. `tests/test_a2a_protocol.py` asserts
  card structure + in-process adapter only: no HTTP-serving test, so CI cannot
  see the gap.
- 22:38Z: #3806 closed `completed` with comment **"Auto-closed: linked PR
  #2779 merged."** (paykaribazaronline). The linked PR is the one that
  *created* the card artifact — the very PR whose merge the finding documents
  as NOT resolving the live gap. The close evidence is the defect's cause,
  cited as the cure.
- U3 live re-probe **23:22:10Z**: `/.well-known/agent-card.json` 404 and
  `/a2a` 404 on tower; same pair 404 on gateway; legacy `agent.json` 404.
  The finding's subject is unchanged ~1h after the "completed" close.

## Same plane, new signals (23:22Z, same probe pass)

- **Gateway fully dark**: `/`, `/health`, `/healthz`, `/api/health` all 404
  ("Not Found"). At 21:24Z gateway `/health` was 200 (v2.0.0). The service
  went dark between the two probes — ops incident, P1-adjacent.
- **Tower self-reports degraded**: `/health` 200 but `status:"degraded"`,
  `services {healthy:20, degraded:1, total:21}`, `stale:true`,
  `lastCompletedSweepAt:null`, `sweepCompletions:0`.

## Root cause (class, per the fix-so-it-never-recurs directive)

Link-based auto-close semantics conflate **"artifact exists in repo"** with
**"operational finding resolved"**. For findings whose subject is a
live/operational surface (HTTP serving, deployment state, runtime health),
a merge link is not resolution evidence — only a fresh live probe is. This is
the bookkeeping-layer twin of the original finding itself ("PR-landed ≠
live-served" becomes "merge-linked ≠ finding-resolved").

Sizing evidence: the closer's wording ("Auto-closed: linked PR #N merged.")
is absent from the entire public tree (`git grep "linked PR"` → 0 hits), and
the two public auto-closers use different wording
(`bridge_landing_watchdog.py`: "Closed: work order deliverable landed on
main"; `pr_lifecycle_guard.py`: duplicate/old-receipt closes). The offending
closer lives in the owner/private plane → **admin lane**; this receipt is the
agent-lane evidence.

## Remedy (owner lane, none agent-editable from here)

1. Re-open #3806 (or re-close it with live-verification evidence showing the
   card served — the probe above shows otherwise as of 23:22Z).
2. The private-plane closer must exempt operational-surface findings (report
   receipts carrying live probes) from merge-link auto-close, or gate any
   auto-close of such rows on a fresh live probe captured at close time.
3. Serve the A2A card on both deployments (or re-point the published card) —
   the original serving gap stands.
4. Treat the gateway darkness as an ops incident independent of the card gap.

## Verification

- Probes: curl status codes captured 23:22:10Z (card URLs), 23:22:28Z
  (healths), quoted above; prior-cycle baseline 21:24:21Z recorded in #3806.
- `git grep -rn "linked PR"` on `8ac4b75` → no hits; wording search in
  `scripts/` + `.github/` → only unrelated matches.
- U5 dedup: tower board window (20 of 51 rows) + GitHub open-issue search
  (`a2a OR agent-card OR gateway`) → no open row covers the false resolve,
  the gateway outage, or the serving gap; #3940 (MCP registry absence) is a
  different subject.
- WO #3433 re-probe: open, unchanged (admin-pairing lane).

Lane discipline: report-only, zero claims, zero closure requests on other
agents' rows; Refs #3806 (evidence complement to a closed row — not a reopen
request by itself). Docs-only, single file, zero protected paths.
