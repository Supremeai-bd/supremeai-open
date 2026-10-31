---
name: task-planner-scope-manager
description: Break a task into small verifiable steps, select skills and tools, define acceptance criteria, and stop when scope is exceeded.
triggers: [plan task, scope management, breakdown, acceptance criteria]
permission_level: read
memory_policy: read
owner: supremeai-skills
verification_required: true
evidence_requirements: [plan, dependencies, risks, verification steps]
idempotency: one plan per task id
stop_conditions: [scope exceeded, budget exceeded]
---

# Task Planner & Scope Manager

## Purpose
Break a task into small verifiable steps, select Skills and tools, define acceptance criteria, and stop when scope is exceeded.

## Output
Plan, dependencies, risks, budget/time bounds, verification steps, and approval gates.

## Keep simple
Prefer short plans and adaptive replanning over elaborate fixed multi-agent handoff trees.

## Existing implementation
`core/dag_planner.py` (topological sort) + `core/decision_engine.py`. This skill documents the procedure and metadata contract.