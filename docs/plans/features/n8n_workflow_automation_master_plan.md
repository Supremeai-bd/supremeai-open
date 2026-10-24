---
target_scope: customer_facing
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:n8n_workflow_automation_master_plan
subject: SupremeAI + n8n Integration Master Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI + n8n Integration Master Plan

**Project:** SupremeAI  
**Repository:** `SaifulHaqueNiloy/supremeai`  
**Purpose:** Integrate n8n as a secure automation/integration layer without replacing SupremeAI's core AI-agent runtime.

---

## 1. Executive Decision

### Decision

**Integrate n8n into SupremeAI as an Automation & Integration Layer.**

Do **not** replace the existing SupremeAI Agent Runtime, Memory, HITL, Security, provider routing, or core business logic with n8n.

### Target architecture

```text
                         SUPREMEAI PLATFORM
                                |
             +------------------+------------------+
             |                  |                  |
          Frontend          SupremeAI Core       n8n
             |                  |                  |
        Dashboards           AI Agents         Automation
        Chat                 Memory            Webhooks
        Admin                Tools             Schedules
        Users                HITL              Integrations
                             Security           Notifications
                             Providers
                                |
                         PostgreSQL / Redis
```

---

## 2. Current Codebase Finding

The current repository already contains **partial n8n integration**.

`backend/tools/api_gateway.py` contains:

- `N8N_URL` environment-variable resolution.
- Local fallback to `http://127.0.0.1:5678`.
- `InternalGateway.trigger_n8n_workflow()`.
- `POST /api/v1/gateway/n8n`.
- HTTP-based triggering of n8n workflows.
- Existing Make.com webhook support beside n8n.

However, the current codebase does not yet represent n8n as a complete first-class automation subsystem.

### Current state

```text
n8n connectivity       YES
n8n trigger helper     YES
n8n gateway endpoint   YES
Workflow registry      NOT YET
Event bus              NOT YET
Secure workflow map    NOT YET
Execution tracking     NOT YET
Admin automation UI    NOT YET
Retry/dead-letter      NOT YET
First-class deployment NOT YET
```

---

# 3. Architectural Principle

## SupremeAI owns intelligence

SupremeAI should remain responsible for:

- AI agent execution
- Agent orchestration
- LLM/provider routing
- Provider/account rotation
- Memory
- Tool execution
- HITL
- Security policy
- RBAC
- Authentication
- Authorization
- Audit logging
- Core business rules
- Conversation state
- AI-specific validation

## n8n owns automation

n8n should primarily handle:

- Scheduled workflows
- Webhook workflows
- External integrations
- Notifications
- Third-party API orchestration
- Repetitive business automation
- Event-driven automation
- Background integration workflows
- Email/Telegram/Slack/GitHub/etc. workflows
- Multi-step external processes

---

# 4. Target Integration Model

```text
SupremeAI Event
      |
      v
Automation/Event Gateway
      |
      v
Workflow Registry
      |
      +---- Authentication
      +---- Authorization
      +---- Validation
      +---- Idempotency
      +---- Audit
      |
      v
n8n Webhook
      |
      v
n8n Workflow
      |
      +---- External services
      +---- Notifications
      +---- SupremeAI APIs
      +---- Conditional logic
      |
      v
Execution Result
      |
      v
SupremeAI Audit / Event Log
```

---

# 5. Phase 0 — Discovery & Safety Audit

Before implementation, inspect the entire repository for existing:

- n8n references
- Make.com integrations
- webhook endpoints
- background workers
- Celery/RQ/Arq/task queues
- cron/scheduler code
- notification services
- Telegram integrations
- email integrations
- GitHub integrations
- event models
- audit models
- Redis usage
- environment configuration
- deployment configuration
- Docker Compose services

### Deliverable

Create:

```text
docs/architecture/N8N_CURRENT_STATE_AUDIT.md
```

Document:

- Existing integration points
- Duplicate automation systems
- Existing schedulers
- Existing webhook infrastructure
- Security risks
- Recommended migration boundaries

---

# 6. Phase 1 — Secure n8n Gateway

The existing `/gateway/n8n` implementation should evolve into a controlled internal integration layer.

## Do NOT allow

```text
POST /gateway/n8n

{
  "webhook_path": "arbitrary-user-controlled-path"
}
```

This should not become a generic SSRF-style webhook proxy.

## Instead use logical workflow names

