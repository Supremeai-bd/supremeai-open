---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:distributed_infrastructure_central_control_plane_plan
subject: SupremeAI Distributed Infrastructure & Centralized Control Plane Plan
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI Distributed Infrastructure & Centralized Control Plane Plan

## Status
Planned — implement after current emergency stability/memory work is finished.

## Core philosophy

> **Distributed execution, centralized control.**

SupremeAI may eventually use multiple Render services, multiple Kaggle accounts/nodes, multiple GitHub repositories, multiple frontends, databases, queues, and external providers. The number of resources must not create proportional administrative work.

The administrator should interact with one SupremeAI control surface rather than manually managing every provider.

## 1. Target architecture

```text
                         SUPREMEAI ADMIN UI
                                |
                         SUPREMEAI MCP
                                |
                    CENTRAL CONTROL PLANE
                                |
          +---------------------+---------------------+
          |                     |                     |
        Render                GitHub                Kaggle
          |                     |                     |
      1..N services          1..N repos           1..N accounts
          |
     +----+----------+
     |       |       |
   Core    Worker  Scraper
   API
     |
   Redis / DB / LLM routing
```

The execution layer is distributed; management is centralized.

## 2. Render migration path

Do not split everything immediately.

### Service A — Core API
Only request-serving responsibilities:

- authentication/authorization
- API routing
- validation
- lightweight business logic
- dynamic configuration
- database access
- Redis access
- LLM routing
- job submission
- health endpoints

Avoid browser engines, long-running workers, heavy batch processing, and unnecessary background agents.

### Service B — Worker
Move:

- queue consumers
- long-running jobs
- automation execution
- batch processing
- background agent work
- file/data processing

Preferred communication:

```text
Core API -> Redis/Queue -> Worker
```

### Service C — Browser/Scraper
Move:

- Playwright
- browser automation
- scraping
- screenshots
- HTML extraction
- browser-heavy integrations

Preferred communication:

```text
Core API -> Queue -> Scraper
```

Return a job ID/result rather than blocking API requests.

### Kaggle
Continue using Kaggle for heavy compute such as:

- GPU work
- model training
- batch inference
- embedding generation when appropriate
- large evaluation jobs

The existing Kaggle orchestrator already provides a job/account abstraction.

## 3. Multiple-account policy

Do not make the architecture depend on creating many accounts purely to multiply free-tier allowance.

Render currently documents Free instance hours at the workspace level, and Free services are intended for testing/hobby/preview use rather than production. Render also prohibits abuse of service capacity or attempts to evade payment obligations.

Therefore:

> Use multiple services for legitimate isolation and workload separation. Do not make quota multiplication through account creation a core design assumption.

The architecture must remain portable to normal paid plans or another cloud provider.

References:
- https://render.com/docs/free
- https://render.com/docs/platform-features-by-plan
- https://render.com/acceptable-use

## 4. Central Control Plane

The long-term control layer should be:

```text
SupremeAI Control Plane
    |
    +-- Resource Registry
    +-- Provider Adapters
    +-- Health Engine
    +-- Deployment Correlator
    +-- Incident Correlator
    +-- Policy/Safety Engine
    +-- Action Executor
    +-- MCP Interface
```

It should hide provider-specific complexity from the admin.

## 5. Resource Registry

Every managed resource receives a stable internal ID.

Example:

```yaml
resource_id: render-core-api-prod
provider: render
resource_type: web_service
environment: production
repository: supremeai
branch: main
health: healthy
deployment_id: ...
dependencies:
  - supabase-prod
  - redis-prod
capabilities:
  - deploy
  - restart
  - logs
  - metrics
  - health
```

For Kaggle:

```yaml
resource_id: kaggle-node-03
provider: kaggle
resource_type: compute_node
status: available
capabilities:
  - gpu
  - batch_inference
  - training
```

Never store raw provider credentials in the registry. Store secure secret references only.

## 6. Provider adapters

Use a common abstraction:

```text
RenderAdapter
GitHubAdapter
KaggleAdapter
FirebaseAdapter
SupabaseAdapter
RedisAdapter
CIAdapter
```

Conceptual interface:

```python
class InfrastructureProvider:
    async def list_resources()
    async def get_resource()
    async def get_health()
    async def get_metrics()
    async def get_logs()
    async def get_deployment()
    async def deploy()
    async def restart()
```

