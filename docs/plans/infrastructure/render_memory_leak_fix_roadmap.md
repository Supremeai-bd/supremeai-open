---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:render_memory_leak_fix_roadmap
subject: SupremeAI — Remaining Render / Memory Fix Roadmap
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Remaining Render / Memory Fix Roadmap

## Confirmed fixed in repository

- `backend/services/config_service.py`
  - Per-AsyncSession lock added around DB reads.
  - Commit: `8a8af16cb2576c982c12dd86e766582322a18562`
  - Goal: eliminate `AsyncSession` concurrent-operation failures caused by multiple config reads sharing one session.

## Apply after verifying production DB migration state

### 1. Automation execution schema
The repository contains the migration
`backend/alembic_migrations/versions/a1b2c3d4e5f6_add_automation_executions_table.py`
and a follow-up migration
`358bcbe79a4a_add_idempotency.py`.

Render previously reported:
`relation "automation_executions" does not exist`.

Action:
- Check the production Alembic revision.
- Apply the migration chain to the production database.
- Confirm `automation_executions` and `automation_execution_attempts` exist.
- Only then treat the maintenance cleanup warning as resolved.

The supplied patch makes the cleanup task schema-aware so a stale DB does not generate a recurring ERROR loop.

### 2. Remove production SQLite memory fallback
`CascadeMemoryService` currently falls back to `data/memory.db` after a Postgres schema-init failure.

This is unsafe on Render because the filesystem is not durable application storage.

Action:
- Apply `supremeai_runtime_db_safety_patch.patch`.
- Production behavior becomes: PostgreSQL available -> use PostgreSQL; PostgreSQL unavailable -> memory feature degrades explicitly, never silently persists to local SQLite.
- After the DB migration/permissions problem is fixed, memory service automatically returns to durable Postgres operation.

## Highest-priority manual audit

### 3. Startup memory profile
The Render log shows ~90.78% memory immediately after startup and then a long plateau.

Audit:
- `brain.model_router` — count instances; target one shared router/client where possible.
- LiteLLM/aiohttp — inspect repeated `ClientSession` creation; target shared lifecycle.
- `core.skill_manager` — inspect repeated construction.
- `services.scraper.browser_agent` — ensure browser is not launched/retained unless requested.
- `tools.code.image_to_code`, TTS, Marketplace, learning tools — lazy import and lazy object creation.
- global caches — enforce bounded size + TTL.
- use `tracemalloc` in a diagnostic deployment to capture top allocations after startup.

### 4. Optional secret loading
Startup bulk-loads many secrets and then performs individual lookups for optional integrations.

Refactor:
- define required/core secret set
- define optional integration secret set
- do not fetch optional secrets unless the feature is enabled
- keep all values environment/Infisical driven

### 5. Background service budget
Already disabled:
- SelfEvolutionAgent
- DailyLearner
- AutoScalingAgent
- PerformanceTuningAgent
- CostOptimizationAgent
- DisasterRecoveryAgent

Still review:
- Sentinel
- task queue worker
- system telemetry
- AutoHealerService
- Immune/Maintenance loop
- orchestrator background tasks

For each, record:
`startup cost`, `steady-state memory`, `interval`, `business necessity`.

Anything not needed for request serving should become on-demand or scheduled.

### 6. Celery
Do NOT remove Celery based only on the existence of `backend/workers/celery_app.py`.

First verify whether a Celery worker is actually deployed/running on Render.
- If not running: it is not the cause of current 90.8% RAM.
- If running in the same 512 MB service: move it out or disable it, then measure memory again.

### 7. Observability
Current logs show Langfuse/PostHog are already in no-op/mock mode.

Review:
- OpenTelemetry HTTPX instrumentation
- repeated INFO/DEBUG startup logs
- duplicate client initialization

Do not globally remove observability until memory profiling proves its cost.

## Validation targets

After every change compare:

1. cold-start memory
2. idle memory after 5 minutes
3. memory after 50/100 health requests
4. one normal LLM request
5. one DB-heavy request
6. memory after garbage collection
7. restart-to-restart stability

Target:
- first milestone: <400 MB
- preferred: ~350–380 MB
- investigate aggressively if memory remains >85% of the 512 MB limit.