Example:

```json
{
  "event": "HITL_REQUIRED",
  "payload": {
    "approval_id": "...",
    "agent_id": "...",
    "risk_level": "high"
  }
}
```

Backend resolves:

```text
HITL_REQUIRED
    |
    v
registered workflow
    |
    v
n8n webhook
```

---

# 7. Workflow Registry

Create a server-side registry.

Suggested location:

```text
backend/core/automation/
```

Suggested modules:

```text
backend/core/automation/
├── __init__.py
├── models.py
├── registry.py
├── dispatcher.py
├── security.py
├── retry.py
├── idempotency.py
├── audit.py
└── events.py
```

## Example registry concept

```python
WORKFLOWS = {
    "HITL_REQUIRED": {
        "webhook": "...",
        "enabled": True,
        "timeout_seconds": 15,
        "max_retries": 3,
    },
    "SECURITY_ALERT": {
        "webhook": "...",
        "enabled": True,
        "timeout_seconds": 15,
        "max_retries": 3,
    },
}
```

Do not expose raw webhook URLs to normal users.

---

# 8. Event Taxonomy

Introduce standardized SupremeAI automation events.

## Initial events

```text
USER_REGISTERED
USER_DISABLED
AGENT_CREATED
AGENT_UPDATED
AGENT_EXECUTION_STARTED
AGENT_EXECUTION_COMPLETED
AGENT_EXECUTION_FAILED

HITL_REQUIRED
HITL_APPROVED
HITL_REJECTED
HITL_EXPIRED

SECURITY_ALERT
SECURITY_POLICY_VIOLATION

PROVIDER_RATE_LIMITED
PROVIDER_FAILED
PROVIDER_RECOVERED

USAGE_LIMIT_REACHED
COST_THRESHOLD_REACHED

PAYMENT_SUCCESS
PAYMENT_FAILED

SYSTEM_HEALTH_DEGRADED
SYSTEM_HEALTH_RECOVERED
```

---

# 9. Event Envelope

All outbound automation events should use a standard envelope.

Example:

```json
{
  "event_id": "uuid",
  "event_type": "HITL_REQUIRED",
  "version": "1",
  "timestamp": "ISO-8601",
  "source": "supremeai",
  "environment": "production",
  "actor": {
    "type": "agent",
    "id": "..."
  },
  "tenant_id": "...",
  "payload": {},
  "trace_id": "..."
}
```

Benefits:

- Traceability
- Idempotency
- Debugging
- Versioning
- Multi-tenant safety
- Auditability

---

# 10. Authentication & Security

n8n must never be treated as a trusted public endpoint.

Implement:

### Required

- Header-based secret or signed webhook authentication
- TLS in production
- Secret storage through environment/secret manager
- Workflow allowlist
- Event allowlist
- RBAC for workflow administration
- Request validation
- Payload size limits
- Timeout
- Rate limiting
- Audit logs
- Idempotency
- Retry limits

### Recommended

Use a signing model:

```text
X-SupremeAI-Event
X-SupremeAI-Timestamp
X-SupremeAI-Signature
X-SupremeAI-Event-ID
```

Signature should be calculated over:

```text
timestamp + event_id + body
```

and verified by the receiver.

---

# 11. Prevent Replay Attacks

Every event should contain:

```text
event_id
timestamp
```

Reject:

- expired timestamps
- duplicated event IDs
- malformed signatures

Recommended replay window:

```text
5 minutes
```

The exact value should be configurable.

---

# 12. Idempotency

n8n workflows can be retried, so SupremeAI must assume duplicate delivery.

Use:

```text
event_id
```

as the idempotency key.

Example:

```text
HITL_REQUIRED
event_id = abc123

first delivery -> process
second delivery -> ignore/already processed
```

---

# 13. Reliability Model

Do not make n8n a hard dependency for core AI execution.

### Correct

```text
User
 |
 v
SupremeAI Agent
 |
 v
Core result
 |
 +---- automation event -> n8n
```

If n8n is down:

```text
Agent execution = SUCCESS
Automation event = RETRY / QUEUE
```

### Incorrect

```text
Agent
 |
 v
n8n
 |
 X
n8n unavailable
 |
 v
Agent fails
```

Core AI functionality must remain operational when automation is unavailable.

---

# 14. Retry Strategy

Implement bounded retries.

Suggested defaults:

```text
Attempt 1: immediate
Attempt 2: +2 sec
Attempt 3: +10 sec
Attempt 4: +30 sec
```

Maximum retry count should be configurable.

After exhaustion:

```text
Dead-letter / failed automation record
```

and optionally trigger:

```text
AUTOMATION_FAILURE
```

---

# 15. Execution Tracking

Create persistent automation execution records.

Suggested model:

```text
automation_executions
```

Fields:

```text
id
event_id
workflow_key
status
attempt
started_at
completed_at
duration_ms
http_status
error_code
error_message
trace_id
created_at
```

Statuses:

```text
PENDING
RUNNING
SUCCESS
FAILED
RETRYING
DEAD_LETTER
CANCELLED
```

---

# 16. Admin Dashboard — Automation Center

Add a first-class Automation section.

## Recommended navigation

```text
Admin
├── Overview
├── Users
├── Agents
├── Security
├── HITL
├── Providers
├── Usage
├── Automations
│   ├── Workflows
│   ├── Executions
│   ├── Failed
│   ├── Templates
│   └── Settings
└── System
```

---

# 17. Automation Dashboard

Show:

```text
AUTOMATION OVERVIEW

Active Workflows
Successful Runs
Failed Runs
Retrying
Dead Letter
Average Duration
Last Execution
```

Example:

```text
+---------------------------------------+
| Automations                            |
+---------------------------------------+
| Active Workflows       12              |
| Runs Today             842            |
| Success Rate           99.1%          |
| Failed                  7             |
+---------------------------------------+
```

---

# 18. Workflow List

Columns:

```text
Name
Event
Status
Last Run
Success Rate
Avg Duration
Failures
Updated
```

Actions:

```text
View
Enable
Disable
Test
Run
View Executions
```

---

# 19. Execution Explorer

Admin should be able to inspect:

```text
Execution ID
Workflow
Event ID
Trigger
Status
Duration
Attempt
Timestamp
Trace ID
Error
```

Provide a detailed timeline:

```text
Event Created
    ↓
Dispatched
    ↓
Authenticated
    ↓
n8n Accepted
    ↓
Workflow Started
    ↓
External API
    ↓
Workflow Completed
```

---

# 20. First Production Workflows

Implement these first.

## Workflow 1 — HITL Notification

```text
HITL_REQUIRED
      ↓
n8n
      ↓
Determine severity
      ↓
Telegram / Email / Slack
      ↓
Admin
```

---

## Workflow 2 — Security Alert

```text
SECURITY_ALERT
      ↓
n8n
      ↓
Severity check
      ↓
Notify security/admin
      ↓
Create incident record
```

---

## Workflow 3 — Provider Rate Limit Alert

```text
PROVIDER_RATE_LIMITED
      ↓
n8n
      ↓
Provider details
      ↓
Notify admin
```

---

## Workflow 4 — Daily Usage Report

```text
Schedule
   ↓
SupremeAI usage API
   ↓
Aggregate usage
   ↓
Generate report
   ↓
Email / Telegram
```

---

## Workflow 5 — Weekly Health Report

```text
Schedule
   ↓
Health APIs
   ↓
Database metrics
   ↓
Provider status
   ↓
AI-generated summary
   ↓
Admin report
```

---

## Workflow 6 — New User Onboarding

```text
USER_REGISTERED
      ↓
Create onboarding state
      ↓
Send welcome message
      ↓
Notify internal system
```

---

# 21. GitHub Automation

Later phase:

```text
GitHub PR
   ↓
n8n
   ↓
SupremeAI Code Agent
   ↓
Analyze
   ↓
Security / Quality Report
   ↓
GitHub Comment
```

Possible events:

```text
PR_OPENED
PR_UPDATED
ISSUE_CREATED
ISSUE_LABELED
RELEASE_CREATED
```

Do not allow an external workflow to bypass SupremeAI's authorization model.

---

# 22. Telegram Automation

Use n8n for integration-heavy flows.

Example:

```text
Telegram
   ↓
n8n
   ↓
SupremeAI API
   ↓
Agent
   ↓
Response
   ↓
Telegram
```

Keep authentication and authorization in SupremeAI.

---

# 23. Scheduled AI Automation

Use n8n for recurring tasks such as:

```text
Daily research
Weekly reports
Usage monitoring
Health checks
Knowledge refresh
Content generation
Notification
Maintenance workflows
```

