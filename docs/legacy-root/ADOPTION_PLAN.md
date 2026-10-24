# 📋 Adoption Plan — `F:\old zip\New folder` → supremeai-bd repos

> Rule: each adopted path must pass `python scripts/ci/boundary_sanitization_guard.py --files <paths>` and target one satellite surface per PR (single-domain).  
> **Full file** = copy whole file, adapt imports/package paths. **Partial** = port only named classes/functions into the existing file (do not overwrite).

## 1. supremeai-core (core/*)

| Source dir in New folder | Mode | Notes |
|---|---|---|
| `backend/core/*` | Full (adapt) | zero-cost engine, llm gateway, cache, security, resilience, orchestration, self_evolution |
| `backend/agents/*` | Full | All autonomous agents (cost, perf, a11y, disaster, anomaly, scaling, retention, vuln scan, bangla NLP, collaboration) |
| `backend/tools/*` | Full | TTS, telegram bot, playwright, rotator, diagram/image-to-code, card_builder, RAG, indexer, smell detector, viral referral |
| `backend/brain/*` | Full | cognitive router, langgraph agent, expert router, causal discovery |
| `backend/adaptive_engine/*` | Full | capability registry, governed executor, health model |
| `backend/external_agents/*` | Full | channels, contracts, control, providers |
| `backend/ecosystem/*` | Full | citizen, evolution_gate, federation_bridge, runtime_selector, standalone_app |
| `backend/ecosystem_scout/*` | Full | gap analyzer, recommender, github trending |
| `backend/evolution/*` | Full | auto_evolution_controller, auto_tuner, benchmark_runner, canary_manager, fitness_evaluator, learning_pipeline |
| `backend/learning/*` | Full | evidence_analyzer, hypothesis_engine, learning_loop, outcome_analyzer, pattern_* |
| `backend/scout/*` | Full | crawler, dedup, extractor, knowledge_extractor, persistence, policy, robots, telemetry |
| `backend/memory/*` | Full | checkpoint_resume, chromadb_store, episodic/long_term memory, mcp_server, rag_pipeline, repository, stores |
| `backend/engine/*` | Full | compression/token_juice, cost_optimizer, debate_engine, embedding, forge_compiler, memory_middleware, self_reflection, smart_router, tool_forge, tree_of_thought, vector_db, worker_node |
| `backend/monitoring/*` | Full | behavioral_guard, causal_debugger, log_batcher, logging, metrics, metrics_collector |
| `backend/runtime/*` | Full | budget_guard, planner, task_context, task_executor, task_result, task_runtime |
| `backend/middleware/*` | Partial | merge logging/tracing middleware into existing gateway middleware |
| `backend/skills/*` | Full | core_doc_summarizer, core_knowledge_qa, installer, provisioner, skill_registry |
| `backend/missions/*` | Full | models, schemas, service, state_machine |
| `backend/workers/*` | Full | celery_app, chaos_worker, precognitive_watcher, synaptic_dream |
| `backend/admin/*` | Partial | merge god/admin logic into existing admin |
| `backend/governance/*` | Full | policy_engine, policy_rules, policy_types, routing_tiers |
| `backend/byoc/*` | Full | cloud_connector, container_orchestrator |
| `backend/mcp_adapters/*` | Full | lovable_adapter, playwright_bolt |
| `backend/context/*`, `backend/context_engine/*` | Full | budget, engine, items, scopes, sources |
| `backend/pipelines/*` | Full | code_to_db_sync, synthetic_data_pipeline |
| `backend/sandbox/*` | Full | docker_sandbox, file_isolation_gate |
| `backend/schemas/*` | Full | skill_index, skill_manifest |
| `backend/storage/*` | Full | asset_manager, r2_storage_client |
| `backend/ws/*` | Partial | merge command_center into gateway ws |
| `backend/p2p/*`, `backend/scaling/*`, `backend/verification/*`, `backend/adapters/*` | Full | credit_system, distributed_manager, verifier, adapters |
| `backend/browser/*` | Full (→ browser/) | action_cascade, autonomous_browser, browser_session, browsing_memory, semantic_dom, session_manager, vision_grounding |
| `backend/models/*` | Partial | merge SQLAlchemy models into existing models (avoid duplicate tables) |
| `backend/services/*` | Partial | merge service classes; keep browser/, billing/, dynamic_ai/ subdirs as new modules |
| `backend/database/*` | Partial | merge supabase_client, session helpers |
| `backend/alembic_migrations/*` | Full | new migration files only (do not overwrite existing) |
| `backend/utils/*` | Partial | merge helpers (http_client, json_helpers, timestamps, uuid_gen) |
| `backend/evaluation/*` | Full | capability_evaluator, scorers |
| `backend/integrations/*` | Full | github_webhook, telegram_config, telegram_handlers |
| `backend/pyerrorfix/*` | Full (tooling) | error catalog and fixers |
| `scripts/core_engine/*`, `scripts/runner/*`, `scripts/tenant/*`, `scripts/worktrees/*`, `scripts/benchmark/*` | Full | port to scripts/ |
| `scripts/bots/*` | Full | telegram bot suite (already listed) |
| `scripts/bridge/*` | Partial | merge into existing bridge scripts |
| `scripts/evolution/*`, `scripts/scout/*` | Full | port |
| `scripts/knowledge/*`, `scripts/tools/*` | Full | port |

