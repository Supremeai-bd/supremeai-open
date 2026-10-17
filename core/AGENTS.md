# SupremeAI Core Intelligence Moat — AGENTS.md

> **Governing Constitution for Supremeai-bd/supremeai-core**
>
> **Freedom:** Core algorithmic modules govern deterministic planning, state transitions, and role arbitration.
> **Control:** Admin/System controls **GOALS, ROLES, LIMITS, ARBITRATION POLICIES and ARCHITECTURAL BOUNDARIES**.

## 1. Proprietary Boundary Mandate

1. **Zero External I/O:** The `core/` package consists strictly of pure algorithmic modules (FSM transitions, DAG solvers, context synthesizers, role arbiters). No database drivers, cloud network calls, or external secrets.
2. **Deterministic Invariant:** Given identical input graphs and state transitions, the core engine must return byte-identical execution plans without random jitter.
3. **Fail-Closed Cycle Detection:** Any detected dependency cycle in a task DAG is an operational halt (fail-closed); the engine never guesses order across cyclical dependencies.