The schedule should not become part of the core agent runtime unless there is a strong business reason.

---

# 24. Deployment Architecture

Recommended:

```text
                    Internet
                       |
                Reverse Proxy / TLS
                       |
          +------------+------------+
          |                         |
       Frontend                  Backend
       Firebase                 Render/etc.
                                    |
                          +---------+---------+
                          |                   |
                       Database             n8n
                                            |
                                     External Services
```

n8n should be deployed separately from FastAPI.

Do not embed n8n inside the FastAPI process.

---

# 25. Environment Configuration

Add documented variables such as:

```env
N8N_ENABLED=true
N8N_BASE_URL=https://n8n.example.com
N8N_WEBHOOK_SECRET=...
N8N_TIMEOUT_SECONDS=15
N8N_MAX_RETRIES=3
N8N_RETRY_BACKOFF=true
N8N_VERIFY_TLS=true
N8N_EVENT_DELIVERY_ENABLED=true
```

Use the project's existing configuration system rather than scattered `os.environ` access wherever practical.

---

# 26. Configuration Refactor

The existing n8n URL resolution in:

```text
backend/tools/api_gateway.py
```

should eventually move toward centralized configuration.

Preferred:

```text
settings.n8n_enabled
settings.n8n_base_url
settings.n8n_timeout
settings.n8n_webhook_secret
```

Then the gateway consumes `settings`.

---

# 27. API Design

Recommended internal APIs:

```text
POST /api/v1/automation/events
GET  /api/v1/automation/workflows
GET  /api/v1/automation/executions
GET  /api/v1/automation/executions/{id}
POST /api/v1/automation/workflows/{key}/test
POST /api/v1/automation/workflows/{key}/enable
POST /api/v1/automation/workflows/{key}/disable
POST /api/v1/automation/workflows/{key}/run
```

Admin-only APIs must enforce existing RBAC.

---

# 28. Workflow Templates

Create official SupremeAI workflow templates.

Initial template catalog:

```text
HITL Alert
Security Alert
Provider Alert
Daily Usage Report
Weekly Health Report
New User Onboarding
Agent Failure Notification
Cost Threshold Alert
```

Templates should be versioned.

---

# 29. Observability

Integrate n8n executions into SupremeAI observability.

Track:

```text
event_id
workflow_key
execution_id
trace_id
duration
status
retry_count
error
```

Where possible, correlate:

```text
SupremeAI trace
        |
        +--- n8n execution
                  |
                  +--- external API call
```

This is especially important because SupremeAI already targets production observability.

---

# 30. Audit Logging

Automation administration is security-sensitive.

Audit:

```text
workflow created
workflow enabled
workflow disabled
workflow tested
workflow manually executed
workflow configuration changed
automation failed
automation retried
dead-letter created
```

Store actor information:

```text
admin_user_id
action
workflow
timestamp
IP/device metadata where appropriate
```

---

# 31. Multi-Tenant Safety

If SupremeAI supports multiple organizations/tenants, every automation event must carry:

```text
tenant_id
```

Never allow:

```text
Tenant A event
      ↓
Tenant B workflow/data
```

n8n workflows must not become an authorization bypass.

SupremeAI remains the authority for access control.

---

# 32. Data Privacy

Do not blindly send full AI conversations or sensitive records to n8n.

Prefer minimal event payloads.

Instead of:

```json
{
  "entire_conversation": "...",
  "all_user_data": "..."
}
```

prefer:

```json
{
  "event_id": "...",
  "user_id": "...",
  "agent_id": "...",
  "risk_level": "high",
  "resource_id": "..."
}
```

n8n can call an authenticated SupremeAI API to retrieve additional information if authorized.

---

# 33. What NOT to Move to n8n

Do not move these to n8n merely for convenience:

```text
Authentication
Authorization
RBAC
Core agent loop
Memory engine
HITL decision engine
LLM provider routing
API key rotation
Security policy engine
Core database business logic
Conversation state
Critical transaction logic
```

These belong in SupremeAI.

---

# 34. What SHOULD Move to n8n

Good candidates:

```text
Notifications
Email
Telegram
Slack
GitHub integrations
Scheduled reports
Webhook automations
Third-party SaaS integrations
Routine synchronization
External API chains
Operational alerts
Recurring workflows
```

---

# 35. Migration Strategy

Do not rewrite existing automation systems immediately.

