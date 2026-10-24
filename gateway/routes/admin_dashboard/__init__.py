"""Admin Dashboard router (``/admin-api``) — package layout.

Formerly a single ~1,774-line module (api/routes/admin_dashboard.py); now
split into cohesive submodules. The public contract is unchanged:

* ``from api.routes.admin_dashboard import router`` still yields one
  :class:`fastapi.APIRouter` with prefix ``/admin-api``, tag
  ``admin-dashboard`` and the same admin-token dependencies;
* every route, Pydantic model and helper the old module exposed is still
  importable from this package (the ``from .endpoints_* import ...``
  statements below double as re-exports);
* routes are registered on ``router`` in exactly the original order
  (the submodule imports are intentionally interleaved with the local
  endpoint definitions), so the OpenAPI schema is identical.

Why some endpoints still live in ``__init__.py``: the test-suite
(tests/core/test_admin_dashboard_full.py) patches module globals through
the package namespace — ``monkeypatch.setattr(mod, "USERS_FILE", ...)``,
``monkeypatch.setattr(mod, "COST_CAPS_FILE", ...)``,
``patch("api.routes.admin_dashboard.CostAuditor")``,
``patch("api.routes.admin_dashboard.export_codebase_to_markdown")`` and
``patch.object(mod, "StreamingResponse")``. Those patches only take effect
on functions whose ``__globals__`` is THIS module's namespace, so
``load_users``/``save_users`` (USERS_FILE), ``load_cost_caps``/
``save_cost_caps`` (COST_CAPS_FILE), ``get_costs``/``get_costs_breakdown``/
``get_full_data_export`` (CostAuditor), ``get_codebase_export``
(export_codebase_to_markdown) and ``logs_stream`` (StreamingResponse) are
intentionally defined here.

Import cycle note: the ``endpoints_*`` submodules import ``router`` (and
``load_users``/``save_users``) from this package while it is still being
initialised. That is safe because this module defines those names BEFORE
the submodule imports run."""

import asyncio
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.dependencies import (
    get_current_admin,  # noqa: F401  (module-attr parity with pre-split module)
)
from api.routes.admin_auth import admin_rate_limit, require_admin_token
from core.config import settings  # noqa: F401  (module-attr parity with pre-split module)
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.utils.time_utils import utc_now
from models.ci_report import CIReportPayload, create_ci_report  # noqa: F401  (module-attr parity)
from tools.billing.cost_auditor import CostAuditor
from tools.knowledge.codebase_exporter import export_codebase_to_markdown

from ._models import ConfigUpdate, UserUpdate  # noqa: F401  (re-export)

router = APIRouter(
    prefix="/admin-api",
    tags=["admin-dashboard"],
    dependencies=[Depends(require_admin_token), Depends(admin_rate_limit)],
)


# Mock user database path
USERS_FILE = "data/users.json"


@with_error_bus("load_users")
def load_users() -> list[dict[str, Any]]:
    if not os.path.exists(USERS_FILE):
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        default_users = [
            {"username": "admin", "role": "God", "permissions": ["all"]},
            {
                "username": "operator1",
                "role": "Operator",
                "permissions": ["read", "write"],
            },
            {"username": "viewer1", "role": "Viewer", "permissions": ["read"]},
        ]
        with open(USERS_FILE, "w") as f:
            json.dump(default_users, f, indent=4)
        return default_users
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except Exception:
        logger.exception("Unhandled exception")
        return []


def save_users(users: list[dict[str, Any]]):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)


# Issue #1471 (HIGH): the SSE log stream never sent anything while the log
# file was quiet, so intermediate proxies/LB silently killed the idle
# connection ("connection timeout") and the EventSource never reconnected
# cleanly. Two guards:
#   - heartbeat: an SSE comment ping every _SSE_HEARTBEAT_INTERVAL seconds of
#     silence (comment lines keep EventSource happy and are ignored by
#     consumers)
#   - max duration: the generator closes cleanly after _SSE_MAX_STREAM_SECONDS
#     with an explicit `stream-end` event, so no connection hangs forever
_SSE_HEARTBEAT_INTERVAL = 15.0
_SSE_MAX_STREAM_SECONDS = 30 * 60.0


