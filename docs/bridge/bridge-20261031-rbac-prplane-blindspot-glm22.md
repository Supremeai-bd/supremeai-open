# Bridge Receipt — post-RBAC-redeploy audit-plane blindspot (report-only evidence)

- **taskId:** `bridge-20261031-rbac-prplane-blindspot-glm22`
- **agent:** GLM Agent 22 (Job 486813), cron cycle 2026-10-31 07:2x+08
- **base:** main @ `fe02b99` · claim taken: **NONE** · kind: report-only, no Closes
- **Related:** completes the degradation accounting predicted by the #3663
  deploy-window matrix (receipt bridge-20261031-3663-acceptance-probe-glm22.md,
  Cycle-1) and live-confirmed in its Cycle-3 run (PR #3905).

## Premise (live, 07:2x+08, HEAD fe02b99)

- `grep -oE "github\.[a-z_]+" scripts/agents/continuous_agent_loop.py | sort | uniq -c`:
  **13 call sites** of `github.list_prs` — the loop's entire PR-plane audit machinery.
- Live anonymous `tools/list` (streamable HTTP, fresh session): **20 descriptors,
  github.\* = NONE**. The viewer-RBAC shrink that remediated P0 #3663 also removed the
  credential-free github read family the loop's audit depended on.
- The loop's own output this cycle: *"Read-only failed PR audit: PR-plane dark (viewer
  RBAC; tower PR tool-call error: MCP error -32602: Tool github.list_prs not found) —
  board-plane partial assurance via tower board fallback: 52 rows … per-PR check status
  UNSEEN, not certified clean (U2)."*

## Impact (honest accounting, not alarmist)

Intact: board plane (47 open rows visible via bridge_work_queue), claim/submit lanes
(`work_claim`, `bridge_submit*` in the anonymous 20-tool set), agent heartbeats — the
#3663 fix's operational goal holds and the acceptance probe guards it.
Lost for agent lanes: per-PR CI status of the landing cohort (16/52 rows in gates),
the read-only failed-PR audit — PR triage is now owner/credential-plane only. Cost
shape: every loop run prints the U2 dark note; failed PRs linger untriaged longer;
each agent re-derives the blindness by hand.

## Options for the owner (recorded, owner's judgment — deploy-policy lane)

- **A. Narrow re-exposure:** viewer-class read-only `github.list_prs` (public repo
  data, credential-free) — one policy line restores the full audit plane; smallest
  change, exactly the read family the Cycle-1 matrix predicted would degrade.
- **B. Purpose-built audit tool:** a `ci.landing_overview`-class viewer tool returning
  the pre-digested landing-cohort/failed-PR summary — least surface, most signal, but
  new tool code.
- **C. Accept the dark plane:** document U2 as expected post-RBAC state — zero tower
  work; ongoing per-cycle cost for every agent, PR triage fully owner-lane.
- Guard for whichever option: P0 #3663 acceptance must stay green — re-run
  `scripts/tower/p0_3663_acceptance_probe.py` after any toolset change; the probe's
  criterion-3 tripwire fails the run if a destructive descriptor returns.

## Reflection Evidence

- **why:** the blindspot is fleet-wide and recurring (every cycle, every agent) — a
  root-cause receipt with options beats each agent re-deriving it; it also closes the
  loop on my own Cycle-1 prediction so the degradation ledger is complete in one place.
- **alternatives_rejected:** (1) patching the loop to drop/quiet the PR-audit plane —
  masks the regression instead of restoring the capability; audit value lost. (2)
  agent-side Bearer-token handling to call the github family — credential management is
  HITL/owner lane. (3) leaving it undocumented — the U2 note repeats forever with no
  recorded decision path.
- **rollback:** none needed (report-only docs commit); delete the receipt + worklog
  line if the owner files a superseding decision receipt.
