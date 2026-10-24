---
id: platform-oss-integration
subject: "SupremeAI — Platform Architecture Enhancement & Open-Source Integration Plan"
document_role: implementation
planning_authority: Platform Circle
canonical: false
status: blocked
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
target_scope: supremeai_internal
---

# SupremeAI — Platform Architecture Enhancement & Open-Source Integration Plan

```yaml
id: platform-oss-integration-plan
title: Platform architecture enhancement & open-source integration evaluation (OpenViking, agentmemory, Browser Use, Harness, Diagram, Archify, Colibrì, skill packs)
status: active
owner_circle: C1 (Code & Quality)
scope: concept-adoption decisions + phase plan; no runtime dependencies introduced by this document
depends_on: [architecture/SUPREMEAI_MASTER_PLAN_CANONICAL.md, UNIFIED_NEXT_ROADMAP_2026-09-15.md]
implements: []
supersedes: []
superseded_by: []
source_of_truth: false
last_verified: 2026-09-15
code_evidence: audit findings in docs/audits/FULL_SYSTEM_AUDIT_2026-09-14.md + module wiring audit
test_evidence: per-phase exit criteria; see roadmap milestones M2-M9
```

**Repository audited:** `SaifulHaqueNiloy/supremeai`  
**Baseline:** `main` / September 2026 audit snapshot  
**Purpose:** Evaluate OpenViking, agentmemory, Browser Use, Awesome Harness Engineering, Diagram Design, Archify, Colibrì, Anthropic Cybersecurity Skills, and Scientific Agent Skills against SupremeAI's **Chat / Files / Tools / Runs / Workspace** architecture, determine what already exists, what is genuinely missing, and define a safe implementation roadmap.

> **Core principle:** Do not copy any repository wholesale. Extract the strongest architectural idea from each project, adapt it to SupremeAI's existing contracts, and avoid creating duplicate subsystems.

---

## 1. Executive decision

| Repository / idea | Current SupremeAI status | Real need | Recommendation | Priority |
|---|---|---|---|---|
| **OpenViking** | No direct OpenViking implementation found in the audited code search | Hierarchical context/file retrieval is highly valuable | **Adopt the concept, not the whole database** | P0 |
| **agentmemory** | No direct agentmemory integration found; SupremeAI already has substantial memory + pgvector infrastructure | Long-term memory is already a platform capability, but consolidation/quality can improve | **Do not add as a second memory backend**; borrow useful memory concepts | P0/P1 |
| **Browser Use** | Browser automation already exists through Playwright/Chromium | High-value Tools/Runs capability, but resource isolation is the real problem | **Do not replace existing browser stack blindly**; evaluate selected ideas/adapters | P1 |
| **Awesome Harness Engineering** | Several related principles already exist in docs/scripts/agent skills | Very useful for AI-agent reliability and safe execution | **Adopt patterns as engineering policy** | P0 |
| **Diagram Design** | No confirmed direct implementation found | Useful for premium output/UI, but not core platform infrastructure | **Optional output renderer/skill** | P2 |
| **Archify** | No confirmed direct integration; repo already has audit tooling and architecture documentation | Useful for internal dependency visualization | **Prefer Dependency Cruiser + Pydeps + custom CI** | P1 |
| **Colibrì** | No relevant implementation found | Does not solve current Chat/Files/Tools/Runs/Workspace problems | **Do not integrate** | P4 |
| **Anthropic Cybersecurity Skills** | No confirmed direct import of this skill pack | Specialized domain capability only | **Optional skill-pack marketplace/content, not core dependency** | P3 |
| **Scientific Agent Skills** | No confirmed direct integration | Specialized vertical capability | **Optional skill-pack marketplace/content** | P3 |

### Bottom line

The four highest-impact architectural themes are:

1. **Hierarchical context retrieval for Files/Workspace**
2. **Unified, durable memory rather than another memory subsystem**
3. **Safe browser/tool execution with isolated Runs**
4. **Automated architecture/dependency intelligence in CI and for AI agents**

