---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:curated_open_source_components_integration_plan
subject: SupremeAI — Carefully Selected Open-Source Components
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Carefully Selected Open-Source Components
## Updated Implementation Plan — Post-Integration Audit

**Repository:** `SaifulHaqueNiloy/supremeai`  
**Branch audited:** `main`  
**Latest audited commit:** `f5a8957b7f4f3aac51f9925200a712f72846a40f`  
**Latest commit:** `feat(integration): implement vendor-independent automation, storage and messaging layers`

---

## 1. Executive Update

The previous open-source integration plan has now been **partially implemented in the codebase**.

The latest implementation already introduces:

- Vendor-independent automation interface/dispatcher
- n8n adapter
- Central workflow registry
- Vendor-neutral automation event/result models
- Automation execution persistence model
- Admin automation workflow endpoint
- Vendor-independent storage interface/dispatcher
- Appwrite storage adapter
- Local storage fallback
- Vendor-independent messaging interface/dispatcher
- Mock messaging fallback
- New integration configuration flags
- Secret handling for n8n/Appwrite credentials
- Automation unit tests

The current direction is therefore correct:

```text
SupremeAI Core
      |
Project-owned interfaces
      |
Adapters
      |
Optional open-source components
```

The remaining work should focus on **hardening, real runtime integration, observability, fallback behavior, testing, and avoiding duplicated/unused dependencies**.

---

# 2. Current Status Snapshot

| Component | Current status | Recommendation |
|---|---|---|
| OpenAPI | Already present | Harden governance/CI |
| OpenTelemetry | Already present in dependencies/config | Consolidate and productionize |
| n8n | Adapter + registry + config implemented | Finish reliability + runtime/event adoption |
| Appwrite | Storage adapter implemented | Keep optional; do not migrate core DB/auth |
| Storage abstraction | Implemented | Audit existing storage callers and migrate safely |
| Messaging abstraction | Implemented | Replace mock only when a real provider is justified |
| Mem0 | Adapter already exists | Keep optional; improve real persistence/fallback semantics |
| Graphiti | Adapter already exists | Keep optional; fix async/upstream path before enabling broadly |
| Browser-use | Feature flag exists | Audit real usage before adding another browser stack |
| E2B | Feature flag exists | Audit actual integration before enabling |
| OpenHands | Feature flag + server URL exists | Treat as optional coding-agent integration |
| LiteLLM | Package already present in requirements | NOT YET verified as a project-owned adapter |
| Langfuse | Package already present in requirements | NOT YET verified as a project-owned adapter |
| Sentry | DSN/config already present | NOT YET verified as a deliberate production integration |
| Ollama | Configuration already exists | Treat as optional USER-LOCAL provider, not backend infrastructure |
| OpenFGA | Not yet adopted | Defer until resource-level authorization requires it |
| LiveKit | Not yet adopted | Defer until voice/realtime becomes a product requirement |
| Appwrite full platform | Not adopted | Continue to defer |

---

# 3. Important Audit Finding: Do Not Re-Implement What Already Exists

The current codebase already contains additional optional integration foundations:

```text
Mem0
Graphiti
browser-use
E2B
OpenHands
Sentry
Ollama
```

The settings layer already contains flags for these optional systems.

Therefore the new roadmap must NOT automatically add all of them again.

Instead:

```text
Existing integration
      |
      v
Audit actual runtime usage
      |
      +-- Useful + maintained -> harden
      |
      +-- Partial              -> complete
      |
      +-- Dead/duplicated      -> remove or archive
```

---

# 4. Current Architecture — What Has Already Been Achieved

## 4.1 Automation abstraction

The new architecture has:

```text
backend/core/automation/
├── interfaces.py
├── models.py
├── registry.py
└── dispatcher.py
```

This is the correct project-owned boundary.

`AutomationProvider` is a protocol, so domain logic does not need to know whether the provider is n8n, Celery, Temporal, or a future custom worker.

---

## 4.2 n8n adapter

The current code has:

```text
backend/core/providers/n8n/adapter.py
```

The adapter:

- reads centralized settings
- resolves registered workflow routes
- builds a signed payload
- sends an async HTTP request
- reports delivery status
- captures an external execution ID where provided

This is a good foundation.

### Remaining n8n work

- event IDs must be added to the canonical event model
- signature verification/replay protection must be implemented on the receiving side
- retry/backoff must be real, not merely configuration
- execution persistence must be wired into dispatch
- n8n outage must not block core AI actions
- workflow health checks must exist
- admin execution history must become real, not registry-only
- route metadata should not remain a bare `dict[str, str]` forever
- workflow versioning should be supported
- provider selection should remain swappable