### Step 1

Keep current systems working.

### Step 2

Add n8n beside them.

### Step 3

Introduce standardized automation events.

### Step 4

Move simple integrations to n8n.

### Step 5

Measure reliability.

### Step 6

Gradually retire duplicate automation code where n8n clearly provides better maintainability.

---

# 36. Make.com Relationship

The current gateway also supports Make.com.

Do not immediately delete it.

Instead:

```text
Automation Provider
├── n8n
└── Make.com (legacy/optional)
```

Eventually decide whether Make.com is still necessary.

The long-term preferred architecture should avoid having multiple overlapping automation platforms unless there is a concrete business requirement.

---

# 37. Testing Strategy

## Unit tests

Test:

```text
workflow registry
event validation
signature validation
idempotency
retry logic
timeout handling
configuration
RBAC
```

## Integration tests

Test:

```text
SupremeAI → n8n webhook
n8n → SupremeAI API
n8n unavailable
n8n timeout
n8n 401
n8n 429
n8n 500
duplicate event
expired signature
invalid signature
```

## End-to-end

Test:

```text
HITL_REQUIRED
   ↓
n8n
   ↓
notification
```

and:

```text
SECURITY_ALERT
   ↓
n8n
   ↓
admin notification
```

---

# 38. Failure Scenarios

The system must explicitly handle:

### n8n unavailable

```text
Core operation succeeds
Automation queued/retried
```

### n8n timeout

```text
Retry
```

### n8n authentication failure

```text
Do not endlessly retry
Create critical configuration error
```

### n8n workflow failure

```text
Record execution failure
Notify admin if configured
```

### Duplicate event

```text
Return/idempotently ignore
```

---

# 39. Performance Rules

Do not synchronously wait for n8n for every core AI action.

Prefer:

```text
Core operation
    ↓
Commit result
    ↓
Emit event
    ↓
Async automation
```

This keeps user-facing AI latency low.

For operations where a workflow result is genuinely required, explicitly mark them as synchronous and enforce strict timeout limits.

---

# 40. Security Checklist

Before production:

- [ ] n8n HTTPS enabled
- [ ] Webhook authentication enabled
- [ ] Secrets not committed
- [ ] No arbitrary webhook URL forwarding
- [ ] Workflow allowlist implemented
- [ ] Event allowlist implemented
- [ ] Payload validation implemented
- [ ] Payload size limits implemented
- [ ] Rate limits implemented
- [ ] Replay protection implemented
- [ ] Idempotency implemented
- [ ] Retry limits implemented
- [ ] Audit logging implemented
- [ ] RBAC implemented
- [ ] Tenant isolation verified
- [ ] TLS verification enabled
- [ ] Sensitive payload minimization implemented

---

# 41. Implementation Order

Use this exact order.

## Sprint 1 — Foundation

```text
1. Repository audit
2. Central n8n configuration
3. Automation module
4. Workflow registry
5. Event schema
6. Secure dispatcher
7. Unit tests
```

## Sprint 2 — Reliability

```text
8. Idempotency
9. Retry
10. Timeout
11. Execution tracking
12. Failure/dead-letter handling
13. Audit integration
14. Integration tests
```

## Sprint 3 — First Workflows

```text
15. HITL notification
16. Security alert
17. Provider alert
18. Daily usage report
19. Weekly health report
20. User onboarding
```

## Sprint 4 — Admin UI

```text
21. Automation navigation
22. Workflow list
23. Execution explorer
24. Failure dashboard
25. Workflow controls
26. Test/run interface
27. Metrics
```

## Sprint 5 — Advanced Integrations

```text
28. GitHub
29. Telegram
30. Email
31. Additional SaaS integrations
32. AI-assisted workflow templates
```

---

# 42. Suggested Repository Structure

Target structure:

```text
supremeai/
├── backend/
│   ├── api/
│   ├── brain/
│   ├── core/
│   │   ├── automation/
│   │   │   ├── __init__.py
│   │   │   ├── events.py
│   │   │   ├── models.py
│   │   │   ├── registry.py
│   │   │   ├── dispatcher.py
│   │   │   ├── security.py
│   │   │   ├── retry.py
│   │   │   ├── idempotency.py
│   │   │   └── audit.py
│   │   └── ...
│   ├── tools/
│   └── tests/
│       └── automation/
│
├── frontend/
│   └── src/
│       ├── features/
│       │   └── automations/
│       └── ...
│
├── n8n/
│   ├── workflows/
│   ├── templates/
│   └── README.md
│
└── docs/
    └── architecture/
        ├── N8N_CURRENT_STATE_AUDIT.md
        └── N8N_INTEGRATION_MASTER_PLAN.md
```

