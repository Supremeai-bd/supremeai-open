# Bridge Receipt — Identity registration + run worklog: GLM Agent 20 (Job 486804) — one cycle, door honored, root-cause fix delivered (PR #3332, Closes #3315)

- **Task ID**: bridge-20261030-identity-glm20
- **Slot**: 2026-10-30T20:20+08 (12:20Z) · Job 486804 · **GLM Agent 20** · continuous_agent_loop contract · trace cron-agent-loop-202610302020
- **Mode**: identity registration + compact run worklog (docs-only, this single new file under `docs/bridge/`); the cycle's code deliverable rides separately on PR #3332 (branch `bridge/bridge-20261030-pick-receipt-coverage-glm20-r1`, Closes #3315)
- **Preconditions**: main at 832d80d3 (rebased 0 behind pre-push); zero-credential anonymous surface, named MCP client `GLM-Agent-20`.

## 1. Registration

GLM Agent 20, Job 486804. Door honored in order: MCP tower handshake (`/mcp?client=GLM-Agent-20`, session stable) → AGENTS.md (5 Universal Invariants) → `docs/AGENT_OPERATING_SYSTEM.md` → `bridge_guide` live contract → `scripts/agents/continuous_agent_loop.py --loop` dispatch.

## 2. Dispatch chain this cycle (compact — skip evidence only)

| # | Picked | Skip reason (verified live, never retried) |
|---|---|---|
| 1 | #2360 | receipt WO #3272 filed 4 min before dispatch; row then claimed (GLM-Agent-04, 12:23:38Z) |
| 2 | #2633 | receipt WO #3281 filed 10 min before dispatch; latestClaim null — pure receipt-coverage gap |
| 3 | #2567 | atomic-claim CONFLICT (claimed 12:26:49Z; feedback view still showed unclaimed at ~12:29Z — tower-side view lag, R49 lane; atomic backstop worked) |
| 4 | #1676 | WO #3292 (detection half) open; remainder is satellite-side, outside agent envelope |

Every skip follows the STALE-CLAIM GUARD: verify → skip with evidence → next candidate → no same-row retry.

## 3. Root-cause work delivered (the flywheel, all four stages)

Incident: 3 dispatch burns in 20 min (rows re-emitted while covered by OPEN bridge receipt WOs — the item-15 premise probe only cross-scans MERGED receipts, the #2794 claim probe only sees claims). RCA + encoding: guard issue **#3315** filed with evidence, claimed (GRANT_NEW 12:38:05Z), fixed in `continuous_agent_loop.py` — pure in-memory `_receipt_covered_note()` + pre-sort receipt-coverage demotion in `pick_next_issue()` live mode (pure mode byte-identical; never raises; word-bounded `#N`/`row N`/`bridge-YYYYMMDD-N`; conservative Bridge-Work-Order issuer gate). Re-check: 15 hermetic tests (`tests/test_pick_receipt_coverage.py`), 4 neighboring pin suites green (26), pytest 47 passed, loop `--verify-only` 8/8 tiers PASS. **Live-fire on the production board: #3093 skipped (#3278/#3124), #2811 skipped (#3305/#3294), pick advanced to uncovered #2766.** Submitted: WO #3331 → PR #3332 (CI Guardian → constitutional gates).

## 4. Out-of-scope observation (recorded, not fixed)

`bridge_read_feedback` latestClaim/labels can lag the atomic claim store by minutes (#2567 case, ~3 min). Tower/controller plane (R49 lane) — no repo PR can reach it; the loop's atomic-claim rejection backstop already contains the residual. Noted for the tower owner.

## 5. Disposition

Docs-only identity receipt → **Refs** convention (no `Closes` line; the row's substance is tracked by PR #3332 which truthfully closes #3315). Worklog kept small per operator instruction: superseded probe transcripts and queue dumps were not persisted; only evidence-bearing receipts and the guard chain above are retained.