@router.get("/logs/stream")
def logs_stream():
    async def log_generator():
        log_file = "logs/supremeai.log"
        if not os.path.exists(log_file):
            log_file = "logs/app.log"

        if os.path.exists(log_file):
            try:
                with open(log_file) as f:
                    lines = f.readlines()[-30:]
                    for line in lines:
                        yield f"data: {line.strip()}\n\n"
            except Exception as e:
                yield f"data: Error reading logs: {e}\n\n"

        file_obj = None
        started_at = time.monotonic()
        last_output = time.monotonic()
        try:
            if os.path.exists(log_file):
                file_obj = open(log_file)  # noqa: SIM115 - handle persists across generator yields, closed in finally
                file_obj.seek(0, os.SEEK_END)

            while True:
                # Hard lifetime cap: always close cleanly, never hang forever.
                if time.monotonic() - started_at >= _SSE_MAX_STREAM_SECONDS:
                    yield "event: stream-end\ndata: log stream reached max duration; reconnecting\n\n"
                    break

                if file_obj:
                    line = file_obj.readline()
                    if line:
                        yield f"data: {line.strip()}\n\n"
                        last_output = time.monotonic()
                    else:
                        if time.monotonic() - last_output >= _SSE_HEARTBEAT_INTERVAL:
                            # SSE comment ping — proxies see traffic, browsers ignore it.
                            yield ": ping\n\n"
                            last_output = time.monotonic()
                        await asyncio.sleep(0.5)
                else:
                    if time.monotonic() - last_output >= _SSE_HEARTBEAT_INTERVAL:
                        yield ": ping\n\n"
                        last_output = time.monotonic()
                    if os.path.exists(log_file):
                        file_obj = open(log_file)  # noqa: SIM115 - handle persists across generator yields, closed in finally
                        file_obj.seek(0, os.SEEK_END)
                    await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info("Log stream client disconnected")
            raise
        finally:
            if file_obj:
                try:
                    file_obj.close()
                except Exception as exc:
                    logger.exception(f"Failed to close log stream file: {exc}")

    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/costs")
def get_costs():
    """Real-time Cost/budget metrics from CostAuditor."""
    auditor = CostAuditor()
    try:
        reports = auditor.generate_report()
        markdown_path = reports.get("text_report", "")
        if os.path.exists(markdown_path):
            with open(markdown_path, encoding="utf-8") as f:
                content = f.read()
                return {"status": "ok", "report": content}
        else:
            # 🚫 নো মোর ফেক ডেটা! রিয়েল ওয়ার্নিং মেসেজ।
            return {
                "status": "ok",
                "report": "# 📊 Cost Data Unavailable\n\nNo tasks have been executed in the current billing cycle to generate a cost report.",
            }
    except Exception as e:
        logger.error(f"Failed to generate cost report: {e}")
        return {
            "status": "error",
            "report": f"# ⚠️ Cost Engine Error\n\nUnable to pull metrics from DB: {e!s}",
        }


