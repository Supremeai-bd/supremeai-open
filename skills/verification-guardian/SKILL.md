---
name: verification-guardian
version: 0.1.0
description: Independently verify changes before merge or release (scope, tests, regression, security, secrets, rollback).
triggers: [verify change, release guard, pre-merge check, regression check]
permission_level: read
memory_policy: read
owner: supremeai-skills
verification_required: true
evidence_requirements: [test output, scope compliance, security impact]
idempotency: one verification per change set
stop_conditions: [missing test evidence, high-risk change without approval]
---

# Verification & Release Guardian

## Purpose
Independently verify changes before merge or release.

## Checks
Scope compliance, tests, regression risk, security impact, migration safety, secrets, test evidence, and rollback.

## Important
A successful CI run is evidence, not automatic proof that a change is correct. High-risk actions require the configured human approval.

## Existing implementation
3-tier verification currently embedded in CI pipeline and `scripts/agents` guards. This skill provides the reusable procedure and metadata contract; extraction is a follow-up PR.