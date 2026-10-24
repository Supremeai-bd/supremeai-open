---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:render_3services_ghcr_deployment_roadmap_bn
subject: SupremeAI — Current Codebase → 3 Render Services Deployment Roadmap
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Current Codebase → 3 Render Services Deployment Roadmap
## বর্তমান `SaifulHaqueNiloy/supremeai` থেকে 3টি role-separated Render service এবং GHCR-based deployment

**Status:** Implementation roadmap  
**Target:** বর্তমান production না ভেঙে Core API + Worker + Scraper হিসেবে workload isolate করা।

---

## 1. বর্তমান অবস্থার ভিত্তি

বর্তমান production Render service `supremeai-backend-v2` image-based এবং `autoDeploy=OFF`। এটি বর্তমানে GHCR-এর `supremeai-core:main` image ব্যবহার করছে এবং health check হিসেবে `/api/v1/health/live` ব্যবহার করছে। তাই GHCR এখনই আপনার deployment chain-এর একটি বাস্তব অংশ; নতুন architecture-এ এটাকে বাদ না দিয়ে আরও পরিষ্কারভাবে ব্যবহার করা উচিত।

বর্তমান `backend/Dockerfile` `python:3.11-slim` ব্যবহার করে এবং main dependency set install করে। সবচেয়ে গুরুত্বপূর্ণভাবে Playwright/Chromium core image-এ রাখা হয়নি; repository comment অনুযায়ী browser runtime আলাদা scraper service/image-এ থাকার পরিকল্পনা ইতিমধ্যে codebase-এ আছে।

Repository-তে dedicated `backend/services/scraper/` আছে, যার আলাদা Dockerfile Playwright + Chromium install করে। অর্থাৎ Scraper service-এর জন্য প্রয়োজনীয় runtime boundary ইতিমধ্যে codebase-এ বাস্তবভাবে উপস্থিত।

Repository-তে `backend/workers/celery_app.py`-ও আছে, যা existing queue application's `celery_app` expose করে। তাই Worker service-ও নতুন করে শূন্য থেকে বানাতে হবে না; প্রথম extraction-এর ভিত্তি already exists।

Current GitHub Actions-এর `deploy-backend-ghcr` job বর্তমানে backend image build করে GHCR-এ push করে, Cosign দিয়ে sign করে, SBOM attach করে এবং পরে Render API দিয়ে deployment trigger করে। এটি `backend-tests` এবং `integration-test`-এর উপর নির্ভরশীল।

**Sources:**
- Current production service configuration: Render `supremeai-backend-v2`
- `backend/Dockerfile`
- `backend/services/scraper/Dockerfile`
- `backend/workers/celery_app.py`
- `.github/workflows/ci.yml`

---

# 2. Target Architecture

প্রথম লক্ষ্য load balancing নয়; workload isolation।

```text
                         SUPREMEAI
                             |
                     Core API / Router
                             |
             +---------------+---------------+
             |               |               |
             v               v               v
        Render #1       Render #2       Render #3
        CORE API         WORKER          SCRAPER
             |               |               |
          DB/Redis        Queue/Redis    Browser/HTTP
             |
             +-------------------------------+
                             |
                           Kaggle
                        Heavy Compute
```

## Service 1 — Core API

রাখবে:

- authentication / authorization
- public API
- request validation
- task creation
- task routing
- LLM/provider routing
- database access
- Redis access
- lightweight orchestration
- health endpoints

Core-এ এড়িয়ে চলতে হবে:

- Chromium
- Playwright runtime
- long-running worker consumers
- unnecessary heavy ML runtime
- rare capability runtime

---

## Service 2 — Worker

রাখবে:

- Celery consumers
- long-running tasks
- background automation
- batch processing
- asynchronous agent work
- file/data processing
- scheduled asynchronous jobs

Architecture:

```text
Core API
   |
   v
Redis / Queue
   |
   v
Worker
   |
   v
Result / Event
```

---

## Service 3 — Scraper / Browser

রাখবে:

- Playwright
- Chromium
- browser automation
- web scraping
- screenshots
- HTML extraction
- browser-heavy workflows