@router.get("/costs/breakdown")
def get_costs_breakdown():
    """Returns structured JSON cost breakdown for the React CostAuditor component."""
    auditor = CostAuditor()
    try:
        tasks = auditor.store.get_task_history()

        # Default structured values if no tasks exist
        spent = sum(t.get("cost", 0.0) for t in tasks) if tasks else 0.0

        # Calculate provider usage
        # Provider mapping based on task_type or description
        providers = {
            "Google Gemini": {"spent": 0.0, "quota": 50.00, "color": "from-[#1a73e8] to-[#8ab4f8]"},
            "OpenRouter (DeepSeek)": {
                "spent": 0.0,
                "quota": 40.00,
                "color": "from-[#ff6b6b] to-[#ff8787]",
            },
            "Hugging Face Hub": {
                "spent": 0.0,
                "quota": 30.00,
                "color": "from-[#ffd43b] to-[#ffe066]",
            },
            "Groq (Llama 3)": {
                "spent": 0.0,
                "quota": 30.00,
                "color": "from-[#20c997] to-[#38d9a9]",
            },
        }

        recent_charges = []

        for t in tasks:
            cost = t.get("cost", 0.0)
            t_type = t.get("task_type", "").lower()
            desc = t.get("task_description", "").lower()

            # Categorize provider
            target_provider = "Google Gemini"
            if "deepseek" in t_type or "openrouter" in t_type or "deepseek" in desc:
                target_provider = "OpenRouter (DeepSeek)"
            elif "huggingface" in t_type or "hf" in t_type or "hugging face" in desc:
                target_provider = "Hugging Face Hub"
            elif "groq" in t_type or "llama" in t_type or "groq" in desc:
                target_provider = "Groq (Llama 3)"

            providers[target_provider]["spent"] += cost

            # Construct charge entry
            recent_charges.append(
                {
                    "time": str(t.get("timestamp", utc_now())),
                    "user": "system",
                    "model": t.get("task_type", "unknown"),
                    "tokens": int(cost * 500000)
                    if cost > 0
                    else 0,  # Estimate tokens based on cost
                    "cost": cost,
                }
            )

        # Real-time Render usage data integration
        render_spent = 0.0
        render_quota = 50.0  # Estimated budget for Render
        try:
            # R2 FIX: use httpx instead of blocking `requests` lib
            import httpx

            render_api_key = os.getenv("RENDER_API_KEY", "")
            if render_api_key:
                with httpx.Client(timeout=5.0) as client:
                    resp = client.get(
                        "https://api.render.com/v1/services",
                        headers={
                            "Authorization": f"Bearer {render_api_key}",
                            "Accept": "application/json",
                        },
                    )
                if resp.status_code == 200:
                    services = resp.json()
                    # Calculate estimated cost based on plan
                    for srv in services:
                        plan = (
                            srv.get("service", {})
                            .get("serviceDetails", {})
                            .get("plan", "free")
                            .lower()
                        )
                        if plan == "starter":
                            render_spent += 7.0
                        elif plan == "standard":
                            render_spent += 25.0
                        elif plan == "pro":
                            render_spent += 85.0
                        elif plan == "pro_plus":
                            render_spent += 175.0
                        elif plan == "custom":
                            render_spent += 50.0

            providers["Render Cloud"] = {
                "spent": render_spent,
                "quota": render_quota,
                "color": "from-[#8a2be2] to-[#da70d6]",
            }
            spent += render_spent
        except Exception as render_err:
            logger.warning(f"Failed to fetch Render API usage: {render_err}")
            providers["Render Cloud"] = {
                "spent": 0.0,
                "quota": render_quota,
                "color": "from-[#8a2be2] to-[#da70d6]",
            }

        provider_costs_list = [
            {"name": name, "spent": p["spent"], "quota": p["quota"], "color": p["color"]}
            for name, p in providers.items()
        ]

        return {
            "status": "ok",
            "spent": spent,
            "limit": 150.00,
            "percentage": min((spent / 150.00) * 100, 100) if spent > 0 else 0,
            "providerCosts": provider_costs_list,
            "recentCharges": recent_charges[:10],  # limit to last 10
        }
    except Exception as e:
        logger.error(f"Failed to generate structured cost breakdown: {e}")
        return {
            "status": "error",
            "spent": 0.0,
            "limit": 150.00,
            "percentage": 0.0,
            "providerCosts": [],
            "recentCharges": [],
            "error": str(e),
        }


from .endpoints_deploy import trigger_deploy  # noqa: E402  (registers route + re-export)
from .endpoints_health import get_health_map  # noqa: E402  (registers route + re-export)
from .endpoints_metrics import (  # noqa: E402  (registers routes + re-export)
    get_metrics,
    get_providers,
)
from .endpoints_router_cfg import (  # noqa: E402  (registers routes + re-export)
    RouterOverrideRequest,
    get_model_router,
    set_router_override,
)
from .endpoints_users import (  # noqa: E402  (registers routes + re-export)
    create_user,
    delete_user,
    get_users,
    reset_tenant_usage_bridge,
)


@router.get("/codebase/export")
async def get_codebase_export():
    try:
        codebase_md = await export_codebase_to_markdown("..")
        return {"success": True, "markdown": codebase_md}
    except Exception as e:
        logger.error(f"Failed to export codebase: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {e!s}") from e


COST_CAPS_FILE = "data/cost_caps.json"