---

# 2. What is already implemented in SupremeAI?

## 2.1 Memory: substantially implemented

SupremeAI already has an `ai_memory` model described as vector-backed semantic memory. The repository contains:

- `backend/models/ai_memory.py`
- `backend/services/memory_service.py`
- `backend/core/ai_memory/vector_store.py`
- `backend/core/memory/auto_rag_injector.py`
- `scripts/ai/memory_read.py`
- `scripts/ai/memory_write.py`
- canonical embedding utilities
- Supabase/pgvector migrations and RPCs

The current database contract is `vector(384)`, with `match_ai_memory` RPC support, and the code includes local/fallback behavior for constrained environments.

### Decision

**Do NOT install agentmemory as another memory database.**

Instead, improve SupremeAI's existing memory layer with ideas from modern memory systems:

```text
User / Workspace
      ↓
Memory extraction
      ↓
Memory classification
 ┌────┼───────────────┐
 │    │               │
Fact Preference   Project Context
 │    │               │
 └────┼───────────────┘
      ↓
Durable memory store
      ↓
Hybrid retrieval
      ↓
Context budgeter
      ↓
Chat / Agent Run
```

### Required improvement

Add explicit memory scopes:

```text
GLOBAL
  ↓
USER
  ↓
WORKSPACE
  ↓
PROJECT
  ↓
CHAT
  ↓
RUN
```

The same memory item should not automatically leak across scopes.

---

# 3. OpenViking: highest-value concept

## 3.1 Problem it solves

A conventional RAG pipeline can retrieve semantically similar chunks but may still lose:

- file hierarchy
- project structure
- local context
- parent/child relationships
- the difference between summary and raw source

For SupremeAI's **Files + Workspace + Chat + Runs**, this matters enormously.

## 3.2 Do not copy the storage engine

Instead, implement an **OpenViking-inspired Context Filesystem layer** over SupremeAI's existing storage/RAG infrastructure.

Suggested logical URI:

```text
sa://workspace/{workspace_id}/project/{project_id}/...
```

Example:

```text
sa://workspace/acme/project/supremeai/
├── README.md
├── frontend/
│   ├── src/
│   └── package.json
└── backend/
    ├── core/
    └── services/
```

## 3.3 Three-level context

Use the same conceptual model:

```text
L0 = tiny semantic summary
L1 = structural/context summary
L2 = raw content
```

Example:

```text
package.json

L0:
"Frontend package manifest for React/Vite monorepo."

L1:
"Defines scripts, dependencies and workspace relationships."

L2:
actual package.json
```

## 3.4 Context selection algorithm

Never dump an entire repository into the LLM.

```text
User request
    ↓
Intent classifier
    ↓
Workspace/project resolver
    ↓
L0 retrieval
    ↓
Need more context?
    ├── no → answer
    └── yes
          ↓
         L1
          ↓
    Need exact source?
          ├── no → answer
          └── yes
                ↓
               L2
```

### Context budget

Every Run gets a hard budget:

```yaml
context:
  max_tokens: 24000
  l0_budget: 2000
  l1_budget: 7000
  l2_budget: 15000
```

This is much more useful than blindly increasing model context windows.

---

# 4. Files architecture upgrade

SupremeAI should evolve Files from:

```text
Upload → Parse → Embed → Search
```

to:

```text
Upload
  ↓
File normalization
  ↓
Structure extraction
  ↓
L0/L1/L2 generation
  ↓
Metadata + embeddings
  ↓
Context index
  ↓
Workspace-aware retrieval
```

### Required metadata

```text
file_id
workspace_id
project_id
parent_id
path
mime_type
language
size
hash
version
summary_l0
summary_l1
content_ref
embedding
```

### Important

The raw file should remain the source of truth.

Embeddings and summaries are derived indexes.