---

# 5. Current Automation Registry — Needed Hardening

Current concept:

```python
AUTOMATION_REGISTRY = {
    "USER_REGISTERED": "...",
    "SECURITY_ALERT": "...",
    ...
}
```

This is acceptable as a first step.

The next version should become metadata-driven:

```python
WorkflowDefinition(
    key="SECURITY_ALERT",
    enabled=True,
    route="/webhook/security-alert",
    timeout_seconds=15,
    max_retries=3,
    synchronous=False,
    sensitive=False,
)
```

Benefits:

- policy controls
- retries
- timeout
- sync/async semantics
- sensitive-data rules
- observability
- UI metadata
- versioning

---

# 6. Automation Event Model — Required Upgrade

Current event model contains:

```text
workflow_key
payload
metadata
```

This is useful but incomplete for durable distributed automation.

Add:

```text
event_id
event_type
schema_version
timestamp
source
tenant_id
trace_id
actor_type
actor_id
idempotency_key
payload
```

Example:

```json
{
  "event_id": "uuid",
  "event_type": "HITL_REQUIRED",
  "schema_version": "1",
  "timestamp": "ISO-8601",
  "source": "supremeai",
  "tenant_id": "tenant-123",
  "trace_id": "trace-123",
  "actor_type": "agent",
  "actor_id": "agent-456",
  "idempotency_key": "event-123",
  "payload": {}
}
```

---

# 7. Automation Execution Persistence — Already Started

A new:

```text
backend/models/automation_execution.py
```

exists and already records:

- event ID
- workflow key
- provider
- status
- attempt
- timestamps
- duration
- HTTP status
- external execution ID
- trace ID
- errors

This is exactly the correct direction.

### Remaining work

- create records when dispatch starts
- update status on completion
- persist each retry attempt
- link event → execution
- add indexes/constraints for idempotency
- expose execution history to admin UI
- retain failure details without leaking secrets
- add retention/cleanup policy

---

# 8. Critical Missing Piece: Real Idempotency

The database has `event_id`, but existence of a field is not enough.

Implement:

```text
event_id
   |
   v
idempotency lookup
   |
   +-- already completed -> return prior result
   |
   +-- currently running  -> return/attach to current execution
   |
   +-- unknown            -> create execution
```

Add a uniqueness strategy at the database level where appropriate.

---

# 9. Critical Missing Piece: Retry/Backoff

Configuration currently includes a maximum retry count, but the adapter currently performs one direct request.

Implement:

```text
attempt 1
   ↓
failure
   ↓
2s
   ↓
attempt 2
   ↓
10s
   ↓
attempt 3
   ↓
30s
   ↓
dead-letter / terminal failure
```

Classify errors:

```text
Transient:
- timeout
- connection failure
- 429
- 5xx

Permanent:
- invalid signature
- invalid workflow
- 400
- malformed payload
- configuration failure
```

Permanent errors should not be endlessly retried.

---

# 10. Critical Missing Piece: Core-Operation Isolation

The target behavior is:

```text
Core AI operation
      |
      +---- success
      |
      +---- emit automation event
                 |
                 +---- n8n unavailable
                         |
                         +---- queue/retry
```

NOT:

```text
Core AI operation
      |
      v
n8n
      |
      X
      |
Core operation fails
```

Automation must remain optional for all non-critical flows.

---

# 11. Storage Abstraction — Already Implemented

The codebase now contains:

```text
backend/core/storage/
├── interfaces.py
├── models.py
├── service.py
└── local_adapter.py
```

plus:

```text
backend/core/providers/appwrite/adapter.py
```

This establishes:

```text
StorageProvider
       |
       +-- Appwrite
       +-- Local
       +-- existing providers
```

This is consistent with vendor independence.

---

# 12. Storage Problem to Fix Next

The current Appwrite adapter returns an Appwrite-generated file ID as the resulting key for uploads.

That can break a provider-neutral semantic where callers expect:

```text
bucket + key
```

to remain stable across providers.

Required:

```text
logical key
    |
    v
provider-specific physical ID
```

Store mapping where necessary instead of allowing upstream providers to redefine the project's storage identity.

---

# 13. Existing Storage Providers Must Be Reconciled

The repository already contains existing storage implementations such as:

```text
MinIO
R2
Cloud storage
Asset manager
Storage API
```

