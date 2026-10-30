---
name: documentation-contract-keeper
version: 0.1.0
description: Update docs, schemas, examples, and integration contracts when implementation changes.
triggers: [update docs, api contract, schema drift, documentation]
permission_level: write
memory_policy: read
owner: supremeai-skills
verification_required: true
evidence_requirements: [changed doc paths, schema diff]
idempotency: one doc update per code change
stop_conditions: [no implementation change, breaking contract change]
---

# Documentation & API Contract Keeper

## Purpose
Update docs, schemas, examples, and integration contracts when implementation changes.

## Benefit
Reduces drift between code, tool descriptions, and actual behavior.

## Existing implementation
api-schemas/ mirror and docs/ in supremeai-open. This skill provides the reusable procedure and metadata contract.