Current repository-তে এই service-এর Dockerfile ইতিমধ্যেই browser runtime আলাদা করে। এটাকে ব্যবহার করাই লক্ষ্য; Chromium core image-এ ফেরত আনা যাবে না।

---

# 3. কেন তিনটি service?

মূল কারণ microservice fashion নয়; resource isolation।

বর্তমানে একটি process-এ অনেক responsibility থাকলে:

```text
API + Worker + Browser + Optional tooling
            |
        এক memory budget
```

Target:

```text
Core RAM      → Core-এর জন্য
Worker RAM    → Worker-এর জন্য
Scraper RAM   → Browser-এর জন্য
```

একটি browser spike যেন core API-কে অপ্রয়োজনে ভারী না করে।

**Important:** মোট system memory অবশ্যই কমবে—এমন guarantee নেই। লক্ষ্য হলো **একটি service-এর memory pressure কমানো, failure isolation এবং independent scaling/rollback**।

---

# 4. Load Balancer এখন নয়

প্রথম deployment-এ এটি করবেন না:

```text
Load Balancer
     |
  Core A
  Core B
  Core C
```

কারণ তিনটি full backend copy চালালে একই dependency/runtime তিনবার load হতে পারে।

প্রথমে ব্যবহার করুন **role/workload routing**:

```text
Normal API request   → Core
Long async task      → Worker
Browser task         → Scraper
Heavy GPU task       → Kaggle
```

Core API-এর actual horizontal replicas দরকার হলে পরে load balancing যোগ হবে।

---

# 5. GHCR-এর জন্য বর্তমান strategy

বর্তমান `deploy-backend-ghcr` job-এর concept ঠিক আছে। এটাকে এক image থেকে বহু service artifact-এর pipeline-এ evolve করতে হবে।

Recommended images:

```text
ghcr.io/saifulhaqueniloy/supremeai/supremeai-core

ghcr.io/saifulhaqueniloy/supremeai/supremeai-worker

ghcr.io/saifulhaqueniloy/supremeai/supremeai-scraper
```

এক commit থেকে:

```text
GitHub
  |
  +--> Build Core
  +--> Build Worker
  +--> Build Scraper
          |
          v
         GHCR
          |
    +-----+-----+-----+
    |           |     |
  Core        Worker Scraper
```

---

# 6. কেন GHCR ব্যবহার করব?

একটি central artifact pipeline পাওয়া যায়:

```text
Source
→ CI
→ image build
→ GHCR
→ signing
→ SBOM
→ Render deployment
```

বর্তমান CI ইতিমধ্যেই GHCR login, Docker build/push, Cosign signing এবং SBOM generation করে। সেই security chain বজায় রেখে শুধু multiple image-এ extend করা উচিত।

---

# 7. Build Once, Deploy Many

ভুল:

```text
Render Core → source rebuild
Render Worker → source rebuild
Render Scraper → source rebuild
```

সঠিক:

```text
GitHub Actions
      |
  build once
      |
     GHCR
      |
 exact image artifact
      |
 Render
```

এতে deployment deterministic হয় এবং একই image পুনরায় build না করেও deploy করা যায়।

---

# 8. Image Tagging

Production identity হিসেবে শুধু `:main`-এর ওপর নির্ভর করবেন না।

Recommended:

```text
:main
:<commit-sha>
```

Production deployment-এর জন্য সবচেয়ে ভালো:

```text
image@sha256:<digest>
```

কারণ তখন Render ঠিক কোন artifact চালাচ্ছে তা নিশ্চিতভাবে জানা যায়।

`main` convenience tag হিসেবে থাকতে পারে।

---

# 9. `deploy-backend-ghcr` কীভাবে পরিবর্তন হবে

এখন:

```text
backend-tests
   ↓
integration-test
   ↓
deploy-backend-ghcr
   ↓
build core
   ↓
push GHCR
   ↓
Render deploy
```

Target:

```text
backend critical/important
          +
integration
          ↓
     publish-images
     /      |       \
   core   worker   scraper
     \      |       /
          GHCR
            ↓
      deployment gate
            ↓
     +------+------+
     |             |
   deploy        deploy
   services      services
```

সব image-এর জন্য current:

- GHCR authentication
- Docker metadata
- Cosign signing
- SBOM