Therefore the next task is NOT “add more storage”.

It is:

```text
Audit all storage implementations
       ↓
Choose canonical StorageProvider interface
       ↓
Move callers behind dispatcher
       ↓
Preserve compatibility
       ↓
Remove duplicate direct provider calls
```

This can lower long-term maintenance substantially.

---

# 14. Messaging Abstraction — Already Started

Current structure:

```text
MessagingProvider
       |
MessagingDispatcher
       |
MockMessagingAdapter
```

This is architecturally correct as a boundary.

However, the current real-world implementation is not complete.

### Next step

Integrate the existing notification systems behind the interface instead of introducing new parallel messaging code.

Potential adapters:

```text
MessagingProvider
├── ExistingTelegramAdapter
├── EmailAdapter
└── AppwriteMessagingAdapter (only if justified)
```

The existing Telegram implementation should be wrapped before building an entirely new Telegram subsystem.

---

# 15. Appwrite Decision — Keep Optional

Current Appwrite integration should remain:

```text
Optional Provider
```

not:

```text
Core Platform
```

Do not migrate:

```text
PostgreSQL
pgvector
AI memory
core auth
HITL
agent runtime
```

into Appwrite without a separate architecture review.

Appwrite is currently useful mainly as an optional infrastructure provider.

---

# 16. Ollama — Correct New Role

Ollama must be implemented as:

```text
USER-SIDE LOCAL AI CAPABILITY
```

not backend infrastructure.

Target:

```text
ModelProvider
   |
   +-- Cloud Provider
   |
   +-- Ollama Local Provider
```

Behavior:

```text
Local unavailable
      ↓
Cloud fallback

Local available
      ↓
Use local only when policy/user preference allows
```

The cloud backend must remain fully functional with:

```text
Ollama = absent
```

No server maintenance budget should depend on user machines.

---

# 17. Ollama Security Model

Do not allow the backend to blindly call arbitrary localhost endpoints.

Use:

```text
Local Capability Discovery
        ↓
Explicit user permission
        ↓
Local Companion / trusted local bridge
        ↓
Ollama
```

The local bridge should not automatically inherit cloud credentials.

Separate:

```text
Cloud identity
```

from:

```text
Local execution permission
```

---

# 18. Mem0 — Already Has an Adapter

The repository contains an optional Mem0 adapter with a dependency-free fallback.

That is aligned with this plan.

### Keep

```text
Memory interface
     |
     +-- existing SupremeAI memory
     +-- Mem0 optional enhancement
```

### Improve

- durable fallback storage
- tenant/user isolation
- concurrency safety
- duplicate suppression
- memory lifecycle policies
- observability
- privacy controls

The current fallback is in-memory and therefore unsuitable as durable production memory by itself.

---

# 19. Graphiti — Already Has an Adapter

Graphiti has a similar optional/fallback implementation.

However, the current adapter has an important design limitation: synchronous callers from a running async event loop can return `None` instead of properly executing the upstream operation.

Before enabling it broadly:

- make the API natively async
- remove sync/async ambiguity
- establish durable backend requirements
- define entity/relationship schema
- add tenant isolation
- add temporal query tests

Do not treat the current fallback as equivalent to a real temporal knowledge graph.

---

# 20. Browser-use

The configuration already contains a `browser_use_enabled` flag.

Before adopting browser-use as a major component:

1. Audit current browser automation implementation.
2. Compare it against the existing Playwright/browser subsystem.
3. Determine whether browser-use adds real agentic value.
4. Avoid running two browser stacks for the same use case.
5. Put either option behind a common `BrowserProvider` interface.

Target:

```text
BrowserProvider
    |
    +-- Existing Playwright adapter
    +-- browser-use adapter
```

Use one provider per task policy.

---

# 21. E2B

E2B is already represented as an optional configuration flag.

Before activation:

```text
SandboxProvider
    |
    +-- Firecracker
    +-- gVisor
    +-- E2B optional
```

Do not add E2B if the existing local/server sandbox implementation already satisfies the required security boundary.

The project should choose based on:

```text
security
latency
cost
isolation
operational burden
```

not popularity.

---

# 22. OpenHands

OpenHands is also already represented by an optional flag/server URL.

Treat it as a specialized coding-agent integration:

```text
CodingAgentProvider
    |
    +-- SupremeAI native code agent
    +-- OpenHands adapter
```

Do not let it replace:

```text
SupremeAI security
HITL
authentication
authorization
audit
```