## 2. supremeai-api (gateway/* & api/*)

| Source dir | Mode | Notes |
|---|---|---|
| `backend/api/routes/*` | Full (new route files) | deep_research, ci_dashboard_api, billing_api, stream_chat_sse, session_takeover, browser/_crown_jewel, prompt_templates, slash_commands, web_ai_proxy, admin_decisions, admin_policies, admin_learning, admin_evaluation, admin_routing |
| `backend/api/*` (middleware, errors, deps) | Partial | merge into existing gateway middleware/deps |
| `backend/services/browser/*` | Full | Dockerfile, main.py, requirements |
| `backend/services/billing/*`, `backend/services/dynamic_ai/*` | Full | new service modules |
| `backend/services/config_registry.py`, `config_service.py`, `data/*`, `delivery_fleet_tracker.py`, `diagram_parser_service.py` | Full | new services |
| `backend/services/memory_service.py` | Partial | merge |
| `backend/middleware/*` | Partial | merge |
| `frontend` (none) | — | gateway has no frontend |
| `backend/ws/command_center.py` | Partial | merge into gateway ws |

## 3. supremeai-studio (studio/*)

| Source dir | Mode | Notes |
|---|---|---|
| `frontend/src/components/admin/*` | Full | ServiceHealthMonitor, AdminDashboardHome, ScreencastViewer |
| `frontend/src/components/dashboard/*` | Full | HumanInTheLoopProtocol, HITLModal, ActionDock, LivingActionDock, LiveSimulator |
| `frontend/src/components/AgentStateShaderBackground.tsx` | Full | 3D shader background |
| `frontend/src/components/admin/infra/*` (if present) | Full | infra monitors |
| Other frontend files (hooks, lib, pages) | Partial | cherry-pick; avoid overwriting existing studio app shell |

## 4. supremeai-browser (browser/*)

| Source dir | Mode | Notes |
|---|---|---|
| `backend/browser/*` | Full | action_cascade, autonomous_browser, browser_session, browsing_memory, semantic_dom, session_manager, vision_grounding |
| `backend/api/routes/browser/_crown_jewel.py` | Full | browser automation hub route |
| `backend/tools/browser/playwright_browser_agent.py` | Full | headless playwright driver |

## 5. supremeai-vscode (vscode/*)

| Source dir | Mode | Notes |
|---|---|---|
| `supremeai-vscode-extension/*` (Java/TS) | Partial | cherry-pick missing controllers/services (AdminMetricsController, CodebaseAuditService, FeatureRegistry*, GlobalMetrics*) |
| `src/main/java/com/supremeai/service/*` (MultiAIVotingService, KnowledgeSeedDataProvider, SelfHealingService, CodeGenerationService, CodeRepository) | Partial | port only if not already present |
| `src/supremeai-vscode-extension/*` | Partial | merge webview-ui |

## 6. supremeai-open (root mirror: scripts, skills, docs, .agents)