---

# 5. agentmemory: adopt concepts, not dependency

SupremeAI already has durable memory and vector search. Adding another memory package would create:

```text
Memory A
Memory B
Memory C
```

which is exactly the kind of duplicate subsystem we want to eliminate.

### Instead add:

#### A. Memory lifecycle

```text
Candidate
   ↓
Validated
   ↓
Stored
   ↓
Reinforced
   ↓
Updated / Superseded
   ↓
Archived
```

#### B. Memory confidence

```text
confidence: 0.0 → 1.0
source: user | system | inferred | tool
last_confirmed_at
expires_at
```

#### C. Hybrid retrieval

```text
Vector similarity
       +
Keyword retrieval
       +
Entity/relationship retrieval
       +
Recency
       +
Workspace scope
```

Final ranking:

```text
score =
  semantic_similarity
  + lexical_score
  + recency
  + confidence
  + scope_match
```

---

# 6. Browser Use: high value, but not as a replacement

SupremeAI already has browser automation through Playwright/Chromium, including browser agents and scraping/browser endpoints.

The repository also documents a lightweight HTTP scraping path and a heavier Playwright/Chromium browser path.

Therefore:

**Do not introduce Browser Use simply because it provides browser control. SupremeAI already has that capability.**

## What should be borrowed

### A. Agent-friendly browser abstraction

Expose tools like:

```text
browser.open
browser.click
browser.type
browser.select
browser.extract
browser.screenshot
browser.download
browser.wait
```

rather than exposing Playwright internals directly to agents.

### B. Action planning

```text
LLM plan
   ↓
Browser tool
   ↓
Action validation
   ↓
Execution
   ↓
Observation
   ↓
LLM
```

### C. Run isolation

Every browser operation belongs to a Run:

```text
Run
 ├── browser session
 ├── cookies
 ├── credentials
 ├── downloads
 ├── screenshots
 └── audit events
```

---

# 7. Browser resource architecture

This is especially important because SupremeAI already has documented concern around the resource cost of Playwright/Chromium.

Do not put every browser task inside the main API process.

Use:

```text
API
 │
 └── Run Scheduler
       │
       ├── lightweight HTTP worker
       │
       └── browser worker
              │
              └── isolated browser session
```

Routing:

```text
Static page?
   ↓
httpx / lightweight parser

JavaScript-heavy page?
   ↓
Browser worker

Multi-step interaction?
   ↓
Browser worker

No browser needed?
   ↓
normal tool execution
```

This preserves the existing lightweight-first direction.

---

# 8. Awesome Harness Engineering: adopt as policy

This repository/category should be treated as **architecture inspiration**, not runtime dependency.

The useful ideas for SupremeAI are:

### Tool boundaries

Agents should never receive unrestricted infrastructure access.

```text
Agent
 ↓
Tool registry
 ↓
Policy
 ↓
Permission
 ↓
Sandbox
 ↓
Execution
```

### Run budget

Every agent Run should have:

```yaml
max_steps: 40
max_duration: 10m
max_tool_calls: 100
max_output_tokens: ...
max_cost: ...
```

### Failure states

Do not allow:

```text
tool failure
   ↓
LLM retries forever
```

Instead:

```text
failure
 ↓
classify
 ├── retryable
 ├── recoverable
 ├── user_action_required
 └── fatal
```

### Quality gates

Before completing a Run:

```text
plan validation
↓
tool result validation
↓
output validation
↓
security validation
↓
completion
```

---

# 9. Runs should become the execution boundary

For SupremeAI's architecture:

```text
Chat
  ↓
creates
  ↓
Run
  ↓
Tools / Files / Browser / Code
  ↓
Artifacts
  ↓
Result
```

This is preferable to allowing Chat directly to invoke arbitrary infrastructure.

A Run should have:

```text
run_id
user_id
workspace_id
chat_id
status
started_at
finished_at
budget
tool_calls
artifacts
events
error
```