---

# 23. LiteLLM — Next AI Infrastructure Candidate

`litellm` is already present in backend dependencies.

This means the next task is not necessarily “install LiteLLM”.

The question is:

> **Is LiteLLM actually wired into the runtime?**

Required audit:

```text
requirements
   ↓
imports
   ↓
provider gateway
   ↓
agent runtime usage
   ↓
tests
   ↓
production configuration
```

If it is only installed but unused, remove it or complete the integration.

Preferred final architecture:

```text
ModelProvider
   |
   +-- existing direct providers
   +-- LiteLLM adapter
   +-- Ollama adapter
```

Do not duplicate existing provider rotation/account-rotation logic.

---

# 24. Langfuse — Next AI Observability Candidate

`langfuse` is already present in dependencies.

Again, verify:

```text
installed
≠
integrated
```

Create a project-owned interface:

```text
AIObservabilityProvider
```

Possible adapters:

```text
OpenTelemetry
Langfuse
No-op
```

Target:

```text
Agent
 ↓
Trace abstraction
 ↓
OpenTelemetry
 ↓
(optional) Langfuse
```

Langfuse should never become mandatory for AI availability.

---

# 25. Sentry

The settings layer already contains:

```text
sentry_dsn
```

Do not assume Sentry is already operational.

Verify:

- SDK initialization
- environment filtering
- release tagging
- sensitive-data scrubbing
- frontend integration
- backend integration
- error sampling

Use:

```text
OpenTelemetry = distributed traces/metrics
Sentry = exception/incident workflow
```

Only adopt both if the duplication is intentional and documented.

---

# 26. OpenAPI — Upgrade Existing Implementation

The codebase already contains OpenAPI generation.

Target:

```text
FastAPI
   ↓
OpenAPI source
   ↓
CI validation
   ↓
breaking-change detection
   ↓
generated clients
```

Priorities:

1. deterministic generation
2. schema validation
3. breaking-change checks
4. correct auth definitions
5. consistent error schemas
6. examples
7. API versioning

---

# 27. OpenTelemetry — Use as the Common Observability Spine

Do not create separate tracing conventions for:

```text
AI
n8n
storage
browser
memory
database
```

Use one trace model:

```text
HTTP Request
    ↓
Agent Run
    ↓
Memory
    ↓
Tool
    ↓
LLM
    ↓
Automation Event
    ↓
n8n
```

Propagate:

```text
trace_id
span_id
event_id
```

where appropriate.

---

# 28. New Integration Governance Layer

Create a registry for all optional integrations:

```text
backend/core/integrations/
├── registry.py
├── health.py
├── capabilities.py
├── policies.py
└── adapters/
```

Each provider should declare:

```text
name
version
enabled
health
capabilities
configuration status
fallback
privacy mode
```

Example:

```json
{
  "name": "ollama",
  "enabled": true,
  "scope": "user-local",
  "required_for_core": false,
  "fallback": "cloud"
}
```

This will make the admin dashboard much easier to build.

---

# 29. Integration Health API

Add:

```text
GET /api/v1/admin/integrations
GET /api/v1/admin/integrations/{key}/health
```

Admin should see:

```text
n8n       Connected
LiteLLM   Configured
Langfuse  Disabled
Ollama    User-local
Appwrite  Disabled
Sentry    Configured
```

Do not expose provider secrets.

---

# 30. Integration Admin UI

Add:

```text
Admin
└── Integrations
    ├── Overview
    ├── AI Providers
    ├── Automation
    ├── Storage
    ├── Messaging
    ├── Observability
    └── Local AI
```

For each integration:

```text
Status
Purpose
Scope
Health
Fallback
Last check
Configuration
```

The UI should describe capabilities, not vendor marketing terminology.

---

# 31. Dependency Hygiene

The current requirements already include several optional ecosystems.

This creates a risk:

```text
Installed package
    ↓
unused dependency
    ↓
security/update burden
    ↓
larger image
    ↓
more maintenance
```

Create a dependency audit:

```text
package
  |
  +-- imported?
  +-- used in runtime?
  +-- tested?
  +-- optional?
  +-- duplicate?
  +-- replaceable?
```

Remove packages that are not justified.

---

# 32. Feature Flags Must Remain Safe

Every optional component should default to:

```text
disabled
```

unless the system can guarantee a safe local fallback.

Required behavior:

```text
integration OFF
    ↓
Core still works
```

No optional component should cause startup failure merely because the component is unavailable.

---

