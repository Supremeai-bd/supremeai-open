"""Phase-1 admin CRUD endpoints
(roles, permissions, workspaces, settings, sessions, customers) + shared
JSON-file load/save helpers."""

import json
import os
import secrets
from typing import Any

from fastapi import HTTPException

from api.routes.admin_dashboard import router
from core.errors.error_bus import with_error_bus
from core.logging_config import logger

# ── Additional Admin CRUD Endpoints (Phase 1) ────────────────────────────────

WORKSPACES_FILE = "data/workspaces.json"
SETTINGS_FILE = "data/settings.json"
SESSIONS_FILE = "data/sessions.json"
CUSTOMERS_FILE = "data/customers.json"


@with_error_bus("_load_json_data")
def _load_json_data(file_path: str, default_data: Any) -> Any:
    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4)
        return default_data
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(
            f"[admin_dashboard] Failed to load JSON data from {file_path}, returning default: {exc}",
            exc_info=True,
        )
        return default_data


def _save_json_data(file_path: str, data: Any):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


@router.get("/roles")
def get_roles():
    return [
        {"id": "1", "name": "God"},
        {"id": "2", "name": "Operator"},
        {"id": "3", "name": "Viewer"},
    ]


@router.get("/permissions")
def get_permissions():
    return [{"id": "1", "name": "all"}, {"id": "2", "name": "read"}, {"id": "3", "name": "write"}]


@router.get("/workspaces")
def get_workspaces():
    return _load_json_data(
        WORKSPACES_FILE,
        [{"id": "ws_1", "name": "Default Workspace", "description": "System default workspace"}],
    )


@router.post("/workspaces")
def create_workspace(workspace: dict):
    workspaces = _load_json_data(WORKSPACES_FILE, [])
    if "id" not in workspace or not workspace["id"]:
        workspace["id"] = f"ws_{secrets.token_hex(4)}"
    workspaces.append(workspace)
    _save_json_data(WORKSPACES_FILE, workspaces)
    return workspace


@router.put("/workspaces/{ws_id}")
def update_workspace(ws_id: str, payload: dict):
    workspaces = _load_json_data(WORKSPACES_FILE, [])
    for ws in workspaces:
        if ws["id"] == ws_id:
            ws.update(payload)
            _save_json_data(WORKSPACES_FILE, workspaces)
            return ws
    raise HTTPException(status_code=404, detail="Workspace not found")


@router.delete("/workspaces/{ws_id}")
def delete_workspace(ws_id: str):
    workspaces = _load_json_data(WORKSPACES_FILE, [])
    new_workspaces = [ws for ws in workspaces if ws["id"] != ws_id]
    if len(new_workspaces) == len(workspaces):
        raise HTTPException(status_code=404, detail="Workspace not found")
    _save_json_data(WORKSPACES_FILE, new_workspaces)
    return {"status": "success", "message": "Workspace deleted"}


@router.get("/settings")
def get_settings():
    return _load_json_data(
        SETTINGS_FILE, {"theme": "dark", "notifications_enabled": True, "max_concurrent_tasks": 5}
    )


@router.post("/settings")
def update_settings(payload: dict):
    settings_data = _load_json_data(SETTINGS_FILE, {})
    settings_data.update(payload)
    _save_json_data(SETTINGS_FILE, settings_data)
    return settings_data


@router.get("/sessions")
def get_sessions():
    return _load_json_data(
        SESSIONS_FILE, [{"id": "sess_1", "name": "Initial Boot Session", "status": "active"}]
    )


@router.get("/customers")
def get_customers():
    return _load_json_data(
        CUSTOMERS_FILE,
        [{"id": "cust_1", "name": "Acme Corp", "email": "admin@acme.com", "billing_tier": "pro"}],
    )
