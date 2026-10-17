# SupremeAI Core — Proprietary Decision Moat

Deterministic task DAG planner, agent finite state machine (FSM), role arbiter, and context budget synthesizer.

## Architecture

```text
┌────────────────────────────────────────────────────────┐
│                   SUPREMEAI-CORE                       │
│                                                        │
│   ├── state_machine.py       (Deterministic Agent FSM) │
│   ├── dag_planner.py         (Acyclic Task Graph)      │
│   ├── decision_engine.py     (Role Arbiter & Scope)    │
│   └── context_synthesizer.py (Token Diet & Budgets)    │
└────────────────────────────────────────────────────────┘
```

## Modules

- **`AgentStateMachine` (`state_machine.py`):** Pure state machine managing transitions across `IDLE`, `PLANNING`, `CLAIMED`, `EXECUTING`, `VERIFYING`, `TERMINATED`, `REJECTED` with an immutable transition audit trail.
- **`DAGPlanner` (`dag_planner.py`):** Task dependency graph resolver. Decomposes high-level missions into atomic subtasks, verifies DAG acyclicity using Kahn's algorithm, and computes parallel execution tiers.
- **`DecisionEngine` (`decision_engine.py`):** Determines role specialization (`Coder`, `Scout`, `Auditor`, `Breaker`) and enforces scope-path and risk-tier governance.
- **`ContextSynthesizer` (`context_synthesizer.py`):** Hierarchical context budgeter enforcing the 3-stage progressive disclosure contract (Discovery < 1000 tokens, Activation < 4000 tokens, Full < 16000 tokens).
