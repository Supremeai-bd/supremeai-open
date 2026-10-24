---
id: tenant-workspace-architecture
subject: "Tenant Workspace Architecture — Isolated Customer Environments"
document_role: architecture
planning_authority: Customer Experience Circle + Data Circle (C3)
status: proposed
target_scope: customer_facing
canonical: candidate
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
depends_on:
  - docs/plans/features/customer_api_spec.md
  - docs/plans/features/Plan_09_Smart_Data_Storage.md
  - docs/plans/features/antihacking_security_defense_framework.md
implements:
  - Tenant-isolated workspace runtime for customer projects
  - Row-level security (RLS) enforcement at database layer
  - Workspace-scoped file storage and agent execution sandbox
supersedes: []
superseded_by: []
---

# Tenant Workspace Architecture

**Status:** proposed  
**Scope:** Customer tenant workspace isolation, storage, and execution boundaries

---

## 1. Purpose

Provide each tenant/customer with an isolated workspace environment where their projects, files, agent executions, and data remain completely segregated from other tenants.

---

## 2. Isolation Boundaries

### 2.1 Database Layer

- **Row-Level Security (RLS):** Every Supabase table includes `tenant_id` with RLS policies
- **Connection pooling:** Separate connection pools per tenant tier (Free/Pro/Enterprise)
- **Migration safety:** Schema changes apply globally; data remains tenant-scoped

### 2.2 Storage Layer

- **Supabase Storage:** Tenant-prefixed paths: `tenant_{id}/projects/{project_id}/...`
- **Cache isolation:** Redis keys prefixed with `tenant:{id}:`
- **Vector isolation:** Qdrant collections scoped per tenant or shared with payload filters

### 2.3 Execution Layer

- **Agent execution sandbox:** Each tenant task runs in isolated Docker container or namespace
- **Resource quotas:** CPU/memory limits per tenant tier
- **Network isolation:** Tenant sandboxes cannot reach other tenants' resources

---

## 3. Workspace Model

```
Tenant
  └── Projects (N)
        ├── Files
        ├── Agent Runs
        ├── Integrations
        └── Settings
```

---

## 4. Multi-Tenancy Patterns

| Pattern | Implementation | Trade-off |
|---------|---------------|-----------|
| Shared DB + RLS | Supabase Postgres with RLS policies | Cost-efficient, requires strict policy enforcement |
| Schema per tenant | Separate Postgres schema per tenant | Stronger isolation, higher migration cost |
| Database per tenant | Separate Supabase project per tenant | Maximum isolation, highest cost |

**Selected:** Shared DB + RLS for Free/Pro; Schema per tenant for Enterprise.

---

## 5. Acceptance Criteria

- [ ] RLS policies cover all customer-facing tables
- [ ] Cross-tenant data access returns 403 in integration tests
- [ ] Workspace provisioning completes within 30 seconds
- [ ] Tenant deletion removes all associated data within 24 hours

---

## 6. Out of Scope

- Admin-level cross-tenant observability (Layer 1 concern)
- Platform resource arbitrage (Layer 1 concern)
- Internal browser pool credential sharing (Layer 1 concern)
