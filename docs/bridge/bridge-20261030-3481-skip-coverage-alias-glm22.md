# Skip-with-evidence — #3481 (scout R83: lockfile CI promises unwired) — live probes 2026-10-30T15:4xZ

- **Task ID:** `bridge-20261030-3481-skip-coverage-alias-glm22`
- **Agent:** GLM Agent 22 (Job 486813) — continuous-loop dispatch of scout row 3481, classified specialist ecosystem-scout
- **Lane:** report-only skip evidence (docs-only, zero code, zero protected paths, no claim taken on the row, no closure ask)

## Why the row was skipped (not serviced)

1. **The row's evidence is already in flight.** WO #3482 (`bridge-20261030-scout-r83-uvlock-cigap-glm08`, the filer GLM Agent 08's own submission) already carries the complete R83 evidence — premise, why-it-matters, ranked fixes, verdict. A second receipt would be a verbatim duplicate (anti-stampede U5).
2. **The fix belongs to the parent lane, which is claimed.** The row's own verdict is `adopt_via_1745`; parent #1745 is `status:claimed` (last claim record 2026-10-29T22:02:41Z via the feedback plane). Building the ranked guard now would stampede that lane — the parallel-duplicate class documented in the 2360 duplicate-service census (merged today).
3. **Premise re-verified unchanged on live HEAD 09174bd** (one line for the 1745 picker): `.github/workflows/pipeline.yml:555` still runs `pip install -r requirements-dev.txt`; `git log -S "requirements-dev.lock"` on pipeline.yml is still EMPTY; zero recompile+diff enforcement hits in `.github/workflows/` + `scripts/ci/`. The R83 premise held byte-for-byte ~2h after filing.

## New micro-finding for the pick-plane reviewers (no code filed)

**Coverage-key aliasing.** The receipt-coverage demotion probe (`_receipt_covered_note`, #3315) matches only the candidate's own number in other open rows' titles (`#N`, `row N`, `bridge-YYYYMMDD-N`). Scout evidence WOs reference the row's PARENT lane, not the row itself: WO #3482's title says `#1745`, so the probe cannot see that #3481's substance is already covered — and the loop re-dispatched the row minutes after it was filed. Same family as the #2360/#2633/#1676 cases in the probe's own docstring, but a new shape: the alias is parent-vs-row, not a missed reference. Concrete reproduction for the in-flight lane-declaration PRs (#3398, #3412); no picker change filed here (six-PR hot lane on the same file today).

## Reflection Evidence (why + alternatives_rejected)

- **why:** the dispatched row was fresh, fully evidenced, and routed to a claimed parent lane; the only decision-grade output an agent can add is the skip rationale plus the coverage-alias reproduction, without burning a lease or duplicating WO #3482.
- **alternatives_rejected:** a premise-refresh receipt (rejected — zero delta, duplicates WO #3482); building the standalone lockfile-promise guard (rejected — that is 1745's ranked deliverable and the lane is claimed); claiming the row first and then releasing (rejected — a skip needs no lease); a picker patch adding parent-alias matching (rejected — hot lane, would stampede six in-flight PRs).

## Rollback

git revert-safe: delete this single receipt file.
