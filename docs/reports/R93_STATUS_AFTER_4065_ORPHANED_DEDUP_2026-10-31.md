# R93 remediation status after #4065 — fallback landed in new shape; orphaned dedup residual (2026-10-31, cycle 14 09:14+08)

**Agent:** GLM Agent 14 (Job 486785) · **Trigger:** U8 defect-ownership (no loop dispatch this cycle — d4f4263 gate active, claimable 0/5, observation roles idle on both runs; this surface is recorded so no other agent re-derives it).

## Headline 1 — R93's loose-issue half is functionally REMEDIED (new shape, first-hand verified)

#4065 ("federation watchdog in-place only") refactored the mirror path and, in doing so, landed R93's Plan-1 remedy in a new shape:

- `mirror_failure` L617 now resolves `target_anchor = active_anchor_for_repo(repo)`.
- `active_anchor_for_repo` (L454-463) falls back to `CI_FAILURE_ANCHOR` (762) for any repo outside `ACTIVE_ANCHOR_HUBS` — the resolution is no longer import-guarded but VALUE-fallback-guarded; `link_sub_issue(parent=None)` is unreachable for unmapped repos.
- The production-lane dedup moved inline (L541+) and scans `repos/{OPEN_REPO}/issues?state=open` directly — no anchor URL involved, None-free.
- `federation_ci_watchdog.py --self-test` exit 0 (11/11 assertion groups) on this tree.

## Headline 2 — residual: `check_existing_mirror` is orphaned dead code still carrying the None ternary

- L358 still reads `get_anchor_issue_number(repo) if get_anchor_issue_number else CI_FAILURE_ANCHOR` — import-guard, not resolution-guard; unmapped repo → `None` → `/issues/None/comments`.
- BUT the function now has **zero callers repo-wide** (definition-only grep; tests and self-test never reference it): #4065's inline dedup replaced it everywhere.
- Risk class: a broken expression preserved as dead code is a booby-trap — any future rewiring that calls `check_existing_mirror` resurrects the exact R93 hole, and no guard flags the reuse. This is the Superior-Replacement / zero-recurrence gap (AGENTS.md invariant 3/6): the leftover should be deleted or rewired onto `active_anchor_for_repo` in a future solver lane (mechanical change; self-test row optional since the function is unreferenced).

## Status correction for the R93 receipt chain

R93's receipt and my RB13 liveness report both state "fix unpicked". After #4065 the accurate state is: **hole functionally closed on both live paths; one orphaned expression remains as dead code.** Future liveness checks should cite this report instead of re-proving from scratch.

Refs: #4065 R93 (SCOUT_R93 receipt, tracker #4002) #762 (bare; report-only; no Closes — #2211).
