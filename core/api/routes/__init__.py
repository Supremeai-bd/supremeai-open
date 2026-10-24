"""Safe re-exports of API routers."""

from __future__ import annotations

import importlib
from typing import Any

from core.logging_config import logger

_safe_imports: dict[str, Any] = {}

# (exported_var_name, relative_module_name, attribute_name)
_ROUTER_DEFINITIONS: list[tuple[str, str, str]] = [
    ("approval_manager_router", ".approval_manager", "router"),
    ("admin_dashboard_router", ".admin_dashboard", "router"),
    ("agent_router", ".agent_tasks", "agent_router"),
    ("auth_router", ".auth", "router"),
    ("async_task_router", ".async_task_router", "router"),
    ("cdc_router", ".cdc_webhooks", "router"),
    ("browser_router", ".browser", "router"),
    ("codeflow_router", ".codeflow", "router"),
    ("feedback_router", ".feedback", "router"),
    ("knowledge_router", ".knowledge", "router"),
    ("marketplace_router", ".marketplace_endpoints", "router"),
    ("media_router", ".media", "router"),
    ("memory_router", ".memory", "router"),
    ("metrics_router", ".metrics", "router"),
    ("site_actions_router", ".site_actions", "router"),
    ("llm_gateway_router", ".llm_gateway_routes", "router"),
    ("simulator_router", ".simulator", "router"),
    ("stream_router", ".stream", "router"),
    ("task_router", ".task", "router"),
    ("email_router", ".email", "router"),
    ("github_router", ".github", "router"),
    ("internal_router", ".internal", "router"),
    ("config_router", ".config_routes", "router"),
    ("sso_router", ".sso", "router"),
    ("repos_router", ".repos", "router"),
    ("tools_ops_router", ".tools_ops", "router"),
    ("voice_router", ".voice", "router"),
    ("onboarding_router", ".onboarding", "router"),
    ("tools_registry_router", ".tools_registry", "router"),
    ("preferences_router", ".preferences", "router"),
    ("usage_metrics_router", ".usage_metrics", "router"),
    ("agents_router", ".agents", "router"),
    ("payments_router", ".payments", "router"),
    ("markdown_router", ".markdown", "router"),
    ("api_keys_router", ".api_keys", "router"),
    ("graph_router", ".graph", "router"),
    ("ci_webhooks_router", ".ci_webhooks", "router"),
    ("websocket_voice_router", ".websocket_voice", "router"),
    ("integrations_router", ".integrations", "router"),
    ("internet_monitor_router", ".internet_monitor", "router"),
    ("service_topology_router", ".service_topology", "router"),
    ("zero_cost_router", ".zero_cost", "router"),
    ("artifacts_router", ".artifacts", "router"),
    ("chat_router", ".chat", "router"),
    ("sse_router", ".stream_chat_sse", "router"),
    ("crawler_admin_router", ".crawler_admin", "router"),
]

for _var_name, _mod_path, _attr_name in _ROUTER_DEFINITIONS:
    try:
        _mod = importlib.import_module(_mod_path, package=__name__)
        _router_obj = getattr(_mod, _attr_name, None)
        globals()[_var_name] = _router_obj
        if _router_obj is not None:
            _safe_imports[_var_name] = _router_obj
    except Exception as _exc:
        logger.warning(f"Router import failed for {_var_name}: {_exc}")
        globals()[_var_name] = None

# STABILIZE FIX: swarm.py was deleted during Phase 1 Router Consolidation.
# Clean placeholder kept for backwards-compatibility.
swarm_router = None

__all__ = list(_safe_imports.keys())