অক্ষুণ্ণ রাখতে হবে।

---

# 10. Recommended CI Job Separation

একটি বিশাল job-এর বদলে:

```text
publish-images
    |
    +--> core image
    +--> worker image
    +--> scraper image

    ↓

deploy-core
    |
    ↓
deploy-worker
    |
    ↓
deploy-scraper
    |
    ↓
post-deploy-verification
```

এর সুবিধা:

- build failure এবং deploy failure আলাদা বোঝা যায়
- এক service fail করলে অন্য service সবসময় ব্যর্থ হতে হবে না
- image একবার তৈরি হয়ে বহু জায়গায় ব্যবহৃত হয়
- rollback সহজ হয়

---

# 11. Worker Image সিদ্ধান্ত

Worker-এর জন্য প্রথমে দুইটি option evaluate করতে হবে।

### Option A — existing backend image + আলাদা command

```text
same image
Core    → python main.py
Worker  → celery -A workers.celery_app.app worker ...
```

সুবিধা:

- Dockerfile duplication কম
- same dependency version
- same source revision

অসুবিধা:

- Worker অপ্রয়োজনীয় API dependencies বহন করতে পারে

### Option B — dedicated worker image

```text
backend/Dockerfile.worker
```

শুধু worker প্রয়োজনীয় dependency রাখবে।

**512 MB পরিবেশে Option B-তে যাওয়া যেতে পারে, কিন্তু measurement-driven decision হবে।** শুধু microservice diagram সুন্দর করার জন্য নতুন image নয়।

---

# 12. Scraper Image

Current dedicated scraper image ব্যবহার করুন।

এতে:

```text
Playwright
Chromium
browser dependencies
```

আলাদা থাকে।

Core image-এ এগুলো যোগ করা যাবে না।

---

# 13. Render Service Mapping

### Render Service 1

```text
Name: supremeai-core
Image: supremeai-core:<immutable-tag/digest>
```

### Render Service 2

```text
Name: supremeai-worker
Image: supremeai-worker:<immutable-tag/digest>
```

### Render Service 3

```text
Name: supremeai-scraper
Image: supremeai-scraper:<immutable-tag/digest>
```

প্রথম service হিসেবে বর্তমান `supremeai-backend-v2`-কে হঠাৎ delete করবেন না। আগে stable migration path তৈরি করুন।

---

# 14. Current Production → 3 Service Migration

## Stage 1 — Current service untouched

`supremeai-backend-v2` চলতে থাকবে।

Current production-এর risk কমানো হবে।

## Stage 2 — Worker side-by-side

নতুন Worker Render service তৈরি করুন।

Core-এর production traffic পরিবর্তন করবেন না।

## Stage 3 — Worker validation

Known asynchronous tasks Worker-এ পাঠিয়ে verify করুন।

Check:

```text
queue receive
job execution
result persistence
retry behavior
failure behavior
memory
```

## Stage 4 — Scraper side-by-side

Existing scraper service deploy করুন।

Browser tasks-এ limited traffic দিন।

## Stage 5 — Route change

Verified tasks-এর routing Core থেকে Worker/Scraper-এ বদলান।

## Stage 6 — Core slimming

Traffic migrate হওয়ার পরে Core থেকে redundant runtime responsibility বাদ দিন।

---

# 15. Big-bang cutover নিষিদ্ধ

এভাবে করবেন না:

```text
old backend OFF
      ↓
3 new services ON
```

বরং:

```text
old production core
+
new worker
+
new scraper
```

তারপর ধীরে দায়িত্ব migrate করুন।

---

# 16. Environment Variables

প্রতিটি service-এ শুধু প্রয়োজনীয় environment দেবেন।

### Core

```text
database
redis
LLM/provider config
JWT/auth
CORS
worker/scraper endpoint or queue config
```

### Worker

```text
redis/queue
DB if required
LLM config if required
worker-specific config
```

### Scraper

```text
browser config
queue/redis if used
scraper policies
timeouts
```

**পুরো `.env` তিন service-এ copy করবেন না।**

---

# 17. Secrets

Current Infisical-based secret import strategy চালু রাখুন। বর্তমান CI-তেও production secrets Infisical থেকে import করা হয়।

