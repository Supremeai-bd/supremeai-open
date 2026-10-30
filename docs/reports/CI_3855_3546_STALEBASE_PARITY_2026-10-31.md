# CI Triage #3855 — PR #3546 Loop-Contract Parity Guard red = stale-base on an already-fixed main (no content defect)

**Agent:** GLM Agent 13 (Job 486783) · **Cycle:** 10 (2026-10-31 06:13 +08) · **Class:** `stale-base/already-fixed-on-main` · **Disposition:** PR content innocent; remedy = author-lane rebase-only; no Closes.

## Tracker facts (live tower read, 22:16–22:17Z)

- Tracker issue: #3855, "fix(ci): PR #3546 failing checks (bridge/bridge-20261031-glm23-browser3538-triage)", opened 2026-10-30T22:01:08Z, auto-created tracker body: "Failed checks: 🔁 Loop-Contract Parity Guard (#118)".
- Claimed atomically by GLM-Agent-13 at 2026-10-30T22:17:13Z (GRANT_NEW, TTL 30 min). The sibling tracker #3853 (PR #3624, same 22:01Z auto-tracker wave) was lost to a claim race at 22:16:05Z and is intentionally **not** retried (STALE-CLAIM GUARD).

## Local reproduction (deterministic, zero-credential)

| Probe | Tree | Result |
| --- | --- | --- |
| `git worktree add /tmp/pr3546 FETCH_HEAD` → `python3 scripts/agents/check_loop_contract_parity.py` | PR head `050bb7c1` | **exit 2** — `GUARD-ENV-ERROR: missing required file: docs/CONTRIBUTING.md` |
| Same script on `origin/main` tip `47c94125` | main | **exit 0** — `✅ Loop-contract parity OK: tiers 1..8 (code == SPEC §4 declared 1..8), 10 guards (workflow == SPEC §5), …` |

Branch shape (git, live origin): head `050bb7c1`, single commit, docs-only — `docs/reports/browser-ci-run41089438563-triage-3538-20261031.md` +62 lines, nothing else; merge-base `5fec3482` (#3524 doc migration), **129 commits behind main**, no conflicts expected from a one-new-file add.

## Root cause chain (why the guard is red on this branch, and only there)

1. `5fec3482` (#3524 founder doc migration) moved `CONTRIBUTING.md` to the repo root: at that tree, `git ls-tree` shows root `CONTRIBUTING.md` present and **no** `docs/CONTRIBUTING.md`.
2. The parity guard at that same tree was not updated in the same commit: `git show 5fec3482:scripts/agents/check_loop_contract_parity.py` line 57 = `CONTRIB = ROOT / "docs" / "CONTRIBUTING.md"` → fail-closed env error (exit 2) on every tree between `5fec3482` and the fix.
3. Main has since fixed the guard (current `check_loop_contract_parity.py`: `CONTRIB = ROOT / "CONTRIBUTING.md"`, "moved to repo root by #3524" comment) — one of the 129 commits the branch is behind. Guard is green on main tip today (probe above, exit 0).
4. PR #3546 branched from the broken intermediate state → its CI runs the branch's own stale guard against the branch's own migrated tree → red. The PR's +62-line report file touches none of the five parity surfaces (loop code, AGENT_LOOP_SPEC, CONTRIBUTING, AUTONOMY_LOOP_CONTRACT, pipeline.yml) and cannot influence this guard.

**Verdict:** deterministic stale-base class — the failing check is an already-repaired main defect inherited via the base, not a PR defect. The PR body carries `Refs #3538 …, #761`, so the no-issue-reference class (#3862, PR #3639) does **not** apply here; the one red check is Loop-Contract Parity only (tracker body names exactly that).

## Remedy

- **Author lane (GLM Agent 23):** `git rebase origin/main` → the 129-commit pull-in includes the repaired guard → re-push; the check flips green with zero content edits. Nothing else to fix.
- **Resolution predicate:** Loop-Contract Parity Guard green on the branch's next run, or PR #3546 lands.
- **Admin/owner lane — anti-recurrence suggestion (root-cause half, not implemented here):** the auto-tracker that opened #3853/#3855 at 22:01Z fires on "PR-lane run red" without a guard-level main-tip comparison. The picker already auto-demotes superseded *runs* (#3050); the tracker plane could apply the same U3 test per *guard*: if the failing guard is green on main tip and red only below the PR merge-base, file the row as `stale-base/already-fixed` (no solver claim needed) instead of an open fix(ci) issue. This would have suppressed both 22:01Z trackers mechanically. Not implemented by this receipt: tracker creation script identity and wiring is owner-lane, and a guard-level rewrite inside a 30-min claim window fails the full-scope completeness bar.

## Guard compliance

- U3: resolved-on-main incident → skipped with evidence above, never re-solved; no claim taken on another agent's branch.
- U5: #3862/#3851 (no-issue-reference class, PR #3639) and the #3538 browser-run receipt inside PR #3546 itself are acknowledged; this receipt covers only the Loop-Contract Parity / stale-base class of #3855.
- Zero credentials probed; all probes are local git/python reads plus tower board/feedback reads.
