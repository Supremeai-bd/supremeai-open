---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:codebase_aligned_master_roadmap
subject: SupremeAI — Current Codebase-Aligned Master Roadmap
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Current Codebase-Aligned Master Roadmap

**Repository:** `SaifulHaqueNiloy/supremeai`  
**Branch:** `main`  
**Purpose:** align the long-term autonomous-platform roadmap with the actual current codebase and avoid rebuild/duplication.

## 1. Executive Verdict

The existing SupremeAI roadmap is directionally correct. The current repository already contains substantial pieces of the target platform: FastAPI + React/Vite, PostgreSQL/pgvector, JWT/RBAC, HITL/tool-policy controls, agent orchestration, memory/files/workspaces, automation/n8n abstractions, MCP tooling, observability, CI/CD and deployment tooling.

Therefore this is a **delta/hardening roadmap, not a rebuild roadmap**.

Core strategy:

> **Stabilize → Simplify → Unify → Extract → Govern → Automate → Evolve**

The north-star architecture remains:

```text
Unified Frontend
  User / Staff / Admin / Operations
          ↓
Authentication + RBAC
          ↓
Lean Core API
          ↓
Task Engine + Capability Registry + Control Plane
          ↓
Policy / Approval / Audit
          ↓
Worker / Scraper / External Compute / Providers
```

Principle:

> **Distributed execution, centralized control.**

---

# 2. Phase 0 — Production Stabilization
## Priority: P0 / MUST FINISH FIRST

### Objectives

- Fix startup/shutdown lifecycle issues.
- Make DB behavior deterministic.
- Make CI results trustworthy.
- Resolve critical container vulnerabilities.
- Remove runtime schema-creation behavior.
- Fix Redis/test-environment noise.
- Make production health verification real.
- Keep Core lightweight.

### Tasks

1. DB/session lifecycle correctness.
2. Alembic as the single schema authority.
3. No production runtime `CREATE TABLE`.
4. Deterministic PostgreSQL test fixtures/schema.
5. Redis configuration/DNS/connectivity verification.
6. Resolve critical image CVEs or formally document accepted risk.
7. Fix CI deployment-trigger failures.
8. Make important audit failures visible in Smart Summary.
9. Verify model/migration drift instead of blindly generating migrations.
10. Verify production schema-contract drift.
11. Fix active YAML/ShellCheck automation errors.
12. Ensure live health checks are actually executed.

### Exit criteria

- Clean startup.
- Clean shutdown.
- Deterministic tests.
- No critical startup exceptions.
- No unreviewed critical vulnerabilities.
- CI distinguishes blocking vs advisory findings.
- Production health verification is real.

---

# 3. Phase 1 — Lean Core API
## Priority: P1

Core should contain request-serving and control responsibilities.

### Keep in Core

- authentication
- authorization
- request validation
- task creation/status
- lightweight orchestration
- capability lookup
- policy decisions
- persistence
- API/WebSocket interfaces
- lightweight telemetry

### Move out only when justified

- browser automation
- long-running jobs
- Chromium
- heavy scraping
- CPU/GPU-heavy workloads
- expensive model runtimes

Rule:

> Do not create a service simply because a folder exists.

---

# 4. Phase 2 — Execution Infrastructure

Target:

```text
Core API
  ├── Worker       → real long-running async workloads
  ├── Scraper      → browser/Chromium workloads
  └── Heavy/GPU    → external compute when justified
```

### Important

Do **not** convert the current Worker into a queue worker until actual production background workloads are inventoried.

Before introducing Celery/another queue:

1. inventory background workloads
2. choose one canonical queue
3. define task contracts
4. register real tasks
5. add dependency
6. implement retry/idempotency
7. add worker health checks
8. deploy worker

---

# 5. Phase 3 — Unified Frontend
## Priority: HIGH

Use:

> **One frontend application + role/permission-based routing.**

Target:

```text
/app
  /workspace
  /admin
  /staff
  /operations
  /settings
```

### Benefits

- one build
- one deployment
- shared auth state
- shared API client
- shared components/design system
- simpler maintenance
- easier role expansion
- lazy-loaded privileged modules

### Security rule

Frontend visibility is **not** authorization.

Backend RBAC/permissions remain the source of truth.

---

# 6. Phase 4 — Shared UI / UX

The existing UI roadmap already calls for one application shell and shared design foundation.

### Shared shell

- Header
- Sidebar/NavRail
- Command Bar
- notifications
- activity
- responsive layout
- role-aware navigation

### User Workspace

- Home
- AI Studio
- Projects
- Agents
- Files
- Memory
- Activity
- Automation
- Usage
- Integrations
- Team/Access
- Settings

### Admin Command Center

