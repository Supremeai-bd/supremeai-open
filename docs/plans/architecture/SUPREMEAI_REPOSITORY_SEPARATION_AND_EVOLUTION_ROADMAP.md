# SUPREMEAI — Repository Separation, Privacy & Self-Evolution Roadmap

**Status:** Proposed canonical roadmap  
**Scope:** Repository architecture, public/private boundaries, extraction strategy, cross-repo maintenance, CI/CD, governance, self-evolution and self-healing  
**Source of truth:** Current `SaifulHaqueNiloy/supremeai` repository + existing architecture/governance direction  
**Decision style:** value-driven separation, not fear-driven separation

---

## 0. Executive Decision

SupremeAI should **not** immediately split the current monolith into eight independent repositories.

The correct target is a **federated ecosystem** with a small number of strongly bounded repositories, introduced in stages:

```text
                    SUPREMEAI ECOSYSTEM
                           │
             ┌─────────────┴─────────────┐
             │                           │
        PUBLIC ECOSYSTEM            PRIVATE CORE
             │                           │
      ┌──────┼──────┐        ┌───────────┼────────────┐
      │      │      │        │           │            │
    Studio   SDK   Open     Core     Evolution     Memory
                    │        │           │            │
                    │        └──────┬────┴────────────┘
                    │               │
                    │         Control Plane
                    │               │
                    └──────── Infrastructure
```

### Core principle

> **Open the implementation that teaches people how to use SupremeAI; keep private the implementation that reveals why SupremeAI performs better.**

Therefore:

- **Public:** UI, SDK, contracts, generic interfaces, generic tools, examples, documentation, community utilities, non-differentiating adapters.
- **Private:** proprietary planning/decision/execution logic, valuable self-improvement implementation, proprietary policies, private learned knowledge/data and sensitive operational logic.
- **Strictly private:** credentials, production secrets, security-sensitive deployment internals, private datasets and anything whose disclosure creates direct security or competitive risk.

The repository split is an **architectural boundary**, not a security substitute. Secrets must never depend on repository visibility.

---

# 1. Verified Current State

The current repository is already a multi-surface system rather than a simple application. The current README describes a governed task-execution platform with FastAPI, a Next.js Mission Control console, a React/Vite frontend, MCP Control Tower, model routing, memory/RAG, agents, policy/governance, eventing and multiple infrastructure integrations. fileciteturn1file0L2-L2

The current tree also contains dedicated agent/skill infrastructure and a substantial `backend/adaptive_engine` surface. The adaptive engine includes capability registration, governed execution, self-improving-agent logic, platform learning, governance, health modelling and task state management. fileciteturn3file0L2-L16 fileciteturn3file3L51-L58 fileciteturn3file4L62-L70 fileciteturn3file7L109-L117 fileciteturn3file8L119-L127 fileciteturn3file9L131-L139

The MCP Control Tower is already a separately buildable surface under `infrastructure/mcp-control-plane`, with its own Dockerfile, Render configuration and TypeScript source. fileciteturn4file1L18-L30 fileciteturn4file3L51-L60

The repository also already has shared-package infrastructure; for example, `packages/core-infrastructure` is explicitly intended to centralize primitives shared by the MCP control plane and Mission Control. fileciteturn4file8L119-L127

### Architectural implication

The split should therefore be treated as **progressive extraction of existing boundaries**, not a rewrite.

---

# 2. Target Repository Map

## 2.1 Recommended target repositories

| Repository | Visibility | Primary responsibility | Priority |
|---|---|---|---|
| `supremeai-studio` | 🟢 Public | User-facing React/Vite Studio | P1 |
| `supremeai-sdk` | 🟢 Public | SDKs, schemas, shared API/MCP contracts | P1 |
| `supremeai-open` | 🟢 Public | Generic agents/tools/interfaces/examples | P2 |
| `supremeai-core` | 🔴 Private | Backend intelligence, orchestration, proprietary execution | P1 |
| `supremeai-evolution` | 🔴 Private | Self-improvement/evolution implementation | P2 |
| `supremeai-memory` | 🔴 Private | Proprietary memory/learning/data layer | P2 |
| `supremeai-mcp-control-plane` | 🔴 Private | Governed tool/control plane implementation | P1 |
| `supremeai-infrastructure` | 🔴 Private | Production deployment/security/operations | P1 |
| `supremeai-mission-control` | 🟡 Hybrid/Public shell | Operator UI; sensitive tower implementation stays private | P2 |