This creates a common execution model for:

- browser tasks
- code execution
- research
- file analysis
- agent workflows
- MCP tools

---

# 10. Diagram Design

This is useful, but it should remain an **output capability**, not core infrastructure.

Use it when the model decides:

```text
User asks:
"Explain this architecture"
```

Then:

```text
LLM
 ↓
Diagram intent
 ↓
Structured graph JSON
 ↓
Safe renderer
 ↓
SVG/HTML
 ↓
Chat artifact
```

Do NOT let the model directly inject arbitrary HTML into the application DOM.

Use a constrained schema:

```json
{
  "type": "architecture",
  "nodes": [],
  "edges": [],
  "groups": [],
  "annotations": []
}
```

Then the frontend renderer owns the HTML/SVG generation.

---

# 11. Archify / architecture visualization

This is valuable primarily for **SupremeAI development**, not for end users.

The better solution is:

```text
Frontend
  → Dependency Cruiser

Backend
  → Pydeps

Repository
  → structure graph

Runtime
  → system_dependencies

CI
  → architecture rules
```

SupremeAI already contains architecture/audit tooling and documentation around dependency/coupling and circular dependencies.

Therefore Archify should not become another permanent dependency unless a concrete capability is missing after testing.

---

# 12. Existing Central Dependency Graph

This is a major opportunity.

SupremeAI already documents a Central MCP Dependency Graph using:

```text
system_dependencies
system_summary
system_health
```

and describes it as the active architecture for dependency/service analysis.

Therefore the target architecture should be:

```text
                 SUPREMEAI GRAPH
                       │
          ┌────────────┴────────────┐
          │                         │
      Static Graph              Runtime Graph
          │                         │
 Dependency Cruiser             MCP Graph
 Pydeps                          system_dependencies
 Repo structure                  service health
          │                         │
          └────────────┬────────────┘
                       ↓
               Unified Graph
                       ↓
          Architecture Intelligence
```

This is much better than introducing Archify as a parallel system.

---

# 13. Architecture intelligence for AI agents

The graph should not only be for humans.

Before an AI agent modifies code:

```text
Task
 ↓
Architecture lookup
 ↓
Dependency graph
 ↓
Affected modules
 ↓
Blast radius
 ↓
Relevant tests
 ↓
Implementation
 ↓
Graph re-check
```

Example:

```text
Changed:
packages/shared-types/src/User.ts

Affected:
7 modules

Critical:
Auth
Billing

New dependency:
User.ts → BillingService

Result:
⚠️ architecture review required
```

---

# 14. Colibrì

## Decision: reject for current roadmap

Colibrì's goal of running large MoE models under tight RAM constraints is interesting technology, but it does not directly improve:

- Chat
- Files
- Workspace
- Tools
- Runs
- memory
- architecture wiring

It also risks introducing another specialized inference subsystem.

SupremeAI's current provider/gateway approach is already better aligned with provider-agnostic model selection.

**Do not integrate.**

Revisit only if SupremeAI later needs local large-MoE inference on constrained hardware.

---

# 15. Cybersecurity Skills

Do not make an 800+ skill pack a core dependency.

Instead build:

```text
SupremeAI Skill Registry
       │
       ├── General
       ├── Coding
       ├── Browser
       ├── Security
       ├── Science
       └── Enterprise
```

Security skills can be installed/activated per workspace.

### Important safety boundary

Security tools must have explicit:

```text
authorization
scope
target allowlist
rate limit
audit trail
```

No global unrestricted penetration-testing tool should be automatically available to every agent.

---

# 16. Scientific Agent Skills

Same architecture.

Do not hardwire 165+ scientific tools into the core backend.

Use:

```text
Skill Pack
   ↓
Tool manifest
   ↓
Capability registry
   ↓
Permission
   ↓
Run
```

A genomics workspace can enable genomics tools without increasing the core platform's dependency footprint.