- Overview
- Topology
- Services
- Agents/Swarm
- Security
- Audit
- Incidents
- Deployments
- Reliability
- Recovery
- Tenants/RBAC
- FinOps
- RCA/Intelligence
- Configuration
- Evolution

Do not recreate capabilities that already exist.

---

# 7. Phase 5 — Capability Registry

Create one canonical capability lifecycle.

### Entities

```text
Capability
CapabilityVersion
CapabilityDependency
CapabilityPermission
CapabilityHealth
CapabilityUsage
```

### Lifecycle

```text
DISCOVER
 ↓
CHECK EXISTING
 ↓
REUSE ────────────┐
 ↓                │
ADAPT / EXTEND    │
 ↓                │
CREATE            │
 ↓                │
VALIDATE          │
 ↓                │
REGISTER          │
 ↓                │
ACTIVATE          │
 ↓                │
MEASURE           │
 ↓                │
PROMOTE / ARCHIVE ┘
```

Rule:

> **Reuse > Adapt > Extend > Create**

---

# 8. Phase 6 — Unified User Task Engine

Shared execution abstraction:

```text
Task
Plan
Step
CapabilityRequirement
Execution
Verification
Repair
Artifact
```

Execution loop:

```text
Goal
 ↓
Understand
 ↓
Plan
 ↓
Capability Check
 ↓
Resource Check
 ↓
Execute
 ↓
Verify
 ↓
Repair / Retry
 ↓
Deliver
 ↓
Measure
 ↓
Learn
```

Eventually this same engine should power user tasks, maintenance, self-healing, capability creation and deployment workflows.

---

# 9. Phase 7 — Unified Control Plane

Create one abstraction over infrastructure.

### Registries

```text
Resource Registry
Account Registry
Capability Registry
Provider Registry
Policy Registry
```

### Provider adapters

```text
Render
GitHub
Cloudflare
Supabase
Firebase
Kaggle
Redis
AI Providers
Custom
```

New providers must be addable without rewriting the core.

---

# 10. Phase 8 — SupremeAI MCP

Roll out gradually.

### Stage A — Read-only

- resources
- health
- deployments
- logs
- metrics
- capabilities

### Stage B — Controlled actions

- restart
- deploy
- rollback
- approved configuration operations

### Stage C — Approval-gated autonomy

```text
Observe
 ↓
Analyze
 ↓
Policy Check
 ↓
Risk Classification
 ↓
Approval if required
 ↓
Act
 ↓
Verify
 ↓
Audit
```

MCP must never bypass backend authorization or policy.

---

# 11. Phase 9 — Automation / n8n Hardening

Keep n8n optional for the Core AI.

Required:

- fail closed when enabled without webhook secret
- receiver-side HMAC verification
- replay protection
- idempotency
- real health checks
- retry-attempt persistence
- OpenTelemetry correlation
- admin execution/failure visibility

Do not rebuild the existing automation abstraction.

---

# 12. Phase 10 — Self-Healing

Connect existing self-healing to the common Task + Capability + Control Plane.

```text
Incident
 ↓
Detect
 ↓
Classify
 ↓
Diagnose
 ↓
Select Capability
 ↓
Policy Check
 ↓
Repair
 ↓
Verify
 ↓
Rollback if needed
 ↓
Record Learning
```

No unlimited retries.

---

# 13. Phase 11 — Capability Self-Creation

Enable only after foundation reliability is strong.

```text
Capability Gap
 ↓
Research
 ↓
Design
 ↓
Implementation
 ↓
Tests
 ↓
Security Scan
 ↓
Sandbox Validation
 ↓
Registration
 ↓
Approval if required
 ↓
Activation
 ↓
Monitoring
```

Generated capabilities must be versioned, auditable and reversible.

---

# 14. Phase 12 — Proactive Learning & Evolution

When production stability is sufficient:

```text
Observe ecosystem
 ↓
Discover technology
 ↓
Identify capability gap/opportunity
 ↓
Practicality + risk + cost analysis
 ↓
Proposal
 ↓
Approval where required
 ↓
Build
 ↓
Validate
 ↓
Register
```

Never allow unlimited autonomous dependency growth, resource creation, code changes or background activity.

---

# 15. Phase 13 — Continuous Optimization

Measure:

- task success rate
- autonomous completion rate
- verification pass rate
- repair success
- latency
- memory
- compute cost
- maintenance cost
- capability reuse
- capability creation frequency
- provider reliability
- user satisfaction

Do not optimize toward arbitrary memory targets without production measurement.

---

# 16. CI/CD Roadmap

Target:

```text
Change Detection
 ↓
Relevant Tests
 ↓
Security Scans
 ↓
Advanced Pre-Merge Audit
 ↓
Build Affected Images
 ↓
Cache
 ↓
Sign + SBOM
 ↓
Deploy Exact Artifact
 ↓
Health Check
 ↓
Smoke Test
 ↓
Smart Summary
```

