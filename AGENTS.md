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
- **MUST AVOID:**
  - **NO Direct Push:** Never push directly to satellites or protected branches without PR gate.
  - **NO Root Shadowing:** Never put satellite code in repo root (`src/*`, `service/*`, `packages/*`).
  - **NO Ghost Fixes:** Never mask errors or fix issues not reproduced on live `main`.
  - **NO Backlog Starvation / Duplicate Stampede:** Never bypass open P0 blockers to create or pick up fast-follow research tickets, and never spawn duplicate PRs/work orders for the same task.

**Beyond these guardrails, you have absolute freedom on HOW to solve your task. Never ask for permission.**