Target:

```text
Infisical
   ↓
CI / deployment
   ↓
service-specific environment
```

Raw secret source code-এ থাকবে না।

---

# 18. Database

তিনটি service মানে তিনটি database নয়।

প্রথম target:

```text
Core ───┐
Worker ─┼──→ existing production PostgreSQL/Supabase
Scraper ┘     only when required
```

Schema changes:

```text
Alembic
→ production DB
```

Application startup থেকে production schema creation বাদ দিতে হবে।

---

# 19. Queue

Core-এর request lifetime-এর মধ্যে long task চালাবেন না।

Target:

```text
API request
   ↓
create task
   ↓
queue
   ↓
worker
   ↓
result/status
```

Browser:

```text
queue
 ↓
scraper
```

Heavy ML:

```text
Kaggle orchestrator
 ↓
Kaggle
```

---

# 20. Health Checks

### Core

Current:

```text
/api/v1/health/live
```

এটাই production health contract হিসেবে continue করা যায়।

### Worker

Worker-কে HTTP API সাজানোর দরকার নেই শুধু health endpoint বানানোর জন্য। ব্যবহার করা যেতে পারে:

```text
heartbeat
queue heartbeat
worker health check
```

### Scraper

Current scraper Dockerfile `/health` check করে। সেই contract verify করে maintain করতে হবে।

---

# 21. Deployment Dependencies

Recommended CI graph:

```text
changes
   ↓
security + registry + advanced checks
   ↓
backend tests
   ↓
integration tests
   ↓
publish images
   ↓
deploy core
   ↓
post-deploy core verification
   ↓
deploy worker
   ↓
worker verification
   ↓
deploy scraper
   ↓
scraper verification
   ↓
final summary
```

তবে independent build jobs parallel করা যাবে যেখানে dependency না থাকে।

---

# 22. Current test strategy-এর সঙ্গে সম্পর্ক

আপনার বর্তমান backend test job critical/important markers ব্যবহার করে; main বা explicit overall run-এ full non-network/non-e2e/non-chaos suite-এর দিকে যায়। Integration test আলাদা job হিসেবে backend success-এর পরে চলে।

এটা multi-service deployment-এর জন্য useful।

Recommended:

```text
Critical/Important
→ fast gate

Integration
→ service contract gate

Full Overall
→ main/release path
```

প্রতিটি Render service-এর জন্য আলাদা massive test suite তৈরি করার দরকার নেই। Shared contracts + service-specific smoke tests যথেষ্ট শুরুতে।

---

# 23. GHCR Image Verification

প্রতিটি image publish হওয়ার পরে record করুন:

```text
image name
commit SHA
digest
build timestamp
SBOM
signature
```

এগুলো deployment summary-তে দেওয়া উচিত।

---

# 24. Cosign এবং SBOM

বর্তমান `deploy-backend-ghcr` job-এ Cosign signing এবং SBOM আছে। এগুলো remove করা যাবে না।

Target:

```text
Core image    → sign + SBOM
Worker image  → sign + SBOM
Scraper image → sign + SBOM
```

---

# 25. Render Deployment Method

বর্তমান Core service-এর `autoDeploy=OFF`, তাই বর্তমান CI Render API দিয়ে deployment trigger করে।

এই model রাখা যেতে পারে:

```text
GHCR push
 ↓
CI knows exact image
 ↓
CI triggers corresponding Render service
```

Future service IDs আলাদা config হিসেবে রাখুন:

```text
RENDER_CORE_SERVICE_ID
RENDER_WORKER_SERVICE_ID
RENDER_SCRAPER_SERVICE_ID
```

পরে Resource Registry এগুলোর logical source of truth হতে পারে।

---

# 26. কেন `:main`-এর বদলে immutable image গুরুত্বপূর্ণ?

ধরা যাক:

```text
main
 ↓
image A
```

পরে আবার:

```text
main
 ↓
image B
```

Render যদি শুধু `:main` দেখে, deployment history থেকে exact artifact বোঝা কঠিন হতে পারে।

Immutable SHA/digest ব্যবহার করলে:

```text
Deployment
→ digest
→ commit
→ source
```

একেবারে traceable হয়।

