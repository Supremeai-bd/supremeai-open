---
id: cross-repo-architecture-transplant-roadmap
subject: "Cross-Repo Architecture Transplant Roadmap"
document_role: architecture
planning_authority: Architecture Circle
status: active
target_scope: supremeai_internal
canonical: candidate
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
---
হ্যাঁ। এবার আমি এটাকে **“কি কি file copy করব”** হিসেবে না দেখে **“বর্তমান `SaifulHaqueNiloy/supremeai`-এর existing 3 backend implementation-এর উপর `paykaribazaronline/supremeai`-এর কোন architecture transplant করলে সবচেয়ে বেশি value পাব”**—এইভাবে roadmap করছি।

একটা গুরুত্বপূর্ণ observation আগে: `paykaribazaronline/supremeai`-তে একটি আলাদা `backend/ecosystem/` implementation তৈরি হয়েছিল, যেখানে Capability Registry, Learning Loop, Source Governance, Approval Workflow, Resource Registry, Deployment/Health/Correlation, MCP এবং Task Engine একসাথে ছিল।  আপনার বর্তমান repo ইতিমধ্যে canonical Task Runtime, Verifier, Rate Limiter, Benchmark, Adaptive Optimizer এবং Performance Monitor-এর মতো production-side components wire করে।

সুতরাং লক্ষ্য হবে **replace নয়, merge/transplant**।

---

# SupremeAI Cross-Repo Integration Roadmap

## Phase 0 — Golden Rule

কোনোভাবেই:

```text
paykaribazaronline/ecosystem/
        ↓
copy entire folder
        ↓
SaifulHaqueNiloy/supremeai
```

করবেন না।

কারণ এতে duplicate:

* task engine
* auth
* persistence
* lifecycle
* runtime model

হয়ে যাবে।

আমাদের target:

```text
CURRENT PRODUCTION CORE
        +
BEST ECOSYSTEM PRIMITIVES
        =
ONE SUPREMEAI ARCHITECTURE
```

---

# Phase 1 — Repository Freeze + Compatibility Map

প্রথমে current target-এর current `main` snapshot freeze করুন।

তারপর একটি mapping বানাবেন:

| Paykar repo         | Target repo                      | Action          |
| ------------------- | -------------------------------- | --------------- |
| Capability Registry | existing capability/skill system | adapt           |
| Learning Loop       | evolution/learning               | transplant      |
| Source Governance   | internet-learning layer          | transplant      |
| Approval Workflow   | admin/HITL                       | transplant      |
| Resource Registry   | infrastructure management        | transplant      |
| MCP Skeleton        | current MCP/tool layer           | adapt           |
| Experience DB       | memory/experience                | merge concept   |
| Health Model        | existing health                  | merge           |
| Deployment Tracker  | CI/deploy                        | merge           |
| standalone app      | current FastAPI                  | **do not copy** |
| users.py auth       | current auth                     | **do not copy** |
| SQLite store        | current DB                       | **do not copy** |

এটা integration-এর source-of-truth হবে।

---

# Phase 2 — Capability Registry

### কেন?

এটাই ecosystem-এর missing central abstraction।

আজ SupremeAI-এর কাছে অনেক agents/tools/features থাকতে পারে, কিন্তু system-level প্রশ্ন হওয়া উচিত:

> **“আমি এখন কী কী করতে পারি?”**

Capability Registry সেই উত্তর দেবে।

Paykar implementation-এ capability object এবং lifecycle/runtime ধারণা already আছে।

### Implement

```text
Capability
CapabilityVersion
CapabilityDependency
CapabilityPermission
CapabilityRuntime
CapabilityEvaluation
CapabilityUsage
```

### Target behavior

```text
request
 ↓
capability search
 ↓
existing?
 ├─ yes → reuse
 └─ no → capability gap
```

### Important

Current agent implementations বাদ দেব না।

বরং:

```text
Existing Agent
      ↓
registered as
      ↓
Capability
```

---

# Phase 3 — Capability Reuse Layer

এটা registry-এর পর immediately করতে হবে।

Search order:

```text
Exact capability
↓
Semantic match
↓
Existing tool
↓
Existing agent
↓
Existing workflow
↓
External adapter
↓
Extend
↓
Create
```

Paykar architecture-এ ecosystem capability concept-এর কারণে future reuse model already implied.

### Why

না হলে:

```text
User A → create PDF tool
User B → create PDF tool again
User C → create PDF tool again
```

হবে।

---

# Phase 4 — Learning Loop

এটা **অবশ্যই transplant** করা উচিত।

Paykar-এর Learning Loop-এর সবচেয়ে valuable অংশ হলো state machine:

```text
DISCOVERY
→ SOURCE_CHECK
→ POLICY_GATE
→ RESEARCH
→ KNOWLEDGE_RECORDED
→ GAP_SIGNAL
→ CAPABILITY_OPPORTUNITY
→ PRACTICALITY_ANALYSIS
→ PROPOSAL
→ AWAITING_APPROVAL
→ BUILDING
→ VALIDATING
→ REGISTERED
→ REUSED
→ ARCHIVED
```

### কেন?

এটা আপনার SupremeAI-এর original philosophy-কে formal machine-এ পরিণত করে:

> “পারছে না → শিখবে → capability বানাবে → validate করবে → ব্যবহার করবে → future-এ reuse করবে।”

---

# Phase 5 — Source Governance

এটিও **direct architecture transplant**, implementation adaptation সহ।

Paykar-এর source states:

```text
UNKNOWN
DISCOVERED
APPROVAL_PENDING
ALLOWLISTED
BLOCKED
DEFERRED
```

এবং categories:

```text
AI_DOCS
OSS_REPO
TECH_DOCS
RESEARCH
STANDARDS
PUBLIC_API
MODEL_PROVIDER_DOCS
...
```

### কেন?

আপনার Internet-first learning vision-এ:

```text
SupremeAI discovers source
→ asks permission
→ learns
```

এটাই core।

### গুরুত্বপূর্ণ improvement

Paykar implementation-এর exact local storage copy করবেন না।

আপনার target:

```text
Source Registry
→ PostgreSQL/Supabase
```

---

# Phase 6 — Approval / Human-in-the-Loop

Paykar-এর Approval Workflow অত্যন্ত reusable।

এখানে:

```text
NEW_SOURCE
NEW_CAPABILITY
CAPABILITY_PROMOTION
CAPABILITY_ARCHIVE
DEPLOYMENT
DB_MIGRATION
SECRET_ROTATION
HIGH_RISK_ACTION
LEARNING_PROPOSAL
```

এরকম proposal types আছে।

এবং:

```text
PENDING
→ APPROVED
→ EXECUTED
```

বা reject/defer/supersede/expire flow আছে।

### Why

Admin যেন:

```text
"SupremeAI, এটা শিখতে পারি?"
```

এখানে **yes/no/defer** দিতে পারে।

আর প্রতিবার একই permission চাইতে না হয়—proposal deduplication/cooldown-ও আছে।

---

# Phase 7 — Proactive Internet Learning

এখন আগের দুই layer connect করুন:

```text
Internet
 ↓
Source Governance
 ↓
Learning Loop
 ↓
Knowledge
 ↓
Capability Opportunity
 ↓
Proposal
 ↓
Admin
```

### Why

Reactive:

```text
User asks
→ then learn
```

থেকে:

```text
Observe
→ discover
→ predict
→ propose
```

হবে।

এটাই আপনার desired SupremeAI।

---

# Phase 8 — Capability Lifecycle

এরপর capability lifecycle চালু করতে হবে:

```text
IDEA
→ PROPOSED
→ APPROVED
→ BUILDING
→ VALIDATING
→ ACTIVE
→ MEASURED
→ HOT / WARM / COLD
→ ARCHIVED
```

### Why

না হলে self-evolving system eventually:

```text
capability #1
capability #2
...
capability #10,000
```

হয়ে যাবে।

### Rules

Common:

```text
PROMOTE
```

Rare:

```text
ARCHIVE
```

Heavy runtime:

```text
UNLOAD
```

Need again:

```text
REACTIVATE
```

---

# Phase 9 — Resource Registry

এখানে Paykar-এর implementation খুব valuable।

Provider abstraction:

```text
RENDER
GITHUB
KAGGLE
SUPABASE
FIREBASE
REDIS
CI
CUSTOM
```

এবং provider-agnostic adapter interface:

```text
list_resources()
get_resource()
get_health()
get_metrics()
get_logs()
get_deployment()
restart()
deploy()
rollback()
```

### Why

আজ:

```text
Render 1
Kaggle 6
GitHub 2
```

কাল:

```text
Render N
Kaggle N
GitHub N
```

কিন্তু SupremeAI যেন সংখ্যা না জানে।

সে জানবে:

```text
resource_id
provider
capability
health
load
```

---

# Phase 10 — Resource Router

Resource Registry-এর ওপর:

```text
Capability
+
resource requirements
+
current load
+
health
```

দিয়ে resource নির্বাচন।

Example:

```text
Browser task
 ↓
Core API ❌
Worker ❌
Scraper B ✅
```

### Why

এটাই future distributed architecture-এর foundation।

---

# Phase 11 — Central Control Plane

এখন:

```text
Capability Registry
+
Resource Registry
+
Learning
+
Approval
+
Health
+
Deployment
```

এক জায়গায় connect করুন।

```text
                    CONTROL PLANE
                         |
       +-----------------+-----------------+
       |                 |                 |
 Resources         Capabilities        Learning
       |                 |                 |
       +-----------------+-----------------+
                         |
                       Policy
```

### Why

Admin-এর কাছে:

```text
ONE SUPREMEAI
```

যদিও infrastructure:

```text
many Render
many GitHub
many Kaggle
```

---

# Phase 12 — MCP Integration

Paykar-এর MCP design-এর সবচেয়ে valuable concept:

```text
OBSERVE
ANALYZE
ACT
```

ACT governance gate-এর মধ্য দিয়ে যায়।

### আমরা যা করব

বর্তমান MCP/tool architecture-এর সঙ্গে merge করব।

এটা standalone MCP system হবে না।

Target:

```text
MCP
 ↓
Control Plane
 ↓
Resource / Capability / Policy
```

---

# Phase 13 — Experience / Learning Memory

Paykar-এর `Experience` model useful:

```text
request
context
action
result
error
feedback
what_worked
what_failed
suggested_improvements
```

### কেন?

কারণ SupremeAI শুধু:

> “কি জানি?”

না, এটাও জানতে হবে:

> “আগে এই কাজ করতে গিয়ে কী হয়েছিল?”

### কিন্তু

Local SQLite/Chroma/Qdrant architecture 그대로 নয়।

কারণ current production-এর persistence strategy আলাদা এবং Render free-tier-এর জন্য remote persistent storage বেশি appropriate।

Paykar নিজেও Supabase pgvector backend-এর দিকে গেছে।

---

# Phase 14 — Experience → Capability Promotion

এখন সবচেয়ে powerful connection:

```text
Experience
 ↓
Repeated success
 ↓
Recognize pattern
 ↓
Capability candidate
 ↓
Practicality analysis
 ↓
Proposal
 ↓
Build/promote
```

এতে শেখা experience eventually reusable capability-তে পরিণত হবে।

---

# Phase 15 — Health + Deployment Correlation

Paykar-এর:

```text
Health Model
Deployment Tracker
Correlation
```

কে current observability/deployment layer-এর সঙ্গে merge করতে হবে। এগুলো `backend/ecosystem/`-এর অংশ হিসেবে already modeled হয়েছে।

Target correlation:

```text
Task
 ↓
Capability
 ↓
Resource
 ↓
Deployment
 ↓
Commit
 ↓
Health
```

### Why

তখন SupremeAI বলতে পারবে:

> “এই capability failure আসলে কোন deployment-এর পরে শুরু হয়েছে।”

---

# Phase 16 — Existing 3 Backend Implementations-এর সঙ্গে Merge

এখানে আপনার current backend architecture নষ্ট করা যাবে না।

Integration model:

```text
CURRENT IMPLEMENTATION #1
        ↓
keep authoritative

CURRENT IMPLEMENTATION #2
        ↓
keep authoritative

CURRENT IMPLEMENTATION #3
        ↓
keep authoritative
```

তার ওপর:

```text
Capability layer
Learning layer
Governance layer
Resource layer
```

বসবে।

### Golden rule

**Existing authoritative implementation wins.**

Paykar code only fills a missing architectural capability.

---

# Phase 17 — Things NOT to Copy

এগুলো intentionally বাদ:

### `standalone_app.py`

এটা ecosystem-এর independent API surface।

Current FastAPI-র পাশে আরেক FastAPI architecture তৈরি করা হবে না।

### `users.py`

ওখানে independent stdlib auth আছে।

Current authentication replace করা হবে না।

### `_store.py`

এটা local SQLite persistence layer।

Production DB architecture-তে transplant করা যাবে না।

### `PlatformLearner` blind fallback

Paykar code-এ docs unavailable হলে general model knowledge দিয়ে API structure “guess” করার fallback আছে।

এটা আমরা **করব না**।

Correct behavior:

```text
source unavailable
→ uncertain
→ do not learn as trusted fact
```

---

# Phase 18 — Database Migration Strategy

Paykar ecosystem-কে current production DB-তে নেওয়ার সময়:

```text
No runtime CREATE TABLE
```

Instead:

```text
Alembic
 ↓
ecosystem tables
```

Candidate tables:

```text
capabilities
capability_versions
capability_usage
capability_evaluations

learning_signals
learning_opportunities
learned_items
sources
source_policies

approval_proposals
approval_decisions

resources
resource_adapters

experience
mcp_calls

deployment_records
```

Schema names/structure current DB conventions অনুযায়ী normalize করতে হবে।

---

# Phase 19 — Testing Strategy

প্রতিটি transplanted subsystem-এর জন্য:

```text
unit
integration
migration
authorization
failure
rollback
```

বিশেষ করে:

### Capability

```text
duplicate capability
version conflict
archive
reactivation
permission
```

### Learning

```text
invalid source
blocked source
approval
rejection
duplicate proposal
```

### Resources

```text
provider unavailable
resource unhealthy
wrong adapter
rollback
```

---

# Phase 20 — Performance / Memory Gate

আপনার current Render 512 MB environment মাথায় রেখে।

New ecosystem layer:

```text
must NOT
```

সব capability startup-এ load করবে।

Must use:

```text
metadata first
lazy runtime
external execution
cold archive
```

Core API-তে permanentভাবে load করা যাবে না:

```text
browser
heavy model
large ML package
rare capability
```

---

# Phase 21 — Deployment Strategy

এটা production-এ সরাসরি merge নয়।

Flow:

```text
Feature branch
 ↓
CI
 ↓
DB migration test
 ↓
application integration test
 ↓
staging/sandbox
 ↓
production canary
 ↓
health
 ↓
memory
 ↓
rollback check
 ↓
merge
```

---

# Phase 22 — Recommended Implementation Order

সবকিছুর exact sequence:

```text
1. Repository compatibility map

2. Capability model

3. Capability Registry

4. Capability search/reuse

5. Learning Loop

6. Source Governance

7. Approval Workflow

8. Capability lifecycle

9. Experience memory integration

10. Resource Registry

11. Resource Router

12. Health/Deployment correlation

13. Control Plane

14. MCP integration

15. Proactive internet learning

16. Capability self-creation

17. 2–3 Render execution split

18. advanced autonomous infrastructure operations
```

এই order-এর কারণ হলো **higher layers নিচের abstractions-এর ওপর depend করবে**।

---

# Phase 23 — First Useful Cut

সবচেয়ে আগে পুরো ecosystem নয়।

প্রথম meaningful integration হওয়া উচিত:

```text
CURRENT SUPREMEAI
        +
Capability Registry
        +
Learning Loop
        +
Source Governance
        +
Approval Workflow
```

এতেই SupremeAI প্রথমবার properly বলতে পারবে:

> “আমি এই কাজ পারি না → আমি কী capability শিখতে/তৈরি করতে পারি?”

তারপর Resource Registry যোগ হলে বলতে পারবে:

> “এই capability কোথায় চালানো উচিত?”

আর Control Plane/MCP-এর পরে:

> “আমার পুরো ecosystem এখন এক জায়গা থেকে manage করা যায়।”

---

# Phase 24 — Final Architecture After Integration

```text
                         USER
                           |
                           v
                    SUPREMEAI BRAIN
                           |
                     TASK ENGINE
                           |
                  CAPABILITY RESOLVER
                     /          \
                  EXISTS        MISSING
                    |             |
                  REUSE       LEARNING LOOP
                                  |
                            SOURCE GOVERNANCE
                                  |
                              RESEARCH
                                  |
                         PRACTICALITY ANALYSIS
                                  |
                             APPROVAL
                                  |
                         BUILD / ADAPT
                                  |
                              VALIDATE
                                  |
                           CAPABILITY REGISTRY
                                  |
                                EXECUTE
                                  |
                         RESOURCE ROUTER
                                  |
          +-----------+------------+------------+
          |           |                         |
        Render      Worker                   Kaggle
        Core API    Browser/Scraper           GPU
          |           |                         |
          +-----------+-------------------------+
                                  |
                              VERIFY
                                  |
                              MEASURE
                                  |
                    PROMOTE / KEEP / ARCHIVE
                                  |
                               LEARN
                                  |
                              REPEAT
```

Admin side:

```text
                           ADMIN
                             |
                     SUPREMEAI ADMIN
                             |
                     CONTROL PLANE
                             |
       +----------+-----------+-----------+----------+
       |          |           |           |          |
    Resources  Capabilities Learning   Approvals Deployments
       |          |           |           |          |
       +----------+-----------+-----------+----------+
                             |
                            MCP
```

---

# Final Priority Matrix

| Component               | Copy strategy     |     Priority | Why                          |
| ----------------------- | ----------------- | -----------: | ---------------------------- |
| Capability Registry     | Adapt/transplant  | 🔴 Very High | “What can SupremeAI do?”     |
| Learning Loop           | Adapt/transplant  | 🔴 Very High | Self-evolution state machine |
| Source Governance       | Adapt/transplant  | 🔴 Very High | Internet learning governance |
| Approval Workflow       | Adapt/transplant  | 🔴 Very High | Human-in-loop                |
| Resource Registry       | Adapt/transplant  | 🔴 Very High | Multi-Render/Kaggle/GitHub   |
| MCP Skeleton            | Integrate concept |      🟠 High | Central operation interface  |
| Experience model        | Merge concept     |      🟠 High | Learn from previous work     |
| Health Model            | Merge             |      🟠 High | ecosystem visibility         |
| Deployment Tracker      | Merge             |    🟡 Medium | deployment correlation       |
| Correlation             | Merge             |    🟡 Medium | debugging/traceability       |
| Platform Learner        | Rewrite/adapt     |    🟡 Medium | Internet learning            |
| Supabase Vector backend | Selective         |    🟡 Medium | persistent experience memory |
| standalone_app          | Do not copy       |            ❌ | duplicate API                |
| users.py                | Do not copy       |            ❌ | duplicate auth               |
| SQLite `_store.py`      | Do not copy       |            ❌ | wrong production persistence |

Paykar-এর ecosystem work-এর সবচেয়ে valuable asset আসলে তার **architecture and state models**, not the fact that those modules exist as files. Capability, learning, governance, resource abstraction এবং MCP—এই five foundations current SupremeAI-এর ওপর বসানোই সবচেয়ে বেশি leverage দেবে।

আর current production side-এর canonical task/runtime machinery রাখা জরুরি; current factory already wires the task runtime, verifier, rate limiter, benchmark, optimizer and performance monitor.

**সুতরাং final strategy: `Paykar Ecosystem as architectural donor → Saiful repo as authoritative production core`.** এভাবে করলে পুরনো repo-র কাজও হারাবে না, আবার দুইটি competing SupremeAI architecture-ও তৈরি হবে না।