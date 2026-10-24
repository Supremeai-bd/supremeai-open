---
id: external-agent-orchestration-layer-canonical-v3
subject: "SupremeAI Universal External Agent & Dynamic Execution Architecture (EAOL)"
status: active
document_role: architecture
planning_authority: Architecture Governance / Control Tower Circle
target_scope: combined_ecosystem
canonical: candidate
scope: "Universal external execution, dynamic capability routing, dual-track operational model (Admin Self-Evolution via Browser Arbitrage vs Frictionless Customer Experience), zero-persistent-credential security, and multi-team zero-conflict parallel orchestration"
version: 3.1.0
last_verified: 2026-09-17
depends_on:
  - docs/plans/CANONICAL_PLANNING_RECONCILIATION_AND_GUARDRAILS_PLAN.md
  - docs/plans/PLAN_LIFECYCLE_POLICY.md
  - docs/plans/architecture/browser_automation.md
  - backend/core/circles/centers/browser_center.py
  - backend/core/security/secure_credential_store.py
  - AGENTS.md Mandatory Rules #1, #2, #6, #7, #8, #9
implements:
  - Dual-Track Operational Model: Admin/SupremeAI Self-Evolution (Browser-driven compute arbitrage) vs Customer Experience (Frictionless, zero-password Mode 3)
  - Dynamic capability-based external execution without hardcoding vendor names
  - On-demand browser session broker with decoupled credential vaulting for internal platform maintenance
  - 4-Tier authentication persistence modes with customer Zero-Persistent-Credential guarantee
  - Multi-team parallel agent execution with pre-execution resource ownership locks
  - MCP Control Tower governed promotion and artifact boundary on GitHub
supersedes: []
disposition: retain
evidence_state: partial
---

# SupremeAI — Universal External Agent & Dynamic Execution Architecture

**Document ID:** `PLAN-EAOL-003`  
**Version:** `3.1.0` (Dual-Track Canonical Architecture)  
**Status:** ACTIVE — Architectural Baseline & Living Canonical Plan  
**Planning Authority:** Architecture Governance / MCP Control Tower Circle  
**Last Verified:** 2026-09-17  

---

## Evolution History

| Stage | Version | Milestone / Context | Key Architectural Refinements |
|---|---|---|---|
| **Stage 1** | `v1.0.0` | Initial Concept & Arbitrage Proposal | Envisioned outsourcing heavy compute/coding tasks to free-tier external platforms (Bolt, Lovable, v0, Z.ai) using browser sessions and sequential agents (Agent 1→2→3→4) with GitHub PR as communication bus. |
| **Stage 2** | `v2.0.0` | Architectural Critique & Decoupling | Decoupled MCP Control Tower (Control Plane) from Browser (Execution Channel) and External Platforms (Workers). Rejected hardcoded vendor names, permanent browser sessions, and GitHub as a state bus. Introduced capability-first registries and dynamic placement. |
| **Stage 3** | `v3.0.0` | Production Baseline & Multi-Team Engine | Formalized 4-tier auth persistence, Pre-Execution Resource Ownership Locks for Multi-Team zero-conflict parallel execution (Monorepo + Git Worktrees), Bounded Verification & Self-Healing Loops, and strict One Domain = One Living Plan governance. |
| **Stage 4** | `v3.1.0` | Dual-Track Separation (Admin vs Customer) | **Critical Operational Correction:** Explicitly bifurcated system into **Track A (SupremeAI Self-Evolution / Admin Plane)** using Admin-managed Browser Automation & Compute Arbitrage, and **Track B (Customer / End-User Plane)** enforcing frictionless, zero-password, Mode 3 (Session-Only / Ephemeral & Direct Managed API) progressive disclosure. |

---

## 1. The Dual-Track Operational Model (Admin vs Customer)

