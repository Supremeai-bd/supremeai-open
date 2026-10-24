---
id: customer-api-spec
subject: "Customer API Specification — /api/v1/projects & /api/v1/agent/task"
document_role: architecture
planning_authority: Customer Experience Circle + C5 (Execution)
status: proposed
target_scope: customer_facing
canonical: candidate
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
depends_on:
  - docs/plans/architecture/SUPREMEAI_MASTER_PLAN_CANONICAL.md
  - docs/plans/features/Plan_01_Dynamic_AI_Agent_System.md
  - docs/plans/features/Plan_09_Smart_Data_Storage.md
implements:
  - Customer-facing REST API contracts for project creation, agent task dispatch, and result retrieval
  - Tenant-isolated request routing with RBAC scopes (customer_user, tenant_admin)
  - Zero-password Mode 3 authentication headers
supersedes: []
superseded_by: []
---

# Customer API Specification

**Status:** proposed  
**Scope:** Customer-visible REST API contracts for `/api/v1/projects` and `/api/v1/agent/task`

---

## 1. Purpose

Define the complete customer-facing API surface that end-users and tenant applications consume. These endpoints are the only public interface to SupremeAI's execution engine from a customer perspective.

---

## 2. Endpoints

### 2.1 `POST /api/v1/projects`

Create a new customer project/workspace.

**Request:**
```json
{
  "name": "string",
  "description": "string",
  "tags": ["string"],
  "mode3_session_token": "string | null"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "string",
  "status": "active",
  "created_at": "ISO8601"
}
```

### 2.2 `POST /api/v1/agent/task`

Dispatch an agent task within a project.

**Request:**
```json
{
  "project_id": "uuid",
  "prompt": "string",
  "agent_profile": "string | null",
  "callback_url": "string | null"
}
```

**Response:** `202 Accepted`
```json
{
  "task_id": "uuid",
  "status": "queued",
  "estimated_completion": "ISO8601"
}
```

### 2.3 `GET /api/v1/agent/task/{task_id}`

Poll for task completion.

**Response:** `200 OK`
```json
{
  "task_id": "uuid",
  "status": "completed | failed | in_progress",
  "result": "object | null",
  "error": "string | null"
}
```

---

## 3. Authentication

- **Mode 3 (Session-Only Ephemeral):** Short-lived bearer tokens issued per browser session. No persistent passwords.
- **Mode 1/2 (API Key):** `X-API-Key` header with tenant-scoped key rotation.
- All requests MUST include `X-Tenant-ID` for multi-tenant isolation.

---

## 4. Rate Limits

| Tier | Requests/min | Burst |
|------|-------------|-------|
| Free | 10 | 20 |
| Pro | 100 | 200 |
| Enterprise | 1000 | 2000 |

---

## 5. Out of Scope

- Admin-only endpoints (`/admin-api/*`)
- Internal MCP Control Tower tools
- Browser automation configuration

---

## 6. Acceptance Criteria

- [ ] OpenAPI 3.1 spec generated from code
- [ ] Tenant isolation verified via integration test
- [ ] Rate-limit headers returned on every response
- [ ] Mode 3 session token expiry ≤ 15 minutes