| Source dir | Mode | Notes |
|---|---|---|
| `scripts/agents/*` | Full (new files) | a2a_messaging_bus, dynamic_credential_broker, acquire_role_slot, agent_identity, credential_manager, dynamic_router, smart_dispatcher, mcp_tower_client, web_intent_engine, zai_browser_worker, etc. (48 files) |
| `scripts/advanced_analysis/*` | Full | api_contract_diff, db_model_drift_checker, migration_safety_diff, error_handling_consistency_checker, llm_cost_projector, endpoint_timeout_auditor, pydantic_schema_consistency_checker, config_single_source_enforcer, duplicate_logic_detector, dead_code_verified_finder, circular_import_mapper, importer_graph, agent_capability_registry_sync |
| `scripts/ci/*` | Partial | merge new ci helpers; do not overwrite existing guards |
| `scripts/deploy/*`, `scripts/security/*`, `scripts/devops/*`, `scripts/monitoring/*`, `scripts/audit/*`, `scripts/backup/*`, `scripts/quality/*`, `scripts/testing/*`, `scripts/governance/*`, `scripts/diagnostics/*`, `scripts/orchestrator/*`, `scripts/refactor/*`, `scripts/operations/*`, `scripts/db/*`, `scripts/billing/*`, `scripts/maintenance/*`, `scripts/health/*`, `scripts/seed/*`, `scripts/knowledge/*`, `scripts/tools/*`, `scripts/ai/*`, `scripts/docs/*`, `scripts/lib/*`, `scripts/patches/*`, `scripts/runtime/*`, `scripts/testenv/*`, `scripts/kaggle/*`, `scripts/resource_collection/*`, `scripts/resource_scraping/*`, `scripts/supremeai_toolkit/*`, `scripts/i18n/*`, `scripts/k6/*` | Full (new files) | port only files not already in scripts/ |
| `scripts/bridge/*`, `scripts/evolution/*`, `scripts/scout/*` | Partial | merge |
| `scripts/auth/*`, `scripts/deploy.sh`, `scripts/install_skills.bat`, `scripts/make_admin.js`, `scripts/validate_ai.sh`, `scripts/keepalive.js`, `scripts/pre_*`, `scripts/setup_*`, `scripts/verify_*`, `scripts/sync_*`, `scripts/safety_guard.py`, `scripts/multi_model_validator.py`, `scripts/supreme_ops.py`, `scripts/free-tier-health-check.sh`, `scripts/render_build_*.sh`, `scripts/prune_cache.sh`, `scripts/rotate_lessons.py`, `scripts/merge_and_consolidate_docs.py`, `scripts/consolidate_identical_plans.py`, `scripts/organize_external_plans.py`, `scripts/scan_duplicate_plans.py`, `scripts/move_nonascii_root_plans.py`, `scripts/apply_plan_renames.py`, `scripts/inspect_rename_candidates.py`, `scripts/generate_*`, `scripts/detect_silent_errors.py`, `scripts/find_stub_data.py`, `scripts/feature_parity_sentinel.py`, `scripts/check_*`, `scripts/codegraph_integration.py`, `scripts/sync_modules_list.py`, `scripts/update_cors_hosts.py`, `scripts/supremeai_performance_benchmark.py`, `scripts/verify_render_env.py`, `scripts/verify_infisical_env.py`, `scripts/verify_capabilities.py`, `scripts/supremeai_free_tier_monitor.py` (backend/scripts) | Partial | review; many are ops helpers—port only if useful |
| `.agents/skills/*` | Full | browser-automation, concise-planning, developing-genkit-js, developing-genkit-python, environment-health, fastapi-pro, github-actions-debugger, mcp-tool-developer, marketing, penetration-testing |
| `docs/plans/*` | Full | crown_jewel_series (24), architecture blueprint, n8n master plan, plus all plans in `docs/plans/` and `docs/archive/` |
| `docs/master_docs/*`, `docs/audit_reports/*`, `docs/generated/*` | Partial | reference only; port selectively |
| `config/*` | Partial | agent_rules.json, autonomous_seed_knowledge.json, audit-rules.yml, compliance-rules.yml, docker-limits.yml, mcp-clients.json, github-app-manifest.json |
| `skills/*` | Full | port entire skills/ tree (not already in skills/) |
| `examples/*` | Full | port |
| `sdk/*` | Full | port |
| `command/*` | Partial | merge |
| `.github/workflows/*` | Partial | merge new workflows (ci, ops-maintenance, nightly-ops, pr-gate, pr-pipeline, deploy-train, etc.) |
| `.github/scripts/*` | Full | constitution gates, ci_summary_v2, platform_deep_audit |
| `.github/actions/*` | Full | setup-backend |
| `.github/constitution/*` | Full | rules.yml |

## 7. supremeai-bd monorepo (docs/, root config)