### Important correction

These are the **target boundaries**, not a requirement to create all repositories now.

Start with the minimum viable separation:

1. `supremeai-core` (private)
2. `supremeai-studio` (public)
3. `supremeai-sdk` (public)
4. `supremeai-mcp-control-plane` (private)
5. `supremeai-infrastructure` (private)

Then extract `evolution`, `memory`, `open`, and Mission Control only when their boundaries are stable.

---

# 3. Value-Based Privacy Matrix

The classification question for every module is:

> **If a capable competitor receives this code, how much measurable competitive or security advantage do we lose?**

| Classification | Meaning | Examples | Action |
|---|---|---|---|
| 🟢 Open | Generic/non-differentiating | UI, SDK, schemas, docs, generic utilities | Public |
| 🟡 Review | Mixed value or shared dependency | Provider adapters, generic MCP clients, basic RAG utilities | Split interface from implementation |
| 🔴 Proprietary | Unique performance advantage | planning strategy, decision logic, execution optimization, evolution implementation | Private |
| ⛔ Restricted | Security/secret material | credentials, secret policies, private datasets, production internals | Private + vault + least privilege |

### Never classify by directory name alone

A file under `backend/` is not automatically private. A file under `packages/` is not automatically public.

Classification is performed at **module/interface level**.

---

# 4. What Goes Where

## 4.1 `supremeai-studio` — Public

### Move

- React/Vite UI
- reusable UI components
- UX state and presentation logic
- public API client
- non-sensitive configuration schema
- public examples
- accessibility and frontend tests

### Keep out

- private orchestration prompts
- internal policy evaluation logic
- production credentials
- privileged MCP execution code
- internal memory datasets

### Advantage

Community contributions become possible without exposing the intelligence moat.

### Risk

The public UI can still reveal product workflows. Mitigation: expose the UX, not privileged implementation details.

---

## 4.2 `supremeai-sdk` — Public

### Move

- API types
- request/response schemas
- MCP-compatible public interfaces
- client SDKs
- error contracts
- authentication abstractions
- integration examples
- versioned protocol definitions

### Rule

The SDK may describe **what the system can do**, but should not reveal **why the private system makes a particular decision**.

### Advantage

Stable external ecosystem and third-party integrations.

### Risk

Bad contract design can lock the private architecture into public compatibility promises.

### Mitigation

Use versioned contracts and adapter layers.

---

## 4.3 `supremeai-open` — Public

### Candidate contents

- generic agent interfaces
- generic tool interfaces
- generic validation utilities
- examples
- test harnesses
- documentation helpers
- provider-neutral adapters where no proprietary routing is exposed
- community skills

### Do not put here

- proprietary agent decision policies
- private task decomposition algorithms
- internal autonomy scoring
- private repair/healing policy

---

## 4.4 `supremeai-core` — Private

This is the primary **intelligence moat**.

### Keep private

- orchestration strategy
- proprietary task decomposition
- planning/decision heuristics
- execution optimization
- model-selection logic that materially improves results
- internal policy composition
- private agent coordination
- proprietary reliability/failover decisions
- high-value reasoning/execution loops

### Public interface

Expose only stable contracts through `supremeai-sdk`.

```text
Public SDK
    │
    ▼
Authenticated API / Contract
    │
    ▼
Private SupremeAI Core
    │
    ├── planner
    ├── orchestrator
    ├── router
    ├── executor
    └── verifier
```

---

# 5. `supremeai-evolution` — Private Self-Evolution Engine

This is the most sensitive intellectual component after Core.

The **concept** can be public. The **implementation that creates measurable advantage** remains private.

### Keep private

- learning policies
- improvement scoring
- hypothesis ranking
- experiment selection
- self-modification proposals
- improvement promotion rules
- adaptive optimization
- autonomous repair strategies
- evolution feedback interpretation

### Public

- high-level architecture documentation
- generic plugin/extension interfaces
- benchmark methodology
- safety principles

### Non-negotiable rule

> Self-evolution may propose changes; it must not bypass governance to deploy arbitrary changes.

---

# 6. `supremeai-memory` — Private Knowledge Moat