Do not commit production secrets or exported workflow credentials.

---

# 43. Definition of Done

n8n integration is considered production-ready only when:

### Architecture

- [ ] n8n is a separate service
- [ ] SupremeAI remains the source of truth for core logic
- [ ] n8n is an automation layer

### Security

- [ ] Authenticated webhooks
- [ ] No arbitrary webhook forwarding
- [ ] RBAC
- [ ] Audit
- [ ] Replay protection
- [ ] Idempotency

### Reliability

- [ ] Timeout
- [ ] Retry
- [ ] Dead-letter/failure state
- [ ] n8n outage does not break core AI

### Observability

- [ ] Execution tracking
- [ ] Trace correlation
- [ ] Admin visibility
- [ ] Failure alerts

### UX

- [ ] Automation Center
- [ ] Workflow status
- [ ] Execution history
- [ ] Failure inspection

### Operations

- [ ] Documented deployment
- [ ] Environment variables
- [ ] Backup/recovery strategy
- [ ] Workflow versioning
- [ ] Tested upgrade path

---

# 44. Final Architectural Recommendation

The target relationship should be:

```text
                     USER
                      |
                      v
                SUPREMEAI UI
                      |
                      v
              SUPREMEAI BACKEND
                      |
          +-----------+-----------+
          |                       |
          v                       v
     AI CORE / AGENTS          EVENT BUS
          |                       |
          |                 +-----+------+
          |                 |            |
          |                 v            v
          |                n8n       Audit/Logs
          |                 |
          |        +--------+--------+
          |        |        |        |
          v        v        v        v
       Memory   GitHub   Telegram   Email
       HITL     APIs     Slack      SaaS
       Tools
       Security
       Providers
```

### Strategic goal

SupremeAI should become the **AI intelligence and secure execution platform**.

n8n should become the **automation and integration fabric around it**.

That separation gives SupremeAI:

- More integrations
- Faster automation development
- Less custom integration code
- Better scheduled workflows
- Better notification capabilities
- Better external API orchestration
- Better admin automation
- Lower maintenance cost
- A cleaner long-term architecture

while preserving SupremeAI's strongest differentiators:

- AI agents
- memory
- HITL
- security
- provider management
- orchestration
- enterprise controls

---

# 45. AI Coding Agent Execution Rules

Any AI coding agent implementing this plan MUST follow these rules:

1. Inspect the existing code before changing anything.
2. Do not rewrite functioning SupremeAI subsystems unnecessarily.
3. Do not introduce n8n as a replacement for the Agent Runtime.
4. Reuse existing authentication, RBAC, configuration, logging, audit, and database patterns.
5. Never expose arbitrary n8n webhook URLs to untrusted users.
6. Never hard-code secrets.
7. Preserve backward compatibility for the existing `/gateway/n8n` integration unless migration is explicitly completed.
8. Add tests for every security-sensitive behavior.
9. Keep n8n failure isolated from core AI execution.
10. Prefer asynchronous event delivery for non-critical automation.
11. Use idempotent event processing.
12. Add observability to every automation execution.
13. Update documentation alongside implementation.
14. Do not remove Make.com support until its replacement is proven and migration is explicitly approved.
15. Run existing test suites before and after implementation.
16. Do not mark a task complete merely because the code compiles; verify runtime behavior.
17. Never commit credentials, tokens, webhook secrets, or private n8n exports.
18. Preserve tenant isolation and authorization boundaries.
19. Keep the integration modular so n8n can be disabled without breaking SupremeAI core functionality.
20. Prefer small, reviewable commits over a single massive refactor.

---

# 46. Success Criteria

The integration is successful when an administrator can:

```text
Create/enable/disable automation
        ↓
Observe executions
        ↓
Inspect failures
        ↓
Retry failed workflows
        ↓
Trace an automation back to a SupremeAI event
```

while an end user can continue using:

```text
Chat
Agents
Memory
Tools
HITL
AI providers
```

even if n8n is temporarily offline.

**Core principle:**

> **n8n should extend SupremeAI, not become SupremeAI.**