| Source | Mode | Notes |
|---|---|---|
| `LESSONS_LEARNED.md`, `STATUS.md`, `MODULES_LIST.md`, `SCRIPTS_GUIDE_BN.md`, `SCRIPTS_INVENTORY.md`, `CHECKPOINT.md`, `PROJECT_SUMMARY.md`, `MERMD_INDEX.md`, `ECOSYSTEM_MAP.md`, `ARCHITECTURE_PLAN.md`, `AUTONOMOUS_TRANSIT_PIPELINE.md`, `AGENT.md`, `AGENT_RULES.md` (compare) | Partial | merge useful sections; avoid overwriting current AGENTS.md/AGENT_RULES.md |
| `docs/plans/infrastructure/*`, `docs/plans/features/*`, `docs/plans/architecture/*` | Full | port plans |
| `secrets_registry.yaml`, `config/autonomous_seed_knowledge.json`, `knowledge/coldstart_knowledge_seed_comprehensive.json` | Partial | merge seeds |
| `src/` (Java) | Partial | only if vscode satellite needs them |
| `supremeai/` (Flutter) | Skip | separate mobile product |
| `dashboard/`, `public/`, `apps/`, `packages/`, `bin/` | Skip | superseded by studio/gateway/core surfaces |
| `archives/*`, `data/*`, `scratch_firebase/*` | Skip | generated/legacy artifacts |

## 8. Full-file vs partial decision rules

- **Full file**: new module with no name collision in target (e.g., `cost_optimization_agent.py`, `card_builder.py`, `ServiceHealthMonitor.tsx`, new migration files, new skill dirs).
- **Partial (merge)**: file with same basename already exists in target (models, services, middleware, utils, config, .github/workflows, AGENTS.md, docs index).
- **Skip**: generated artifacts (public/assets, package-lock, docs/generated, archives, dist, build, .vsix, .db), compiled (bin), Flutter app, legacy dashboard, duplicate across 14 zips (pick one source).

## 8.5. Non-regression & no-loss guard (verified)

### A. Current-only files that MUST be preserved (never overwrite)
`docs/CURRENT_ONLY_FILES.md` lists 412 production files present in `supremeai-open` but absent from every zip. Key groups:
- `infrastructure/*` (118) — mcp-control-plane, satellites, docker, k8s
- `docs/*` (88) — federation charter, crown jewels inventory, browser integration
- `scripts/*` (55) — bridge, ci, ops, tower guards
- `browser/*` (31), `vscode/*` (24), `studio/*` (15), `gateway/*` (14), `core/*` (3)
- `.github/*` (12), `.agents/*` (6), `skills/*` (4), `examples/*` (9), `api-schemas/*` (19)
- Root governance: `AGENTS.md`, `AGENT_RULES.md`, `ARCHITECTURE_PLAN.md`, `AUTONOMOUS_TRANSIT_PIPELINE.md`, `ECOSYSTEM_MAP.md`, `mcp.json`

Rule: adopt old files only as **new** files or **partial merges**; never replace these.

### B. Filename collisions requiring merge (not overwrite)
Only 2 relative paths collide between `New folder` and current repo, and they differ:
- `infrastructure/mcp-control-plane/docs/TOOL-EXPOSURE.md`
- `infrastructure/mcp-control-plane/src/adapters/gemini/gemini.adapter.ts`
Action: 3-way merge, keep current improvements, fold in old additions.

### C. Old valuable files captured (no loss)
All non-junk, non-test, non-generated production files from the 17 zips not already in current repo are copied into `New folder` (3220 files) plus vault (134 curated). `docs/ZIP_USE_LIST.md` enumerates the crown jewels; `MANIFEST.md` lists every copied file.

### D. Boundary guard
Adopted paths must be remapped into approved surfaces only (`scripts/{agents,ops,ci,tower,bridge}`, `studio/*`, `gateway/*`, `core/*`, `browser/*`, `vscode/*`, `skills/*`). Root-level `backend/`, `frontend/`, `src/`, `apps/`, `packages/` from zips are never copied verbatim.

### E. Single-domain PR rule
One PR touches one satellite surface (e.g., `core/*` OR `gateway/*`), never both, to avoid partial-landing drift.

## 9. Priority order for PRs

1. P0 security: secret_vault, sql_prevention, circuit_breaker, multi_account_rotator, admin_decisions, admin_policies, web_ai_proxy, a2a_messaging_bus, dynamic_credential_broker.
2. P1 core intelligence: zero_cost_patch_phase1_4, llm gateway + router, swarm_orchestrator, auto_skill_creator, agents, card_builder, RAG, indexer, memory, brain, adaptive_engine.
3. P2 UI + automation: ServiceHealthMonitor, HITL, ActionDock, LiveSimulator, ScreencastViewer, telegram bot, playwright agent, TTS, diagram/image-to-code.
4. P3 scripts/skills/specs: 48 scripts/agents, 10 skills, 24 crown jewel specs, advanced_analysis, ci/deploy/security helpers.
5. P4 (optional): Java vscode controllers, config seeds, generated docs, .github workflows.
