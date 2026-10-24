"""Task listing + effective-policy endpoints (Neon-backed).

Split out of the former single-module api/routes/browser.py verbatim.
"""

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_tenant, get_current_user_token
from api.routes.admin_dashboard import require_admin_token
from api.routes.browser import router
from core.effective_policy import get_effective_policy, policy_store
from core.neon_repository import (
    list_tasks as list_neon_tasks,
)
from core.neon_repository import (
    load_policy as load_neon_policy,
)
from core.neon_repository import (
    save_policy as save_neon_policy,
)


@router.get("/tasks")
async def get_tasks(
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    owner_id = str(user.get("sub") or "")
    return {"tasks": await list_neon_tasks(tenant_id, owner_id)}


class PolicyUpdateRequest(BaseModel):
    rules: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)
    actions: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, int] = Field(default_factory=dict)


class UserPolicyUpdateRequest(BaseModel):
    rules: dict[str, Any] = Field(default_factory=dict)


@router.get("/policy")
async def get_policy(
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    user_id = str(user.get("sub") or "")
    policy = get_effective_policy(user_id)
    admin_row = await load_neon_policy(tenant_id)
    user_row = await load_neon_policy(tenant_id, user_id)
    if admin_row:
        policy_store.update_admin(
            admin_row["rules"], admin_row["features"], admin_row["actions"], admin_row["limits"]
        )
        policy = get_effective_policy(user_id)
    if user_row:
        policy_store.update_user(user_id, user_row["rules"])
        policy = get_effective_policy(user_id)
    return {
        "rules": policy.rules,
        "features": policy.features,
        "actions": policy.actions,
        "limits": policy.limits,
        "sources": policy.sources,
        "version": policy.version,
    }


@router.put("/policy")
async def update_user_policy(
    payload: UserPolicyUpdateRequest,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    user_id = str(user.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user required")
    policy = policy_store.update_user(user_id, payload.rules)
    await save_neon_policy(tenant_id, user_id, user_id=user_id, rules=payload.rules)
    return {
        "rules": policy.rules,
        "features": policy.features,
        "actions": policy.actions,
        "limits": policy.limits,
        "sources": policy.sources,
    }


@router.put("/admin/policy", dependencies=[Depends(require_admin_token)])
async def update_admin_policy(
    payload: PolicyUpdateRequest,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    updated_by = str(user.get("sub") or "admin")
    policy = policy_store.update_admin(
        payload.rules, payload.features, payload.actions, payload.limits
    )
    await save_neon_policy(
        tenant_id,
        updated_by,
        rules=payload.rules,
        features=payload.features,
        actions=payload.actions,
        limits=payload.limits,
    )
    return {
        "rules": policy.rules,
        "features": policy.features,
        "actions": policy.actions,
        "limits": policy.limits,
        "sources": policy.sources,
    }
