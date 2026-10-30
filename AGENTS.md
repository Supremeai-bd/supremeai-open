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
  1. **Dual-Rebase:** Rebase `origin/main` at work-start AND pre-push (0 behind). Strictly 14 Anchor Hubs (#749–#762: 12 domain + 2 federation desks); all work attaches as Sub-Issues.
  2. **Boundary:** Satellite code lives strictly in its approved domain mirror (`studio/*`, `gateway/*`, `core/*`, `browser/*`, `vscode/*`).
  3. **Superior Replacement:** Discard broken legacy code/tests rather than hacking new code to appease past mistakes. Work must tangibly benefit Machine, Admin, or User.
  4. **Verification & PR Blueprint:** 3-Tier Verify (Reflection -> Smoke -> Tests). PRs must carry `Closes #N` and `## Reflection Evidence (why + alternatives_rejected)`.
  5. **P0 Drainage & Anti-Stampede Invariant:** Open architectural blockers (`P0-critical`) supersede all speculative research, routine audits, and lower-priority work. Agents and Bridge pipelines MUST verify idempotency (zero duplicate work orders, zero duplicate issues/PRs for the same task/branch) before filing or claiming.
  6. **Zero-Recurrence Invariant (Anti-Regression & Continuous Learning):** Every identified mistake, defect, false closure, or contract violation MUST have an automated mechanical guard or test written against it. A mistake once discovered and remediated MUST NEVER recur. Machine enforcement supersedes human vigilance.
  7. **Loop-Driven Determinism:** Agents NEVER guess, speculate, or arbitrarily pick tasks. The continuous autonomous loop (`continuous_agent_loop.py`) is the sole SSOT for task assignment, dispatching, and role constraints. "The loop is the permission (U10)."
  8. **Universal Defect Ownership & Anti-Blindspot Invariant:** Whenever an agent discovers, uncovers, or observes ANY unhandled defect, pipeline failure (such as failed unmerged PRs or silent gate rejections), architectural blindspot, or unowned failure anywhere in the federation during execution, the agent MUST NEVER ignore, bypass, or silently discard it. The agent must record, claim, or surface an actionable structured work order with proper deduplication before considering its cycle complete. Avoidance of discovered defects is strictly prohibited.
- **MUST AVOID:**
  - **NO Direct Push:** Never push directly to satellites or protected branches without PR gate.
  - **NO Root Shadowing:** Never put satellite code in repo root (`src/*`, `service/*`, `packages/*`).
  - **NO Ghost Fixes:** Never mask errors or fix issues not reproduced on live `main`.
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
- **Stale-Base Pin (enforced by the tower's #2333 pre-land check):** for
  `full_file` on a path that already exists, always pin the CURRENT landed
  blob sha as `files[].baseSha` (`git rev-parse HEAD:<path>` on a freshly
  rebased tree). A stale `baseSha` is rejected with `STALE_BASE_ERROR`; an
  absent `baseSha` proceeds **unchecked** (fail-open) — the exact vector that
  let #3404's stale landing revert co-landed work (#3438 burn trail).
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
