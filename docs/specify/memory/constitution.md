# SupremeAI Engineering Constitution

Spec-Driven Development (SDD) principles for the SupremeAI platform.

**Scope.** This constitution governs feature/engineering decisions made through
the Spec Kit workflow (`.specify/`, `specs/`, `/speckit.*` commands). It does not
replace `AGENTS.md` (AI-agent operating behavior), `README.md` (project overview),
or `CONTRIBUTING.md` (contribution process) — it composes with them, and must not
contradict them. If a conflict is found, stop and resolve it before implementation.

All principles use RFC-2119 language: **MUST** = non-negotiable, **SHOULD** =
strongly expected, deviations require a documented, evidence-based decision.

---

## Core Principles

### Principle I — Core Independence

SupremeAI Core MUST remain independent from optional third-party providers.

Evidence: README architecture separates the backend core from "AI Provider
(OpenAI/Compatible)" external services; provider absence is a configuration state,
not a runtime failure.

### Principle II — Security & HITL

Authentication, authorization, tenant isolation, auditability and Human-in-the-Loop
(HITL) approval MUST NOT be bypassed by feature implementations or external
integrations.

Evidence: `AGENTS.md` HITL Guidelines; README Enterprise Security (RBAC, HITL,
audit logging). No spec, plan, or task may design around these boundaries.

### Principle III — Graceful Degradation

Optional provider/integration failure MUST NOT unnecessarily break core AI
functionality.

Evidence: `AGENTS.md` Core Principle 5 ("Graceful Degradation"); circuit-breaker
and fallback behavior documented in README.

### Principle IV — Dynamic Production Configuration

Production deployment identity, endpoints, secrets and service selection MUST come
from environment/secret-management configuration (environment variables / Infisical)
rather than hardcoded application values.

Evidence: existing dynamic-configuration direction and free-tier deployment model
(Supabase/Render/Vercel). The invariant is:
`change service → change environment/Infisical → rebuild/redeploy → same application source`.

### Principle V — User-Local AI Is Optional

User-local Ollama MUST remain an optional user capability and MUST NOT become a
backend availability dependency.

Evidence: local-execution is a user-controlled privacy feature; backend health and
availability MUST NOT depend on it.

### Principle VI — Existing Architecture First

A new dependency/component MUST solve a verified gap and MUST NOT duplicate an
existing capability without an evidence-based decision.

Evidence: `CONTRIBUTING.md` review process; existing FastAPI / React/Vite /
PostgreSQL+pgvector / Redis-abstraction / OpenTelemetry stack is the default.

### Principle VII — Multi-Tenant Safety

Changes handling customer/user data MUST preserve tenant/user isolation and
authorization boundaries.

Evidence: `AGENTS.md` Safety Protocols (input validation, output sanitization);
RBAC model (user, admin, agent_operator).

### Principle VIII — Verification Before Completion

Tests, security checks, contract checks and convergence review are part of
implementation, not optional follow-up work.

Evidence: `CONTRIBUTING.md` testing guidelines and PR process; Spec Kit
`/speckit.analyze` (pre-implementation) and `/speckit.converge`
(post-implementation) gates.

### Principle IX — Vendor Exit Path

External integrations SHOULD be isolated behind project-owned interfaces/adapters
and remain replaceable.

Evidence: provider-agnostic "OpenAI-compatible APIs" integration model in README.

### Principle X — Resource Awareness

Implementations MUST respect current free-tier resource constraints and avoid
unnecessary process, cache or service multiplication.

Evidence: README "Zero-Cost Friendly" (free-tier compatibility, optimized resource
usage); no new runtime service/database/deployment dependency may be introduced by
development tooling (Spec Kit included).

---

## Additional Constraints

### Security Rules for Spec Artifacts

Spec files (`spec.md`, `plan.md`, `tasks.md`, checklists) are repository artifacts
and MUST NOT contain API keys, secrets, passwords, private credentials, production
tokens, or Infisical secret values. Referencing configuration by name is correct
(e.g. "Use `N8N_BASE_URL` from deployment configuration"); embedding its value is
prohibited.

### Configuration Classification

Every feature plan MUST identify whether new configuration is: `required`,
`optional`, `conditional`, `secret`, `public`, `runtime`, or `build-time`. This
prevents hardcoded deployment values from re-entering the codebase.

### Multi-Tenant Data Questions

Every spec touching customer data MUST explicitly answer: tenant scope, user scope,
resource owner, shared resources, cross-tenant access policy, cache-key scope,
storage-key scope, audit scope, and telemetry scope.

### AI/LLM Feature Constraints

Every AI feature spec MUST document model requirements, optional provider
requirements, fallback behavior, token/resource limits, privacy mode, tool
permissions, HITL requirements and observability policy. A missing optional
provider key MUST surface as `NOT_CONFIGURED`, never as a system failure.

### User-Local Ollama Constraints

Any feature using local Ollama MUST declare: Ollama is optional; the backend works
without it; local execution is user-controlled; cloud fallback behavior is defined;
private local content does not automatically leave the device.

---

## Development Workflow & Quality Gates

### Feature Classification

| Class | Examples | Process |
|---|---|---|
| **A — Tiny** | copy change, small CSS fix, simple typo | Normal PR process (no SDD) |
| **B — Bounded Feature** | new UI module, new API endpoint, provider adapter, storage feature | `specify → plan → tasks → implement → converge` |
| **C — Production/Architecture** | multi-tenancy, billing, auth/RBAC, new third-party platform, database/deployment architecture, major memory/reliability work | Full SDD (constitution → specify → clarify → checklist → plan → tasks → analyze → implement → converge) |

### Gate Chain for Class C

constitution check → specification → clarification → requirement checklist →
architecture plan → tasks → analyze → implementation → tests/security/CI →
converge → human review → merge/deploy.

### CI Policy

CI does NOT run Spec Kit commands per-PR. Standard PRs run existing
tests/lint/typecheck/build/security checks. Major-feature PRs additionally verify
spec artifacts exist and were reviewed. No AI-generated semantic interpretation
inside CI until the process stabilizes.

### Persistence Model

**Flow-forward / historical feature records** for major features: implemented
feature directories under `specs/NNN-name/` are retained as traceable history;
future major changes get a new numbered feature. Do not delete historical feature
artifacts.

---

## Governance

- This constitution is the authority for SDD engineering principles on SupremeAI;
  `AGENTS.md` remains the authority for AI-agent operating behavior. Neither may
  be weakened to bypass the other.
- Amendments require: documented rationale, human review approval, and a version
  bump in the footer below.
- All PRs and reviews MUST verify compliance with Core Principles I–X.
- Complexity and new dependencies MUST be justified against Principle VI and X.
- Spec Kit CLI version is pinned (see `docs/SPEC_KIT_ADOPTION.md`); upgrades are
  reviewed before adoption.

**Version**: 1.0.0 | **Ratified**: 2026-08-29 | **Last Amended**: 2026-08-29