---

# 17. Recommended SupremeAI platform architecture

The final conceptual architecture should become:

```text
                         USER
                          │
                          ▼
                       CHAT
                          │
                          ▼
                    CONTEXT ENGINE
              ┌───────────┼───────────┐
              │           │           │
            Memory      Files      Workspace
              │           │           │
              │       L0/L1/L2        │
              │           │           │
              └───────────┼───────────┘
                          │
                          ▼
                        AGENT
                          │
                          ▼
                         RUN
                          │
              ┌───────────┼────────────┐
              │           │            │
            Tools      Browser       Code
              │           │            │
              └───────────┼────────────┘
                          │
                          ▼
                      ARTIFACTS
                          │
                          ▼
                       RESULT
```

Cross-cutting:

```text
Security
Permissions
Observability
Cost/Token budget
Architecture graph
Audit trail
```

---

# 18. Implementation phases

## Phase 0 — Baseline

- [ ] Freeze current architecture contracts
- [ ] Inventory existing memory/files/browser/run/tool subsystems
- [ ] Generate frontend dependency graph
- [ ] Generate backend dependency graph
- [ ] Establish architecture baseline
- [ ] Identify duplicate implementations

**Deliverable:** architecture baseline report.

---

## Phase 1 — Context Engine

**Highest priority**

- [ ] Create context abstraction
- [ ] Add workspace/project hierarchy
- [ ] Implement L0 summaries
- [ ] Implement L1 structural summaries
- [ ] Keep L2 raw source
- [ ] Add context budgeter
- [ ] Add scoped retrieval
- [ ] Integrate with Files
- [ ] Integrate with Chat
- [ ] Integrate with Runs

**Goal:** retrieve the minimum context required for a task.

---

## Phase 2 — Memory consolidation

- [ ] Audit existing memory paths
- [ ] Remove/avoid duplicate memory stores
- [ ] Add memory scopes
- [ ] Add confidence
- [ ] Add source/provenance
- [ ] Add lifecycle
- [ ] Add hybrid ranking
- [ ] Integrate memory with context engine

**Goal:** one canonical SupremeAI memory system.

---

## Phase 3 — Run-centric execution

- [ ] Make Run the common execution boundary
- [ ] Add step budgets
- [ ] Add time budgets
- [ ] Add tool-call budgets
- [ ] Add retry classification
- [ ] Add cancellation
- [ ] Add artifact tracking
- [ ] Add execution audit events

---

## Phase 4 — Browser modernization

- [ ] Keep lightweight HTTP path
- [ ] Keep Playwright as heavy path
- [ ] Isolate browser workers
- [ ] Add browser tool abstraction
- [ ] Add Run association
- [ ] Add session lifecycle
- [ ] Add SSRF/target policy
- [ ] Add resource quotas
- [ ] Measure RAM/CPU per browser Run

**Do not blindly replace Playwright with Browser Use.**

---

## Phase 5 — Architecture Intelligence

- [ ] Dependency Cruiser
- [ ] Pydeps
- [ ] Repository structure graph
- [ ] Architecture rules
- [ ] Circular dependency detection
- [ ] Architecture diff
- [ ] Blast-radius analysis
- [ ] Health score
- [ ] GitHub PR checks
- [ ] Nightly deep audit

---

## Phase 6 — Runtime graph integration

- [ ] Connect static dependency graph to `system_dependencies`
- [ ] Add service/runtime nodes
- [ ] Reconcile declared vs observed dependencies
- [ ] Add health information
- [ ] Add runtime blast radius
- [ ] Expose graph through MCP
- [ ] Add human-readable dashboard

---

## Phase 7 — Diagram output

- [ ] Define structured diagram schema
- [ ] Add safe SVG renderer
- [ ] Add architecture diagram renderer
- [ ] Add sequence diagram renderer
- [ ] Add flow diagram renderer
- [ ] Integrate with Chat artifacts

