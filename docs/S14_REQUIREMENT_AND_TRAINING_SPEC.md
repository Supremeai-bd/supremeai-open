# S14 — Requirements Understanding, Audit Playbook & Training Curriculum SSOT

Companion to `AGENTS.md` / `AGENT_RULES.md` and `FEDERATION_SPECS_SSOT.md`.

## 1. Overview & Components

This specification provides the institutional intelligence framework for SupremeAI:
1. Understanding human requirements across multi-tenant boundaries.
2. Self-auditing codebases and MCP control planes without destructive side effects.
3. Training autonomous agents with character, security discipline, and verifiable evidence.

| Component | File Path | Primary Function |
|---|---|---|
| **Requirements KB (Concept)** | [`requirement-understanding-kb.md`](./requirement-understanding-kb.md) | 7 truths of human requirements, 5-stage intake cycle, 3-tier memory reuse model. |
| **Requirements KB (Schema)** | [`requirement-understanding-kb.json`](./requirement-understanding-kb.json) | `requirement_intake_schema`, ambiguity triggers, clarification question bank, prompt templates. |
| **Audit Playbook** | [`audit-process.json`](./audit-process.json) | 6-phase audit lifecycle, strict read-only safety rules, known pitfalls, 7-point smoke checklist. |
| **Training Curriculum** | [`supremeai-training-curriculum.json`](./supremeai-training-curriculum.json) | 10 Core Values, 4-stage progression (Foundation, Core, Pro, Mastery), exam bank, codebase anchors. |
| **Live Audit Report** | [`supremeai-audit-report-bn.md`](./supremeai-audit-report-bn.md) | Current codebase and services audit scorecard (Bengali). |

## 2. Invariants & Rules

- **Tenant Isolation:** No customer requirement or context can ever cross into another tenant's retrieval (`tenant_id` filter is mandatory).
- **Evidence First:** Claims require tool outputs or file:line citations; unproven claims are rejected.
- **Fail-Closed Security:** In any trade-off between security, speed, and features, security wins.
- **Single Source of Truth:** Centralized in Supabase (`knowledge_base`, `learned_facts`) and Qdrant (`supremeai_documents`, `supremeai_memory`).