Separate **memory technology** from **valuable memory contents**.

### Potentially public

- generic memory interface
- storage abstractions
- generic vector-search adapters
- public RAG examples

### Private

- proprietary learned experiences
- private user/tenant memory
- internal decision history
- proprietary evaluation datasets
- experience-derived strategies
- embeddings/indexes containing protected data
- private feedback corpus

### Critical rule

Repository privacy does not protect runtime data. Data must have its own tenancy, encryption, access-control and retention model.

---

# 7. `supremeai-mcp-control-plane` — Private Control Tower

The current repository already has a dedicated `infrastructure/mcp-control-plane` implementation with its own runtime packaging and deployment configuration. fileciteturn4file0L2-L16 fileciteturn4file3L51-L60

### Private

- governed tool registry
- privileged tool adapters
- access policy enforcement
- credential brokering
- execution routing
- remediation controls
- internal service controls
- admin-only operations
- autonomy kill-switch implementation

### Public

- MCP protocol compatibility
- public client examples
- non-sensitive schemas
- documentation for approved integrations

### Design principle

```text
Public MCP contract
        ↓
Private Control Tower
        ↓
Policy → Permission → Credential → Tool → Verify
```

---

# 8. `supremeai-infrastructure` — Private Operations Plane

### Keep private

- production deployment topology
- secret-management configuration
- privileged Cloudflare/Render automation
- internal network details
- production monitoring internals
- security policies
- emergency recovery procedures
- private operational runbooks

### Public where useful

- generic local development compose examples
- public deployment documentation
- non-sensitive infrastructure templates

### Never commit

- real credentials
- production tokens
- private endpoints that are not intended for publication
- vault bootstrap secrets
- internal security bypasses

The existing project already documents Infisical identity scope and uses it across backend, MCP and CI, so extraction must preserve a single controlled secret-management model rather than duplicating secrets per repository. fileciteturn4file6L87-L95

---

# 9. Mission Control — Hybrid Boundary

Mission Control should be treated as an **operator experience**, not the owner of the private intelligence.

### Public/open candidate

- dashboard shell
- visualizations
- command palette UI
- generic system views
- public API client

### Private

- privileged tower API routes
- admin-only commands
- secret-bearing server actions
- private operational data

Recommended architecture:

```text
Mission Control UI
      │
      ▼
Public/Versioned SDK
      │
      ▼
Authenticated private gateway
      │
      ▼
MCP Control Plane / Core
```

---

# 10. Repository Contracts — The Glue

The ecosystem must not become eight disconnected applications.

Create a **contract-first boundary**.

## Contract families

1. API contracts
2. event schemas
3. task state schemas
4. agent result schemas
5. memory record schemas
6. tool invocation schemas
7. capability registry schemas
8. health/status schemas
9. evolution proposal schemas
10. audit/evidence schemas

The public SDK owns stable external contracts; private repositories consume versioned contracts.

### Versioning rule

```text
MAJOR = breaking semantic change
MINOR = backward-compatible capability
PATCH = bug/security correction
```

Every cross-repository deployment must declare the contract version it supports.

---

# 11. Dependency Direction

The dependency graph must become **acyclic at the architectural level**.

```text
                   supremeai-sdk
                  /      |      \
                 /       |       \
            Studio      Open    external clients
               |          |
               └──────┬───┘
                      ▼
               authenticated APIs
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
        Core      Control Plane   Memory
          │           │            │
          └───────────┼────────────┘
                      ▼
                  Evolution
                      │
                      ▼
               Infrastructure
```

In practice, Infrastructure should host/deploy the services but should not contain business logic belonging to Core.

### Rule

> A repository may depend on a lower-level contract; it must not reach into another repository's private implementation.

---

# 12. Migration Strategy — Do Not Rewrite

## Phase 0 — Freeze the boundary (Week 0–1)

### Actions

- declare this roadmap canonical
- inventory every top-level module
- classify every module 🟢/🟡/🔴/⛔
- identify cross-module imports
- identify secrets and runtime data
- identify shared types
- define target APIs
- mark modules that are not ready to extract

### Gate

No repository is created until its boundary has a dependency map.

### Advantage

Prevents premature fragmentation.

### Disadvantage

Requires analysis before visible movement.

---

# 13. Phase 1 — Build the Contract Layer (Week 1–2)

### Deliverables