# 33. Configuration Strategy

Centralize all integration configuration.

Current settings already contain many integration flags.

Next step:

```text
settings
  |
  +-- feature flags
  +-- endpoints
  +-- timeout
  +-- retry
  +-- secret references
  +-- privacy mode
```

Avoid direct `os.getenv()` in provider adapters.

---

# 34. Privacy Modes

Every AI/telemetry integration should support:

```text
FULL
METADATA_ONLY
DISABLED
```

Especially:

```text
Ollama local prompts
private files
sensitive conversations
HITL payloads
security alerts
```

Default sensitive workflows to the safest mode.

---

# 35. Vendor Exit Requirements

For every optional integration maintain:

```text
Provider interface
Adapter
Feature flag
Health check
Fallback
Migration notes
Removal procedure
```

Examples:

```text
n8n
  ↓
AutomationProvider
```

```text
LiteLLM
  ↓
ModelProvider
```

```text
Langfuse
  ↓
AIObservabilityProvider
```

```text
Appwrite
  ↓
StorageProvider / MessagingProvider
```

```text
Ollama
  ↓
ModelProvider
```

---

# 36. Recommended Implementation Order From the Current State

## Phase 1 — Finish Existing Foundations

**Priority: P0**

1. Complete automation event schema.
2. Add durable event IDs and idempotency.
3. Implement real retry/backoff.
4. Persist automation execution lifecycle.
5. Add n8n health checks.
6. Add n8n outage isolation.
7. Harden workflow registry metadata.
8. Reconcile storage providers.
9. Route existing messaging implementations through `MessagingProvider`.

---

## Phase 2 — Observability & API Governance

**Priority: P0**

10. Standardize OpenTelemetry trace propagation.
11. Add automation spans.
12. Complete OpenAPI CI validation.
13. Add breaking-change detection.
14. Add integration health endpoints.
15. Add structured integration audit logs.

---

## Phase 3 — Local AI

**Priority: P1**

16. Implement `ModelProvider`.
17. Add `OllamaAdapter`.
18. Add Cloud / Local / Auto modes.
19. Add local capability discovery.
20. Add safe cloud fallback.
21. Keep all user-local execution optional.
22. Add privacy controls.

---

## Phase 4 — AI Gateway

**Priority: P1**

23. Audit current provider router.
24. Audit LiteLLM usage.
25. Implement `LiteLLMAdapter` only if useful.
26. Preserve existing provider/account rotation ownership.
27. Test latency, failure and cost.
28. Make LiteLLM removable without core changes.

---

## Phase 5 — AI Observability

**Priority: P1**

29. Create `AIObservabilityProvider`.
30. Connect OpenTelemetry.
31. Connect Langfuse optionally.
32. Add prompt/version metadata.
33. Add model/tool/retrieval traces.
34. Add evaluation hooks.
35. Add metadata-only privacy mode.

---

## Phase 6 — Existing Optional Adapters

**Priority: P2**

36. Audit Mem0.
37. Harden Mem0 fallback.
38. Audit Graphiti.
39. Fix Graphiti async semantics.
40. Audit browser-use vs Playwright.
41. Audit E2B vs existing sandbox.
42. Audit OpenHands vs native code agent.
43. Remove duplicate implementations if unnecessary.

---

## Phase 7 — Enterprise/Future Integrations

**Priority: P3**

Only when real product requirements exist:

```text
OpenFGA
Sentry
LiveKit
```

Each gets its own architecture review and adapter.

---

# 37. Explicitly Do NOT Do

Do not:

- migrate the whole backend to Appwrite
- make n8n mandatory for core AI
- make Ollama mandatory for backend operation
- deploy Ollama on SupremeAI infrastructure for users
- duplicate Telegram integration
- duplicate storage systems
- duplicate browser automation stacks
- duplicate provider rotation logic
- install packages without runtime justification
- expose arbitrary n8n webhook URLs
- expose secrets to the frontend
- send private local prompts to remote observability by default
- introduce Kubernetes merely to host these components
- treat a hosted SaaS endpoint as permanent infrastructure when an exit path is required

---

# 38. Target Architecture

```text
                         SUPREMEAI
                            |
                 +----------+----------+
                 |                     |
              Core AI              Interfaces
                 |                     |
       +---------+---------+    +------+-------+--------+
       |         |         |    |              |        |
     Agent     Memory     HITL ModelProvider Automation Observability
                                  |             |          |
                        +---------+----+     +--+--+    +--+----+
                        |              |     |     |    |       |
                     Cloud          Ollama  n8n  future OTel  Langfuse
                     adapters       local
                        |
                  Existing provider
                  rotation/account
                  management
```

