---
name: security-secret-hygiene
description: Detect exposed credentials, unsafe configuration, overbroad permissions, and risky changes.
triggers: [secret scan, security audit, credential leak, permission review]
permission_level: read
memory_policy: read
owner: supremeai-skills
verification_required: true
evidence_requirements: [file path, secret type, remediation]
idempotency: one finding per location
stop_conditions: [no repository access]
---

# Security & Secret Hygiene

## Purpose
Detect exposed credentials, unsafe configuration, overbroad permissions, and risky changes.

## Important distinction
A Skill may detect and recommend remediation, but the actual authorization and secret isolation must be enforced by the security layer, not by prompt instructions alone.

## Existing implementation
gitleaks config (.gitleaks.toml), fail-closed webhook HMAC, protected paths. This skill documents the procedure and metadata contract.