- `supremeai-sdk`
- versioned API schemas
- event schemas
- task/result/error contracts
- capability/tool contracts
- authentication contract
- compatibility tests

### Gate

Core must be able to consume SDK contracts without importing Studio code.

### Advantage

Makes future repository extraction much safer.

### Risk

Over-designing contracts.

### Control

Only publish contracts currently needed by two or more surfaces.

---

# 14. Phase 2 — Extract Studio (Week 2–3)

Move frontend code into `supremeai-studio`.

### Process

1. copy history-preserving where practical
2. replace internal imports with SDK/API calls
3. remove private implementation imports
4. add public CI
5. publish development documentation
6. run integration tests against a private Core environment

### Gate

Studio can build and test without private repository source access.

---

# 15. Phase 3 — Extract MCP Control Plane (Week 3–5)

The current `infrastructure/mcp-control-plane` is already a natural extraction candidate because it has its own Docker/runtime/deployment boundary. fileciteturn4file1L18-L30

### Actions

- create private `supremeai-mcp-control-plane`
- move source/history
- define SDK-facing tool contracts
- remove direct dependency on monolith-only paths
- establish private CI
- establish service-to-service authentication
- deploy independently
- run compatibility tests against Core

### Gate

Control Plane can be deployed without cloning the entire monolith.

---

# 16. Phase 4 — Extract Infrastructure (Week 4–6)

Create private `supremeai-infrastructure`.

### Responsibilities

- deployment
- environment configuration
- observability
- secret references
- rollback
- production policy
- disaster recovery

### Critical architecture

```text
Infrastructure
   ├── deploy Core
   ├── deploy Evolution
   ├── deploy Memory
   ├── deploy MCP
   └── deploy Studio
```

Infrastructure **deploys** applications; it does not become a second application brain.

---

# 17. Phase 5 — Extract Core (Week 5–8)

This is the largest and highest-risk extraction.

### First isolate inside the monolith

```text
backend/
  public-contracts/
  core/
  orchestration/
  routing/
  execution/
  verification/
```

Only after these internal boundaries are stable should the code move to `supremeai-core`.

### Gate

- API compatibility
- mission regression suite
- latency baseline
- cost baseline
- memory baseline
- security test
- rollback path

### Rule

Do not extract and refactor simultaneously unless required to break an unsafe dependency.

---

# 18. Phase 6 — Extract Evolution (Week 7–10)

Evolution should be extracted only after Core has stable contracts.

### Architecture

```text
                    ┌───────────────┐
                    │   Evolution   │
                    └───────┬───────┘
                            │ proposal
                            ▼
                      Governance Gate
                            │
                 ┌──────────┴──────────┐
                 │                     │
               reject                approve
                 │                     │
                 │                     ▼
                 │                 Experiment
                 │                     │
                 │                  Verify
                 │                     │
                 │               Canary/Shadow
                 │                     │
                 └──────────────┬──────┘
                                ▼
                              Learn
```

### No direct self-modification of production

Evolution creates **evidence-backed proposals**, not uncontrolled mutations.

---

# 19. Phase 7 — Extract Memory (Week 8–11)

### Separate three layers

```text
Memory API / Contract       → public/stable
Memory implementation       → private where valuable
Memory data                 → private/restricted
```

### Migration

- define tenant-scoped memory contract
- export/import historical data safely
- preserve IDs and provenance
- verify semantic-search parity
- verify retention/deletion semantics
- switch reads first
- switch writes second
- remove old path last

---

# 20. Phase 8 — Extract `supremeai-open` (Week 10–12)

Only after real boundaries are known.

This repository should contain what is genuinely useful to the community, not a forced copy of private internals.

### Public quality bar

Every published component must have:

- clear license
- API documentation
- tests
- security review
- dependency scan
- provenance
- compatibility statement

---

# 21. Cross-Repository CI/CD

The ecosystem needs **one release system, not one repository**.

## CI layers

### Per-repository CI

Every repository runs:

- formatting/lint
- unit tests
- security scan
- dependency scan
- contract tests
- build/package validation

### Integration CI

A central integration pipeline runs:

```text
Studio
  + SDK
  + Core
  + MCP
  + Memory
  + Evolution
  + Infrastructure
        ↓
  End-to-end mission suite
        ↓
  Reliability gate
```