---

# 27. Rollback Model

প্রতিটি service-এর জন্য রাখুন:

```text
current digest
previous-good digest
health
rollback target
```

উদাহরণ:

```text
Scraper deploy
 ↓
health failed
 ↓
rollback scraper only
 ↓
Core + Worker remain live
```

এটাই service isolation-এর বড় সুবিধা।

---

# 28. Failure Isolation

### Core failure

Worker/Scraper immediately redeploy করতে হবে—এমন নয়।

### Worker failure

Core API live থাকতে পারবে; queue backlog থাকবে।

### Scraper failure

Core + Worker live থাকতে পারবে; browser-specific tasks degraded হবে।

### Kaggle failure

External compute task retry/fallback পেতে পারে।

---

# 29. Resource Routing

Service names দিয়ে hard-code না করে capability-based routing করুন।

```yaml
core:
  capabilities:
    - api
    - auth
    - orchestration

worker:
  capabilities:
    - async_task
    - batch
    - automation

scraper:
  capabilities:
    - browser
    - scraping
    - extraction

kaggle:
  capabilities:
    - gpu
    - heavy_compute
```

পরে resource registry এটাকে dynamic করবে।

---

# 30. Memory Measurement

Migration-এর আগে এবং পরে measure করুন:

```text
Core
- startup RAM
- idle RAM
- peak RAM
- request pressure

Worker
- startup RAM
- idle RAM
- peak RAM

Scraper
- startup RAM
- browser-task peak RAM
```

Target 20–30% হতে পারে একটি design objective হিসেবে, কিন্তু **এটা code/config দেখে guarantee করা যাবে না**। Production metrics দিয়ে validate করতে হবে।

---

# 31. খুব গুরুত্বপূর্ণ: total memory বনাম per-service memory

উদাহরণ:

```text
Before:
1 × 450 MB = 450 MB
```

After:

```text
Core    180 MB
Worker  140 MB
Scraper 300 MB
```

Total:

```text
620 MB
```

তবুও architecture ভালো হতে পারে, কারণ Core আর browser runtime একই memory budget share করছে না।

তাই success metric হবে:

```text
per-service stability
+ failure isolation
+ request responsiveness
+ operational flexibility
```

শুধু total RAM নয়।

---

# 32. Core-কে আবার ভারী হয়ে যাওয়া থেকে রক্ষা

Migration-এর পরে Core-এ নতুন করে এগুলো ঢুকতে দেবেন না:

```text
Chromium
Playwright
large optional ML packages
rare capability runtime
long-running loops
browser-only dependencies
```

যে capability Core-এর জন্য দরকার নয়, সেটি lazy/external/worker runtime-এ থাকবে।

---

# 33. Current service-এর safe transition strategy

Current:

```text
supremeai-backend-v2
```

কে immediately replace করবেন না।

প্রথম rollout:

```text
current core
+
worker service
+
scraper service
```

সব healthy হলে routing বদলাবে।

তারপর existing Core image slim করা হবে।

---

# 34. Production deployment gate

Production-এ যেতে হলে অন্তত:

```text
CI green
+
images published
+
images signed
+
SBOM present
+
Core health green
+
Worker health green
+
Scraper health green
+
DB schema check green
+
smoke tests green
```

যে gate fail করবে, সেই stage থামবে।

---

# 35. DB Schema Check

Current CI-তে production database schema contract check-এর জন্য আলাদা job আছে এবং `deploy-backend-ghcr` সফল হওয়ার পরে সেটা চলে।

Multi-service migration-এ এটাকে broader deployment gate হিসেবে ব্যবহার করা যায়:

```text
Deploy
→ DB schema check
→ service smoke
```

কিন্তু **application boot-time DDL-এর ওপর নির্ভরতা রাখা যাবে না।**

---

# 36. Final CI Architecture

