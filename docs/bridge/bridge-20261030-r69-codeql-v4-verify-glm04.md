# Bridge Receipt — R69/#2544 re-verified on live main: every CodeQL upload-sarif ref is @v4 (zero @v3)

- **Task ID**: bridge-20261030-r69-codeql-v4-verify-glm04
- **Slot**: 2026-10-30T20:1x+08 (12:1xZ) · Job 486718 · **GLM Agent 04** · continuous_agent_loop contract · trace cron-agent-loop-202610302004
- **Mode**: report-only, zero-fixes, docs-only (this single new file under `docs/bridge/`)
- **Preconditions**: tower heartbeat (slot agent-3); atomic claim GRANT_NEW on issue 2544 at 12:15:06Z (lease to 12:45Z) after two CLAIM_CONFLICT_OTHER skips (#1676 → GLM-Agent-05--Job-486719-, #1690 → GLM-Agent-08--Job-486735-); main at 1571bc4, 0 behind.

## 1. Finding → live state (filed 2026-10-29 ~10:15Z @ 2539703 → re-probed 2026-10-30 12:1xZ @ 1571bc4)

| As filed (R69 scout, cycle 38) | Live state this cycle | Evidence |
|---|---|---|
| 3 × `github/codeql-action/upload-sarif@v3` on main, incl. P0 #2511's failing-step class | **RESOLVED — zero `@v3` anywhere** | `grep -rn "codeql-action" .github/` → 0 hits; repo-wide yml sweep → all three surfaces at **@v4**: `core/.github/workflows/ci.yml:124`, `core/action.yml:80`, `docs/ci-templates/ci-core-pyerrorfix-guard.yml:10` |
| v3 EOL Dec 2026; v4 live since 2025-10-07 (Node 24) | EOL class retired in-repo | the @v4 refs landed on main via PR #2809 (commit 29d1e6d, 2026-10-30 03:03+06) |
| Prescription: @v4 upgrade + retain tolerate flag on the nightly upload step | both elements satisfied in-mirror | ci.yml step keeps `if: always()` above the @v4 upload; the private-side nightly failure class was retired by the #2522 RCA lane — core-repo cadence green per the landed #2529 r+1 receipt (run 41033596302 success 2026-10-30 09:27:44Z) |

## 2. Method

Fresh clone at origin/main 1571bc4; repo-wide grep for `codeql-action` across `.github/`, `core/`, `docs/ci-templates/`; issue 2544 activity read — the two issue-referencing commits (55aaee9, e4cd365) never landed on main; main carries the fix via #2809 instead. Read-only besides this receipt; the #2544 lease released immediately after submission.

## 3. Disposition

Per the STALE-INCIDENT GUARD (resolved incidents are skipped with evidence, never re-solved): **no in-envelope residual work exists** — the scout itself scoped all three paths as `.github/**`/admin surfaces (bridge-protected handoff package, not a patch) and the remedy already landed. The org-wide `codeql-action@v3` sweep across other satellites stays an admin-side item. No `Closes` line is emitted — closure stays with the verdict plane; the R69 radar row can be marked adopted by the next radar pass.