### Release train

A release manifest pins exact versions:

```yaml
studio: 1.x.x
sdk: 1.x.x
core: 1.x.x
mcp: 1.x.x
memory: 1.x.x
evolution: 1.x.x
infrastructure: 1.x.x
```

No production deployment should depend on floating `main` branches.

---

# 22. One Issue → One PR Still Applies

Repository separation does **not** change the existing safe execution philosophy.

Default:

```text
1 focused issue
      ↓
1 isolated branch
      ↓
1 PR
      ↓
automated verification
      ↓
review/merge gate
```

For a cross-repository feature:

```text
Parent capability issue
       ├── SDK issue → SDK PR
       ├── Core issue → Core PR
       ├── MCP issue → MCP PR
       └── Studio issue → Studio PR
```

A release/integration issue coordinates them.

This avoids giant multi-repo branches while preserving traceability.

---

# 23. Agent Governance Across Repositories

All agents continue to follow the universal constitutional layer first.

Then task-specific rules are generated from database policy according to role.

```text
AGENTS.md
   ↓
Task scope
   ↓
Agent role
   ↓
DB policy/rules
   ↓
Repository permissions
   ↓
Generated task instructions
   ↓
Agent action
```

## Repository permissions

Each agent should receive only the repositories and paths required for its task.

Example:

| Agent | Studio | SDK | Core | Evolution | Memory | MCP | Infra |
|---|---:|---:|---:|---:|---:|---:|---:|
| Frontend coder | RW | R | API-only | - | - | API-only | - |
| SDK maintainer | R | RW | contract-only | - | - | contract-only | - |
| Core coder | - | R | RW | API-only | API-only | API-only | - |
| Evolution agent | - | R | API-only | RW | API-only | API-only | - |
| Memory agent | - | R | API-only | API-only | RW | API-only | - |
| Infrastructure agent | - | R | deploy-only | deploy-only | deploy-only | deploy-only | RW |
| Auditor | scoped read | scoped read | scoped read | scoped read | scoped read | scoped read | scoped read |

`RW` means source modification; `R` means read; `API-only` means no source access and only approved service contracts.

---

# 24. Agent Decision Memory / Learning Artifact

After completing a task, every agent should produce a structured decision record.

Example:

```json
{
  "task_id": "...",
  "repository": "supremeai-core",
  "issue": 123,
  "decision": "...",
  "why": "...",
  "alternatives_considered": ["..."],
  "evidence": ["..."],
  "tests": ["..."],
  "risk": "low|medium|high",
  "result": "success|partial|failed",
  "lessons": ["..."],
  "follow_up": ["..."]
}
```

The JSON can be committed as a lightweight audit artifact and ingested into the private learning/memory system.

### Why this matters

It converts multi-agent work from isolated actions into cumulative organizational memory.

---

# 25. Self-Evolution Lifecycle

The future SupremeAI loop should be:

```text
OBSERVE
  ↓
MEASURE
  ↓
DETECT
  ↓
UNDERSTAND
  ↓
FORM HYPOTHESIS
  ↓
PROPOSE CHANGE
  ↓
POLICY CHECK
  ↓
PLAN EXPERIMENT
  ↓
IMPLEMENT IN ISOLATION
  ↓
TEST
  ↓
BENCHMARK
  ↓
SHADOW/CANARY
  ↓
VERIFY
  ↓
PROMOTE or ROLLBACK
  ↓
CAPTURE EXPERIENCE
  ↓
UPDATE MEMORY
  ↓
RE-EVALUATE
```

This is the core self-evolving/self-healing ecosystem.

---

# 26. Self-Healing Lifecycle

Self-healing must be narrower than self-evolution.

## Safe automatic healing

Examples:

- retry transient provider failure
- switch provider on rate limit
- restart unhealthy worker
- clear recoverable cache state
- replay idempotent event
- roll back a known-bad deployment
- recreate disposable worker

## Approval-required healing

Examples:

- database schema mutation
- permission changes
- production policy changes
- secret rotation with broad impact
- modifying core orchestration
- modifying evolution rules

## Never autonomous

- disabling security controls
- exposing secrets
- bypassing governance
- changing constitutional constraints
- silently modifying audit history

---

# 27. Self-Evolution Safety Levels

