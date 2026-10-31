---
name: agent-cadence-dispatcher
description: Role-based cadence dispatcher for the SupremeAI continuous agent loop. Determines which agent roles are due to run, creates scoped full-project audit issues when the board is empty, and records per-role last_run. Thin wrapper over scripts/agents/continuous_agent_loop.py.
triggers: [cadence, agent dispatch, role schedule, empty board, audit issue]
entry: scripts/dispatch.py
permission_level: write
memory_policy: write
owner: supremeai-skills
verification_required: true
evidence_requirements: [due roles list, issue number, last_run store]
idempotency: one audit issue per empty-board tick
stop_conditions: [no repository access, scope exceeded]
---

# Agent Cadence Dispatcher

## Purpose
Decide which agent roles are due to run based on per-role cadence windows, create a
scoped full-project audit issue when the task board is empty, and record `last_run`.

## Workflow
1. Load cadence config (`scripts/agents/agent_cadence.json`).
2. Load per-role `last_run` store (`.agent_last_run.json`).
3. Compute due roles via `due_roles()`.
4. If the board is empty, create a scoped audit issue via `create_full_project_audit_issue()`.
5. Dispatch due roles (idle auditor) and record `last_run` via `mark_role_run()`.

## Output contract
Due roles list, created issue number (if any), updated last_run store.

## Safety
Fail-closed: missing config/gh/API errors are logged and never crash the loop.
Idempotent audit issue creation (one per empty-board tick).

## Existing implementation
Thin wrapper over `scripts/agents/continuous_agent_loop.py` (role-cadence + empty-board issue
creation helpers). Logic remains in scripts/agents; this skill provides reusable procedure
and metadata contract.
