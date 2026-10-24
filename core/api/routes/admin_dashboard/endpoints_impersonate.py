"""Impersonation endpoints
(POST /admin-api/users/impersonate/{username}, POST /admin-api/impersonate)."""

import jwt
from fastapi import Depends, HTTPException

from api.routes.admin_auth import require_admin_token
from api.routes.admin_dashboard import load_users, router
from api.routes.admin_dashboard._models import ImpersonateRequest
from core.config import settings


@router.post("/users/impersonate/{username}")
async def impersonate_user(username: str, current_admin: dict = Depends(require_admin_token)):
    users = load_users()
    target = next((u for u in users if u["username"] == username), None)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    impersonation_token = jwt.encode(
        {
            "uid": target["username"],
            "role": target["role"],
            "impersonator": current_admin.get("uid", "admin"),
            "impersonation": True,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {
        "status": "success",
        "impersonation_token": impersonation_token,
        "user": target,
    }


@router.post("/impersonate")
async def impersonate_by_payload(
    payload: ImpersonateRequest, current_admin: dict = Depends(require_admin_token)
):
    """Impersonate user via JSON payload for CommandCenter."""
    users = load_users()
    target = next(
        (
            u
            for u in users
            if u["username"] == payload.user_id or str(u.get("id")) == payload.user_id
        ),
        None,
    )
    target_username = target["username"] if target else payload.user_id
    target_role = target.get("role", "user") if target else "user"
    token = jwt.encode(
        {
            "uid": target_username,
            "role": target_role,
            "impersonator": current_admin.get("uid", "admin"),
            "impersonation": True,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"token": token, "user": target}