| Level | Action | Autonomy |
|---|---|---:|
| L0 | Observe/report | 100% automatic |
| L1 | Retry/recover known-safe failure | 100% automatic |
| L2 | Low-risk optimization in sandbox | 99.99% automatic target |
| L3 | Canary production optimization | automatic with hard gates |
| L4 | Architectural/proprietary change | approval required |
| L5 | Constitutional/security change | admin only |

The desired **99.99% agent automation / 0.01% admin control** is therefore implemented as a **risk-based control model**, not as an unrestricted autonomy claim.

---

# 28. Daily Ecosystem Scout

The planned Ecosystem Scout becomes part of the learning loop.

Every 24 hours it should:

1. inspect recent internal changes
2. inspect regressions/degradations
3. inspect benchmark trends
4. compare relevant external platform capabilities
5. identify useful patterns
6. distinguish inspiration from copy
7. create evidence-backed improvement suggestions
8. create separate regression issues
9. rank suggestions by value/risk/cost
10. feed accepted proposals into the planning queue

### Important

The Scout must **not automatically copy external architecture**.

It produces:

```text
Observation
→ Evidence
→ Relevance to SupremeAI
→ Proposed adaptation
→ Expected benefit
→ Cost
→ Risk
→ Experiment design
```

---

# 29. Daily Audit + Scout Ecosystem

```text
                    DAILY ECOSYSTEM LOOP
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
     Internal Audit                    Ecosystem Scout
          │                                 │
          ▼                                 ▼
 regressions / debt                 external capabilities
          │                                 │
          └──────────────┬──────────────────┘
                         ▼
                 Evidence Normalizer
                         ▼
                  Opportunity Queue
                         ▼
                 Priority / Risk Gate
                         ▼
                     Planner
                         ▼
                  Agent Execution
                         ▼
                    Verification
                         ▼
                     Learning
                         └──────────► next cycle
```

This unifies audit, planning, healing and learning instead of maintaining disconnected intelligence subsystems.

---

# 30. Database-Driven Governance

Static documents should provide the constitutional foundation, but dynamic agent rules should live in the governed database.

### Suggested records

- `agent_roles`
- `agent_policies`
- `repository_permissions`
- `capabilities`
- `tool_permissions`
- `risk_levels`
- `change_policies`
- `approval_rules`
- `contract_versions`
- `evolution_proposals`
- `experiments`
- `decision_records`
- `lessons`
- `audit_findings`
- `ecosystem_observations`

### Principle

> Documents explain the system; governed data controls the live system.

---

# 31. Release / Deployment Model

The production product is composed from immutable versions of repositories.

```text
GitHub
  │
  ├── public repos
  └── private repos
          │
          ▼
       CI Build
          │
          ▼
     Artifact Registry
          │
          ▼
   Integration Verification
          │
          ▼
      Release Manifest
          │
          ▼
       Deployment
          │
       ┌──┴──┐
       ▼     ▼
    Canary  Stable
       │
       ▼
    Verify
       │
  ┌────┴────┐
  ▼         ▼
Promote   Rollback
```

---

# 32. Observability Requirements

Each repository/service must expose a common minimum telemetry contract:

- version
- contract version
- health
- readiness
- latency
- error rate
- dependency status
- resource usage
- deployment ID
- correlation ID

This makes the ecosystem auditable without coupling implementations.

---

# 33. Security Boundary

Security has three independent layers:

### Repository security

- public/private visibility
- branch protection
- least-privilege GitHub access
- CODEOWNERS where useful

### Runtime security

- authentication
- authorization
- tenant isolation
- service identity
- network policy

### Secret/data security

- vault-managed secrets
- encryption
- data classification
- retention
- deletion
- audit trail

Repository privacy alone is never sufficient.

---

# 34. Main Branch and Merge Train

Each repository maintains its own protected `main`.

The integration system determines whether the complete ecosystem remains healthy.

```text
Repo PR
  ↓
Repo CI
  ↓
Contract CI
  ↓
Integration candidate
  ↓
Mission suite
  ↓
Security/reliability gate
  ↓
Merge train
  ↓
Release
```

A repository can pass its own tests and still be rejected because it breaks ecosystem-level contracts.

---

# 35. Rollback Strategy

Every service must support rollback to its previous known-good artifact.

For cross-repository releases:

```text
Release N
  ↓
Failure
  ↓
Freeze promotion
  ↓
Rollback changed service(s)
  ↓
Restore compatible manifest
  ↓
Capture failure evidence
  ↓
Open regression issue
```

Never let a self-healing system erase evidence of the failure it repaired.

---

# 36. Migration Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Circular dependencies | High | contract-first architecture |
| Version drift | High | release manifest + contract tests |
| Duplicate utilities | Medium | shared SDK/package policy |
| Slower development | Medium | extract only stable boundaries |
| Operational complexity | High | central deployment/orchestration |
| Secret leakage | Critical | vault + secret scanning + private repos |
| Public/private boundary mistake | High | value classification review |
| Data migration failure | Critical | dual-read/dual-write + backups |
| Agent overreach | Critical | DB policy + risk gates + kill switch |
| Self-evolution regression | Critical | sandbox → benchmark → canary → rollback |
| Open-source fragmentation | Medium | clear ownership and contribution rules |

---

# 37. Advantages of the Target Architecture

## Technical

- independent deployment
- smaller cognitive surface per repository
- clearer ownership
- better failure isolation
- easier scaling
- cleaner contracts

## Business/IP

- community can contribute to public surfaces
- core intelligence remains protected
- proprietary data remains protected
- private control plane remains difficult to reproduce

## AI/Agent ecosystem

- agents can receive repository-scoped permissions
- auditors can operate across repositories without write access
- self-evolution can propose changes across the ecosystem
- learning can aggregate evidence without exposing private implementations

---

# 38. Disadvantages

## More operational complexity

Eight repositories are harder to coordinate than one.

## Version management

Every cross-repository contract creates compatibility work.

## CI cost

Integration tests become more important.

## Debugging

A failure may cross repository boundaries.

## Agent complexity

Agents need repository-aware permissions and context.

### Decision

These costs are acceptable **only after the internal boundaries are stable**.

---

# 39. What We Must NOT Do

1. Do not split repositories solely because directories look large.
2. Do not make every backend module private.
3. Do not expose private code through a public SDK accidentally.
4. Do not store secrets in private repositories as a substitute for a vault.
5. Do not let Evolution directly modify production.
6. Do not make every external observation an engineering task.
7. Do not create a new repository before defining its contract.
8. Do not rewrite architecture during extraction unless necessary.
9. Do not allow repositories to import each other's private source trees.
10. Do not let self-healing hide or destroy failure evidence.

---

# 40. Final Target State

```text
                          SUPREMEAI
                              │
              ┌───────────────┴────────────────┐
              │                                │
        PUBLIC ECOSYSTEM                 PRIVATE INTELLIGENCE
              │                                │
      ┌───────┼────────┐          ┌────────────┼─────────────┐
      │       │        │          │            │             │
    Studio   SDK     Open       Core       Evolution      Memory
      │       │        │          │            │             │
      └───────┴────────┘          └──────┬─────┴─────────────┘
                                         │
                                  Control Plane
                                         │
                                  Infrastructure
                                         │
                                         ▼
                                  Production System
```

And above all of them:

```text
                  GOVERNANCE / CONSTITUTION
                           │
                    Policy + Permissions
                           │
                    Evidence + Verification
                           │
                    Human Override / Kill Switch
```

The system then becomes:

> **Open at the ecosystem boundary, private at the intelligence boundary, governed at the execution boundary, and continuously learning at the system boundary.**

---

# 41. Recommended Execution Order

> **Status annotation (2026-10-07):** প্রতিটি আইটেমের বাস্তব-অবস্থা প্রমাণ-পয়েন্টারসহ লিপিবদ্ধ —
> আনুমানিক টিক নয়; প্রতিটি `[x]` একটি merged-PR/রেপো/CI-রান দ্বারা বাঁধা। মুলতবি-গুলি
> প্রমাণ-সমর্থিত বিরতি (probe-রায়), অসম্পূর্ণতা নয়।

### Immediate