In strict accordance with SupremeAI's **Mandatory Rule #1 (Rule Scope)** and **Mandatory Rule #7 (Dual-Driven Principle)**, the system enforces an absolute separation between internal platform evolution and customer-facing delivery:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        SupremeAI MCP Control Tower Gate                                │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    ▼                                               ▼
   [ TRACK A: SupremeAI Self-Evolution ]           [ TRACK B: Customer / End-User Plane ]
       (Admin Managed & Maintained)                    (Zero Friction & Zero Setup)
                    │                                               │
   • Purpose: Internal codebase evolution,         • Purpose: Fast, instant results for
     automated builds, testing, heavy compute.       user projects, app generation, tasks.
   • Credentials: Admin sets passwords/cookies     • Credentials: NO PASSWORD REQUIRED.
     in dedicated Admin Cloud Vault.                 Customers never manage browser logins.
   • Channel: Heavy BROWSER AUTOMATION &           • Channel: NATIVE MANAGED APIS & MCP.
     free-tier compute arbitrage pool.               Direct outcomes via Mode 3 (Ephemeral).
   • Workspaces: Multi-team Git Worktrees &        • UX: 1-Click prompt-to-outcome, zero
     path locks for repository maintenance.          complexity, progressive disclosure.
```

### Track A: SupremeAI Platform Evolution & Admin Compute Plane
- **The Reality:** SupremeAI requires massive computational intelligence to self-improve, refactor code, audit dependencies, run regression benchmarks, and synthesize documentation without bankrupting development budgets.
- **Admin Capability:** As the platform owner, the System Administrator can willingly provide accounts, credentials, and persistent cookies for various external platforms.
- **Execution Mechanism:** High utilization of **Level 3 (Browser Automation & Compute Arbitrage)**. The platform deploys headless browser pools against web sandbox platforms using Admin-owned accounts. The admin manages these sessions in the secure Admin Cloud Vault.

### Track B: Customer / End-User Capability Plane
- **The Reality:** Forcing end-users or clients to provide third-party website passwords, solve CAPTCHAs, or configure browser session profiles is an unacceptable usability failure ("অহেতুক ঝামেলা") and a major security liability.
- **Customer Usability Guarantee:** Customers are **NEVER asked to supply external website passwords**.
- **Execution Mechanism:** Customers operate via **Mode 3 (Session-Only / Ephemeral & Managed APIs)**:
  1. Instant capabilities are delivered through SupremeAI's pre-integrated native APIs and MCP toolchains.
  2. If a customer wishes to link an external account (e.g., their personal GitHub repo or Slack workspace), they do so strictly via standard **OAuth2** or a single-run **Ephemeral Token (Mode 3)** that is held in temporary memory and wiped upon run completion.
  3. Customers never see browser automation, headless scrapers, or git worktree mechanics—they experience instant, clean, outcome-driven responses.

---

## 2. Core Principles & Global Invariants

SupremeAI enforces the following universal architectural invariants across all layers:

> ### The Universal Dynamic Rule
> **If a value, entity, provider, model, integration, capability, resource, workflow, policy, or behavior can be discovered, registered, configured, or selected dynamically, it MUST NOT be hardcoded into application logic.**

1. **Workers, Never the Control Plane:** External systems, whether proprietary APIs, open-source agents, or web-based coding platforms, are interchangeable execution workers. The SupremeAI MCP Control Tower strictly owns intent, task planning, policy enforcement, quota accounting, run state, verification, and promotion.
2. **Intent Over Concrete Examples:** Mentions of external platforms (e.g., Bolt, Lovable, v0, OpenHands, Z.ai) are illustrative instances of dynamic resource pools ($1 \dots N$). The system core must never contain `if provider == "bolt"` or `if provider == "lovable"`.
3. **Decoupled Three-Pillar Separation:**
   - **Control Plane:** SupremeAI MCP Control Tower (governance, policy, state, events).
   - **Execution Channel:** Native REST/gRPC API, MCP Tool Gateway, or Browser Automation Fallback.
   - **External Worker:** The 3rd-party intelligence or platform executing the assigned capability.
4. **Zero-Gap Operational Rigor:** A capability is never complete until end-to-end data flow, execution engine, security verification, and audit telemetry are verified in running code.

---

## 3. Capability-First Abstraction Layer

Workflows define required **Capabilities**, never specific providers. Providers register the capabilities they can satisfy along with cost, quota, latency, and trust metrics.

```text
User / Orchestrator Task
          ↓
  Required Capability
          ↓
  Provider Discovery & Policy Filtering
          ↓
  Runtime Selector (Cost, Quota, Health)
          ↓
  Execution via Adapter
