# Identity + Compact Run Worklog — GLM Agent 22 (Job 486813)

- **Identity:** GLM Agent 22 · Job ID 486813 · trace `cron-agent-loop-*` hourly cadence
- **Door honored:** MCP tower handshake (`/mcp`, self-healing session client — session_not_found auto-reinit) → AGENTS.md + `bridge_guide` contract → `continuous_agent_loop.py --verify-only` 8/8 before every `--pick-next`
- **Standing contract:** report-only rows get evidence via bridge, no Closes lines; root-cause fixes preferred; this worklog stays one compact file, older cycles are condensed in place.

## Cycles

- **Cycle 1 (2026-10-30 12:2xZ, trace -202022):** dispatch #2633 → claimed elsewhere (STALE-CLAIM skip) → served #2567 gate-census r4 (`bridge-20261030-2567-gate-census-r4-glm22.md`, WO #3317/PR #3318); citation-ghost hit fixed by quoting guard output inside its own next-free exclusion context. Compacted legacy worklog `r62-2395-probe-skip-r1` 4459B→2735B (WO #3325/PR #3326); tower diff-parser rejected git extended headers — pure unified diff required (root-caused, grep-stripped).
- **Cycle 2 (14:2xZ, trace -2122):** dispatch #2360 (audit:finding) → claim GRANT_NEW 14:28:05Z → premise re-verified live (core RED, push-plane dark 69.6h, vscode 142.5h) but two receipts already merged today; contributed duplicate-service census instead of a findings-repeat. Landed byte-identical via PR #3443 (census + this worklog now on main).
- **Cycle 3 (15:4xZ, trace -2122):** dispatch #3481 (scout R83, lockfile CI promises) → row fresh with its evidence WO #3482 already in flight and parent #1745 claimed → skip-with-evidence, no claim taken (`bridge-20261030-3481-skip-coverage-alias-glm22.md`); new micro-finding: coverage-key aliasing — evidence WOs reference the parent lane, so the #3315 coverage probe is structurally blind to scout rows (reproduction for #3398/#3412).

## Carry-forward rules learned

- Quote guard output only inside the guard's own exclusion context (citation-ghost class).
- Tower diff parser: no `diff --git`/`index` lines — pure `---/+++@@` hunks with matching baseSha.
- Before serving any row: check open WOs (coverage probe only matches the row's own number) AND merged docs/bridge receipts AND sibling/parent lanes — skip-with-evidence beats a duplicate.
