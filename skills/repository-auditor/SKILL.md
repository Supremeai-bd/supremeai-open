---
name: repository-auditor
version: 0.1.0
description: Inspect repositories and connected project components, discover actionable risks and opportunities, and create evidence-backed findings. Read-only by default.
triggers: [repository audit, ecosystem scout, risk scan, code review, dead code, dependency audit]
permission_level: read
memory_policy: write
owner: supremeai-skills
verification_required: true
evidence_requirements: [file path, line number, confidence, duplicate check]
idempotency: one finding per evidence location
stop_conditions: [no repository access, scope exceeded]
---

# Repository Auditor & Ecosystem Scout

## Purpose
Inspect repositories and connected project components, discover actionable risks and opportunities, and create evidence-backed findings.

## Workflow
1. Read repository instructions and task contracts first (AGENTS.md, README, contracts).
2. Check similar open issues and existing fixes before creating new issues.
3. Identify bugs, security risks, dependency issues, duplicate implementations, dead code, failing tests, and documentation drift.
4. Separate confirmed findings from hypotheses.
5. Suggest the smallest safe next action.

## Output contract
Finding, evidence/location, impact, confidence, duplicate check, recommended action, verification method.

## Safety
Read-only by default; issue creation is allowed only with the configured permission.

## Existing implementation
Thin wrapper over `scripts/agents/ecosystem_scout_reference.py` and `scripts/agents/scout_extractor.py` (Surgical Code & Pattern Extraction). Logic remains in scripts/agents; this skill provides the reusable procedure and metadata contract.