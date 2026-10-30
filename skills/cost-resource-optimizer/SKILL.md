---
name: cost-resource-optimizer
version: 0.1.0
description: Measure resource consumption, latency, failures, and provider cost; recommend evidence-based simplification.
triggers: [cost optimization, resource usage, latency, provider cost]
permission_level: read
memory_policy: write
owner: supremeai-skills
verification_required: true
evidence_requirements: [baseline metrics, before/after measurement]
idempotency: one report per measurement window
stop_conditions: [no baseline, insufficient data]
---

# Cost & Resource Optimizer

## Purpose
Measure resource consumption, latency, failures, and provider cost; recommend evidence-based simplification.

## Rule
Measure before deleting or merging services. Optimize for reliability and total operating cost, not just fewer components.

## Existing implementation
No dedicated implementation yet. This skill provides the procedure and metadata contract; instrumentation is a follow-up.