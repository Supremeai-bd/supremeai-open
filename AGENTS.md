# SupremeAI — AGENTS.md

> **The Universal Agent Constitution (Single Door SSOT)**  
> **Freedom:** Agent controls **HOW** to solve any task inside its contract.  
> **Control:** Admin/System controls **WHERE, WHAT, ACCESS, LIMITS, STOPPING**.  
> **Zero-Admin Target:** Work budget ≤ 0.01% · **The loop is the permission (U10).**

---

## 🚪 The Single Door: Soul & Engine of SupremeAI Agents

All agents live, enter, and execute through exactly two unified pillars:

1. **The Life & Senses — MCP Control Tower:**  
   Zero-credential proxy hub providing context, tools, and actions (`https://supremeai-mcp-tower.onrender.com/mcp`).
2. **The Soul & Engine — Continuous Autonomous Loop:**  
   Run `python scripts/agents/continuous_agent_loop.py`. The loop self-dispatches:  
   - Inspects board for unclaimed issues -> dispatches `solver`.  
   - Checks role cadence timers -> dispatches scheduled routine role.  
   - Directly injects the 5 Universal Invariants and role mandate into execution.

---

> **Operating System (the two-sided guarantee in action):** the step-by-step
> verification ladder, the harm-containment map, and the self-healing /
> self-evolving flywheel that keep this constitution alive:
> [`docs/AGENT_OPERATING_SYSTEM.md`](docs/AGENT_OPERATING_SYSTEM.md)

## 📜 The 5 Universal Invariants (Must Follow vs Must Avoid)

