---
name: autonomous-developer
version: 0.1.0
description: Implement a narrowly scoped task safely with smallest suitable change, tests, and rollback approach.
triggers: [implement task, code change, fix bug, add feature, refactor]
permission_level: write
memory_policy: write
owner: supremeai-skills
verification_required: true
evidence_requirements: [changed files, test results, rollback approach]
idempotency: one branch per task id
stop_conditions: [scope exceeded, protected path touched, tests failing]
---

# Autonomous Developer

## Purpose
Implement a narrowly scoped task safely.

## Workflow
1. Read the issue, AGENTS.md, task contract, and relevant prior memory.
2. Check related issues and code paths.
3. Define scope and acceptance criteria.
4. Implement the smallest suitable change.
5. Run relevant tests, syntax checks, and build checks.
6. Report changed files, test evidence, limitations, and rollback approach.
7. Submit through the approved branch/PR or bridge workflow.

## Safety
Respect protected paths and diff limits; do not claim tests passed without actual results.

## Existing implementation
Logic lives in `scripts/agents/continuous_agent_loop.py` (monolith). This skill provides the reusable procedure and metadata contract; extraction is a follow-up PR.