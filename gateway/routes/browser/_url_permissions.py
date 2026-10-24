"""URL permission allow/deny list + permission-request decision endpoints.

Split out of the former single-module api/routes/browser.py verbatim.
``URL_PERMISSIONS`` lives in THIS module (not _state.py) because
``delete_url`` rebinds it via ``global``.
"""

import uuid
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from api.routes.admin_dashboard import require_admin_token
from api.routes.browser import router

URL_PERMISSIONS: list[dict[str, Any]] = []
PERMISSION_REQUESTS: list[dict[str, Any]] = []


class UrlPermissionRequest(BaseModel):
    urlPattern: str
    userId: str | None = "default"
    reason: str | None = "None"


class DecisionRequest(BaseModel):
    approved: bool


@router.get("/urls/allowed")
def get_allowed_urls(userId: str = "default"):
    allowed = [
        u for u in URL_PERMISSIONS if u.get("type") == "allowed" and u.get("userId") == userId
    ]
    return {"urls": allowed}


@router.get("/urls/denied")
def get_denied_urls(userId: str = "default"):
    denied = [u for u in URL_PERMISSIONS if u.get("type") == "denied" and u.get("userId") == userId]
    return {"urls": denied}


@router.post("/urls/allowed", dependencies=[Depends(require_admin_token)])
def add_allowed_url(req: UrlPermissionRequest):
    perm = req.model_dump()
    perm["id"] = f"perm_{uuid.uuid4().hex[:12]}"
    perm["type"] = "allowed"
    URL_PERMISSIONS.append(perm)
    return perm


@router.post("/urls/denied", dependencies=[Depends(require_admin_token)])
def add_denied_url(req: UrlPermissionRequest):
    perm = req.model_dump()
    perm["id"] = f"perm_{uuid.uuid4().hex[:12]}"
    perm["type"] = "denied"
    URL_PERMISSIONS.append(perm)
    return perm


@router.post("/urls/allowAll", dependencies=[Depends(require_admin_token)])
def allow_all_urls(userId: str = "default"):
    perm = {
        "id": f"perm_{uuid.uuid4().hex[:12]}",
        "urlPattern": "*",
        "userId": userId,
        "type": "allowAll",
        "reason": "Allow all URLs",
    }
    URL_PERMISSIONS.append(perm)
    return perm


@router.delete("/urls/{id}", dependencies=[Depends(require_admin_token)])
def delete_url(url_id: str):
    global URL_PERMISSIONS
    URL_PERMISSIONS = [u for u in URL_PERMISSIONS if u.get("id") != url_id]
    return {"success": True}


@router.get("/urls/requests")
def get_requests():
    return {"requests": PERMISSION_REQUESTS}


@router.post("/urls/requests/{id}/decision", dependencies=[Depends(require_admin_token)])
def decision(request_id: str, req: DecisionRequest):
    """AUD-2.6/AUD-3.5: URL permission decisions grant browser access scope and
    therefore require an admin token (previously any authenticated user could
    self-approve URL permissions)."""
    for r in PERMISSION_REQUESTS:
        if r["id"] == request_id:
            r["status"] = "APPROVED" if req.approved else "DENIED"
            return {"success": True}
    raise HTTPException(status_code=404, detail="Request not found")