def load_cost_caps() -> dict[str, Any]:
    if not os.path.exists(COST_CAPS_FILE):
        os.makedirs(os.path.dirname(COST_CAPS_FILE), exist_ok=True)
        default = {"default_cap": 10.0, "per_tenant": {}}
        with open(COST_CAPS_FILE, "w") as f:
            json.dump(default, f, indent=4)
        return default
    with open(COST_CAPS_FILE) as f:
        return json.load(f)


def save_cost_caps(caps: dict[str, Any]):
    with open(COST_CAPS_FILE, "w") as f:
        json.dump(caps, f, indent=4)


@router.get("/cost-caps")
@router.get("/budget-caps")
def get_cost_caps():
    return load_cost_caps()


@router.post("/cost-caps")
@router.post("/budget-caps")
def update_cost_caps(payload: dict[str, Any]):
    caps = load_cost_caps()
    caps.update(payload)
    save_cost_caps(caps)
    return {"status": "success", "caps": caps}


from .endpoints_backups import (  # noqa: E402  (registers routes + re-export)
    create_backup,
    emergency_deploy,
    get_backups,
    restore_backup,
    trigger_backup,
)
from .endpoints_flags import (  # noqa: E402  (registers routes + re-export)
    create_feature_flag,
    get_feature_flags,
    update_feature_flag,
)
from .endpoints_impersonate import (  # noqa: E402  (registers routes + re-export)
    ImpersonateRequest,
    impersonate_by_payload,
    impersonate_user,
)


@router.get("/data-export")
def get_full_data_export():
    try:
        codebase_md = export_codebase_to_markdown("..")
        users = load_users()
        costs = CostAuditor().generate_report()
        return {
            "status": "success",
            "codebase": codebase_md,
            "users": users,
            "costs": costs,
        }
    except Exception as e:
        logger.error(f"Full data export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {e!s}") from e


from .endpoints_approvals_mcp import (  # noqa: E402  (registers routes + re-export)
    ApprovalActionPayload,
    get_commandcenter_approvals_mcp,
    resolve_commandcenter_approval_mcp,
)
from .endpoints_ci import (  # noqa: E402  (registers routes + re-export)
    get_ci_logs,
    receive_ci_report,
)
from .endpoints_command import (  # noqa: E402  (registers routes + re-export)
    AlertAcknowledgePayload,
    ApprovalDecisionPayload,
    DeployGateToggle,
    acknowledge_alert,
    decide_commandcenter_approval,
    get_admin_audit_logs,
    get_command_swarm,
    get_commandcenter_approvals,  # pending-task মালিক (M17 P-A: MCP-proxy এখন /approvals/mcp-এ)
    get_commandcenter_knowledge_stats,
    get_commandcenter_memory_stats,
    get_commandcenter_rate_limits,
    get_commandcenter_roi_dashboard,
    get_commandcenter_rules,
    get_commandcenter_skills,
    get_deploy_gate,
    list_command_agents,
    toggle_deploy_gate,
    update_commandcenter_rules,
)
from .endpoints_config import (  # noqa: E402  (registers routes + re-export)
    _acquire_env_lock,
    _release_env_lock,
    get_config,
    get_env_etag,
    update_config,
)
from .endpoints_crud import (  # noqa: E402  (registers routes + re-export)
    CUSTOMERS_FILE,
    SESSIONS_FILE,
    SETTINGS_FILE,
    WORKSPACES_FILE,
    _load_json_data,
    _save_json_data,
    create_workspace,
    delete_workspace,
    get_customers,
    get_permissions,
    get_roles,
    get_sessions,
    get_settings,
    get_workspaces,
    update_settings,
    update_workspace,
)
from .endpoints_events import get_events, list_reports  # noqa: E402  (registers routes + re-export)
from .endpoints_gate import (  # noqa: E402  (registers route + re-export)
    GateOverridePayload,
    execute_manual_gate_override,
)
from .endpoints_secrets_health import (  # noqa: E402  (registers routes + re-export)
    get_secrets_health,
)
from .endpoints_security import (  # noqa: E402  (registers routes + re-export)
    get_security_findings,
    run_security_scan,
)
from .endpoints_security_memory import (  # noqa: E402  (registers routes + re-export)
    get_security_memory,
    get_security_tasks,
)
from .endpoints_ws import admin_websocket  # noqa: E402  (registers route + re-export)
