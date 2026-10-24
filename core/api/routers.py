"""Centralized router registration for SupremeAI API."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from api import register_router
from api.deps import get_current_user_token
from core.config import settings
from core.logging_config import logger

# Unified declarative registry of all routers.
# Format: {"path": str, "prefix": str, "is_admin": bool, "is_critical": bool}
# Deduplicated and cleaned up according to Phase 2 API Cleanup.
ALL_ROUTERS = [
    # ---- Core & User Routes ----
    # Phase 1: formerly orphaned feature routes are now centrally registered.
    {"path": "api.routes.artifacts", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.kernel_dispatch", "prefix": "", "is_admin": False, "is_critical": True},
    {"path": "api.routes.task_gateway", "prefix": "", "is_admin": False, "is_critical": True},
    {"path": "api.routes.browser", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.branch_conversations",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {
        "path": "api.routes.browser_action_registry",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.chat_export", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.chat_search", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.chat_upload", "prefix": "", "is_admin": False, "is_critical": False},
    # ERR-B01 (defect register 2026-09-15): Project Spaces CRUD — real backend
    # for the formerly-static /projects page. Own APIRouter prefix (/api/v1/projects).
    {"path": "api.routes.projects", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.code_dependency_graph",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.deep_research", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.prompt_templates", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.reasoning", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.scheduled_tasks", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.share", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.slash_commands", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.memory", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.unified_memory_api",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.task", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.capabilities", "prefix": "", "is_admin": False, "is_critical": False},
    # FCC (Federated Capability Circles): topology/health are user-gated,
    # POST /dispatch enforces admin auth inside the router itself.
    {"path": "api.routes.circles", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.social_growth", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.markdown", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {"path": "api.routes.simulator", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.stream", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.media", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.graph", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.marketplace_endpoints",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.auth", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {"path": "api.routes.onboarding", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.localization",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.analytics", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {"path": "api.routes.email", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.github", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.config_routes", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.cognitive", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.cache_predictions",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {
        "path": "api.routes.healing_stats",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.repos", "prefix": "", "is_admin": False, "is_critical": False},
    # ERR-H07 two-surface agent contract (drift-guarded by
    # backend/tests/api/test_agent_execute_contract.py):
    #   api.routes.agents → /api/agents        (USER token, read-only catalog/status)
    #   api.routes.agent  → /api/v1/agents     (INTEGRATION JWT, canonical execution)
    {"path": "api.routes.agents", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.agent", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "agents.code_vulnerability_scanner_agent",
        "prefix": "",
        "is_admin": True,
        "is_critical": False,
    },
    {"path": "api.routes.tools_registry", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.skills", "prefix": "/api", "is_admin": False, "is_critical": False},
    {"path": "api.routes.files", "prefix": "/api", "is_admin": False, "is_critical": False},
    {"path": "api.routes.usage_metrics", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.sso", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.api_keys", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.ci_webhooks", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.merge_learning", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.n8n_webhooks", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.task_workspace",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    # {"path": "api.routes.websocket_agent", "prefix": "", "is_admin": False, "is_critical": False},
    # R10 FIX: SSE stream for the /chat route (lightweight HTTP transport)
    {"path": "api.routes.stream_chat_sse", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.agent_workspace",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {
        "path": "api.routes.integrations",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.admin_v1", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.agent_action",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    # {"path": "api.routes.websocket_hitl", "prefix": "", "is_admin": False, "is_critical": False},
    # R10 FIX: SSE stream for the HITL route
    {"path": "api.routes.stream_hitl_sse", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.syncguard", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.session_stream",
        "prefix": "/api",
        "is_admin": False,
        "is_critical": False,
    },
    {
        "path": "api.routes.realtime_dashboard",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.ci_dashboard_api", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.living_engine", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.scraper", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {"path": "api.routes.kaggle", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.dock_integrations",
        "prefix": "/api",
        "is_admin": False,
        "is_critical": False,
    },
    # {"path": "api.routes.websocket_voice", "prefix": "", "is_admin": False, "is_critical": False},
    # #1832: stream_voice_sse removed — zero consumers (feature_parity_baseline
    # listed it as an orphan endpoint); the live voice transport is the
    # re-mounted websocket_voice below (CommandCenter connects /ws/voice).
    # FIX (API-contract audit): এই তিনটি রাউটারের ফ্রন্টএন্ড কনজিউমার দীর্ঘদিন
    # সক্রিয় ছিল কিন্তু রাউটারগুলো কখনো মাউন্টই হয়নি — ফলে সব রিয়েলটাইম
    # সংযোগ নীরবে ব্যর্থ হতো:
    #   - events            → GET /api/dashboard/stream (SSE) — ServiceHealthMetrics,
    #                          AutomationQueuePage, useDashboardData
    #   - session_takeover  → WS /ws/session/{id}/takeover — ScreencastViewer,
    #                          sessionCockpitStore
    #   - websocket_voice   → WS /ws/voice — CommandCenter voice realtime
    {"path": "api.routes.events", "prefix": "/api", "is_admin": False, "is_critical": False},
    {"path": "api.routes.session_takeover", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.websocket_voice", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "tools.collaborative_editor",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "tools.code.image_to_code", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "tools.learning.style_learner",
        "prefix": "/api",
        "is_admin": False,
        "is_critical": False,
    },
    # Mount-hygiene (2026-09-15): the api.routes.codeflow entry used to sit
    # here, but codeflow.py is a legacy re-export shim that re-exports the SAME
    # router object as api.routes.code_dependency_graph (registry entry above)
    # — mounting both double-registered every /api/codeflow route.
    {"path": "api.routes.feedback", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "tools.media.multilingual_tts",
        "prefix": "/api",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.voice", "prefix": "/api/voice", "is_admin": False, "is_critical": False},
    {"path": "tools.comment_thread_ai", "prefix": "/api", "is_admin": False, "is_critical": False},
    {"path": "api.routes.mobile_bff", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.payments", "prefix": "", "is_admin": False, "is_critical": False},
    # RESTORE-AND-WIRE (2026-09-14): admin auth endpoints (firebase-login, TOTP
    # setup/verify/recover, trusted browsers, free-tier controls) were previously
    # unmounted — yet core/config_fields.py public-path allowlist and
    # tests/api/test_admin_routes.py both EXPECT these routes to exist.
    # Endpoints enforce their own admin auth internally; login itself must be
    # reachable pre-authentication, hence is_admin=False.
    # Issue #683 Section 1: moved from core.admin_routes → api.routes.admin_routes
    # (core must never import api; the admin router imports api.dependencies).
    {"path": "api.routes.admin_routes", "prefix": "", "is_admin": False, "is_critical": True},
    # RESTORE-AND-WIRE (2026-09-14): /api/v1/gateway proxy (rate-limited
    # forward + capability dispatch) restored and mounted; admin flag adds
    # router-level get_current_user_token to every endpoint (its /forward
    # already has endpoint-level auth — duplicate deps are harmless).
    {"path": "tools.api_gateway", "prefix": "", "is_admin": True, "is_critical": False},
    # WIRE-NEXT (2026-09-27, issue #2148): EAOL Part-3 seed (external_agents,
    # registry §11 NEAR-READY-UNWIRED → wired) exposed as a managed admin
    # surface — double-gated: ALL_ROUTERS admin auth (this entry) + in-module
    # SUPREMEAI_EXTERNAL_AGENTS_ENABLED env flag (default off, fails closed).
    {
        "path": "api.routes.external_agents_admin",
        "prefix": "",
        "is_admin": True,
        "is_critical": False,
    },
    {
        "path": "api.routes.maintenance",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.sandbox_api", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.pr_review_api", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.v1.telemetry", "prefix": "/api", "is_admin": False, "is_critical": False},
    {
        "path": "tools.social.telegram_bot.router",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.keys", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.conversations",
        "prefix": "/api/v1",
        "is_admin": False,
        "is_critical": False,
    },
    # ---- Critical Routes ----
    {"path": "api.routes.llm_gateway_routes", "prefix": "", "is_admin": False, "is_critical": True},
    {"path": "api.routes.knowledge", "prefix": "/api", "is_admin": False, "is_critical": True},
    {"path": "api.routes.billing_api", "prefix": "", "is_admin": False, "is_critical": True},
    # ---- Admin & Health Routes ----
    {
        # #1833: the router carries its own /admin-api prefix — a previous
        # /api mount here produced a double-prefixed /api/admin-api/... path
        # that no docstring or frontend consumer ever called.
        "path": "api.routes.health_aggregation",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.health", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    {"path": "api.routes.public_config", "prefix": "/api", "is_admin": False, "is_critical": False},
    {"path": "api.routes.preferences", "prefix": "/api", "is_admin": False, "is_critical": False},
    {"path": "api.routes.simulator_admin", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.site_actions", "prefix": "", "is_admin": True, "is_critical": False},
    {
        "path": "api.routes.hitl_admin",
        "prefix": "/api/v1/hitl",
        "is_admin": True,
        "is_critical": False,
    },
    {"path": "api.routes.evolution", "prefix": "/api/v1", "is_admin": True, "is_critical": False},
    # Issue #446: SSE bridge the EvolutionForge DebateOverlay has always called
    # (router module declares its own /api/v1/swarm prefix).
    {"path": "api.routes.swarm_stream", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.agent_breeding",
        "prefix": "/api/v1",
        "is_admin": True,
        "is_critical": False,
    },
    {"path": "api.routes.admin_dashboard", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.internal", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.admin", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.admin_llm", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.ai_assignment", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.traffic_monitor", "prefix": "", "is_admin": True, "is_critical": False},
    {
        "path": "api.routes.admin_librarian",
        # Issue #1492: the router already declares its own `/api/admin/librarian`
        # prefix — adding "/api" here produced `/api/api/admin/librarian/...`
        # (live-verified: only the double-prefixed path resolved). Empty prefix
        # matches every other self-prefixed admin router in this registry.
        "prefix": "",
        "is_admin": True,
        "is_critical": False,
    },
    {"path": "api.routes.tenant_admin", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.workspaces_route", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.metrics", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.cloud_mesh", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.tools_ops", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.execution_policies", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.living_brain", "prefix": "", "is_admin": True, "is_critical": False},
    {
        "path": "api.routes.render_preflight_admin",
        "prefix": "",
        "is_admin": True,
        "is_critical": False,
    },
    # ── Tier-S (all 12 routers via centralized registry) ──
    # CI FIX: Also register individual Tier-S modules directly so the API
    # contract diff analyzer can discover their @router decorators.
    # (tier_s_routes.py uses a tuple list, not @router decorators in-file.)
    {"path": "api.routes.ecosystem", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.ecosystem_admin", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.global_memory", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.zero_cost", "prefix": "/api/v1", "is_admin": False, "is_critical": False},
    # AUD-3.5 / Phase 4: the HITL approval REST surface was previously never
    # mounted (dead end: events were visible but could never be decided). The
    # router itself enforces verify_admin_session_fail_closed on every route.
    {
        "path": "api.routes.approval_manager",
        "prefix": "",
        "is_admin": True,
        "is_critical": False,
    },
    # বাংলা: internet_monitor route আগে _safe_imports dict-এ ছিল যেটা কেউ consume করত না
    # (USAGE-A analysis-এ "ACTIVE LOADED, ROUTES UNWIRED" হিসেবে চিহ্নিত ছিল)।
    # এখন ALL_ROUTERS-এ registered — admin auth (get_current_admin) সব endpoint-এ আছে।
    {"path": "api.routes.internet_monitor", "prefix": "", "is_admin": True, "is_critical": False},
    # Audit fix (this session): service_topology (admin service health checker +
    # admin-token WebSocket health-stream consumed by the CI dashboard) was never
    # registered — doubly dead (missing ADMIN_URL_DEFAULT/SCRAPER_URL_DEFAULT
    # imports fixed in core/deployment_fallback_defaults.py + absent here).
    # Router enforces get_current_admin on routes and authenticate_websocket on
    # the WS endpoint; admin routing flag additionally applies the token dependency.
    {"path": "api.routes.service_topology", "prefix": "", "is_admin": True, "is_critical": False},
    # Canonical browser-facing broker for service discovery and health.
    {"path": "api.routes.control_plane", "prefix": "", "is_admin": False, "is_critical": True},
    {
        "path": "api.routes.intelligence_insights",
        "prefix": "",
        "is_admin": True,
        "is_critical": False,
    },
    # Tenant-scoped capability discovery and provider-consent registration.
    {
        "path": "api.routes.workspace_capabilities",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    # Admin Command Center aggregated metrics, controls and submodules
    {"path": "api.routes.commandcenter", "prefix": "", "is_admin": True, "is_critical": False},
    # Policy-Driven Web Crawler Admin API
    {"path": "api.routes.crawler_admin", "prefix": "", "is_admin": True, "is_critical": False},
    # Universal Zero-Complexity Interface (Phase 1): modular connection engine +
    # execution-mode self-service. All routes auth-guarded; no secrets handled.
    {"path": "api.routes.connections", "prefix": "", "is_admin": False, "is_critical": True},
    {"path": "api.routes.access", "prefix": "", "is_admin": False, "is_critical": False},
    # ── AUDIT-WIRE FIX (isolated-routes audit): এই ১২টি রাউটার মডিউল বিদ্যমান,
    # import-যাচাইকৃত এবং সঠিক 'router' attribute সহ — কিন্তু রে���িস্ট্রিতে ছিল না
    # বলে তাদের ২৪+ এন্ডপয়েন���ট প্রোডাকশনে 404 দিত। এখন মাউন্ট করা হলো।
    # মাউন্ট-নিরাপত্তা নোট: chat.py-এর chat-router ফ্রন্টএন্ড ExportMenu/
    # ImageUploadButton/ChatSearchDialog এভendpoints কল করে।
    # মাউন্ট-নোট: এই মডিউলগুলোর প্রতিটির নিজস্ব APIRouter prefix আছে, তাই
    # রেজিস্ট্রি prefix অবশ্যই "" (নইলে URL দ্বিগুণ হয়ে যায়)।
    {"path": "api.routes.chat", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.advanced_router", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.agent_tasks", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.async_task_router", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.cdc_webhooks", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.hybrid_search", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.ide_trio", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.mcp_marketplace", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "api.routes.plugin_submissions",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "api.routes.plugins", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.selector_healing", "prefix": "", "is_admin": True, "is_critical": False},
    {"path": "api.routes.webhooks_ai", "prefix": "", "is_admin": False, "is_critical": False},
    # #1802: GitHub webhook ingest for event-driven orchestration (own prefix /api/webhooks)
    {
        "path": "api.routes.webhooks_github",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    # ── AUDIT-WIRE FIX 2 (backend/frontend parity audit, 2026-09-11): এই ৭টি মডিউলের
    # কার্যকর APIRouter ছিল কিন্তু র���জিস্ট্রিতে ছিল না — তাদের সব এন্ডপয়েন্ট বুটে 404 দিত।
    # মাউন্ট-নোট: প্রতিটির নিজস্ব APIRouter prefix আছে (/diagram, /voice, /pair, /agent,
    # /video-to-code, /security/vulnerabilities, /ws/command-center) — তাই রেজিস্ট্রি
    # prefix অবশ্যই "" (নইলে URL দ্বিগুণ হয়ে যায়)।
    # নিরাপত্তা নোট:
    #   - vulnerability_prophet প্রতিটি রুটে নিজস্ব admin গার্ড (_require_admin) এনফোর্স করে।
    #   - voice_coder-এ WebSocket রুট আছে; HTTP-only রেজিস্ট্রি-লেভেল টোকেন ডিপেন্ডেন্সি
    #     (admin dependency) WS handshake ভেঙে দিত, তাই sibling tool-router প্যাটার্ন
    #     (image_to_code/style_learner-এর মতো is_admin=False) অনুসরণ করা হয়েছে।
    {
        "path": "tools.code.diagram_to_architecture",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    # Issue #449 wire-next: services/diagram_parser_service.py defined a full
    # APIRouter (prefix="/diagram-parser") that NO router registry referenced —
    # doubly-dead module. Light deps (stdlib + fastapi + defusedxml + llm_router),
    # its own tests exist → wired, not archived.
    {
        "path": "services.diagram_parser_service",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "tools.code.voice_coder", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "tools.code.ai_pair_programmer",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    {"path": "tools.self_planner", "prefix": "", "is_admin": False, "is_critical": False},
    {
        "path": "services.video_to_code_pipeline",
        "prefix": "",
        "is_admin": False,
        "is_critical": False,
    },
    # Mount-hygiene (2026-09-15): vulnerability_prophet.py is a legacy re-export
    # shim for agents.code_vulnerability_scanner_agent (registry entry above);
    # listing both mounted the same /security/vulnerabilities routes twice.
    {"path": "ws.command_center", "prefix": "", "is_admin": False, "is_critical": False},
    # ── AUDIT-WIRE FIX 3 (Task 7-c/7-d mount repair, 2026-09-15): PR #304 (missions)
    # এবং PR #305 (mcp_hub) নিজ নিজ APIRouter সহ রাউটার মডিউল ship করেছিল, কিন্তু
    # এই রেজিস্ট্রিতে register হয়নি — ফলে তাদের সব এন্ডপয়েন্ট প্রোডাকশনে 404 দিত
    # (Feature Parity Sentinel: unmounted-router HIGH ×২)। এখন মাউন্ট করা হলো।
    # মাউন্ট-নোট: দুটো মডিউলেরই নিজস্ব APIRouter prefix আছে (/api/v1/missions,
    # /api/v1/mcp), তাই রেজিস্ট্রি prefix অবশ্যই "" (নইলে URL দ্বিগুণ হয়ে যায়)।
    # নিরাপত্তা নোট: দুটো রাউটারই identity verified JWT (api.dependencies.
    # get_current_user_token) থেকে derive করে — কোনো public write surface নেই;
    # missions নিজস্ব _is_admin চেক এবং mcp_hub নিজস্ব scope/role enforcement
    # রাউট-লেভেলেই এনফোর্স করে, তাই sibling tool-router প্যাটার্ন (is_admin=False)।
    {"path": "api.routes.missions", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "api.routes.mcp_hub", "prefix": "", "is_admin": False, "is_critical": False},
    # ── M1 Canonical Run fabric (roadmap M1 / PR-chain #341 → M1-B → M1-C):
    # runs রাউটার নিজস্ব prefix (/api/v1/runs) সহ আসে, তাই registry prefix ""।
    # identity verified JWT থেকে derive হয় (get_current_user_token); ownership
    # enforcement রাউট-লেভেলেই (foreign run → 404, missions parity)।
    {"path": "runs.api", "prefix": "", "is_admin": False, "is_critical": False},
    # ── MESH-1 (#939): Tower presence endpoint — multi-agent mesh foundation
    # (Phase A, P1-high)। রাউটার নিজস্ব prefix (/api/v1/nodes) সহ আসে, তাই
    # registry prefix "" (নইলে URL দ্বিগুণ হয়ে যায়)। এই endpoints presence
    # state ছাড়া আর কিছু স্পর্শ করে না — একটি follow-up issue (MESH-3) auth যোগ
    # করবে; আপাতত pre-auth heartbeat support করা হয়েছে যাতে একটি fresh agent
    # প্রথম কলেই registration করতে পারে। নতুন file: backend/core/presence_registry.py
    {"path": "api.routes.mesh", "prefix": "", "is_admin": False, "is_critical": False},
    # ── MESH-6 (#926, P0): Tower-native Task Queue — /api/v1/tasks/*
    # রাউটার নিজস্ব prefix (/api/v1/tasks) সহ আসে, তাই registry prefix ""।
    # Core: backend/core/task_router.py (CAS claim + lease + Zero Zombie reap)।
    {"path": "api.routes.mesh_tasks", "prefix": "", "is_admin": False, "is_critical": False},
    # ── MESH-3 (#927, P1-high): Agent Mailbox — agent↔agent direct + pub/sub
    # messaging (/api/v1/mesh/messages/*, /subscriptions)। Core নিজস্ব prefix
    # সহ আসে, তাই registry prefix ""। Core: backend/core/agent_mailbox.py।
    {"path": "api.routes.mesh_mailbox", "prefix": "", "is_admin": False, "is_critical": False},
    # ── #1150 Phase 1: Agent Registry — admin-defined roles + AI provider per
    # agent (/api/v1/agents/*)। রাউটার নিজস্ব prefix সহ আসে, তাই registry prefix
    # ""। Reads are inert (no privileged resource); writes are admin-only.
    {"path": "api.routes.agent_registry", "prefix": "", "is_admin": False, "is_critical": False},
    {"path": "integrations.github_webhook", "prefix": "", "is_admin": False, "is_critical": False},
]


def register_all_routers(app: FastAPI) -> None:
    """Register all unified routers on the FastAPI app.

    FIX (AUDIT-FF, HIGH): আগে is_critical ফ্ল্যাগটি মৃত কোড ছিল — critical ও সাধারণ
    দুই শাখাই optional=True পাঠাত, ফলে যেকোনো critical রাউটার (llm_gateway,
    knowledge, billing, control_plane) সাইলেন্টলি আনমাউন্ট থেকে যেত এবং অ্যাপ
    সবুজ হেলথ-চেক সহ চলত (প্রমাণিত: billing_api stripe-import ব্যর্থ হলে পুরো
    payments/webhook সারফেস 404 দেয় অথচ স্টার্টআপ সফল হয়)। এখন:
      1. is_critical=True রাউটার optional=False — import ব্যর্থ হলে স্টার্টআপ fail-fast।
      2. রেজিস্ট্র����শন শেষে mounted-vs-registered হিসাব লগ হয়; অনুপাত সন্দেহজনক
         হলে (০ বা অর্ধেকের কম) warning সহ কাউন্ট রিপ���র্ট হয়।
    """
    current_role = getattr(settings, "supremeai_service_role", "monolith").lower()
    logger.info(f"Registering routers for SERVICE_ROLE: {current_role}")

    registered = 0
    mounted = 0
    from api import _registration_report

    for router_def in ALL_ROUTERS:
        path = router_def["path"]
        prefix = router_def["prefix"]
        is_admin = router_def["is_admin"]
        is_critical = router_def["is_critical"]

        # OOM FIX: Service modularization based on SUPREMEAI_SERVICE_ROLE
        is_scraper_route = "scraper" in path or "browser" in path
        is_health_route = "health" in path or "service_topology" in path

        if current_role == "scraper" and not (is_scraper_route or is_health_route):
            continue

        if current_role == "worker" and not is_health_route:
            continue

        if current_role == "core" and is_scraper_route:
            continue

        deps = [Depends(get_current_user_token)] if is_admin else None
        registered += 1

        if is_critical:
            # AUDIT-FF: critical রাউটার সাইলেন্টলি মিস হওয়া যাবে না — fail-fast।
            logger.info(f"Loading critical router: {path}")
            register_router(app, path, prefix=prefix, optional=False, dependencies=deps)
            mounted += 1
        else:
            before = len(_registration_report)
            register_router(app, path, prefix=prefix, optional=True, dependencies=deps)
            if len(_registration_report) == before:
                mounted += 1

    if settings.encryption_key and settings.encryption_key.get_secret_value():
        register_router(app, "api.routes.byoc_api", "", optional=True)
    else:
        logger.warning("Universal BYOC router not loaded: ENCRYPTION_KEY missing")

    # AUDIT-FF: স্ট���র্টআপে মাউন্ট-রিপোর্ট — সাইলেন্ট আনমাউন্ট এখন দৃশ্যমান।
    failed = list(_registration_report)
    logger.info(f"Router registration complete: mounted={mounted}/{registered} registry entries")
    if failed:
        logger.warning(
            f"Router registration FAILURES ({len(failed)}): "
            + ", ".join(f"{r['module']} ({r['error_type']}: {r['message'][:80]})" for r in failed)
        )
    if registered and mounted < registered / 2:
        logger.error(
            f"Less than half of registry routers mounted ({mounted}/{registered}) — "
            "API surface is likely broken; check the failure list above."
        )

    # Issue #1494: mount the Memory MCP server over HTTP at /mcp (SSE +
    # client→server frames), Bearer MCP_ADMIN_KEY auth, fail-closed. Optional
    # dependency — a missing mcp SDK logs a warning and boot continues
    # (the sub-app answers 503 at request time). Skipped on scraper/worker
    # roles, mirroring the registry gating above: the memory surface is a
    # core/monolith concern.
    if current_role in ("scraper", "worker"):
        logger.info(f"Memory MCP HTTP mount skipped for SERVICE_ROLE={current_role}")
    else:
        try:
            from api.routes.memory_mcp_http import create_memory_mcp_asgi_app

            app.mount("/mcp", create_memory_mcp_asgi_app())
        except Exception as exc:
            logger.warning(f"Memory MCP HTTP mount skipped: {exc}")


def include_user_routers(app: FastAPI) -> None:
    """For compatibility/tests - registers non-admin routers."""
    for router_def in ALL_ROUTERS:
        if not router_def["is_admin"]:
            register_router(app, router_def["path"], prefix=router_def["prefix"], optional=True)


def include_admin_routers(app: FastAPI) -> None:
    """For compatibility/tests - registers admin routers."""
    for router_def in ALL_ROUTERS:
        if router_def["is_admin"]:
            deps = [Depends(get_current_user_token)]
            register_router(
                app,
                router_def["path"],
                prefix=router_def["prefix"],
                optional=True,
                dependencies=deps,
            )


__all__ = [
    "ALL_ROUTERS",
    "include_admin_routers",
    "include_user_routers",
    "register_all_routers",
]
