---
name: provider-pool-failover
description: Give agents a stable logical capability while infrastructure selects a healthy configured account/provider.
triggers: [provider pool, failover, account rotation, capability routing]
permission_level: read
memory_policy: read
owner: supremeai-skills
verification_required: true
evidence_requirements: [selected alias, latency, outcome]
idempotency: selection per request
stop_conditions: [no eligible account, quota exhausted]
---

# Provider Pool & Failover

## Purpose
Give agents a stable logical capability while infrastructure selects a healthy configured account/provider.

## Example
Agent requests `cache`; the capability layer selects an eligible account and handles retry/failover.

## Requirements
Health state, quota awareness, circuit breaker, backoff, account cooldown, idempotency, audit trail, and admin override.

## Important
Do not rotate accounts to evade provider restrictions or limits. Respect each provider's terms and quotas.

## Existing implementation
`gateway/capability_router.py` (new) + `gateway/provider_chain.py`. This skill documents the procedure and metadata contract.