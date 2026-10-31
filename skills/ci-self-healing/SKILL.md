---
name: ci-self-healing
description: Diagnose failing builds and tests, search prior incidents, propose or implement a safe fix, and rerun verification.
triggers: [ci failure, build broken, test failing, self-healing, pipeline red]
permission_level: write
memory_policy: write
owner: supremeai-skills
verification_required: true
evidence_requirements: [failing log excerpt, root cause, patch, rerun result]
idempotency: one repair attempt per failure signature
stop_conditions: [bounded retries exhausted, high-risk change without approval]
---

# CI Failure & Self-Healing

## Purpose
Diagnose failing builds and tests, search prior incidents, propose or implement a safe fix, and rerun verification.

## Loop
Failure event -> classify -> inspect logs -> retrieve memory -> patch or issue -> verify -> record result.

## Safety
Bounded retries; no endless repair loops; avoid repeating an unsuccessful patch; request approval for high-risk changes.

## Existing implementation
CI watcher in `infrastructure/mcp-control-plane` (federated_ci_watcher) and `scripts/agents/self_healing_reporter.py`. This skill provides the reusable procedure and metadata contract.