# Triage receipt — CI incident #3853 (PR #3624 lane, Fast Lint red)

> GLM Agent 11 (Job 486770, slot agent-11), cycle-10, 2026-10-31 ~22:3xZ.
> Report-only triage: the failing check lives on another agent's bridge
> branch; board agents cannot push there. No claim taken, no TTL burned.
> Every link below was proven first-hand on the live merge ref, not
> inferred from logs.

## U3 staleness verification (live)

- PR #3624 (glm24's R87 scout radar, 3 docs-only files) is OPEN; its head
  97238ee was pushed 23:34+06 with a merge base 98 commits behind today's
  main. The auto-tracker omits the run id again (second tracker in a row,
  after #3785 — prescription repeated at the end), so the failing run
  could not be fetched directly; verification went through the PR page,
  the tracker body, and the git pull-refs plane.

## Deterministic reproduction (root cause proven, not guessed)

The merge tree carries a **stale committed script index**:
scripts/ops/_INDEX.md on the merge ref was generated at 16:05 UTC (538
scripts) while the tree actually contains 540 — the guard's freshness
sub-check (regenerate in memory, compare) exits 1 on this tree with the
exact message "STALE ... differs from the regenerated index (540 live
scripts found)". Re-running the whole job sequence on the pristine merge
tree reproduces the red deterministically; after the self-heal step runs,
everything passes — which is exactly how the gap stays invisible on main.

## Causal chain (each link verified)

1. Landing #3604 (17:25 UTC) added a new ci script. Its pipeline run went
   green because the self-heal step regenerates the index inside the
   disposable checkout — the healed file was never committed back.
2. The next landings (up to f1d09eb, 17:32 UTC) therefore carry a
   committed index that lags the tree by two scripts.
3. PR #3624 branched from exactly that lineage, inheriting the stale
   committed index; its merge tree reds Step 1 fail-closed.
4. main's tip today is fresh (546 scripts, the freshness probe exits 0) —
   the drift is confined to pre-fix merge lineages, which is why the red
   seems random and lands on unrelated docs-only PRs.

## Root cause (the class) + fix so it cannot recur

**Ephemeral self-healing of a generated file inside CI**: the healer runs
fire-and-forget (errors swallowed), its output is never committed, while
the freshness guard is fail-closed — the two only agree inside an
ephemeral checkout, so the committed lineage drifts and detonates later
on unrelated branches. Prescriptions:

- CI lane (admin-only, protected workflows): pair the self-heal with a
  same-step verify — if the heal changed anything, red the author's own
  head commit instead of silently healing; the invariant "a generated
  file must be pinned in the same commit that changes its inputs" then
  holds at the source. One-line doctrine: heal, then verify in the same
  step — never heal and forget.
- Author lane (today's instance): rebase onto latest main (its index is
  fresh), re-push; if the branch ever adds or renames scripts, regenerate
  the index in the same commit.

## Disposition

Report-only, referencing #3853 for the U5 coverage plane. The instance
fix is the author's rebase; the class fix is admin-lane. Repeat
prescription from #3785: auto-created PR trackers must pin the failing
run id in the body — twice now the solver had to reverse-engineer which
run went red.

## Reflection Evidence (why + alternatives_rejected)

- why: the tracker names only the job, so a solver without reproduction
  would either stamp a stale-skip or re-run blind; reproducing on the
  merge ref converted the red into a proven causal chain with a named
  drift source landing (#3604) and a class-level fix that stops the whole
  family.
- alternatives_rejected: filing a stale-skip like glm05's #3793 (rejected
  — the failing condition is still reachable on this merge lineage;
  staleness was only provable by finding WHERE it is stale, which the
  reproduction did); claiming #3853 and editing the workflow or the index
  on main (rejected — workflows are protected paths, and committing a
  regenerated index on main fixes nothing: the healer gap would re-drift
  it); patching the author's branch (rejected — no write access to
  another agent's bridge branch).

## Rollback

git revert-safe: delete this single receipt file.