Provider-specific APIs remain inside adapters.

This lets the Control Plane scale from 3 resources to hundreds without duplicating management code.

## 7. MCP tool model

MCP should expose high-level capabilities instead of hundreds of raw provider commands.

### Observe

```text
list_resources
get_resource
get_service_health
get_memory_usage
get_cpu_usage
get_logs
get_deployment
get_git_status
get_kaggle_quota
get_dependency_graph
```

### Understand

```text
find_unhealthy_resources
correlate_error
trace_deployment
find_related_resources
compare_versions
identify_memory_hotspots
find_dependency_failures
summarize_incident
```

### Act

```text
restart_service
deploy_service
rollback_service
pause_worker
resume_worker
trigger_kaggle_job
create_github_issue
create_github_pr
```

High-risk actions must pass policy and approval checks.

## 8. Safety model

Use:

```text
Read
  -> Analyze
  -> Risk classification
  -> Policy check
  -> Approval level
  -> Execute
  -> Verify
```

### Safe automatic actions

- health checks
- metrics/log reads
- inventory
- deployment status
- dependency discovery

### Controlled automatic actions

- restart unhealthy non-critical worker
- retry failed job
- bounded cache cleanup
- re-run CI check

### Explicit approval required

- production deployment
- rollback
- schema migration
- secret rotation
- destructive actions
- infrastructure deletion

## 9. Unified dependency graph

The Control Plane should understand:

```text
GitHub commit
     |
     v
Build / image
     |
     v
Render service
     |
     +----> Redis
     |
     +----> Supabase
     |
     +----> Worker
                |
                +----> Kaggle
```

This allows questions such as:

- Which commit is currently serving production?
- Which deployment caused the regression?
- Which service depends on this Redis instance?
- Which frontends are affected by this backend?
- Why is this service unhealthy?

## 10. Unified deployment model

Track:

```text
deployment_id
service_id
repository
commit_sha
image_digest
environment
start_time
finish_time
status
health_after_deploy
rollback_status
```

Connect GitHub CI -> artifact/image -> Render deployment.

## 11. Unified health model

Normalize provider-specific states into:

```text
HEALTHY
DEGRADED
WARNING
CRITICAL
UNKNOWN
MAINTENANCE
```

Track:

```text
availability
latency
memory
CPU
error_rate
version
dependency_health
```

## 12. Unified memory monitoring

Because Render memory is a current concern, normalize:

```text
memory_used
memory_limit
memory_percent
startup_memory
idle_memory
peak_memory
memory_trend
```

Example admin view:

```text
Highest memory consumers
------------------------
Core API       34%
Worker         41%
Scraper        63%
Scheduler      18%
```

No matter whether there are 3 or 300 resources.

## 13. Unified logs

Do not permanently copy every raw log into a central database.

Store/index lightweight metadata:

```text
timestamp
resource_id
provider
environment
level
message
correlation_id
deployment_id
```

Fetch detailed provider-native logs on demand.

This keeps the control plane lightweight and inexpensive.

## 14. Correlation IDs

Every important operation should carry:

```text
request_id
correlation_id
job_id
deployment_id
resource_id
```

Example:

```text
User request
    |
request_id=abc123
    |
Core API
    |
job_id=job-928
    |
Worker
    |
Kaggle job
    |
Kaggle node 03
```

This gives end-to-end traceability.

## 15. GitHub centralization

The Control Plane should map:

```text
repository
branch
commit
workflow
workflow run
PR
deployment
service
```

So:

```text
GitHub commit
   -> CI run
      -> artifact/image
         -> Render deployment
```

appears as one deployment chain.

## 16. Kaggle centralization

Keep the current Kaggle Orchestrator as the execution layer.

The Control Plane sits above it:

```text
Admin
  |
Control Plane
  |
Kaggle Orchestrator
  |
+---+---+---+---+---+
K1  K2  K3  K4  K5/K6
```

The admin sees:

```text
available capacity
running jobs
failed jobs
quota
node/account health
```

not individual account-management details.

## 17. Frontend centralization

Register every frontend as a resource:

```text
frontend_id
provider
repository
environment
deployment
domain
health
backend_dependency
```

The control plane must answer:

- Which backend does this frontend use?
- Which frontends depend on this backend?
- Which frontend deployment is live?
- Is its backend healthy?

