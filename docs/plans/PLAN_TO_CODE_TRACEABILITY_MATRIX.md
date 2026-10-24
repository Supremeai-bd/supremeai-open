---
id: plan-to-code-traceability-matrix
subject: "SupremeAI Plan-to-Code Traceability Matrix"
document_role: audit
planning_authority: Architecture Governance / Planning Circle
canonical: true
status: active
evidence_state: partial
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
target_scope: supremeai_internal
---

# SupremeAI Plan-to-Code Traceability Matrix

**Status:** active  
**Source of truth:** `docs/plans/implementation_plan.md`  
**Last verified:** 2026-09-17 (PLAN-001 prompt caching + PLAN-002 WS compaction + PLAN-004 memory distillation + PLAN-003 repo map implemented; M2 Context Engine row refreshed; L1 Reliability Moat — nightly Mission pass^3 ≥ 0.8 gate wired; M3/L4.1 store decision table published; CI consolidation plan verified complete; L2 orphan-spine pass executed — M3 ARCHIVE memory modules + dormant `context_collector` chain deleted with regression guard; MCP CI expanded 1 → 7 test suites, F-13 closed)

This matrix is intentionally evidence-driven. Rows must not be marked complete from documentation alone.

| Canonical area | Primary plan | Code/module evidence | API/data surface | Test/release evidence | Status | Known gap |
|---|---|---|---|---|---|---|
| Architecture governance | `architecture/SUPREMEAI_MASTER_PLAN_CANONICAL.md` | architecture docs, dependency graph, `system_dependencies` | architecture reports | architecture CI to be expanded | active | unified static/runtime graph |
| QA governance | `implementation_plan.md` | QA contract and CI workflows; L1 Reliability Moat: mission suite 20/20 missions + pass^k gate harness (`scripts/ci/mission_passk.py --min-pass-hat-k`, honest exit-1 on breach) | `qa/checklist/core.yaml` | `qa-contract.yml`, build/security/preflight checks; nightly Mission Reliability Gate pass^3 ≥ 0.8 (`mission-reliability-gate` job in `scheduled-deep-audit.yml`, cron 03:00 UTC) + push-time scoreboard (`backend-aggregate`); local evidence pass^3=1.0 (n=57) and simulated-flaky run 0.7553 → exit 1; M0-G: auth setups collected + 7/13 fixme converted (`docs/audits/M0_G_QA_SPEC_COMPLETION.md`) | active | 6 fixme stay honestly blocked (need product features/fixtures); broader E2E and coverage breadth |
| Memory and context | `implementation_plan.md` | memory service, vector/RAG, Files/Workspace integration; M2 Context Engine LANDED (`e48daaf0` — `backend/context_engine/` budgeted smallest-sufficient-context assembly, wired into HTTP chat route); PLAN-002 Claude-style WS compaction LANDED (`_compact_history` + hooks in `websocket_agent.py`, pure helpers in `prompt_handler.py`); PLAN-004 write-time memory distillation LANDED (`store_long_term_memory_distilled` + `distill_content` in `core/unified_memory.py`, syncguard writer switched, `distill=` opt-in flag on `/unified-memory/long-term/store`, `metadata["distilled"]`/`memory_structure` provenance, kill-switch `SUPREMEAI_MEMORY_DISTILL`); M3/L4.1 store decision table published (`docs/plans/M3_MEMORY_STORE_CONSOLIDATION_DECISION_TABLE.md` — canonical = `ai_memory` via CascadeMemoryService; KEEP 15 / MERGE 1 / ARCHIVE 5); **L2 orphan-spine pass EXECUTED** — ARCHIVE decision carried out: `memory/unified_db_manager.py`, `memory/cloud_postgres_store.py`, `memory/summary_tree.py`, `memory/vector_store_config.py`, `memory/hierarchical_tree.py` + dormant chain `services/ingestion/context_collector.py` (+ both duplicate test files) deleted after verifying zero production importers | memory tables/RPCs and context APIs (`ai_memory` Phase C EXECUTED on Supabase, `docs/database/AI_MEMORY_PHASE_C_EXECUTION_EVIDENCE.md`) | retrieval and tenant-isolation tests; 20/20 contract+injector tests; live store→recall round-trip; `tests/api/test_websocket_compaction.py` 11/11 (success/fallback/bounded) + `test_websocket_agent.py` 42/42 regression; `tests/memory/test_memory_distillation.py` 13/13 (distilled write, legacy fallback, malformed-JSON, cost guard, kill-switch) + `tests/memory/` tree 171/171 + cross-tenant isolation 33/33; `tests/memory/test_memory_pkg_integrity.py` `TestM3ArchiveGuard` regression guard (file-absence + import-spec absence for all 6 ARCHIVE-deleted modules — reintroduction fails CI) | active | Context Engine measurement harness; WS compaction live 60+ turn Gate-5 evidence; PLAN-004 Gate-5 offline retrieval eval (distilled vs truncation top-3 hit-rate, +15pp threshold) |
| Execution | `architecture/SUPREMEAI_MASTER_PLAN_CANONICAL.md` | `backend/runs/` — canonical Run fabric (state_machine, retry, budgets, models, service, bridges, hitl, api); `runs` + `run_events` tables (Alembic `2026_09_15_120000`, single head); PLAN-003 Aider-style repo map LANDED (`core/code_indexer.py` stdlib-ast symbol graph + pure-Python PageRank + budget-bounded render, 512MB cap-guard; wired into DynamicPlanningEngine CODER-domain Epistemic Probe as `input_params["repo_map"]`, guard-protected with honest degradation) | `/api/v1/runs` — 8 endpoints (create→`run_id` ack async boundary, get/list ownership-scoped, events, transition, usage admission control, classify, retry, cancel); `runs.api` mounted (148/148 registry entries); evidence bridges for mission/tool/MCP/automation paths | `tests/runs/` 116/116 — lifecycle edge-matrix + guards, retry classification (8-class) + budget exhaustion, budget admission control (overspend refused, not detected post-hoc), cancellation matrix + terminal-race honesty, per-run sequenced audit stream, unified-view query (`mission`+`tool`+`mcp`+`automation` in one table), HITL suspend/resolve loop, API contract via real app; `tests/core/test_code_indexer.py` 9/9 + planner regression 6/6 + live smoke (1836 files, 2.47s build <5s threshold) | active | dispatch-path instrumentation of live mission/tool/MCP callers (bridges ready; wiring per subsystem) + staging runtime evidence |
| Browser | `architecture/browser_automation.md` ⭐ (consolidated from EAOL + dual_channel) | lightweight scraper and Playwright browser tools | browser endpoints and artifacts | browser smoke tests where environment permits | active | unified browser contract and worker isolation |
| Control Tower/MCP | `implementation_plan.md` | MCP gateway, capability registry and orchestration (88 tools, 0 stub) | MCP/API contracts | MCP build + typecheck + lockfile-sync checks; **F-13 closed** — `ci-mcp-build.yml` now gates 7 suites (unit: health-history/policy/registry/events/summary/resource-list-with-live-:3771-server/guardian, smoke, service-circles, timestamps, client-registry, access-control) with test-only HMAC keys; evidence JSON records per-suite outcome | active | explicit control-plane boundary; `test:guardian` still manual-only |
| Production readiness | specialized production plans | Render/GitHub/Cloudflare/Infisical/Supabase configuration | env, health, migration and release contracts | release evidence and preflight; M0-A..M0-E: deps locked (openpyxl/sqlglot), alembic single-head guard in CI, dormant-module triage recorded (`docs/audits/M0_D_DORMANT_MODULE_DECISIONS.md`), script hygiene | active | staging promotion and rollback evidence |
| Cost/federation | `implementation_plan.md` | cache, queue, provider adapters and optional workers; PLAN-001 Anthropic prompt caching LANDED (`cloud_adapter.py` `_mark_anthropic_cache_blocks` on generate/stream; usage surfaces `cache_read_input_tokens`/`cache_creation_input_tokens` → Langfuse via existing trace pass-through) | quota/cost metadata incl. Anthropic cache telemetry | quota/failure/load tests; `tests/core/test_cloud_provider_cache.py` 10/10 (marker present for anthropic-family, absent for gemini/groq on generate+stream, cache metrics surfaced/zeroed) | active | measured admission and cost policy |
| Self-evolution | `implementation_plan.md` | discovery, verification and learning candidates | lesson/capability lifecycle | sandbox/promotion/rollback tests | proposed | governed promotion path |

## Required evidence for a completed row

- implementation path and caller;
- API/schema or contract reference;
- automated test evidence;
- deployment or runtime evidence where applicable;
- observability and failure behavior;
- rollback, deprecation or recovery path;
- last verified date.

## Update rule

Any code change affecting a canonical area must update this matrix or explicitly record why the matrix is unchanged.