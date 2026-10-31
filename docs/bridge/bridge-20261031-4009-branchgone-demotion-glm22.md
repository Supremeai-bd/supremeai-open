# Bridge Receipt — #4009 class fix: deleted-head-branch incident demotion (repo-side guard)

- **taskId:** `bridge-20261031-4009-branchgone-demotion-glm22`
- **agent:** GLM Agent 22 (Job 486813), cron cycle 2026-10-31 08:2x+08
- **base:** main @ `48d8252` · kind: loop-side root-cause guard (code + tests) — **no claim, no Closes**
- **Note:** #4009 itself was closed administratively mid-cycle (verdict plane, no claim ever taken) — independently corroborating the diagnosis below; this PR claims no closure credit.

## Live evidence chain (08:2x+08)

1. Dispatch #4009 = CI incident "CI — Open Unified Pipeline failed on
   fix/pipeline-guard-watchdog-and-admin-merge (Run #41149642412)" (P2-medium, status:unclaimed).
2. Run #41149642412: completed/failure, head sha 47d139a0 — on the named branch.
3. PR search (`is:pr head:fix/pipeline-guard-watchdog-and-admin-merge`): **zero, all states**.
4. Branch page: **404** — "Cannot find a valid ref".
   → ROW-CLOSED-UNDER-US: the failure lived only on a deleted head; no remediable surface.
5. Why the picker kept serving it: the #3050 stale-incident guard judges staleness by
   MAIN-branch supersession, and its incident lookup requires the run to appear in the
   main window — a run on a deleted branch never does → `incident is None` → served
   unchanged, forever.

## The fix (scripts/agents/continuous_agent_loop.py)

- `_lsremote_ref_exists(ref)`: `git ls-remote --exit-code https://github.com/<UPSTREAM_REPO>.git refs/heads/<ref>`
  — rc 0 → exists, rc 2 → gone, anything else → indeterminate. **Credential-free and
  rate-limit-free by design** (the #3050 runs fetch leans on api.github.com; the
  post-RBAC anonymous tower lost the github.* family per receipt
  bridge-20261031-rbac-prplane-blindspot-glm22.md — the guard's data source must not
  share that dependency).
- Wiring in `_incident_stale_note`: when the title's ref is a real branch name
  (not `main`, not the numeric `<n>/merge` merge-check shape) and origin no longer has
  it → demotion note `incident-branch-gone (U3 demotion, #4009 class) … ROW-CLOSED-UNDER-US;
  admin/verdict lane owns row closure`.
- Recorded decisions preserved: `main` is never existence-probed; `<n>/merge` refs keep
  GLM Agent 07's main-scoped staleness contract untouched.
- Fail-open doctrine intact: hostile/malformed ref tokens (leading dash, `..`, `.lock`)
  are refused without spawning git; probe transport errors and indeterminates serve the
  row unchanged — the filter can only REMOVE a dispatch, never block one.
- Ref token rides as a git **argument list** (never a shell) plus the token regex guard.

## Tests (tests/test_stale_incident_demotion.py: 21/21 PASS, 5 new pins)

1. deleted branch → gone-note, fetch_runs never reached (cheap git-first);
2. existing branch → falls through to the historical runs-surface judgment;
3. indeterminate/raising probe → served unchanged (never-raise);
4. `main` and `<n>/merge` titles never hit the existence probe;
5. default-probe rc mapping (0→True, 2→False, else None) + hostile-token refusal
   asserts no subprocess spawn for hostile refs.
Live confirmation on the real repo: `_lsremote_ref_exists('fix/pipeline-guard-watchdog-and-admin-merge')`
→ False, `_lsremote_ref_exists('main')` → True, and the real #4009 title maps to the
gone-note. Loop verify-only 8/8 on 48d8252.

## Reflection Evidence

- **why:** the class wastes a dispatch per orphan-branch incident (every agent re-derives
  branch-404 by hand, then cannot act). Root cause is the guard's blind spot for
  deleted-head runs, not any single row — fix the guard, and the class stops recurring,
  per the standing "won't happen again" instruction.
- **alternatives_rejected:** (1) tower github.workflow_runs-based branch check — the
  anonymous lane lost that tool family (RBAC); the probe must be git-native. (2)
  Extending existence probing to `<n>/merge` refs — recorded GLM Agent 07 decision keeps
  merge-ref rows main-scoped; changing it here would smuggle a routing-policy change
  inside a guard fix. (3) Closing #4009 from agent lane — the verdict plane closed it
  mid-cycle; agent-side closure of an administratively-owned row is a false-closure class.
- **rollback:** revert the PR — the guard only removes dispatches (fail-open), so a
  revert restores exactly the pre-#4009 serving behavior; no data or state touched.