---

## Phase 8 — Skill ecosystem

- [ ] Skill registry
- [ ] Skill manifest
- [ ] Capability permissions
- [ ] Security skill pack
- [ ] Scientific skill pack
- [ ] Workspace-level enable/disable
- [ ] Skill versioning
- [ ] Skill sandboxing

---

# 19. CI architecture

Recommended workflow:

```text
PR
 │
 ├── Frontend dependency scan
 ├── Backend dependency scan
 ├── Architecture rules
 ├── Cycle detection
 ├── Changed-edge detection
 ├── Blast-radius analysis
 └── Relevant tests
          │
          ▼
      Architecture Gate
```

### Baseline strategy

Do not fail the entire project because of old violations.

If `main` has:

```text
14 existing cycles
```

then a PR that keeps 14 should pass.

A PR that creates 15 should fail.

This makes architecture cleanup incremental and realistic for a solo developer.

---

# 20. Cost and resource policy

Every new integration must pass:

```text
Does it duplicate an existing subsystem?
Does it increase production RAM?
Does it add a large dependency tree?
Can it run asynchronously?
Can it be optional?
Can an existing capability be extended instead?
```

### Default rule

```text
Core platform
    ↓
small + stable

Optional capability
    ↓
plugin/skill/worker

Heavy capability
    ↓
isolated worker
```

This is especially important for browser automation and ML-heavy components.

---

# 21. What NOT to do

### Do not:

- [ ] install all repositories wholesale
- [ ] create a second memory backend
- [ ] create a second dependency graph
- [ ] replace working Playwright code without benchmarks
- [ ] put Chromium into the normal API path
- [ ] put 800 security skills into the core image
- [ ] put 165 scientific tools into the core image
- [ ] allow model-generated raw HTML/SVG directly into the DOM
- [ ] make every architecture warning a blocking CI failure
- [ ] duplicate `system_dependencies`

---

# 22. Success metrics

## Context

```text
↓ average tokens per workspace task
↓ irrelevant retrieved chunks
↓ context-window overflow
↑ answer relevance
```

## Memory

```text
↑ correct cross-session recall
↓ false memories
↓ duplicate memories
↑ scoped retrieval precision
```

## Browser

```text
↓ API process RAM
↓ browser lifetime
↓ unnecessary Chromium launches
↑ successful multi-step tasks
```

## Architecture

```text
0 new circular dependencies
0 new forbidden boundaries
0 broken dependency edges
100% PR architecture diff
100% critical-path blast-radius detection
```

---

# 23. Final priority matrix

```text
P0 — Build now
────────────────────────
Context Engine / OpenViking concepts
Memory consolidation
Harness/Run safety principles
Architecture baseline

P1 — Build next
────────────────────────
Run-centric execution
Browser worker isolation
Dependency Cruiser
Pydeps
Architecture CI
Blast-radius engine
Runtime/static graph merge

P2 — Product polish
────────────────────────
Diagram renderer
Interactive architecture dashboard

P3 — Optional ecosystem
────────────────────────
Cybersecurity skills
Scientific skills

P4 — Reject for now
────────────────────────
Colibrì
Wholesale replacement of existing subsystems
```

---

# 24. Final architectural principle

The objective is **not**:

> "How many open-source repositories can we integrate?"

The objective is:

> **"How much capability can SupremeAI gain without increasing architectural duplication, operational complexity, token waste, or production resource pressure?"**

The strongest strategy is therefore:

```text
Open-source research
       ↓
Extract best concept
       ↓
Compare with existing SupremeAI capability
       ↓
Reuse existing subsystem
       ↓
Add only missing abstraction
       ↓
Enforce through Run + policy + CI
       ↓
Measure
       ↓
Keep / rollback
```

This preserves SupremeAI's existing architecture while making **Chat, Files, Tools, Runs, and Workspace operate as one context-aware platform rather than five loosely connected features.**