Smart Summary must surface:

- job status
- blocking failures
- advisory failures
- security findings
- schema drift
- migration drift
- dependency findings
- test statistics
- coverage
- lint failures
- advanced-audit counts
- report/artifact references

Principle:

> Valuable audit findings must not remain hidden only in job logs.

---

# 17. Deployment Optimization

> **Every push ≠ rebuild everything.**

Use:

- affected-service detection
- parallel image builds
- BuildKit/GHA cache
- immutable Git SHA/digest
- build once / deploy exact artifact
- service-specific deployment
- post-deploy verification

Engineering targets from the existing CI plan:

```text
Optimized normal run: ~5–7 min
Small frontend/docs/config change: ~1–3 min
```

These are targets, not guarantees.

---

# 18. Database Strategy

Primary persistent system:

> **PostgreSQL + pgvector**

Rules:

- Alembic owns schema evolution.
- No production runtime DDL.
- Pooler/direct connection roles are explicit.
- DDL uses the appropriate writer/direct path.
- Runtime queries use the appropriate runtime path.
- SQLite remains local/test-only where justified.
- Do not remove ChromaDB/Qdrant blindly; first prove every production path and migration dependency.

---

# 19. Security Roadmap

### Identity

- JWT/session lifecycle
- RBAC
- permission scopes
- tenant isolation

### Tool security

- risk classification
- allowlists
- SSRF protection
- input validation
- sandboxing
- approval gates

### Infrastructure

- secrets through Infisical/environment injection
- no production default secrets
- internal service networking where possible
- signed images
- SBOM
- vulnerability scanning

### Audit record

```text
actor
tenant
action
resource
risk
decision
timestamp
correlation_id
result
```

---

# 20. Multi-Tenant Expansion

Target:

```text
SupremeAI Internal Tenant
Customer Tenant A
Customer Tenant B
Customer Tenant C
```

Support:

- hosted/shared MCP
- dedicated MCP
- customer-owned MCP
- hybrid/self-hosted where appropriate

Capabilities:

```text
GLOBAL
TENANT
PRIVATE
```

Credentials and resources must remain tenant-scoped.

---

# 21. What NOT to Do

Never:

- rewrite the backend without evidence
- create duplicate memory/file/workspace/billing/audit/security systems
- create a service for every folder
- add dependencies without measured need
- deploy a fake Worker
- introduce Celery before real workload inventory
- delete infrastructure blindly
- make frontend hiding the security boundary
- allow unlimited self-modification
- allow unlimited retries
- allow unlimited capability creation
- store unlimited raw logs
- hard-code provider/account counts
- deploy generated code without validation
- use fake metrics or fake execution results

---

# 22. Master Execution Order

## P0 — NOW

1. Production/runtime stabilization
2. DB lifecycle/schema correctness
3. Redis/test correctness
4. Critical security vulnerabilities
5. CI failure visibility
6. Live health verification

## P1 — FOUNDATION

7. Lean Core
8. Background workload inventory
9. Worker/Scraper separation where justified
10. Unified frontend
11. Shared UI shell
12. RBAC/permission matrix

## P2 — AUTONOMOUS PLATFORM

13. Capability Registry
14. User Task Engine
15. Execution/Verification/Repair
16. Unified Control Plane
17. Provider adapters
18. MCP read-only
19. MCP controlled actions

## P3 — AUTONOMY

20. Self-healing integration
21. Capability self-creation
22. Approval workflow
23. Proactive learning
24. Evolution

## P4 — SCALE

25. Multi-tenancy
26. Customer MCP
27. Provider/account expansion
28. Continuous optimization
29. Intelligent resource placement
30. Marketplace/ecosystem

---

# 23. Definition of Done

Every phase must report:

- current-state evidence
- existing implementation reused
- files changed
- API impact
- DB impact
- security impact
- tests run/results
- deployment verification
- performance/resource impact
- remaining gaps
- rollback plan
- documentation update

---

# 24. Final Product Definition

SupremeAI is not merely:

> “An AI chatbot with many tools.”

Target:

> **An autonomous task-execution platform that can understand a goal, discover what it requires, reuse/adapt/create capabilities, execute work, verify results, repair failures and continuously improve its capability ecosystem — while using the same machinery to operate and improve itself.**

The primary benchmark remains:

> **Can SupremeAI reliably finish the user's real task?**

Not whether it is already equal to a frontier general-purpose model.

---

## Final Strategic Rule

**Stabilize first.  
Simplify second.  
Unify third.  
Extract only where justified.  
Govern every powerful action.  
Measure everything important.  
Then enable autonomy.**