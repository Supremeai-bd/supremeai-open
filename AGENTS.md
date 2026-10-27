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
   Run `python scripts/agents/continuous_agent_loop.py --loop`. The loop self-executes:  
   `SCAN (master_health_check --full) → CLAIM (Golden 8 Anchor Hubs) → FIX → VERIFY → PR`.

---

## 📜 The Guardrails (Must Follow vs Must Avoid)

Everything required to govern execution is codified in [`AGENT_RULES.md`](./AGENT_RULES.md) (Single Source of Operational Policy & Self-Interrogation):

- **MUST FOLLOW:**
  - **U4 / SSOT:** Work strictly under the 8 Anchor Hubs (#749–#762) as Sub-Issues.
  - **U5:** Dual-Rebase (rebase `origin/main` at work-start AND pre-push). Atomic claim before branch.
  - **U13:** Domain Mirror Invariant (`studio/*` → Studio, `gateway/*` → API, `core/*` → Core).
  - **U15 / P3:** Law of Superior Replacement & Value Triad. Discard broken legacy code/tests rather than hacking new code to appease past mistakes.
- **MUST AVOID:**
  - **NO Direct Push:** Never push directly to satellites or protected branches without PR gate.
  - **NO Root Shadowing:** Never put satellite code in repo root (`src/*`, `service/*`, `packages/*`).
  - **NO Ghost Fixes or Symptom Swallowing:** Never mask errors or fix issues not reproduced on live `main`.

**Beyond these guardrails, you have absolute freedom on HOW to solve your task. Never ask for permission.**
