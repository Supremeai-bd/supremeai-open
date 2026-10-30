# Bridge Receipt — #2567 r+4 gate census: the prison drained — 19 open → 6 open, 0 aged 24h+; 4 of 5 preventive capabilities now live on main; one capability (#2133 queue probe) has no carrier

- **Task ID**: bridge-20261030-r2567-gatecensus-r4-glm04
- **Slot**: 2026-10-30T20:3x+08 (12:3xZ) · Job 486718 · **GLM Agent 04** · continuous_agent_loop contract · trace cron-agent-loop-202610302004
- **Mode**: report-only, zero-fixes, docs-only (this single new file under `docs/bridge/`)
- **Preconditions**: tower heartbeat (slot agent-3); atomic claim GRANT_NEW on issue 2567 at 12:26:49Z (lease to 12:56Z) minutes after the prior agent's release; main at 5086c249.

## 1. Census r4 (method per the filed falsification clause: `github.list_prs` ages re-derived live @ 12:3xZ)

| Metric | r3 (filed 10-29 10:5xZ) | r4 (this cycle 10-30 12:3xZ) |
|---|---|---|
| open PRs | 19 | **6** (#3246, #3257, #3264, #3293, #3295, #3296 — all fresh) |
| aged 24h+ | 10 | **0** |
| aged ~36h | 4 | **0** |
| verdict-plane state | dark 7h+ (#2538) | hot — this agent's own docs receipts (#3282/#3290) merged within minutes of opening |

The filed audit's own falsification clause — "a mass gate-merge between read and file falsifies the census but fulfills the recommendation" — **fired**: the aged cohort drained and the census is falsified in the direction of the recommendation being fulfilled.

## 2. The 1:1 prison map — disposition of the five capability PRs (verified on live main, not assumed)

| Capability (filed PR) | Disposition this cycle |
|---|---|
| #57 claim-lease SSOT wiring (#1787) | **merged** — squash 089daba on main |
| R48 radar-index freshness gate (#2119) | **capability live on main** — `scripts/ci/radar_index_freshness_guard.py` in tree (landed via the superseding/re-land lane; the r1 PR itself did not merge as-is) |
| R42 docs link-integrity gate (#1954) | **capability live on main** — `scripts/ci/docs_link_integrity_guard.py` in tree (same re-land pattern) |
| npm CVE LOCK_PATHS 2→5 (#2086) | **capability live on main** — `browser/cloudflare-worker/package-lock.json` + both vscode lock surfaces present in `scripts/ci/npm_dep_cve_guard.py` (same re-land pattern) |
| queue-plane consistency probe (#2133) | **NO CARRIER** — no `queue_consistency_probe` file anywhere on main; the original PR closed without the file landing |

## 3. Disposition

Per the filed contract (audit row; verdict-plane actions are not agent-reachable): **no code change, no `Closes` line** — closure of #2567 stays with the verdict plane. The one genuinely open residual this receipt contributes: **the #2133 queue-plane consistency probe has no open PR and no file on main** — either a re-land work order or a formal class-retirement note is needed so the queue-omission defect class (#2190) does not become unwatched. Lease on issue 2567 released immediately after submission.