## 18. Secrets

Do not turn the Control Plane into another secret store.

Keep raw secrets in the existing secure secret management system.

The registry stores:

```text
secret_ref
provider
resource
purpose
status
last_checked
```

Example:

```text
secret://render/prod/api
secret://kaggle/node-03/api
secret://github/main/token
```

## 19. Admin experience

The future admin surface should look approximately like:

```text
SUPREMEAI
--------------------------------
System Health       97%
Resources           42
Healthy             38
Warning              3
Critical             1

Render
  Core API           Healthy
  Worker             Healthy
  Scraper            Warning

Kaggle
  Nodes              6
  Active jobs         2
  Remaining quota   128h

GitHub
  Repositories        8
  CI                  Healthy

Frontends
  Admin               Healthy
  User                Healthy

Deployments
  Latest              Healthy

Incidents
  Active                1
--------------------------------
```

The same UI model should work for 3, 30, 300, or more resources.

## 20. Migration phases

### Phase 0 — Emergency stabilization
Finish current production issues first:

- DB/session correctness
- schema/migration correctness
- persistent storage correctness
- Render memory stabilization
- startup profiling
- dependency cleanup

### Phase 1 — Lean Core API
Extract only request-serving responsibilities.

Goal:

- predictable startup
- low memory
- no browser
- no long-running worker

### Phase 2 — Worker extraction
Move queue and long-running work.

### Phase 3 — Browser/Scraper extraction
Move browser-heavy operations.

### Phase 4 — Control Plane foundation
Build:

```text
Resource Registry
Provider Adapters
Unified IDs
Health model
Deployment model
```

### Phase 5 — MCP
Start with read-only tools.

### Phase 6 — Centralized Admin UI
Expose the unified resource model.

### Phase 7 — Controlled actions
Enable safe automation first, then approval-gated production actions.

## 21. Rules for low maintenance

1. Never hard-code the number of services/accounts/resources.
2. Never hard-code provider credentials.
3. Use environment/secret references.
4. Prefer provider-native data sources.
5. Centralize metadata, not all raw data.
6. Use on-demand diagnostics for expensive operations.
7. Prefer events/webhooks over constant polling where supported.
8. Keep provider integrations behind adapters.
9. Treat resource discovery as dynamic.
10. Keep the Control Plane itself lightweight.
11. Make every action auditable.
12. Make provider replacement possible.

## 22. Anti-patterns

Avoid:

```text
one tool per individual service
```

Avoid:

```text
one giant provider-specific MCP implementation
```

Avoid:

```text
central database containing every raw log forever
```

Avoid:

```text
hard-coded Render account/service IDs
```

Avoid:

```text
microservice explosion for every folder/domain
```

## 23. Success criteria

The architecture is successful when:

### Scale
Adding resources does not require proportional admin effort.

### Visibility
One dashboard can show system-wide health.

### Traceability
The system can trace:

```text
User request
-> service
-> job
-> deployment
-> GitHub commit
-> dependency
-> external worker
```

### Operations
The Control Plane can answer:

- What is unhealthy?
- Why?
- Which dependency caused it?
- What changed recently?
- What is the safest remediation?

### Maintenance
Adding a new service should require registration and adapter metadata, not a completely new manual management workflow.

## 24. Final target

```text
                         ADMIN
                           |
                  SUPREMEAI ADMIN UI
                           |
                    SUPREMEAI MCP
                           |
                SUPREMEAI CONTROL PLANE
                           |
       +-------------------+-------------------+
       |                   |                   |
    Registry              Health             Actions
       |                   |                   |
       +-------------------+-------------------+
                           |
       +---------+---------+---------+---------+
       |         |         |         |         |
     Render    GitHub    Kaggle   Firebase  Supabase
       |
   +---+----------------+
   |   |                |
 Core Worker          Scraper
 API
   |
 Redis / DB / LLM routing
   |
 Kaggle for heavy compute
```

## 25. Final decision

**Now:** stay on the current architecture until emergency stability and memory work are complete.

**Next:** move only the clearly heavy workloads into 2–3 Render services.

**At the same time:** define the Resource Registry and provider-adapter interfaces.

**Later:** add the SupremeAI MCP Control Plane and centralized Admin UI.

The long-term goal is not “fewest services.” The goal is:

> **Many distributed execution resources, one simple management experience.**