- [x] Adopt value-based classification. <!-- PHASE0_BOUNDARY_CLASSIFICATION.md (PR #16) -->
- [x] Freeze current architecture before major split. <!-- Phase 5 Core-freeze অটুট; monolith zero-touch -->
- [x] Build module/dependency inventory. <!-- PHASE67_PREANALYSIS_BOUNDARY_PROBE.md (PR #16, §9 convergence) -->
- [x] Define SDK/contracts. <!-- supremeai-sdk (openapi+types) + supremeai-api contracts + §21 federation parity CI -->
- [x] Define repository permission matrix. <!-- claim-chain + constitutional gates + evaluator (fork; PR #2/#16-প্রমাণ) -->

### Next

- [x] Extract Studio. <!-- supremeai-studio: 565 code-files, Vercel-নিবন্ধিত -->
- [x] Extract MCP Control Plane. <!-- supremeai-mcp-control-plane: 133 code-files, render.yaml সহ -->
- [x] Extract Infrastructure. <!-- supremeai-infrastructure: SECRETS_MODEL + FEDERATION_WIRING + deploy-অস্ত্রাগার (PR #1) -->
- [x] Establish cross-repository integration CI. <!-- infrastructure/federation-integration.yml — 5-check parity CI, daily cron (PR #3/#5/#7) -->

### Then

- [ ] Extract Core. <!-- মুলতবি (probe-রায়): প্রথম পদক্ষেপ logging-ডিকাপলিং (৩৬→১৩) — Core-freeze অটুট -->
- [ ] Extract Evolution. <!-- মুলতবি (probe-রায়): core-কাপলিং + ফ্রিজ -->
- [ ] Extract Memory. <!-- মুলতবি (probe-রায়): repository-interface seed SDK-তে ভবিষ্যৎ-প্রার্থী -->
- [x] Publish Open foundation. <!-- supremeai-open (public): gateway-স্পেক + client-kit মিরর, §21 byte-parity CI-রক্ষিত -->
- [x] Stabilize Mission Control hybrid boundary. <!-- MISSION_CONTROL_HYBRID_BOUNDARY_PROBE.md (PR #28): §9-স্থাপত্য কোডে-প্রমাণিত; extraction-বিরতি -->

### Finally

- [ ] Activate full self-evolution loop. <!-- আংশিক: self-heal ✓ (fleet #3774, fork self-heal-chain), evolution-loop ✗ -->
- [ ] Activate daily internal audit + Ecosystem Scout. <!-- আংশিক: Scheduled Deep Audit চলছে (fork+upstream); Scout = monolith-অভ্যন্তরীণ -->
- [x] Activate evidence-backed automatic healing. <!-- fleet-merge প্রমাণ (#3774-fix 203246e9) + fork evaluator self-heal চক্র (PR #16) -->
- [ ] Introduce canary-based autonomous optimization. <!-- অ-শুরু — সচেতন বিরতি (স্ক্রিপ্ট canary_deploy.py অস্ত্রাগারে আছে) -->
- [ ] Continuously re-evaluate public/private classification. <!-- চলমান: upstream-convergence §9 নোট (#4053/#4056) + §21 CI দৈনিক রায় -->

---

# 42. Success Criteria

The migration is successful only if all of the following are true:

1. A public clone does **not** contain SupremeAI's proprietary intelligence.
2. Public developers can build against stable contracts.
3. Private services can evolve independently.
4. No private repository depends on a public implementation for security-critical behavior.
5. Cross-repository releases are reproducible.
6. Every autonomous change is attributable and verifiable.
7. Self-healing can recover known-safe failures without bypassing governance.
8. Self-evolution improves measurable benchmarks rather than merely changing code.
9. Every important agent decision can be traced to evidence and policy.
10. Admin retains final authority over constitutional, security and high-risk changes.

---

# 43. Bottom Line

The goal is **not** to turn SupremeAI into eight disconnected products.

The goal is to turn the current monolith into a **single coherent ecosystem composed of independently maintainable trust boundaries**.

The winning architecture is therefore:

```text
                  ONE SUPREMEAI PRODUCT
                           │
          ┌────────────────┼────────────────┐
          │                │                │
       Public            Private          Restricted
       ecosystem         intelligence     production
          │                │                │
       Studio/SDK       Core/Evolution     Infra/Secrets
       Open tools       Memory/MCP         Security/Data
          │                │                │
          └────────────────┼────────────────┘
                           │
                     Shared Contracts
                           │
                      Governance
                           │
                Self-Evolution + Healing
                           │
                       Verification
                           │
                        Learning
```

**Final policy:**

> **Private by value. Public by usefulness. Restricted by risk. Autonomous by evidence. Controlled by governance.**