```

### Canonical Capability Signatures

#### 1. `coding.plan.v1`
- **Intent:** Analyze requirements and repository context to produce an atomic, testable execution plan.
- **Input:** `goal`, `repo_context`, `file_manifest`, `architectural_constraints`, `risk_tier`.
- **Output:** `StructuredPlan` (ordered tasks, acceptance criteria, target file boundaries, expected test suites).
- **Default Risk Tier:** LOW. Merge Authority: None.

#### 2. `coding.execute.v1`
- **Intent:** Implement an approved plan inside an isolated workspace.
- **Input:** `approved_plan`, `worktree_ref`, `execution_constraints`, `allowed_tool_matrix`.
- **Output:** `ChangesetArtifact` (git branch, commit diff, new test files, PR proposal).
- **Default Risk Tier:** MEDIUM. Merge Authority: Propose Only.

#### 3. `code.review.v1`
- **Intent:** Adversarially review proposed changesets against the approved plan, security invariants, and regressions.
- **Input:** `changeset_ref`, `original_plan`, `ci_telemetry`, `security_rules`.
- **Output:** `ReviewVerdict` (PASS, REJECT, REQUEST_REPAIR), detailed line-level findings.
- **Default Risk Tier:** LOW.

#### 4. `code.repair.v1`
- **Intent:** Remediate verification failures or review defects within an existing changeset.
- **Input:** `failed_changeset`, `verification_errors`, `review_findings`, `attempt_number`.
- **Output:** `RepairedChangesetArtifact` (supplementary commits, corrected tests).
- **Default Risk Tier:** MEDIUM (Subject to bounded retry limits: Max 3 attempts).

---

## 4. Dynamic Registries Architecture

SupremeAI maintains three decoupled, data-driven registries:

### 4.1 Capability Registry (`backend/core/registries/capability_registry.py`)
Maps capability identifiers to parameter schemas, validation contracts, default risk tiers, and SLA bounds:

```python
class CapabilityDefinition(BaseModel):
    capability_id: str          # e.g., "coding.execute.v1"
    version: str                # SemVer
    input_schema: dict          # JSONSchema for task payload
    output_schema: dict         # JSONSchema for returned artifacts
    default_risk: RiskTier      # LOW, MEDIUM, HIGH, CRITICAL
    timeout_seconds: int        # Hard SLA deadline
    max_retries: int            # Bound for self-repair loops
```

### 4.2 Provider Registry (`backend/core/registries/provider_registry.py`)
Tracks registered external entities, their supported capabilities, adapter references, and live operational metrics:

```python
class ProviderRecord(BaseModel):
    provider_id: str            # Unique slug, e.g., "ext-claude-worker", "sandbox-web-01"
    display_name: str
    provider_kind: ProviderKind # NATIVE_API, MCP_SERVER, BROWSER_AUTOMATION, INTERNAL
    supported_capabilities: list[str]
    channel_priority: int       # 1 (Native) -> 2 (MCP) -> 3 (Browser)
    health_status: HealthState  # HEALTHY, DEGRADED, UNHEALTHY, SUSPENDED
    operational_track: TrackType# ADMIN_INTERNAL, CUSTOMER_EXTERNAL, BOTH
    quota_policy_id: str
    cost_per_unit: Decimal
    latency_p50_ms: int
    trust_tier: TrustTier       # UNTRUSTED, SANDBOXED, TRUSTED, SYSTEM
    adapter_class: str          # Fully qualified Python path
    enabled: bool
    metadata: dict[str, Any]
```

### 4.3 Integration Registry (`backend/core/registries/integration_registry.py`)
Defines external services and websites accessed via authenticated channels, required authentication mechanisms, and rate limits:

```python
class IntegrationRecord(BaseModel):
    integration_id: str         # e.g., "github-enterprise", "web-builder-alpha"
    domain: str
    supported_capabilities: list[str]
    target_track: TrackType     # ADMIN_INTERNAL (Browser Arbitrage) vs CUSTOMER (OAuth/API)
    auth_requirement: AuthType  # OAUTH2, API_KEY, COOKIE_SESSION, USER_DEVICE_PASS
    persistence_mode_supported: list[AuthPersistenceMode]
    rate_limit_per_minute: int
    session_timeout_minutes: int
    tos_compliance_verified: bool
    enabled: bool
```

---

## 5. Execution Channel Hierarchy & Operational Discipline

The selection of communication channels differs strictly by track:

```text
Track A (Admin / SupremeAI Self-Evolution):
  ┌────────────────────────────────────────────────────────┐
  │ 1. Admin-Managed Browser Automation (Compute Arbitrage)│ ◄── Primary cost-saver for heavy internal tasks
  │ 2. Native API / MCP (Where free tiers or keys exist)   │
  └────────────────────────────────────────────────────────┘