Storage:

```text
StorageProvider
      |
      +-- existing R2/MinIO/cloud
      +-- Local
      +-- Appwrite (optional)
```

Messaging:

```text
MessagingProvider
      |
      +-- existing Telegram
      +-- Email
      +-- Appwrite (optional)
```

---

# 39. Success Criteria

The new integration architecture is complete when:

### Core independence

```text
n8n OFF          → SupremeAI works
LiteLLM OFF      → SupremeAI works
Langfuse OFF     → SupremeAI works
Appwrite OFF     → SupremeAI works
Ollama OFF       → SupremeAI works
```

### User-local independence

```text
User has Ollama  → extra capability
User lacks Ollama → normal cloud experience
```

### Automation independence

```text
n8n outage → automation delayed/failed safely
            core AI continues
```

### Provider independence

```text
LLM provider changes
        ↓
adapter/config changes
        ↓
core agent unchanged
```

### Storage independence

```text
Storage provider changes
        ↓
StorageProvider adapter changes
        ↓
domain logic unchanged
```

---

# 40. Final Priority Matrix

| Item | Priority | Current state | Next action |
|---|---:|---|---|
| Automation abstraction | P0 | Implemented | Harden |
| n8n adapter | P0 | Implemented | Reliability + runtime adoption |
| Automation executions | P0 | Model implemented | Wire lifecycle |
| Storage abstraction | P0 | Implemented | Migrate callers |
| Messaging abstraction | P0 | Implemented | Wrap real providers |
| OpenAPI | P0 | Existing | CI/governance |
| OpenTelemetry | P0 | Existing foundation | Unify traces |
| Ollama | P1 | Config exists | Build local adapter |
| LiteLLM | P1 | Dependency exists | Audit/wire only if useful |
| Langfuse | P1 | Dependency exists | Audit/wire optional |
| Mem0 | P2 | Adapter exists | Harden |
| Graphiti | P2 | Adapter exists | Fix async/persistence |
| browser-use | P2 | Flag exists | Compare against existing browser stack |
| E2B | P2 | Flag exists | Compare against current sandbox |
| OpenHands | P2 | Flag exists | Compare against current coding agent |
| Sentry | P2 | DSN exists | Verify before enabling |
| OpenFGA | P3 | Not adopted | Defer |
| LiveKit | P3 | Not adopted | Defer |
| Full Appwrite | NEVER as default | Optional storage adapter only | Keep deferred |

---

# 41. AI Coding Agent Rules

Any future coding agent must:

1. Read the current repository state first.
2. Treat this document as a **delta plan**, not a request to rebuild completed work.
3. Reuse existing interfaces and adapters.
4. Never introduce a second implementation of an existing capability without a comparison.
5. Keep all optional integrations removable.
6. Preserve current authentication, RBAC, HITL and security boundaries.
7. Never make user-local Ollama a backend dependency.
8. Never make n8n a hard dependency for core AI.
9. Add tests before claiming an integration is complete.
10. Wire execution persistence rather than merely defining models.
11. Add observability to every new distributed boundary.
12. Keep secrets outside source control.
13. Prefer standard protocols over vendor-specific domain models.
14. Remove unused dependencies discovered during implementation.
15. Update documentation and architecture diagrams together with code.
16. Run the full relevant test suite before completion.
17. Do not mark a component “implemented” merely because a package is present in `requirements.txt`.
18. Do not mark a provider “production-ready” until failure, timeout, fallback and disabled modes are tested.
19. Preserve vendor exit paths.
20. If a proposed component duplicates existing functionality, stop and perform an evidence-based comparison before adding it.

---

# 42. Final Architecture Principle

The SupremeAI platform should remain:

> **Core-owned, provider-independent, automation-capable, locally-optional, and operationally lightweight.**

The ideal dependency relationship is:

```text
                 SUPREMEAI CORE
                       |
               PROJECT-OWNED API
                       |
          +------------+------------+
          |            |            |
       Provider     Automation   Observability
       Interfaces   Interface      Interface
          |            |            |
     adapters       adapters       adapters
          |            |            |
   Cloud/Ollama       n8n       OTel/Langfuse
```

The project should gain the capabilities of open-source ecosystems without allowing those ecosystems to become the architecture itself.

**Core principle:**

> **Adopt capabilities, not lock-in.**