- **MUST FOLLOW:**
  1. **Dual-Rebase & 14-Anchor Continuity:** Rebase `origin/main` at work-start AND pre-push (0 behind). Strictly 14 Anchor Hubs (#749–#762: 12 domain satellites + 2 federation desks, notably including `#749` [supremeai-studio](https://github.com/Supremeai-bd/supremeai-studio), `#750` [supremeai-api](https://github.com/Supremeai-bd/supremeai-api), `#756` [supremeai-browser](https://github.com/Supremeai-bd/supremeai-browser), `#3782` CI Intelligence Desk, and `#3783` Bridge Desk). Anchor Hubs are permanent architectural governance desks. Routine CI/lane failures NEVER spawn sub-issues or duplicate work orders; failures are labeled strictly in-place (`ci-failed`, `status:unclaimed`) on the failing PR and linked issue. Sub-issues attach strictly for genuine domain feature tasks or systemic architectural remediation.
  2. **Boundary:** Satellite code lives strictly in its approved domain mirror (`studio/*`, `gateway/*`, `core/*`, `browser/*`, `vscode/*`).
  3. **Superior Replacement:** Discard broken legacy code/tests rather than hacking new code to appease past mistakes. Work must tangibly benefit Machine, Admin, or User.
  4. **Verification & PR Blueprint:** 3-Tier Verify (Reflection -> Smoke -> Tests). PRs must carry `Closes #N` and `## Reflection Evidence (why + alternatives_rejected)`.
  5. **P0 Drainage & Anti-Stampede Invariant:** Open architectural blockers (`P0-critical`) supersede all speculative research, routine audits, and lower-priority work. Agents and Bridge pipelines MUST verify idempotency (zero duplicate work orders, zero duplicate issues/PRs for the same task/branch) before filing or claiming.
  6. **Zero-Recurrence Invariant (Anti-Regression & Continuous Learning):** Every identified mistake, defect, false closure, or contract violation MUST have an automated mechanical guard or test written against it. A mistake once discovered and remediated MUST NEVER recur. Machine enforcement supersedes human vigilance.
  7. **Loop-Driven Determinism:** Agents NEVER guess, speculate, or arbitrarily pick tasks. The continuous autonomous loop (`continuous_agent_loop.py`) is the sole SSOT for task assignment, dispatching, and role constraints. "The loop is the permission (U10)."
  8. **Universal Defect Ownership & Anti-Blindspot Invariant:** Whenever an agent discovers, uncovers, or observes ANY unhandled defect, pipeline failure (such as failed unmerged PRs or silent gate rejections), architectural blindspot, or unowned failure anywhere in the federation during execution, the agent MUST NEVER ignore, bypass, or silently discard it. The agent must record, claim, or surface an actionable structured work order with proper deduplication before considering its cycle complete. Avoidance of discovered defects is strictly prohibited.
  9. **Full-Scope Completeness Invariant (End-to-End Implementation):** Agents (specifically `solver`, `coder`, `ci-fixer`) MUST NEVER deliver half-done or partial solutions. When a task requires database changes, schema migrations, environment configurations, security rules (RLS), or API wiring, the agent MUST write and submit the migration/config files as part of the exact same patch or PR. Leaving database schemas unmigrated, configs unmapped, or tests unwritten while marking a task "fixed" or "complete" is strictly prohibited.
- **MUST AVOID:**
  - **NO Direct Push:** Never push directly to satellites or protected branches without PR gate.
  - **NO Root Shadowing:** Never put satellite code in repo root (`src/*`, `service/*`, `packages/*`).
  - **NO Ghost Fixes:** Never mask errors or fix issues not reproduced on live `main`.
  - **NO Incomplete / Half-Baked Submissions:** Never claim a task or bug is resolved when the underlying database migration, configuration, or integration dependency remains missing or unapplied.
  - **NO Backlog Starvation / Duplicate Stampede:** Never bypass open P0 blockers to create or pick up fast-follow research tickets, and never spawn duplicate PRs/work orders for the same task.
  - **NO Speculative Dispatch:** Never manually claim or work on issues outside the loop's dispatch envelope.
  - **NO Defect Avoidance / Blindspot Bypassing:** Never observe a broken pipeline, failed unmerged PR, or system defect and walk away without mechanical recording or remediation.

**Beyond these guardrails, you have absolute freedom on HOW to solve your task. Never ask for permission.**

---

## 🌐 External Agent Hybrid Invariant

External web agents (Devin, OpenHands, custom runners) participate through the
hybrid bridge contract. The following rules are non-negotiable:

- **READ Boundary:** External web agents MAY read the codebase, history, and
  issue tracking through the direct `github-reader` MCP (`get_issue`,
  `get_file_contents`, `search_repositories`). Read access is read-only.
- **Single Write Gateway (Enforced):** No external agent may commit to GitHub
  or open a direct PR. Every code change MUST arrive through the Tower's
  `bridge_submit` / `bridge_submit_patch` API (`taskId`, `files`, `summary`,
  `reflectionWhy`, `alternativesRejected`, `testsEvidence`, `agentIdentity`).
- **Stale-Base Pin (fail-closed CAS gate — #3487, PR #3513):** for
  `full_file` on a path that already exists, always pin the CURRENT landed
  blob sha as `files[].baseSha` (`git rev-parse HEAD:<path>` on a freshly
  rebased tree). The gate is **fail-closed**: a stale `baseSha` is rejected
  with `STALE_BASE_ERROR`; an existing path with **no declared `baseSha`** is
  rejected with `STALE_BASE_MISSING`; an unverifiable main read rejects with
  `STALE_BASE_UNVERIFIED`; only a **brand-new path** (absent on main) may omit
  it. This closes the fail-open vector that let #3404's stale landing revert
  co-landed work (#3438 burn trail).
- **Credential Zero-Leak Rule:** No agent may print or expose GitHub tokens or
  secrets in plaintext in console output or prompt logs. Secrets are loaded
  from Infisical into memory only (`GITHUB_READONLY_TOKEN`).

### Tool Routing Contract

- **Rule 1 (Intel / Reading):** Use only `github-reader` tools (`get_issue`,
  `get_file_contents`, `search_repositories`) for GitHub issues, file contents,
  discussions, and history.
- **Rule 2 (Submission / PR):** Never call direct GitHub push tools. Send code
  changes through the Tower `bridge_submit` / `bridge_submit_patch` API with
  `taskId`, `files`, `summary`, `reflectionWhy`, `alternativesRejected`,
  `testsEvidence`, `agentIdentity`, and per-file `baseSha` pinned to the
  current blob (see Stale-Base Pin above).
- **Rule 3 (Infrastructure Health):** Use only Tower tools such as
  `supabase_schema_inspect` and `render_service_health` for database, cache, or
  deployment status.
- **Rule 4 (Payload Shape Conventions — the false-null trap):** the Tower's
  github list adapters emit **camelCase** keys (`createdAt`, `updatedAt`,
  `mergedAt`, `closedAt`), and list-mode rows omit `body` / `labels` / `head` /
  `draft` and the `merged` boolean; only single-PR addressability
  (`github.list_prs` with `pull_number`, landed for #3368) returns the full
  truth shape (`merged: true|false` plus timestamps). Probing list rows with
  GitHub-REST snake_case (`merged_at`, `pull_request.merged_at`) reads a
  **FALSE NULL** on merged PRs — live-proven 2026-10-31: eleven
  squash-landed PRs (#3460..#3522, verified on `origin/main`) carry the
  correct camelCase `mergedAt` while snake_case probes read null. Landing
  verification ("did my WO's paired PR merge?") MUST use `pull_number`
  addressability or `git log origin/main` — never a list-mode snake_case
  probe (Refs #3523).
## Push Mode Policy (Anti-Regression)

- **Prefer patch over full_file.** Use `bridge_submit_patch` for existing files.
- **full_file is allowed ONLY for brand-new paths** (absent on main).
- **full_file on existing paths requires baseSha CAS** (stale-base check).
- This reduces regression risk: patches are smaller, targeted, and conflict-detectable.
- Agents MUST NOT use full_file to overwrite large files when a patch suffices.
## Stale PR Fix Workflow (No Force-Push)

When a PR fails CI due to stale base (Autonomous Auto-Landing / Stale-Base Guard):

1. Fetch the PR branch: git fetch origin <branch>
2. Create worktree: git worktree add <path> origin/<branch>
3. Merge main (NOT rebase): git merge origin/main --no-edit
4. Resolve conflicts: deleted file in main -> git rm <file>; others -> resolve + git add
5. Commit merge: git commit --no-verify --no-edit
6. Push (no force, no verify): git push origin HEAD:<branch> --no-verify
7. Cleanup: git worktree remove <path> --force

NEVER use git rebase + force push (regression risk + branch protection blocks).
NEVER use git push --force (blocked by branch protection).

Pre-submission checks (before creating PR):
- Run: python scripts/ci/pr_preflight_guard.py --branch <name> --files <changed> --pr-body <file>
- pre-commit hook runs automatically on commit (branch naming, boundary, lint, parity)

When to use which:
- New work: git checkout -b feat/<slug>, commit, push (pre-commit guards run)
- Stale PR fix: merge + push --no-verify (above workflow)
- Failed PR audit: loop reports failing PRs; ci-fixer marks existing issue as ci-failed
- Close PR: only if superseded or invalid branch name (document reason)
