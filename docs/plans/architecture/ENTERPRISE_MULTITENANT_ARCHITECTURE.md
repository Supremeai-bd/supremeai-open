---
id: enterprise-multitenant-architecture
subject: "SupremeAI Enterprise Multi-Tenant & Dual-Driven Architecture (Timeless Standard)"
document_role: architecture
planning_authority: Architecture Circle
canonical: true
status: active
target_scope: combined_ecosystem
evidence_state: verified
disposition: retain
last_verified: 2026-09-18
---

# SupremeAI Enterprise Multi-Tenant Architecture (Timeless Living Standard)

> **Core Law:** One Unified Intelligence Engine, Two First-Class Operational Planes (Admin & Customer), Strict Multi-Tenant Data Isolation, and Complete Infrastructure Sovereignty. Valid today, in 100 days, or 1000 days later.

---

## 1. The Dual-Driven Operational Planes

SupremeAI is neither an internal admin debugging console nor an oversimplified customer toy. It operates two distinct, purpose-built operational planes backed by identical core intelligence:

| Dimension | Customer / Tenant User Plane | Platform Admin / Operator Plane |
|---|---|---|
| **Core Intent** | Goal-driven task execution, app building, code generation, self-service projects. | Fleet health monitoring, policy governance, HITL approvals, telemetry, resource orchestration. |
| **API Boundary** | `/api/v1/projects`, `/api/v1/runs`, `/api/v1/agent/task`, `/api/v1/integrations` | `/admin-api/*`, MCP Control Tower Hub, system telemetry endpoints. |
| **UX Surface** | Progressive disclosure, clean minimalist IDE/chat/workspace, zero infrastructure friction. | 3D system topology, live log streams, audit trails, tenant management, kill-switch console. |
| **Compute Choice** | Self-hosted local machine, BYOK (Bring Your Own Keys), or platform-managed worker. | Enterprise private servers, on-prem bare-metal clusters, or free/cloud rotation pools. |

---

## 2. Multi-Tenant Invariants (The Non-Negotiables)

1. **Strict Cryptographic & Database Isolation:**
   - Database level Row-Level Security (RLS) is strictly enforced on all queries with mandatory `tenant_id` binding.
   - Vector embeddings, session caches (SQLite/Redis), and cold memory (Parquet/Qdrant) must never allow cross-tenant leakage.
2. **Deterministic Role-Based Access Control (RBAC):**
   - `customer_user`: Scoped strictly to own tenant workspace and authorized resources.
   - `tenant_admin`: Manages team seats, project quotas, and tenant-level API credentials.
   - `super_admin`: Platform-wide governance, security kill-switch, and global infrastructure orchestration.
3. **User-Intent & Infrastructure Agnosticism:**
   - An enterprise customer can deploy on private Kubernetes clusters or self-hosted bare metal.
   - A community customer can run locally on laptop silicon or $0 free-tier compute.
   - The platform never forces or locks a tenant to any single cloud provider.
4. **Zero Silent Weakening:**
   - Admin actions never silently compromise customer data privacy.
   - Customer actions can never escalate privilege to access host system secrets or peer tenant workspaces.
5. **Auditable Traceability:**
   - Every tenant mutation, run execution, and admin override leaves an immutable, cryptographically timestamped audit log.

---

## 3. Execution Lifecycle Across Actors

```text
Actor Request (Customer or Admin)
       │
       ▼
JWT & RBAC Scope Validation (Fail-Closed)
       │
       ▼
Tenant Boundary Resolution (tenant_id binding)
       │
       ▼
Resource & Quota Placement (Local / BYOK / Cluster / Free-Tier)
       │
       ▼
Canonical Run Execution (`backend/runs/`)
       │
       ▼
Output Verification & Invariant Check (SECURITY_GUARDIAN)
       │
       ▼
Isolated State Persistence (RLS Database + Tenant Memory)
```

---

## 4. Why This Architecture Survives 1000 Days

- **Technology Independent:** Whether authentication uses JWT today or Passkeys tomorrow, the *Auth Boundary & Tenant Isolation* invariant remains identical.
- **Database Independent:** Whether storage is PostgreSQL/Supabase today or decentralized graph stores tomorrow, the *Tenant Scope Resolution* remains identical.
- **Compute Independent:** Whether compute is Kaggle/Render today or private Edge Silicons tomorrow, the *Zero-Waste User-Intent* invariant remains identical.
