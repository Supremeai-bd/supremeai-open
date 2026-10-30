# Duplicate / Similar-Solution File Audit

Scope: source files under project root (excluding .git, node_modules, dist, build, caches, __pycache__).
Method: (1) exact/near-duplicate content similarity scan; (2) basename collision grouping; (3) shim/facade detection.

## 1. True duplicate / near-duplicate implementation pairs (content similarity >= 0.85)

- 1.00  browser/ghost_tower/stealth_browser_engine/*  <>  browser/runtime/* (8 files: __init__, config, content_pruner, cookie_bridge, infinite_scanner, semantic_extractor, session_manager, stealth_profile)
- 1.00  core/api/routes/{admin_dashboard,browser,commandcenter}/__init__.py  <>  gateway/routes/... (shim re-exports)
- 0.99  browser/ghost_tower/stealth_browser_engine/content_pruner.py  <>  browser/runtime/content_pruner.py
- 0.97  browser/security.py  <>  core/services/scraper/security.py
- 0.97  browser/ghost_tower/stealth_browser_engine/session_manager.py  <>  browser/runtime/session_manager.py
- 0.96  scripts/ops/resource_scraping/awesome_python/scrape.py  <>  scripts/ops/resource_scraping/awesome_selfhosted/scrape.py
- 0.91  scripts/ops/security/delete_vault_duplicate_render_keys.py  <>  scripts/ops/security/delete_vault_stale_keys.py
- 0.90  core/skills/installer.py  <>  skills/installer.py
- 0.88  scripts/ops/resource_scraping/awesome_go/scrape.py  <>  scripts/ops/resource_scraping/awesome_{python,selfhosted}/scrape.py
- 0.86  browser/web_scraper.py  <>  core/services/scraper/web_scraper.py
- 0.85  vscode/desktop/src/bridge/platform.ts  <>  vscode/mobile/src/bridge/platform.ts
- 1.00  scripts/ops/audit/system_deep_scan.py  <>  scripts/ops/audit/system_deep_scan_2026_09_15.py
- 0.97  scripts/ops/audit/system_defect_scan.py  <>  scripts/ops/audit/system_defect_scan_2026_09_16.py
- 0.88  scripts/ci/validate_md_links.py  <>  scripts/ci/validate_md_links_seq04.py
- 0.84  scripts/knowledge/ingest_project_docs.py  <>  scripts/ops/ingest_project_docs.py
- 0.81  browser/browser_agent.py  <>  core/services/scraper/browser_agent.py
- 0.75  infrastructure/mcp-control-plane/scripts/runtime/infisical_bootstrap.py  <>  scripts/ops/runtime/infisical_bootstrap.py

## 2. Multi-implementation families (same purpose, different code)

These are distinct implementations of the same capability in multiple locations:
- **Stealth browser engine**: browser/ghost_tower/stealth_browser_engine/*  and  browser/runtime/* (8 identical files)
- **Web scraper**: browser/web_scraper.py, core/services/scraper/web_scraper.py, core/tools/browser/web_scraper.py, gateway/services/scraper/web_scraper.py (shim), skills/dynamic/web_scraper.py
- **Browser agent**: browser/browser_agent.py, core/agents/live/browser_agent.py, core/services/scraper/browser_agent.py, core/tools/ai_agents/browser_agent.py (facade), gateway/services/scraper/browser_agent.py (shim)
- **Security (scraper)**: browser/security.py, core/services/scraper/security.py, gateway/services/scraper/security.py (shim)
- **Installer**: core/skills/installer.py, skills/installer.py
- **Platform bridge**: studio/packages/shared-services/src/platform.ts, vscode/{desktop,extension,mobile}/src/bridge/platform.ts
- **Scrape (resource)**: scripts/ops/resource_scraping/awesome_{go,python,selfhosted}/scrape.py
- **Vault key cleanup**: scripts/ops/security/delete_vault_duplicate_render_keys.py, delete_vault_stale_keys.py
- **MD link validator**: scripts/ci/validate_md_links.py, validate_md_links_seq04.py
- **System scan scripts**: scripts/ops/audit/system_deep_scan.py + _2026_09_15.py; system_defect_scan.py + _2026_09_16.py
- **Ingest project docs**: scripts/knowledge/ingest_project_docs.py, scripts/ops/ingest_project_docs.py

## 3. Shim / facade re-export files (intentional SSOT mirrors, not harmful but duplicate files)

- Gateway Python shims: 255 files (re-export from core).
- Core facade files: 51 files (moved/renamed wrappers).
- Total facade/re-export Python files: 306.

## 4. Archived old copies (core/_archive)
- 50 Python files in core/_archive (old implementations retained).

## 5. Name-collision groups (same basename, different purpose in most cases)

Total groups (excluding __init__/index): 381
Full list below.

### models.py (13)
- .\core\automation\models.py
- .\core\ecosystem_scout\models.py
- .\core\evaluation\models.py
- .\core\github\scripts\constitution\models.py
- .\core\intelligence\models.py
- .\core\messaging\models.py
- .\core\missions\models.py
- .\core\runs\models.py
- .\core\scout\models.py
- .\core\storage\models.py
- .\core\tools\gap_finder\models.py
- .\core\tools\knowledge_squeezer\knowledge_squeezer\models.py
- .\scripts\ops\devops\config\models.py

### base.py (10)
- .\core\base.py
- .\core\circles\centers\base.py
- .\core\github\scripts\constitution\rules\base.py
- .\core\models\base.py
- .\core\plugins\experimental\base.py
- .\core\plugins\official\base.py
- .\core\pyerrorfix\detectors\base.py
- .\core\pyerrorfix\fixers\base.py
- .\core\sandbox\base.py
- .\core\skills\base.py

### main.py (9)
- .\browser\main.py
- .\core\main.py
- .\core\services\browser\main.py
- .\core\services\scraper\main.py
- .\core\services\worker\main.py
- .\gateway\main.py
- .\gateway\services\browser\main.py
- .\gateway\services\scraper\main.py
- .\gateway\services\worker\main.py

### registry.py (8)
- .\core\adaptive_engine\registry.py
- .\core\automation\registry.py
- .\core\circles\registry.py
- .\core\external_agents\providers\registry.py
- .\core\integrations\registry.py
- .\core\llm\llm_gateway\registry.py
- .\core\sandbox\registry.py
- .\skills\registry.py

### security.py (7)
- .\browser\security.py
- .\core\evaluation\scorers\security.py
- .\core\middleware\security.py
- .\core\pyerrorfix\detectors\security.py
- .\core\services\scraper\security.py
- .\gateway\security.py
- .\gateway\services\scraper\security.py

### actions.ts (7)
- .\infrastructure\mcp-control-plane\src\adapters\cloudflare\actions.ts
- .\infrastructure\mcp-control-plane\src\adapters\firecrawl\actions.ts
- .\infrastructure\mcp-control-plane\src\adapters\notify\actions.ts
- .\infrastructure\mcp-control-plane\src\adapters\qdrant\actions.ts
- .\infrastructure\mcp-control-plane\src\adapters\redis\actions.ts
- .\infrastructure\mcp-control-plane\src\adapters\render\actions.ts
- .\infrastructure\mcp-control-plane\src\adapters\supabase\actions.ts

### engine.py (6)
- .\core\context\engine.py
- .\core\context_engine\engine.py
- .\core\github\scripts\constitution\engine.py
- .\core\services\hitl\engine.py
- .\core\tools\knowledge_squeezer\knowledge_squeezer\engine.py
- .\gateway\services\hitl\engine.py

### cli.py (6)
- .\core\pyerrorfix\cli.py
- .\core\tools\gap_finder\cli.py
- .\core\tools\knowledge\cli.py
- .\core\tools\knowledge_squeezer\knowledge_squeezer\cli.py
- .\scripts\ops\devops\config\cli.py
- .\scripts\ops\supremeai_toolkit\cli.py

### browser_agent.py (5)
- .\browser\browser_agent.py
- .\core\agents\live\browser_agent.py
- .\core\services\scraper\browser_agent.py
- .\core\tools\ai_agents\browser_agent.py
- .\gateway\services\scraper\browser_agent.py

### web_scraper.py (5)
- .\browser\web_scraper.py
- .\core\services\scraper\web_scraper.py
- .\core\tools\browser\web_scraper.py
- .\gateway\services\scraper\web_scraper.py
- .\skills\dynamic\web_scraper.py

### config.py (5)
- .\browser\ghost_tower\stealth_browser_engine\config.py
- .\browser\runtime\config.py
- .\core\config.py
- .\core\tools\gap_finder\config.py
- .\gateway\config.py

### interfaces.py (5)
- .\core\automation\interfaces.py
- .\core\llm\interfaces.py
- .\core\messaging\interfaces.py
- .\core\observability\interfaces.py
- .\core\storage\interfaces.py

### agent_registry.py (4)
- .\core\agent_registry.py
- .\core\agents\framework\agent_registry.py
- .\core\api\routes\agent_registry.py
- .\gateway\routes\agent_registry.py

### task_contract.py (4)
- .\core\task_contract.py
- .\core\external_agents\contracts\task_contract.py
- .\core\queue\task_contract.py
- .\core\task_queue\task_contract.py

### admin_auth.py (4)
- .\core\api\routes\admin_auth.py
- .\gateway\admin_auth.py
- .\gateway\routes\admin_auth.py
- .\gateway\service\admin_auth.py

### living_engine.py (4)
- .\core\api\routes\living_engine.py
- .\core\services\living_engine.py
- .\gateway\routes\living_engine.py
- .\gateway\services\living_engine.py

### metrics.py (4)
- .\core\api\routes\metrics.py
- .\core\monitoring\metrics.py
- .\core\_archive\batch-6\metrics.py
- .\gateway\routes\metrics.py

### telemetry.py (4)
- .\core\api\v1\telemetry.py
- .\core\llm\telemetry.py
- .\core\observability\telemetry.py
- .\core\scout\telemetry.py

### service.py (4)
- .\core\messaging\service.py
- .\core\missions\service.py
- .\core\runs\service.py
- .\core\storage\service.py

### rate_limiter.py (4)
- .\core\middleware\rate_limiter.py
- .\core\security\rate_limiter.py
- .\core\_archive\batch-5\rate_limiter.py
- .\gateway\middleware\rate_limiter.py

### engine.ts (4)
- .\infrastructure\mcp-control-plane\src\guardian\engine.ts
- .\infrastructure\mcp-control-plane\src\health\engine.ts
- .\infrastructure\mcp-control-plane\src\remediation\engine.ts
- .\infrastructure\mcp-control-plane\src\tasks\engine.ts

### platform.ts (4)
- .\studio\packages\shared-services\src\platform.ts
- .\vscode\desktop\src\bridge\platform.ts
- .\vscode\extension\src\bridge\platform.ts
- .\vscode\mobile\src\bridge\platform.ts

### types.ts (4)
- .\studio\src\types.ts
- .\studio\src\commandcenter\data\types.ts
- .\studio\src\components\admin\admin-browser\types.ts
- .\studio\src\components\admin\ci\ci-dashboard\types.ts

### session_manager.py (3)
- .\browser\session_manager.py
- .\browser\ghost_tower\stealth_browser_engine\session_manager.py
- .\browser\runtime\session_manager.py

### config_registry.py (3)
- .\core\config_registry.py
- .\core\services\config_registry.py
- .\gateway\services\config_registry.py

### http_client.py (3)
- .\core\http_client.py
- .\core\llm\llm_gateway\http_client.py
- .\core\utils\http_client.py

### social_growth.py (3)
- .\core\social_growth.py
- .\core\api\routes\social_growth.py
- .\gateway\routes\social_growth.py

### state_machine.py (3)
- .\core\state_machine.py
- .\core\missions\state_machine.py
- .\core\runs\state_machine.py

### learning_loop.py (3)
- .\core\adaptive_engine\learning_loop.py
- .\core\learning\learning_loop.py
- .\core\_archive\batch-4\learning_loop.py

### admin.py (3)
- .\core\api\routes\admin.py
- .\core\models\admin.py
- .\gateway\routes\admin.py

### agents.py (3)
- .\core\api\routes\agents.py
- .\core\startup\agents.py
- .\gateway\routes\agents.py

### analytics.py (3)
- .\core\api\routes\analytics.py
- .\core\models\analytics.py
- .\gateway\routes\analytics.py

### control_plane.py (3)
- .\core\api\routes\control_plane.py
- .\core\contracts\control_plane.py
- .\gateway\routes\control_plane.py

### conversations.py (3)
- .\core\api\routes\conversations.py
- .\core\tools\social\telegram_bot\conversations.py
- .\gateway\routes\conversations.py

### events.py (3)
- .\core\api\routes\events.py
- .\core\messaging\events.py
- .\gateway\routes\events.py

### evolution.py (3)
- .\core\api\routes\evolution.py
- .\core\models\evolution.py
- .\gateway\routes\evolution.py

### files.py (3)
- .\core\api\routes\files.py
- .\core\pyerrorfix\detectors\files.py
- .\gateway\routes\files.py

### integrations.py (3)
- .\core\api\routes\integrations.py
- .\core\skills\integrations.py
- .\gateway\routes\integrations.py

### localization.py (3)
- .\core\api\routes\localization.py
- .\core\models\localization.py
- .\gateway\routes\localization.py

### memory.py (3)
- .\core\api\routes\memory.py
- .\gateway\memory.py
- .\gateway\routes\memory.py

### meta_ai.py (3)
- .\core\api\routes\meta_ai.py
- .\core\models\meta_ai.py
- .\gateway\routes\meta_ai.py

### simulator.py (3)
- .\core\api\routes\simulator.py
- .\core\self_evolution\digital_twin\simulator.py
- .\gateway\routes\simulator.py

### voice.py (3)
- .\core\api\routes\voice.py
- .\core\tools\media\voice.py
- .\gateway\routes\voice.py

### idempotency.py (3)
- .\core\automation\idempotency.py
- .\core\middleware\idempotency.py
- .\gateway\middleware\idempotency.py

### contracts.py (3)
- .\core\circles\contracts.py
- .\core\orchestration\contracts.py
- .\core\tools\intelligence_extensions\supremeai_intelligence\contracts.py

### adapters.py (3)
- .\core\contracts\adapters.py
- .\core\messaging\adapters.py
- .\gateway\service\providers\adapters.py

### tool_forge.py (3)
- .\core\engine\tool_forge.py
- .\core\services\tool_forge.py
- .\gateway\services\tool_forge.py

### error_remediation.py (3)
- .\core\errors\error_remediation.py
- .\core\models\error_remediation.py
- .\core\_archive\batch-3\error_remediation.py

### provider_registry.py (3)
- .\core\llm\provider_registry.py
- .\core\services\dynamic_ai\provider_registry.py
- .\gateway\services\dynamic_ai\provider_registry.py

### mcp_server.py (3)
- .\core\memory\mcp_server.py
- .\core\tools\mcp\mcp_server.py
- .\infrastructure\mcp-control-plane\sidecars\memory\mcp_server.py

### cors_policy.py (3)
- .\core\middleware\cors_policy.py
- .\core\_archive\batch-5\cors_policy.py
- .\gateway\middleware\cors_policy.py

### idempotency_middleware.py (3)
- .\core\middleware\idempotency_middleware.py
- .\core\_archive\batch-6\idempotency_middleware.py
- .\gateway\middleware\idempotency_middleware.py

### tenant_rate_limiter.py (3)
- .\core\middleware\tenant_rate_limiter.py
- .\core\tools\tenant_rate_limiter.py
- .\gateway\middleware\tenant_rate_limiter.py

### log_batcher.py (3)
- .\core\monitoring\log_batcher.py
- .\core\observability\log_batcher.py
- .\core\_archive\batch-6\log_batcher.py

### __main__.py (3)
- .\core\pyerrorfix\__main__.py
- .\core\tools\gap_finder\__main__.py
- .\core\tools\social\telegram_bot\__main__.py

### billing_plans.py (3)
- .\core\services\billing\billing_plans.py
- .\core\_archive\batch-5\billing_plans.py
- .\gateway\services\billing\billing_plans.py

### orchestrator.py (3)
- .\core\services\dynamic_ai\orchestrator.py
- .\core\_archive\batch-3\orchestrator.py
- .\gateway\services\dynamic_ai\orchestrator.py

### email_service.py (3)
- .\core\services\email\email_service.py
- .\core\_archive\batch-5\email_service.py
- .\gateway\services\email\email_service.py

### cloud_storage.py (3)
- .\core\services\storage\cloud_storage.py
- .\core\_archive\batch-5\cloud_storage.py
- .\gateway\services\storage\cloud_storage.py

### gcp_firestore.py (3)
- .\core\services\storage\gcp_firestore.py
- .\core\_archive\batch-6\gcp_firestore.py
- .\gateway\services\storage\gcp_firestore.py

### index.css (3)
- .\examples\dashboard-preview\index.css
- .\studio\public\dashboard-preview\index.css
- .\studio\src\index.css

### index.html (3)
- .\examples\dashboard-preview\index.html
- .\studio\index.html
- .\studio\public\dashboard-preview\index.html

### scrape.py (3)
- .\scripts\ops\resource_scraping\awesome_go\scrape.py
- .\scripts\ops\resource_scraping\awesome_python\scrape.py
- .\scripts\ops\resource_scraping\awesome_selfhosted\scrape.py

### tokens.css (3)
- .\studio\packages\design-tokens\outputs\tokens.css
- .\studio\src\commandcenter\styles\tokens.css
- .\studio\src\styles\tokens.css

### Header.tsx (3)
- .\studio\src\components\Header.tsx
- .\studio\src\components\core\Header.tsx
- .\studio\src\components\dashboard\Header.tsx

### server.py (2)
- .\browser\server.py
- .\core\api\server.py

### content_pruner.py (2)
- .\browser\ghost_tower\stealth_browser_engine\content_pruner.py
- .\browser\runtime\content_pruner.py

### cookie_bridge.py (2)
- .\browser\ghost_tower\stealth_browser_engine\cookie_bridge.py
- .\browser\runtime\cookie_bridge.py

### infinite_scanner.py (2)
- .\browser\ghost_tower\stealth_browser_engine\infinite_scanner.py
- .\browser\runtime\infinite_scanner.py

### semantic_extractor.py (2)
- .\browser\ghost_tower\stealth_browser_engine\semantic_extractor.py
- .\browser\runtime\semantic_extractor.py

### stealth_profile.py (2)
- .\browser\ghost_tower\stealth_browser_engine\stealth_profile.py
- .\browser\runtime\stealth_profile.py

### app.py (2)
- .\core\app.py
- .\gateway\service\app.py

### conftest.py (2)
- .\core\conftest.py
- .\tests\conftest.py

### execution_policy.py (2)
- .\core\execution_policy.py
- .\core\models\execution_policy.py

### health_check.py (2)
- .\core\health_check.py
- .\scripts\ops\health_check.py

### intelligent_cache.py (2)
- .\core\intelligent_cache.py
- .\core\_archive\batch-3\intelligent_cache.py

### logging_config.py (2)
- .\core\logging_config.py
- .\core\monitoring\logging_config.py

### mcp_client.py (2)
- .\core\mcp_client.py
- .\core\brain\mcp_client.py

### rate_limit.py (2)
- .\core\rate_limit.py
- .\gateway\rate_limit.py

### sentinel_agent.py (2)
- .\core\sentinel_agent.py
- .\core\agents\sentinel_agent.py

### approval_workflow.py (2)
- .\core\adaptive_engine\approval_workflow.py
- .\core\_archive\batch-4\approval_workflow.py

### capability_registry.py (2)
- .\core\adaptive_engine\capability_registry.py
- .\core\_archive\batch-3\capability_registry.py

### correlation.py (2)
- .\core\adaptive_engine\correlation.py
- .\core\_archive\batch-4\correlation.py

### deployment_tracker.py (2)
- .\core\adaptive_engine\deployment_tracker.py
- .\core\_archive\batch-4\deployment_tracker.py

### governance.py (2)
- .\core\adaptive_engine\governance.py
- .\core\_archive\batch-4\governance.py

### health_model.py (2)
- .\core\adaptive_engine\health_model.py
- .\core\_archive\batch-4\health_model.py

### mcp_skeleton.py (2)
- .\core\adaptive_engine\mcp_skeleton.py
- .\core\_archive\batch-4\mcp_skeleton.py

### resource_registry.py (2)
- .\core\adaptive_engine\resource_registry.py
- .\core\_archive\batch-4\resource_registry.py

### source_governance.py (2)
- .\core\adaptive_engine\source_governance.py
- .\core\_archive\batch-3\source_governance.py

### task_engine.py (2)
- .\core\adaptive_engine\task_engine.py
- .\core\_archive\batch-4\task_engine.py

### _store.py (2)
- .\core\adaptive_engine\_store.py
- .\core\_archive\batch-4\_store.py

### autonomous_agent.py (2)
- .\core\agents\autonomous_agent.py
- .\core\brain\autonomous_agent.py

### churn_prophet.py (2)
- .\core\agents\churn_prophet.py
- .\core\tools\analytics\churn_prophet.py

### insight_mage.py (2)
- .\core\agents\insight_mage.py
- .\core\tools\analytics\insight_mage.py

### cloud_watchman.py (2)
- .\core\agents\devops\cloud_watchman.py
- .\scripts\ops\devops\cloud_watchman.py

### agent_departments.py (2)
- .\core\agents\framework\agent_departments.py
- .\core\brain\agent_departments.py

### langgraph_agent.py (2)
- .\core\agents\framework\langgraph_agent.py
- .\core\brain\langgraph_agent.py

### vision_agent.py (2)
- .\core\agents\live\vision_agent.py
- .\core\tools\ai_agents\vision_agent.py

### repository.py (2)
- .\core\ai_memory\repository.py
- .\core\memory\repository.py

### errors.py (2)
- .\core\api\errors.py
- .\core\llm\llm_gateway\errors.py

### access.py (2)
- .\core\api\routes\access.py
- .\gateway\routes\access.py

### admin_decisions.py (2)
- .\core\api\routes\admin_decisions.py
- .\gateway\routes\admin_decisions.py

### admin_evaluation.py (2)
- .\core\api\routes\admin_evaluation.py
- .\gateway\routes\admin_evaluation.py

### admin_learning.py (2)
- .\core\api\routes\admin_learning.py
- .\gateway\routes\admin_learning.py

### admin_librarian.py (2)
- .\core\api\routes\admin_librarian.py
- .\gateway\routes\admin_librarian.py

### admin_llm.py (2)
- .\core\api\routes\admin_llm.py
- .\gateway\routes\admin_llm.py

### admin_policies.py (2)
- .\core\api\routes\admin_policies.py
- .\gateway\routes\admin_policies.py

### admin_routes.py (2)
- .\core\api\routes\admin_routes.py
- .\gateway\routes\admin_routes.py

### admin_routing.py (2)
- .\core\api\routes\admin_routing.py
- .\gateway\routes\admin_routing.py

### admin_v1.py (2)
- .\core\api\routes\admin_v1.py
- .\gateway\routes\admin_v1.py

### advanced_router.py (2)
- .\core\api\routes\advanced_router.py
- .\gateway\routes\advanced_router.py

### agent.py (2)
- .\core\api\routes\agent.py
- .\gateway\routes\agent.py

### agent_action.py (2)
- .\core\api\routes\agent_action.py
- .\gateway\routes\agent_action.py

### agent_breeding.py (2)
- .\core\api\routes\agent_breeding.py
- .\gateway\routes\agent_breeding.py

### agent_tasks.py (2)
- .\core\api\routes\agent_tasks.py
- .\gateway\routes\agent_tasks.py

### agent_workspace.py (2)
- .\core\api\routes\agent_workspace.py
- .\gateway\routes\agent_workspace.py

### ai_assignment.py (2)
- .\core\api\routes\ai_assignment.py
- .\gateway\routes\ai_assignment.py

### api_keys.py (2)
- .\core\api\routes\api_keys.py
- .\gateway\routes\api_keys.py

### approval_manager.py (2)
- .\core\api\routes\approval_manager.py
- .\gateway\routes\approval_manager.py

### artifacts.py (2)
- .\core\api\routes\artifacts.py
- .\gateway\routes\artifacts.py

### async_task_router.py (2)
- .\core\api\routes\async_task_router.py
- .\gateway\routes\async_task_router.py

### auth.py (2)
- .\core\api\routes\auth.py
- .\gateway\routes\auth.py

### billing_api.py (2)
- .\core\api\routes\billing_api.py
- .\gateway\routes\billing_api.py

### branch_conversations.py (2)
- .\core\api\routes\branch_conversations.py
- .\gateway\routes\branch_conversations.py

### browser_action_registry.py (2)
- .\core\api\routes\browser_action_registry.py
- .\gateway\routes\browser_action_registry.py

### byoc_api.py (2)
- .\core\api\routes\byoc_api.py
- .\gateway\routes\byoc_api.py

### cache_predictions.py (2)
- .\core\api\routes\cache_predictions.py
- .\gateway\routes\cache_predictions.py

### capabilities.py (2)
- .\core\api\routes\capabilities.py
- .\gateway\routes\capabilities.py

### cdc_webhooks.py (2)
- .\core\api\routes\cdc_webhooks.py
- .\gateway\routes\cdc_webhooks.py

### chat.py (2)
- .\core\api\routes\chat.py
- .\gateway\routes\chat.py

### chat_export.py (2)
- .\core\api\routes\chat_export.py
- .\gateway\routes\chat_export.py

### chat_search.py (2)
- .\core\api\routes\chat_search.py
- .\gateway\routes\chat_search.py

### chat_upload.py (2)
- .\core\api\routes\chat_upload.py
- .\gateway\routes\chat_upload.py

### circles.py (2)
- .\core\api\routes\circles.py
- .\gateway\routes\circles.py

### ci_dashboard_api.py (2)
- .\core\api\routes\ci_dashboard_api.py
- .\gateway\routes\ci_dashboard_api.py

### ci_webhooks.py (2)
- .\core\api\routes\ci_webhooks.py
- .\gateway\routes\ci_webhooks.py

### cloud_mesh.py (2)
- .\core\api\routes\cloud_mesh.py
- .\gateway\routes\cloud_mesh.py

### codeflow.py (2)
- .\core\api\routes\codeflow.py
- .\gateway\routes\codeflow.py

### code_dependency_graph.py (2)
- .\core\api\routes\code_dependency_graph.py
- .\gateway\routes\code_dependency_graph.py

### cognitive.py (2)
- .\core\api\routes\cognitive.py
- .\gateway\routes\cognitive.py

### config_routes.py (2)
- .\core\api\routes\config_routes.py
- .\gateway\routes\config_routes.py

### connections.py (2)
- .\core\api\routes\connections.py
- .\gateway\routes\connections.py

### crawler_admin.py (2)
- .\core\api\routes\crawler_admin.py
- .\gateway\routes\crawler_admin.py

### deep_research.py (2)
- .\core\api\routes\deep_research.py
- .\gateway\routes\deep_research.py

### dock_actions.py (2)
- .\core\api\routes\dock_actions.py
- .\gateway\routes\dock_actions.py

### dock_integrations.py (2)
- .\core\api\routes\dock_integrations.py
- .\gateway\routes\dock_integrations.py

### ecosystem.py (2)
- .\core\api\routes\ecosystem.py
- .\gateway\routes\ecosystem.py

### ecosystem_admin.py (2)
- .\core\api\routes\ecosystem_admin.py
- .\gateway\routes\ecosystem_admin.py

### email.py (2)
- .\core\api\routes\email.py
- .\gateway\routes\email.py

### execution_policies.py (2)
- .\core\api\routes\execution_policies.py
- .\gateway\routes\execution_policies.py

### external_agents_admin.py (2)
- .\core\api\routes\external_agents_admin.py
- .\gateway\routes\external_agents_admin.py

### feedback.py (2)
- .\core\api\routes\feedback.py
- .\gateway\routes\feedback.py

### github.py (2)
- .\core\api\routes\github.py
- .\gateway\routes\github.py

### global_memory.py (2)
- .\core\api\routes\global_memory.py
- .\gateway\routes\global_memory.py

### graph.py (2)
- .\core\api\routes\graph.py
- .\gateway\routes\graph.py

### healing.py (2)
- .\core\api\routes\healing.py
- .\gateway\routes\healing.py

### healing_stats.py (2)
- .\core\api\routes\healing_stats.py
- .\gateway\routes\healing_stats.py

### health.py (2)
- .\core\api\routes\health.py
- .\gateway\routes\health.py

### health_aggregation.py (2)
- .\core\api\routes\health_aggregation.py
- .\gateway\routes\health_aggregation.py

### hitl_admin.py (2)
- .\core\api\routes\hitl_admin.py
- .\gateway\routes\hitl_admin.py

### hybrid_search.py (2)
- .\core\api\routes\hybrid_search.py
- .\gateway\routes\hybrid_search.py

### ide_trio.py (2)
- .\core\api\routes\ide_trio.py
- .\gateway\routes\ide_trio.py

### intelligence_insights.py (2)
- .\core\api\routes\intelligence_insights.py
- .\gateway\routes\intelligence_insights.py

### internal.py (2)
- .\core\api\routes\internal.py
- .\gateway\routes\internal.py

### internet_monitor.py (2)
- .\core\api\routes\internet_monitor.py
- .\gateway\routes\internet_monitor.py

### kaggle.py (2)
- .\core\api\routes\kaggle.py
- .\gateway\routes\kaggle.py

### kernel_dispatch.py (2)
- .\core\api\routes\kernel_dispatch.py
- .\gateway\routes\kernel_dispatch.py

### keys.py (2)
- .\core\api\routes\keys.py
- .\gateway\routes\keys.py

### knowledge.py (2)
- .\core\api\routes\knowledge.py
- .\gateway\routes\knowledge.py

### living_brain.py (2)
- .\core\api\routes\living_brain.py
- .\gateway\routes\living_brain.py

### llm_gateway_routes.py (2)
- .\core\api\routes\llm_gateway_routes.py
- .\gateway\routes\llm_gateway_routes.py

### maintenance.py (2)
- .\core\api\routes\maintenance.py
- .\gateway\routes\maintenance.py

### markdown.py (2)
- .\core\api\routes\markdown.py
- .\gateway\routes\markdown.py

### marketplace_endpoints.py (2)
- .\core\api\routes\marketplace_endpoints.py
- .\gateway\routes\marketplace_endpoints.py

### mcp_hub.py (2)
- .\core\api\routes\mcp_hub.py
- .\gateway\routes\mcp_hub.py

### mcp_marketplace.py (2)
- .\core\api\routes\mcp_marketplace.py
- .\gateway\routes\mcp_marketplace.py

### media.py (2)
- .\core\api\routes\media.py
- .\gateway\routes\media.py

### memory_mcp_http.py (2)
- .\core\api\routes\memory_mcp_http.py
- .\gateway\routes\memory_mcp_http.py

### merge_learning.py (2)
- .\core\api\routes\merge_learning.py
- .\gateway\routes\merge_learning.py

### mesh.py (2)
- .\core\api\routes\mesh.py
- .\gateway\routes\mesh.py

### mesh_mailbox.py (2)
- .\core\api\routes\mesh_mailbox.py
- .\gateway\routes\mesh_mailbox.py

### mesh_tasks.py (2)
- .\core\api\routes\mesh_tasks.py
- .\gateway\routes\mesh_tasks.py

### missions.py (2)
- .\core\api\routes\missions.py
- .\gateway\routes\missions.py

### mobile_bff.py (2)
- .\core\api\routes\mobile_bff.py
- .\gateway\routes\mobile_bff.py

### n8n_webhooks.py (2)
- .\core\api\routes\n8n_webhooks.py
- .\gateway\routes\n8n_webhooks.py

### onboarding.py (2)
- .\core\api\routes\onboarding.py
- .\gateway\routes\onboarding.py

### payments.py (2)
- .\core\api\routes\payments.py
- .\gateway\routes\payments.py

### plugins.py (2)
- .\core\api\routes\plugins.py
- .\gateway\routes\plugins.py

### plugin_submissions.py (2)
- .\core\api\routes\plugin_submissions.py
- .\gateway\routes\plugin_submissions.py

### preferences.py (2)
- .\core\api\routes\preferences.py
- .\gateway\routes\preferences.py

### projects.py (2)
- .\core\api\routes\projects.py
- .\gateway\routes\projects.py

### prompt_templates.py (2)
- .\core\api\routes\prompt_templates.py
- .\gateway\routes\prompt_templates.py

### pr_review_api.py (2)
- .\core\api\routes\pr_review_api.py
- .\gateway\routes\pr_review_api.py

### public_config.py (2)
- .\core\api\routes\public_config.py
- .\gateway\routes\public_config.py

### realtime_dashboard.py (2)
- .\core\api\routes\realtime_dashboard.py
- .\gateway\routes\realtime_dashboard.py

### reasoning.py (2)
- .\core\api\routes\reasoning.py
- .\gateway\routes\reasoning.py

### render_preflight_admin.py (2)
- .\core\api\routes\render_preflight_admin.py
- .\gateway\routes\render_preflight_admin.py

### repos.py (2)
- .\core\api\routes\repos.py
- .\gateway\routes\repos.py

### sandbox_api.py (2)
- .\core\api\routes\sandbox_api.py
- .\gateway\routes\sandbox_api.py

### scheduled_tasks.py (2)
- .\core\api\routes\scheduled_tasks.py
- .\gateway\routes\scheduled_tasks.py

### scraper.py (2)
- .\core\api\routes\scraper.py
- .\gateway\routes\scraper.py

### selector_healing.py (2)
- .\core\api\routes\selector_healing.py
- .\gateway\routes\selector_healing.py

### service_topology.py (2)
- .\core\api\routes\service_topology.py
- .\gateway\routes\service_topology.py

### session_stream.py (2)
- .\core\api\routes\session_stream.py
- .\gateway\routes\session_stream.py

### session_takeover.py (2)
- .\core\api\routes\session_takeover.py
- .\gateway\routes\session_takeover.py

### share.py (2)
- .\core\api\routes\share.py
- .\gateway\routes\share.py

### simulator_admin.py (2)
- .\core\api\routes\simulator_admin.py
- .\gateway\routes\simulator_admin.py

### site_actions.py (2)
- .\core\api\routes\site_actions.py
- .\gateway\routes\site_actions.py

### skills.py (2)
- .\core\api\routes\skills.py
- .\gateway\routes\skills.py

### slash_commands.py (2)
- .\core\api\routes\slash_commands.py
- .\gateway\routes\slash_commands.py

### sso.py (2)
- .\core\api\routes\sso.py
- .\gateway\routes\sso.py

### stream.py (2)
- .\core\api\routes\stream.py
- .\gateway\routes\stream.py

### stream_chat_sse.py (2)
- .\core\api\routes\stream_chat_sse.py
- .\gateway\routes\stream_chat_sse.py

### stream_hitl_sse.py (2)
- .\core\api\routes\stream_hitl_sse.py
- .\gateway\routes\stream_hitl_sse.py

### swarm_stream.py (2)
- .\core\api\routes\swarm_stream.py
- .\gateway\routes\swarm_stream.py

### syncguard.py (2)
- .\core\api\routes\syncguard.py
- .\gateway\routes\syncguard.py

### task.py (2)
- .\core\api\routes\task.py
- .\gateway\routes\task.py

### task_gateway.py (2)
- .\core\api\routes\task_gateway.py
- .\gateway\routes\task_gateway.py

### task_workspace.py (2)
- .\core\api\routes\task_workspace.py
- .\gateway\routes\task_workspace.py

### tenant_admin.py (2)
- .\core\api\routes\tenant_admin.py
- .\gateway\routes\tenant_admin.py

### tier_s_routes.py (2)
- .\core\api\routes\tier_s_routes.py
- .\gateway\routes\tier_s_routes.py

### tools_ops.py (2)
- .\core\api\routes\tools_ops.py
- .\gateway\routes\tools_ops.py

### tools_registry.py (2)
- .\core\api\routes\tools_registry.py
- .\gateway\routes\tools_registry.py

### traffic_monitor.py (2)
- .\core\api\routes\traffic_monitor.py
- .\gateway\routes\traffic_monitor.py

### unified_memory_api.py (2)
- .\core\api\routes\unified_memory_api.py
- .\gateway\routes\unified_memory_api.py

### usage_metrics.py (2)
- .\core\api\routes\usage_metrics.py
- .\gateway\routes\usage_metrics.py

### webhooks_ai.py (2)
- .\core\api\routes\webhooks_ai.py
- .\gateway\routes\webhooks_ai.py

### webhooks_github.py (2)
- .\core\api\routes\webhooks_github.py
- .\gateway\routes\webhooks_github.py

### websocket_hitl.py (2)
- .\core\api\routes\websocket_hitl.py
- .\gateway\routes\websocket_hitl.py

### websocket_voice.py (2)
- .\core\api\routes\websocket_voice.py
- .\gateway\routes\websocket_voice.py

### web_ai_proxy.py (2)
- .\core\api\routes\web_ai_proxy.py
- .\gateway\routes\web_ai_proxy.py

### workspaces_route.py (2)
- .\core\api\routes\workspaces_route.py
- .\gateway\routes\workspaces_route.py

### workspace_capabilities.py (2)
- .\core\api\routes\workspace_capabilities.py
- .\gateway\routes\workspace_capabilities.py

### workspace_feature_routes.py (2)
- .\core\api\routes\workspace_feature_routes.py
- .\gateway\routes\workspace_feature_routes.py

### zero_cost.py (2)
- .\core\api\routes\zero_cost.py
- .\gateway\routes\zero_cost.py

### endpoints_approvals_mcp.py (2)
- .\core\api\routes\admin_dashboard\endpoints_approvals_mcp.py
- .\gateway\routes\admin_dashboard\endpoints_approvals_mcp.py

### endpoints_backups.py (2)
- .\core\api\routes\admin_dashboard\endpoints_backups.py
- .\gateway\routes\admin_dashboard\endpoints_backups.py

### endpoints_ci.py (2)
- .\core\api\routes\admin_dashboard\endpoints_ci.py
- .\gateway\routes\admin_dashboard\endpoints_ci.py

### endpoints_command.py (2)
- .\core\api\routes\admin_dashboard\endpoints_command.py
- .\gateway\routes\admin_dashboard\endpoints_command.py

### endpoints_config.py (2)
- .\core\api\routes\admin_dashboard\endpoints_config.py
- .\gateway\routes\admin_dashboard\endpoints_config.py

### endpoints_crud.py (2)
- .\core\api\routes\admin_dashboard\endpoints_crud.py
- .\gateway\routes\admin_dashboard\endpoints_crud.py

### endpoints_deploy.py (2)
- .\core\api\routes\admin_dashboard\endpoints_deploy.py
- .\gateway\routes\admin_dashboard\endpoints_deploy.py

### endpoints_events.py (2)
- .\core\api\routes\admin_dashboard\endpoints_events.py
- .\gateway\routes\admin_dashboard\endpoints_events.py

### endpoints_flags.py (2)
- .\core\api\routes\admin_dashboard\endpoints_flags.py
- .\gateway\routes\admin_dashboard\endpoints_flags.py

### endpoints_gate.py (2)
- .\core\api\routes\admin_dashboard\endpoints_gate.py
- .\gateway\routes\admin_dashboard\endpoints_gate.py

### endpoints_health.py (2)
- .\core\api\routes\admin_dashboard\endpoints_health.py
- .\gateway\routes\admin_dashboard\endpoints_health.py

### endpoints_impersonate.py (2)
- .\core\api\routes\admin_dashboard\endpoints_impersonate.py
- .\gateway\routes\admin_dashboard\endpoints_impersonate.py

### endpoints_metrics.py (2)
- .\core\api\routes\admin_dashboard\endpoints_metrics.py
- .\gateway\routes\admin_dashboard\endpoints_metrics.py

### endpoints_router_cfg.py (2)
- .\core\api\routes\admin_dashboard\endpoints_router_cfg.py
- .\gateway\routes\admin_dashboard\endpoints_router_cfg.py

### endpoints_secrets_health.py (2)
- .\core\api\routes\admin_dashboard\endpoints_secrets_health.py
- .\gateway\routes\admin_dashboard\endpoints_secrets_health.py

### endpoints_security.py (2)
- .\core\api\routes\admin_dashboard\endpoints_security.py
- .\gateway\routes\admin_dashboard\endpoints_security.py

### endpoints_security_memory.py (2)
- .\core\api\routes\admin_dashboard\endpoints_security_memory.py
- .\gateway\routes\admin_dashboard\endpoints_security_memory.py

### endpoints_users.py (2)
- .\core\api\routes\admin_dashboard\endpoints_users.py
- .\gateway\routes\admin_dashboard\endpoints_users.py

### endpoints_ws.py (2)
- .\core\api\routes\admin_dashboard\endpoints_ws.py
- .\gateway\routes\admin_dashboard\endpoints_ws.py

### _models.py (2)
- .\core\api\routes\admin_dashboard\_models.py
- .\gateway\routes\admin_dashboard\_models.py

### _automation.py (2)
- .\core\api\routes\browser\_automation.py
- .\gateway\routes\browser\_automation.py

### _cognitive.py (2)
- .\core\api\routes\browser\_cognitive.py
- .\gateway\routes\browser\_cognitive.py

### _credentials.py (2)
- .\core\api\routes\browser\_credentials.py
- .\gateway\routes\browser\_credentials.py

### _crown_jewel.py (2)
- .\core\api\routes\browser\_crown_jewel.py
- .\gateway\routes\browser\_crown_jewel.py

### _health.py (2)
- .\core\api\routes\browser\_health.py
- .\gateway\routes\browser\_health.py

### _learning.py (2)
- .\core\api\routes\browser\_learning.py
- .\gateway\routes\browser\_learning.py

### _legacy_status.py (2)
- .\core\api\routes\browser\_legacy_status.py
- .\gateway\routes\browser\_legacy_status.py

### _policy.py (2)
- .\core\api\routes\browser\_policy.py
- .\gateway\routes\browser\_policy.py

### _render_proxy.py (2)
- .\core\api\routes\browser\_render_proxy.py
- .\gateway\routes\browser\_render_proxy.py

### _scraping.py (2)
- .\core\api\routes\browser\_scraping.py
- .\gateway\routes\browser\_scraping.py

### _session_store.py (2)
- .\core\api\routes\browser\_session_store.py
- .\gateway\routes\browser\_session_store.py

### _state.py (2)
- .\core\api\routes\browser\_state.py
- .\gateway\routes\browser\_state.py

### _surf_actions.py (2)
- .\core\api\routes\browser\_surf_actions.py
- .\gateway\routes\browser\_surf_actions.py

### _surf_controls.py (2)
- .\core\api\routes\browser\_surf_controls.py
- .\gateway\routes\browser\_surf_controls.py

### _tasks.py (2)
- .\core\api\routes\browser\_tasks.py
- .\gateway\routes\browser\_tasks.py

### _url_permissions.py (2)
- .\core\api\routes\browser\_url_permissions.py
- .\gateway\routes\browser\_url_permissions.py

### build.py (2)
- .\core\api\routes\commandcenter\build.py
- .\gateway\routes\commandcenter\build.py

### money.py (2)
- .\core\api\routes\commandcenter\money.py
- .\gateway\routes\commandcenter\money.py

### observe.py (2)
- .\core\api\routes\commandcenter\observe.py
- .\gateway\routes\commandcenter\observe.py

### operate.py (2)
- .\core\api\routes\commandcenter\operate.py
- .\gateway\routes\commandcenter\operate.py

### overview.py (2)
- .\core\api\routes\commandcenter\overview.py
- .\gateway\routes\commandcenter\overview.py

### secure.py (2)
- .\core\api\routes\commandcenter\secure.py
- .\gateway\routes\commandcenter\secure.py

### system.py (2)
- .\core\api\routes\commandcenter\system.py
- .\gateway\routes\commandcenter\system.py

### dispatcher.py (2)
- .\core\automation\dispatcher.py
- .\core\kernel\dispatcher.py

### economic_optimizer.py (2)
- .\core\brain\economic_optimizer.py
- .\core\optimization\economic_optimizer.py

### budget.py (2)
- .\core\context\budget.py
- .\core\context_engine\budget.py

### event_bus.py (2)
- .\core\contracts\event_bus.py
- .\core\messaging\event_bus.py

### policy.py (2)
- .\core\contracts\policy.py
- .\core\scout\policy.py

### sqlite_store.py (2)
- .\core\contracts\sqlite_store.py
- .\core\memory\sqlite_store.py

### db_repository.py (2)
- .\core\database\db_repository.py
- .\core\_archive\batch-5\db_repository.py

### pgbouncer_pool.py (2)
- .\core\database\pgbouncer_pool.py
- .\core\_archive\batch-6\pgbouncer_pool.py

### tenant_db.py (2)
- .\core\database\tenant_db.py
- .\core\_archive\batch-6\tenant_db.py

### seed_ecosystem.py (2)
- .\core\ecosystem\seed_ecosystem.py
- .\core\_archive\batch-2\backend\scripts\seed_ecosystem.py

### error_pattern_db.py (2)
- .\core\errors\error_pattern_db.py
- .\core\_archive\batch-6\error_pattern_db.py

### policy_engine.py (2)
- .\core\external_agents\control\policy_engine.py
- .\core\governance\policy_engine.py

### trigger_render_deploy.py (2)
- .\core\github\scripts\trigger_render_deploy.py
- .\scripts\ops\deploy\trigger_render_deploy.py

### router.py (2)
- .\core\intelligence\router.py
- .\core\tools\social\telegram_bot\router.py

### audit_logger.py (2)
- .\core\kernel\audit_logger.py
- .\core\security\audit_logger.py

### dedup.py (2)
- .\core\learning\dedup.py
- .\core\scout\dedup.py

### anti_hacking.py (2)
- .\core\middleware\anti_hacking.py
- .\gateway\middleware\anti_hacking.py

### chaos_injector.py (2)
- .\core\middleware\chaos_injector.py
- .\gateway\middleware\chaos_injector.py

### schemas.py (2)
- .\core\missions\schemas.py
- .\core\runs\schemas.py

### crawler.py (2)
- .\core\models\crawler.py
- .\core\scout\crawler.py

### integration.py (2)
- .\core\models\integration.py
- .\core\self_evolution\neural_symbolic\integration.py

### shared_workspace.py (2)
- .\core\models\shared_workspace.py
- .\core\_archive\batch-2\backend\core\models\shared_workspace.py

### logging.py (2)
- .\core\monitoring\logging.py
- .\core\_archive\batch-6\logging.py

### metrics_collector.py (2)
- .\core\monitoring\metrics_collector.py
- .\core\_archive\batch-6\metrics_collector.py

### gmail_plugin.py (2)
- .\core\plugins\experimental\gmail_plugin.py
- .\core\plugins\official\gmail_plugin.py

### google_drive_plugin.py (2)
- .\core\plugins\experimental\google_drive_plugin.py
- .\core\plugins\official\google_drive_plugin.py

### notion_plugin.py (2)
- .\core\plugins\experimental\notion_plugin.py
- .\core\plugins\official\notion_plugin.py

### slack_plugin.py (2)
- .\core\plugins\experimental\slack_plugin.py
- .\core\plugins\official\slack_plugin.py

### telegram_plugin.py (2)
- .\core\plugins\experimental\telegram_plugin.py
- .\core\plugins\official\telegram_plugin.py

### adapter.py (2)
- .\core\providers\appwrite\adapter.py
- .\core\providers\n8n\adapter.py

### scanner.py (2)
- .\core\pyerrorfix\core\scanner.py
- .\core\tools\gap_finder\scanner.py

### task_queue.py (2)
- .\core\queue\task_queue.py
- .\core\task_queue\task_queue.py

### task_queue_enhanced.py (2)
- .\core\queue\task_queue_enhanced.py
- .\core\task_queue\task_queue_enhanced.py

### circuit_breaker.py (2)
- .\core\resilience\circuit_breaker.py
- .\gateway\circuit_breaker.py

### docker_sandbox.py (2)
- .\core\sandbox\docker_sandbox.py
- .\core\tools\devops\docker_sandbox.py

### auto_find_blindspots.py (2)
- .\core\scripts\auto_find_blindspots.py
- .\scripts\ops\security\auto_find_blindspots.py

### auto_healer.py (2)
- .\core\services\auto_healer.py
- .\gateway\services\auto_healer.py

### config_service.py (2)
- .\core\services\config_service.py
- .\gateway\services\config_service.py

### delivery_fleet_tracker.py (2)
- .\core\services\delivery_fleet_tracker.py
- .\gateway\services\delivery_fleet_tracker.py

### diagram_parser_service.py (2)
- .\core\services\diagram_parser_service.py
- .\gateway\services\diagram_parser_service.py

### dynamic_planner.py (2)
- .\core\services\dynamic_planner.py
- .\gateway\services\dynamic_planner.py

### escrow_service.py (2)
- .\core\services\escrow_service.py
- .\gateway\services\escrow_service.py

### integration_discovery.py (2)
- .\core\services\integration_discovery.py
- .\gateway\services\integration_discovery.py

### intent_deciphering.py (2)
- .\core\services\intent_deciphering.py
- .\gateway\services\intent_deciphering.py

### internet_monitor_service.py (2)
- .\core\services\internet_monitor_service.py
- .\gateway\services\internet_monitor_service.py

### knowledge_qa.py (2)
- .\core\services\knowledge_qa.py
- .\gateway\services\knowledge_qa.py

### memory_service.py (2)
- .\core\services\memory_service.py
- .\gateway\services\memory_service.py

### minio_client.py (2)
- .\core\services\minio_client.py
- .\gateway\services\minio_client.py

### project_context_service.py (2)
- .\core\services\project_context_service.py
- .\gateway\services\project_context_service.py

### render_account_service.py (2)
- .\core\services\render_account_service.py
- .\gateway\services\render_account_service.py

### render_preflight_service.py (2)
- .\core\services\render_preflight_service.py
- .\gateway\services\render_preflight_service.py

### rider_tracker.py (2)
- .\core\services\rider_tracker.py
- .\gateway\services\rider_tracker.py

### sandbox_service.py (2)
- .\core\services\sandbox_service.py
- .\gateway\services\sandbox_service.py

### self_correction.py (2)
- .\core\services\self_correction.py
- .\gateway\services\self_correction.py

### video_to_code_pipeline.py (2)
- .\core\services\video_to_code_pipeline.py
- .\gateway\services\video_to_code_pipeline.py

### vision_service.py (2)
- .\core\services\vision_service.py
- .\gateway\services\vision_service.py

### voice_service.py (2)
- .\core\services\voice_service.py
- .\gateway\services\voice_service.py

### learning_engine.py (2)
- .\core\services\dynamic_ai\learning_engine.py
- .\gateway\services\dynamic_ai\learning_engine.py

### local_fallback.py (2)
- .\core\services\dynamic_ai\local_fallback.py
- .\gateway\services\dynamic_ai\local_fallback.py

### dispatch.py (2)
- .\core\services\hitl\dispatch.py
- .\gateway\services\hitl\dispatch.py

### hitl_ledger.py (2)
- .\core\services\hitl\hitl_ledger.py
- .\gateway\services\hitl\hitl_ledger.py

### resume_token.py (2)
- .\core\services\hitl\resume_token.py
- .\gateway\services\hitl\resume_token.py

### cline_checker.py (2)
- .\core\services\ide_trio\cline_checker.py
- .\gateway\services\ide_trio\cline_checker.py

### gemini_writer.py (2)
- .\core\services\ide_trio\gemini_writer.py
- .\gateway\services\ide_trio\gemini_writer.py

### kilo_reviewer.py (2)
- .\core\services\ide_trio\kilo_reviewer.py
- .\gateway\services\ide_trio\kilo_reviewer.py

### installer.py (2)
- .\core\skills\installer.py
- .\skills\installer.py

### solution_synthesizer.py (2)
- .\core\tools\discovery_fabric\supremeai_discovery\solution_synthesizer.py
- .\core\tools\solution_synthesizer\tools\solution_synthesizer.py

### branding.py (2)
- .\core\utils\branding.py
- .\gateway\service\branding.py

### firestore_helpers.py (2)
- .\core\utils\firestore_helpers.py
- .\core\_archive\batch-2\backend\core\utils\firestore_helpers.py

### command_center.py (2)
- .\core\ws\command_center.py
- .\gateway\ws\command_center.py

### client.py (2)
- .\examples\mcp-client-py\client.py
- .\examples\sdk-client-py\client.py

### extension.ts (2)
- .\examples\vscode-agent-monitor\src\extension.ts
- .\vscode\extension\src\extension.ts

### infisical_bootstrap.py (2)
- .\infrastructure\mcp-control-plane\scripts\runtime\infisical_bootstrap.py
- .\scripts\ops\runtime\infisical_bootstrap.py

### key-pool.ts (2)
- .\infrastructure\mcp-control-plane\src\adapters\ai\key-pool.ts
- .\infrastructure\mcp-control-plane\src\lib\key-pool.ts

### audit.ts (2)
- .\infrastructure\mcp-control-plane\src\adapters\devtools\audit.ts
- .\infrastructure\mcp-control-plane\src\audit\audit.ts

### create_issue.py (2)
- .\scripts\agents\create_issue.py
- .\scripts\ops\maintenance\create_issue.py

### self_healing_reporter.py (2)
- .\scripts\agents\self_healing_reporter.py
- .\scripts\ci\self_healing_reporter.py

### deploy.sh (2)
- .\scripts\ci\deploy.sh
- .\scripts\ops\deploy.sh

### generate_types.py (2)
- .\scripts\ci\generate_types.py
- .\scripts\ops\generate_types.py

### migration_safety_diff.py (2)
- .\scripts\ci\migration_safety_diff.py
- .\scripts\ops\advanced_analysis\migration_safety_diff.py

### ingest_project_docs.py (2)
- .\scripts\knowledge\ingest_project_docs.py
- .\scripts\ops\ingest_project_docs.py

### chat.ts (2)
- .\studio\packages\shared-types\src\chat.ts
- .\studio\src\types\chat.ts

### App.tsx (2)
- .\studio\src\App.tsx
- .\vscode\mobile\src\App.tsx

### hooks.ts (2)
- .\studio\src\commandcenter\data\hooks.ts
- .\studio\src\data\hooks.ts

### CommandPalette.tsx (2)
- .\studio\src\commandcenter\kit\CommandPalette.tsx
- .\studio\src\commandcenter\shell\CommandPalette.tsx

### EmptyState.test.tsx (2)
- .\studio\src\commandcenter\kit\EmptyState.test.tsx
- .\studio\src\components\ui\EmptyState.test.tsx

### EmptyState.tsx (2)
- .\studio\src\commandcenter\kit\EmptyState.tsx
- .\studio\src\components\ui\EmptyState.tsx

### CostAuditor.tsx (2)
- .\studio\src\commandcenter\modules\money\CostAuditor.tsx
- .\studio\src\components\admin\CostAuditor.tsx

### HealthMap.tsx (2)
- .\studio\src\commandcenter\modules\observe\HealthMap.tsx
- .\studio\src\components\admin\HealthMap.tsx

### LiveLogs.tsx (2)
- .\studio\src\commandcenter\modules\observe\LiveLogs.tsx
- .\studio\src\components\admin\LiveLogs.tsx

### ConfigEditor.tsx (2)
- .\studio\src\commandcenter\modules\system\ConfigEditor.tsx
- .\studio\src\components\admin\ConfigEditor.tsx

### CommandBar.tsx (2)
- .\studio\src\commandcenter\shell\CommandBar.tsx
- .\studio\src\components\layout\CommandBar.tsx

### BrowserViewport.tsx (2)
- .\studio\src\components\admin\admin-browser\BrowserViewport.tsx
- .\studio\src\components\browser\BrowserViewport.tsx

### constants.ts (2)
- .\studio\src\components\admin\ci\ci-dashboard\constants.ts
- .\studio\src\config\constants.ts

### ActionCard.tsx (2)
- .\studio\src\components\admin\shared\ActionCard.tsx
- .\studio\src\components\ui\ActionCard.tsx

### MobilePreviewPanel.tsx (2)
- .\studio\src\components\common\MobilePreviewPanel.tsx
- .\studio\src\components\customer\MobilePreviewPanel.tsx

### Skeleton.test.tsx (2)
- .\studio\src\components\common\Skeleton.test.tsx
- .\studio\src\components\ui\Skeleton.test.tsx

### Skeleton.tsx (2)
- .\studio\src\components\common\Skeleton.tsx
- .\studio\src\components\ui\Skeleton.tsx

### Sidebar.tsx (2)
- .\studio\src\components\core\Sidebar.tsx
- .\studio\src\components\dashboard\Sidebar.tsx

### DashboardLayout.tsx (2)
- .\studio\src\components\dashboard\DashboardLayout.tsx
- .\studio\src\components\layout\DashboardLayout.tsx

### AgentNode.tsx (2)
- .\studio\src\components\nodes\AgentNode.tsx
- .\studio\src\pages\user\EvolutionForge\nodes\AgentNode.tsx

### auth.setup.ts (2)
- .\tests\qa\playwright\admin\.auth\auth.setup.ts
- .\tests\qa\playwright\customer\.auth\auth.setup.ts

### shims.d.ts (2)
- .\vscode\desktop\src\shims.d.ts
- .\vscode\mobile\src\shims.d.ts
