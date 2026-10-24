# 📦 Zip → Current Codebase: Recommended Adoption List

> Source folder: `F:\old zip\` (17 archives). Compared against `F:\supremeai-open` (federation mirror).  
> Rule: every adopted path must pass `python scripts/ci/boundary_sanitization_guard.py --files <paths>` and target an active satellite surface (`studio/*`, `gateway/*`/`api/*`, `core/*`, `browser/*`, `vscode/*`, `skills/*`, `scripts/*`).

## 1. Archive roles (one-line each)

| Archive | Role |
|---|---|
| `supremeai-main.zip`, `(1)`–`(12)` | Monolithic SupremeAI snapshots; identical core/backend/frontend across (1)–(11); `(12)` is a trimmed agent/tooling subset. |
| `supremeai_current_state.zip` | Peak monolith (Sep 28): Zero-Cost Patch 1–4, Card Builder RAG, Telegram bot, ServiceHealthMonitor, HITL. |
| `supremeai_step1_baseline_5bf27d218.zip` | Same as current_state (baseline rebase snapshot). |
| `supremeai_1.0_backup.zip` | Older Java/Gradle + Flutter + Firebase project; dashboard/functions/vscode extension; mostly superseded. |

## 2. Core intelligence & zero-cost engine → `core/*`

| Source (zip) | Source path | Target | Notes |
|---|---|---|---|
| main/current_state/step1 | `backend/core/zero_cost_architecture/zero_cost_patch_phase1_4.py` | `core/resilience/` | Zero-cost patch phases 1–4 (85.7 KB) |
| main/current_state | `backend/core/competitive_kit.py` | `core/` | Competitive benchmarking kit |
| all main | `backend/core/resilience/circuit_breaker.py` | `core/resilience/` | Auto circuit breaker |
| all main | `backend/core/llm/llm_gateway/completion.py` | `core/llm/` | Cascading free-model gateway |
| all main | `backend/core/llm/advanced_model_router.py` | `core/llm/` | Smart LLM router |
| all main | `backend/core/self_evolution/auto_skill_creator.py` | `core/evolution/` | Self-learning skill creator |
| main (1–4)/current_state | `backend/core/orchestration/swarm_orchestrator.py` | `core/orchestration/` | Multi-agent swarm |
| all main | `backend/core/security/secret_vault.py` | `core/security/` | Credential masking |
| current_state/step1/main | `backend/core/security/injections/sql_prevention.py` | `core/security/` | SQL injection shield |
| all main | `backend/core/cache/multi_layer_cache.py` | `core/cache/` | L1/L2 + Redis cache |
| current_state/step1/main | `backend/core/cache/redis_manager.py` | `core/cache/` | Redis manager |
| all main | `backend/agents/infrastructure/cost_optimization_agent.py` | `core/agents/` | Cost optimization agent (34 KB) |
| all main | `backend/agents/infrastructure/performance_tuning_agent.py` | `core/agents/` | Performance tuning agent |
| main (1–4)/current_state | `backend/agents/ux/accessibility_agent.py` | `core/agents/` | WCAG audit agent |
| all main | `backend/agents/infrastructure/disaster_recovery_agent.py` | `core/agents/` | Disaster recovery agent |
| all main | `backend/agents/data_trend_anomaly_agent.py` | `core/agents/` | Anomaly detection agent |
| all main | `backend/agents/infrastructure/auto_scaling_agent.py` | `core/agents/` | Auto-scaling agent |
| all main | `backend/agents/user_retention_risk_agent.py` | `core/agents/` | Retention risk agent |
| all main | `backend/agents/code_vulnerability_scanner_agent.py` | `core/agents/` | OWASP scanner agent |
| all main | `backend/agents/domain/bangla_nlp_agent.py` | `core/agents/` | Bangla NLP agent |
| all main | `backend/agents/evolution_agents/multi_agent_collaboration_agent.py` | `core/agents/` | Multi-agent collaboration |

## 3. API routes & governance → `gateway/service/` (and `api/*`)

| Source | Source path | Target | Notes |
|---|---|---|---|
| zips (7)–(12) only | `backend/api/routes/web_ai_proxy.py` | `gateway/service/` | Web AI relay proxy |
| zips (7)–(12) only | `backend/api/routes/admin_decisions.py` | `gateway/service/` | Admin decision ledger |
| zips (7)–(12) only | `backend/api/routes/admin_policies.py` | `gateway/service/` | Policy ledger |
| all main | `backend/api/routes/deep_research.py` | `gateway/service/` | Deep research endpoint |
| all main | `backend/api/routes/ci_dashboard_api.py` | `gateway/service/` | CI health dashboard |
| all main | `backend/api/routes/billing_api.py` | `gateway/service/` | Billing/wallet |
| all main | `backend/api/routes/stream_chat_sse.py` | `gateway/service/` | SSE streaming chat |
| all main | `backend/api/routes/session_takeover.py` | `gateway/service/` | HITL session takeover |
| all main | `backend/api/routes/browser/_crown_jewel.py` | `gateway/service/` | Browser automation hub |
| all main | `backend/api/routes/prompt_templates.py` | `gateway/service/` | Prompt library backend |
| all main | `backend/api/routes/slash_commands.py` | `gateway/service/` | Slash commands backend |
| current_state/step1/main | `backend/database/supabase_client.py` | `gateway/service/` | Supabase client w/ retry/pooling |
| all main | `backend/alembic_migrations/versions/cfe7c95dbee2_add_sentinel_morphic_schema.py` | `gateway/` (migrations) | Sentinel morphic schema |
| all main | `backend/alembic_migrations/versions/k1l2m3n4o5p6_fix_downgrade_upgrade_table_swap.py` | `gateway/` (migrations) | Table swap bugfix |

## 4. Automation tools & relays → `scripts/*` / `core/tools/` / `skills/`

| Source | Source path | Target | Notes |
|---|---|---|---|
| all main | `backend/tools/media/multilingual_tts.py` | `skills/multilingual_tts/` | Bangla+English TTS |
| all main | `backend/tools/social/telegram_bot/` (4 modules) | `scripts/bots/` | Telegram HITL bot suite |
| all main | `backend/tools/browser/playwright_browser_agent.py` | `browser/` | Headless Playwright agent |
| all main | `backend/tools/security_tools/multi_account_rotator.py` | `scripts/ops/` | Multi-account quota rotator |
| all main | `backend/tools/code/diagram_to_architecture.py` | `core/tools/` | Diagram → code |
| all main | `backend/tools/code/image_to_code.py` | `core/tools/` | Image → code |
| current_state/step1/main | `tools/knowledge/card_builder.py` (115 KB) | `core/tools/` | Deep RAG card builder |
| all main | `backend/tools/knowledge/local_search_rag.py` | `core/tools/` | Local vector RAG |
| all main | `backend/tools/knowledge/knowledge_base_indexer.py` | `core/tools/` | KB indexer |
| all main | `backend/tools/social/viral_referral_engine.py` | `scripts/` | Viral referral engine |
| zips (7)–(12) | `scripts/agents/a2a_messaging_bus.py` | `scripts/agents/` | A2A messaging bus |
| zips (7)–(12) | `scripts/agents/dynamic_credential_broker.py` | `scripts/agents/` | Credential broker |
| all main (10+) | `scripts/agents/acquire_role_slot.py` | `scripts/agents/` | Multi-tenant slot acquisition |
| zips (7)–(12) | `docs/plans/features/n8n_workflow_automation_master_plan.md` | `docs/plans/` | n8n automation master plan |

## 5. Frontend UI crown jewels → `studio/src/components/`

| Source | Source path | Target | Notes |
|---|---|---|---|
| main (1–4)/current_state | `frontend/src/components/admin/infra/ServiceHealthMonitor.tsx` | `studio/src/components/admin/` | Live service health monitor |
| main (1–4)/current_state | `frontend/src/components/admin/AdminDashboardHome.tsx` | `studio/src/components/admin/` | Admin command center |
| main (1–4)/current_state | `frontend/src/components/dashboard/HumanInTheLoopProtocol.tsx` | `studio/src/components/dashboard/` | HITL modal |
| main (1–4)/current_state | `frontend/src/components/dashboard/HITLModal.tsx` | `studio/src/components/dashboard/` | HITL modal (alt) |
| main (1–4)/current_state | `frontend/src/components/dashboard/ActionDock.tsx` | `studio/src/components/dashboard/` | macOS-style action dock |
| main (1–4)/current_state | `frontend/src/components/dashboard/LivingActionDock.tsx` | `studio/src/components/dashboard/` | Living action dock |
| main (1–4)/current_state | `frontend/src/components/AgentStateShaderBackground.tsx` | `studio/src/components/` | 3D agent-state shader |
| main (1–4)/current_state | `frontend/src/components/dashboard/LiveSimulator.tsx` | `studio/src/components/dashboard/` | Live mobile/browser simulator |
| main (1–4)/current_state | `frontend/src/components/admin/ScreencastViewer.tsx` | `studio/src/components/admin/` | Headless screencast viewer |

## 6. Agent skills → `.agents/skills/`

Missing in current (only `devtools-audit` exists). Adopt from zips:

- `browser-automation`
- `concise-planning`
- `developing-genkit-js`
- `developing-genkit-python`
- `environment-health`
- `fastapi-pro`
- `github-actions-debugger`
- `mcp-tool-developer`
- `marketing`
- `penetration-testing`

## 7. Scripts/agents → `scripts/agents/` (48 missing files)

Adopt the 48 files listed in the diff (a2a_messaging_bus, dynamic_credential_broker, acquire_role_slot, agent_identity, credential_manager, dynamic_router, smart_dispatcher, mcp_tower_client, web_intent_engine, zai_browser_worker, etc.). See `scripts/agents/` diff output.

## 8. Architecture specs → `docs/plans/`

- All 24 files under `docs/plans/crown_jewel_series/` (MODULE_01…MODULE_23 + README).
- `docs/plans/architecture/crown_jewel_complete_system_integration_blueprint.md`.
- `scripts/docs/BROWSER_CROWN_JEWEL_INTEGRATION_GUIDE.md`.

## 9. 1.0_backup (low priority / optional)

| Item | Notes |
|---|---|
| `dashboard/` (React/Vite admin) | Possibly superseded by studio; review before porting. |
| `functions/` (Firebase) | Only if Firebase deployment is revived. |
| `supremeai/` (Flutter app) | Separate mobile product; not a satellite surface. |
| `supremeai-vscode-extension/` | Compare with current `vscode/`; cherry-pick Java controllers if missing. |
| `bin/` (1106 files) | Compiled artifacts; do not port. |

## 10. Priority tiers

- **P0 (governance & security):** secret_vault, sql_prevention, circuit_breaker, multi_account_rotator, admin_decisions, admin_policies, web_ai_proxy, a2a_messaging_bus, dynamic_credential_broker.
- **P1 (core intelligence):** zero_cost_patch_phase1_4, llm gateway completion + router, swarm_orchestrator, auto_skill_creator, cost/performance/disaster agents, card_builder, local_search_rag, KB indexer.
- **P2 (UI & automation):** ServiceHealthMonitor, HITL modal, ActionDock, LiveSimulator, ScreencastViewer, telegram bot suite, playwright agent, multilingual TTS, diagram/image-to-code, viral referral.
- **P3 (skills, specs, scripts):** all 10 missing skills, 24 crown jewel specs, 48 missing scripts/agents.

## 11. Boundary guard

All adopted paths must be remapped into approved surfaces (`scripts/{agents,ops,ci,tower,bridge,validate_schemas.py}`, `studio/*`, `gateway/*`, `core/*`, `browser/*`, `vscode/*`, `skills/*`). Root-level `backend/`, `frontend/`, `src/`, `apps/`, `packages/` from the zips are **not** approved surfaces and must never be copied verbatim.