Track B (Customer / End-User Plane):
  ┌────────────────────────────────────────────────────────┐
  │ 1. Managed Native API & MCP (Instant, high-speed)      │ ◄── Fast, zero-friction, standard UX
  │ 2. Standard OAuth2 / Customer BYOK                     │
  │ 3. Mode 3 (Session-Only Ephemeral - Zero DB Storage)   │ ◄── Strictly NO browser scraping for customers
  └────────────────────────────────────────────────────────┘
```

### The Browser Conservation Protocol (For Internal Admin Tasks):
- **Zero Idle Sessions:** 40 registered integrations **never** means 40 running browser processes. Idle browser sessions are strictly terminated.
- **Lightweight Pre-Flight:** If a simple HTTP scrape or API probe can satisfy the intent, headless browser launching is prohibited.
- **Headless & Resource Stripped:** Images, fonts, stylesheets, and multimedia are dropped at network layer unless visual layout verification is explicitly required.

---

## 6. Authentication Persistence Modes & Zero-Persistent-Credential Security

> ### Critical Invariant
> **Credential Persistence ≠ Browser Session Persistence.**  
> Authorization is securely managed; browser execution sessions are short-lived, isolated, and disposable.

SupremeAI formalizes **Four Authentication Persistence Modes**, mapping them to the appropriate operational track:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    Four Authentication Persistence Modes                        │
├─────────────────────┬──────────────────┬─────────────────┬──────────────────────┤
│ Mode 1: Cloud Vault │ Mode 2: Local    │ Mode 3: Session │ Mode 4: User-Session │
│                     │         Device   │         Only    │         Attach       │
├─────────────────────┼──────────────────┼─────────────────┼──────────────────────┤
│ Encrypted AES-256   │ User's OS store  │ Memory-only     │ Attaches directly to │
│ in SupremeAI DB.    │ (DPAPI/Keychain) │ for 1 Run; zero │ user's live browser  │
│ [Primary for Admin  │ or LocalStorage. │ DB persistence. │ via extension hook.  │
│  Self-Evolution]    │ Machine-bound.   │ [BEST FOR USER] │ Active user presence.│
└─────────────────────┴──────────────────┴─────────────────┴──────────────────────┘
```

### Mode 1: Cloud Vault (Admin-Dedicated Persistent Store)
- **Primary Use:** SupremeAI self-evolution, background cron maintenance, unattended admin jobs.
- **Mechanism:** Secrets encrypted with AES-GCM-256 keys managed by Infisical / KMS.
- **Capability:** Full autonomous background execution; scheduled cron jobs run 24/7.
- **Security Control:** Master key separation, audit logs on every decryption event, zero secret leakage in logs.

### Mode 2: Local / Device-Bound Store
- **Mechanism:** Credentials saved on the customer’s local machine via OS Credential Manager (Windows DPAPI, macOS Keychain, Linux Secret Service).
- **Capability:** When running tasks from IDE / Local CLI, credentials are fed securely through IPC.
- **Constraint:** Cloud server cannot run unattended scheduled jobs if the customer's machine is offline.

### Mode 3: Session-Only / Ephemeral (The Recommended Customer Standard)
- **Primary Use:** All privacy-conscious end-users and client applications.
- **Mechanism:** The user supplies a one-time API token or OAuth grant for a single task execution.
- **Capability:** Credential is held in volatile memory for the duration of the run and wiped via memory overwrite (`bzero`) upon completion.
- **Guarantee:** Zero password storage in SupremeAI database. No browser hassle. Instant execution.

### Mode 4: User-Session Attach (Direct Extension Hook)
- **Mechanism:** The agent connects to an active user session in the user's browser via a local companion extension or CDP (Chrome DevTools Protocol) bridge.
- **Capability:** Uses the user's already-logged-in session without ever extracting, transmitting, or storing passwords.
- **Constraint:** Requires active user presence and interactive permission.

---

## 7. On-Demand Browser Session Broker (For Admin Self-Evolution)

For Track A internal compute arbitrage, the **Session Broker** manages the lifecycle of browser contexts:

```text
Admin Task Triggered (e.g., Heavy Refactoring / Code Generation)
                           │
                           ▼
                [ Session Broker Check ]
               Reusable context available?
              ├── YES (Valid TTL, same target) ──► Attach
              └── NO ───────────────────────────► Spawn Headless Context
                                                         │
                                                         ▼
                                          [ Ephemeral Playwright Context ]
                                          (Injected admin cookies, stealth)
                                                         │
                                                         ▼
                                          [ Run Arbitrage Worker & Extract ]
                                                         │
                                                         ▼
                                          [ Context Closed & Memory Wiped ]
```

### Lifecycle Constraints:
1. **Hard TTL:** Browser contexts expire after 15 minutes max, regardless of activity.
2. **Inactivity Timeout:** 3 minutes of zero DOM activity triggers immediate disposal.
3. **Anti-Detection Stealth:** Injected stealth scripts mask `navigator.webdriver`, spoof canvas fingerprints, and mimic human typing cadences (30ms–100ms jitter).

---

## 8. Multi-Team Parallel Agent Orchestration & Zero-Conflict Engine

When multiple agents or multiple agent teams work concurrently across the SupremeAI codebase during self-evolution, collisions are prevented using the **Monorepo Isolated Execution & Pre-Execution Resource Lock Architecture**:

```text
                                  SupremeAI Control Tower
                                             │
                   ┌─────────────────────────┴─────────────────────────┐
                   ▼                                                   ▼
            Team 1 / Workgroup A                                Team 2 / Workgroup B
          (e.g., Frontend Feature)                            (e.g., AI Integration)
                   │                                                   │
     [ Resource Lock Check ]                             [ Resource Lock Check ]
     Acquire: `frontend/src/chat/*`                      Acquire: `backend/ai/*`
                   │                                                   │
                   ▼                                                   ▼
     Isolated Git Worktree A                             Isolated Git Worktree B
    `feature/team-a-task-001`                           `feature/team-b-task-002`
                   │                                                   │
     ┌─────────────┴─────────────┐                       ┌─────────────┴─────────────┐
     │ Planner ──► Coder ──►     │                       │ Planner ──► Coder ──►     │
     │ Tester  ──► Reviewer      │                       │ Tester  ──► Reviewer      │
     └─────────────┬─────────────┘                       └─────────────┬─────────────┘
                   │                                                   │
                   ▼                                                   ▼
              PR Proposed                                         PR Proposed
                   │                                                   │
                   └─────────────────────────┬─────────────────────────┘
                                             │
                                             ▼
                                Team 3: Integration Authority
                             (Conflict Resolver, CI, Policy Gate)
                                             │
                                             ▼
                                  Promotion / Merge to MAIN
```

### 8.1 Single Monorepo with Isolated Workspaces
- External agents **NEVER touch the `main` branch directly**.
- Each run executes inside an isolated **Git Worktree** or lightweight ephemeral container.
- Shared contracts, types, and documentation remain synchronized in the monorepo without cross-repo fragmentation.

### 8.2 Pre-Execution Resource Ownership Lock (Zero Merge-Conflict Strategy)
1. **Scope Declaration:** During `coding.plan.v1`, the Planner declares the list of target file paths or directories.
2. **Lock Acquisition:** The Orchestrator attempts to acquire path-based advisory locks in Redis:
   - Task A acquires `lock:path:frontend/src/features/chat/*`.
   - Task B requests `lock:path:backend/ai/*` -> Granted (Disjoint scopes).
3. **Collision Detection & Adaptive Queuing:**
   - If Task C attempts to acquire `frontend/src/features/chat/ChatBox.tsx` while Task A holds the lock, the Orchestrator **detects the conflict immediately**.
   - Instead of running concurrently and failing at git merge, Task C is placed in a **Sequential Dependency Queue** waiting on Task A's PR finalization.

### 8.3 Team 3 / Integration Authority
- **Conflict Resolver:** Analyzes non-overlapping git rebases automatically.
- **CI / Static Gate:** Verifies build compilation, linting, unit tests, and regression suites.
- **Admin / Policy Engine:** Only the MCP Control Tower and Human Administrators hold merge credentials to `main`.

---

## 9. Run State Machine & Execution Lifecycle

Every external execution operates under an observable, fault-tolerant state machine:

```text
        [ REQUESTED ]
              │
              ▼
      [ POLICY_CHECKED ] ──(Violation)──► [ REJECTED ]
              │
              ▼
         [ PLANNED ]
              │
              ▼
      [ PLAN_APPROVED ]
              │
              ▼
        [ EXECUTING ] ────(Timeout/Crash)──► [ RETRY / FAILOVER ]
              │
              ▼
     [ ARTIFACT_READY ]
              │
              ▼
       [ VERIFYING ] ◄─────────────────────────┐
         │         │                           │
      (Pass)     (Fail)                        │
         │         ▼                           │
         │   [ REPAIRING ] ──(Attempt < 3)─────┘
         │         │
         │      (Attempt >= 3)
         │         ▼
         │   [ ESCALATED_TO_HUMAN ]
         │
         ▼
  [ PROMOTION_GATE ]
         │
         ▼
    [ COMPLETED ]
```

---

## 10. Bounded Self-Healing & Verification Loop

External code generation must undergo rigorous, automated validation before promotion:
- **Strict Retry Ceiling:** Maximum 3 automated repair iterations. Unbounded loops are hard-prevented.
- **Failure Context Injection:** The repair agent receives exact stack traces, failed test names, and reviewer diff comments.
- **Rollback Guarantee:** If a repair attempt degrades existing tests, the worktree is rolled back to the previous stable commit before retrying.

---

## 11. Concurrency-Safe Durable Quota Accounting

Free-tier and paid-tier quotas are tracked durably via Redis atomic commands (`DECRBY` / `INCRBY`) to prevent race conditions across parallel runs. Multi-tenant rate limiters protect shared provider pools.

---

## 12. Governance, Security & Risk Tiers

| Risk Tier | Task Characteristics | Permitted Automation | Governance Gate |
|---|---|---|---|
| **LOW** | Documentation, test creation, pure function generation, read-only analysis. | Fully autonomous external execution. | Automatic CI verification. |
| **MEDIUM** | Feature implementation, component refactoring, non-critical bug fixes. | External execution with isolated worktree. | Automated review + verification pass. |
| **HIGH** | Core business logic, API contract changes, external integrations, routing logic. | External execution allowed under strict sandboxing. | Human-in-the-Loop (HITL) approval required before merge. |
| **CRITICAL** | Auth systems, database migrations, security policies, billing, infrastructure provisioning. | **External agent execution strictly prohibited.** Internal trusted core only. | Super-Admin dual-signoff. |

---

## 13. Canonical Plan Governance & Living Document Architecture

1. **One Distinct Subject = One Canonical Plan:** External Agent Orchestration is maintained solely in `docs/plans/architecture/EXTERNAL_AGENT_ORCHESTRATION_LAYER_PLAN.md`.
2. **Evolution Section Inside Document:** Tracks Stages 1 through 4.
3. **Structured YAML Frontmatter:** Conforms to `CANONICAL_PLANNING_RECONCILIATION_AND_GUARDRAILS_PLAN.md`.

---

## 14. Implementation Roadmap (Phases 1–6)

- **Phase 1 (Universal Foundation):** Dynamic registries and Pydantic capability contracts.
- **Phase 2 (Managed APIs & Gateway):** Native API & MCP routing for fast customer tasks.
- **Phase 3 (Admin Browser Broker & Arbitrage Pool):** Admin Cloud Vault + headless Playwright pool for SupremeAI background evolution.
- **Phase 4 (Customer Mode 3 & Zero-Persistent Credential):** Ephemeral token handling, OAuth2 flows, and zero-password customer UX.
- **Phase 5 (Multi-Team Worktrees & Path Locks):** Monorepo parallel isolation and pre-execution resource locking.
- **Phase 6 (Telemetry & Self-Learning Routing):** Cost/latency observability and MCP Control Tower dashboard integration.

---

## 15. Architectural Signoff & Invariants Summary

1. **Dual-Track Separation:** SupremeAI self-evolution uses Admin-managed browser arbitrage; customers get frictionless, zero-password, Mode 3 managed APIs.
2. **No Hardcoded Vendor Logic:** Providers are interchangeable workers selected dynamically by capability, quota, and health.
3. **Workers, Not Authorities:** External agents only propose diffs; SupremeAI Control Tower and Governance retain sole merge authority.
4. **Pre-Execution Conflict Prevention:** Monorepo parallel runs operate in isolated worktrees with proactive path-level resource locking, preventing merge conflicts before execution begins.