```text
                          CHANGE
                            |
                    Change Detection
                            |
            +---------------+---------------+
            |               |               |
         Security        Quality          Registry
            |               |               |
            +---------------+---------------+
                            |
                  Backend Fast Gate
                Critical + Important
                            |
                    Integration Gate
                            |
                     Publish Images
             +--------------+--------------+
             |              |              |
            Core          Worker        Scraper
             |              |              |
             +--------------+--------------+
                            |
                    GHCR / signatures
                            |
                    Deployment Gate
                            |
              +-------------+-------------+
              |             |             |
           Core Deploy  Worker Deploy  Scraper Deploy
              |             |             |
              +-------------+-------------+
                            |
                  Health / Smoke Tests
                            |
                    DB Schema Contract
                            |
                     Final Summary
```

---

# 37. Implementation Phases

## Phase A — Preparation

- freeze current production behavior
- define service contracts
- define image names
- define service-specific env
- define Render service IDs
- define queue contract

Exit:

```text
No ambiguity about what each service owns.
```

## Phase B — Worker

- deploy Worker
- verify Celery
- verify queue
- verify result flow
- measure memory

Exit:

```text
long-running tasks work independently.
```

## Phase C — Scraper

- use existing scraper Dockerfile
- publish scraper image
- deploy scraper
- verify browser tasks
- measure memory

Exit:

```text
browser workloads no longer require Core browser runtime.
```

## Phase D — GHCR CI refactor

- rename/generalize image publishing step
- build three images
- retain signing/SBOM
- record digests
- separate deploy jobs

Exit:

```text
one commit → reproducible multi-image release.
```

## Phase E — Routing

- route async tasks to Worker
- route browser tasks to Scraper
- route heavy compute to Kaggle
- preserve fallback behavior

Exit:

```text
Core owns coordination, not every workload.
```

## Phase F — Core slimming

- remove redundant runtime imports
- stop loading worker-only components
- stop browser dependencies
- reduce unnecessary background startup
- remeasure memory

Exit:

```text
Core memory materially improved/predictable.
```

## Phase G — Centralization

Then build:

```text
Resource Registry
Capability Registry
Control Plane
MCP
```

The first 3 Render services become resources rather than special cases.

---

# 38. What NOT to do

```text
❌ তিনটি full SupremeAI copy deploy করা
❌ একই backend image-এর তিনটি duplicate copy চালানো শুধু load balance করার জন্য
❌ Chromium core-এ ফেরত আনা
❌ তিনটি database বানানো
❌ সব secrets সব service-এ দেওয়া
❌ শুধু :main দিয়ে production identity নির্ধারণ
❌ Render-কে source rebuild করতে দেওয়া যখন GHCR artifact already exists
❌ একসাথে old service shutdown + new cutover
❌ Core-এর memory problem যাচাই না করে arbitrary microservices বানানো
❌ microservice-per-folder
❌ load balancer আগে, workload routing পরে
```

---

# 39. Final Decision

আপনার বর্তমান codebase দেখে **3 Render role split technically justified** কারণ Core Dockerfile ইতিমধ্যে browser runtime বাদ দিয়েছে, dedicated Scraper service আছে, এবং Celery worker entrypoint-ও আছে। অর্থাৎ architecture-টা repository-র বর্তমান structure-এর বিরুদ্ধে নয়; বরং বর্তমান structure-কে deployment boundary-তে পরিণত করে।

প্রথমে:

```text
Core + Worker + Scraper
```

তারপর:

```text
GHCR multi-image release
```

তারপর:

```text
central resource routing
```

তারপর:

```text
Control Plane / MCP
```

Load balancing কেবল তখনই, যখন **একই workload-এর multiple Core replicas** সত্যিই দরকার হয়।

---

# 40. Final Goal

```text
                         SUPREMEAI
                              |
                      Central Orchestration
                              |
          +-------------------+-------------------+
          |                   |                   |
       Core API             Worker             Scraper
          |                   |                   |
       API/Auth            Queue/Tasks        Browser
          |                   |                   |
          +-------------------+-------------------+
                              |
                         Resource Router
                              |
              +---------------+---------------+
              |                               |
           PostgreSQL                       Kaggle
              |
        GitHub / GHCR / CI / Redis / external providers
```

The architectural objective is not “three services for the sake of three services.”

It is:

> **Keep the current production system running, isolate expensive workloads, publish deterministic container artifacts through GHCR, deploy each role independently, and prepare SupremeAI for centralized ecosystem-level resource management without prematurely turning the system into an over-engineered microservice maze.**