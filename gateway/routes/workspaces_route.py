"""SupremeAI 2.0 - Workspaces & Multi-Platform Admin API Routes.

Provides REST endpoints for Admin Command Center to dynamically register, list, and bind
target repositories and cloud platforms across 100+ connected endpoints.

Endpoints:
- `POST /admin-api/workspaces/bind-target`: Bind a target repo with permission scope (READ_ONLY/FULL_CONTROL).
- `GET /admin-api/workspaces/targets`: List all registered target entities and their live scopes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from api.dependencies import get_project_admin
from core.logging_config import logger
from core.repo_manager import repo_manager
from core.target_registry import (
    PermissionScope,
    TargetEntity,
    TargetPlatformType,
    target_registry,
)
from tools.social.telegram_security import check_totp_code

router = APIRouter(
    prefix="/admin-api/workspaces",
    tags=["Admin Workspaces"],
    dependencies=[Depends(get_project_admin)],
)


class BindTargetRequest(BaseModel):
    """রেপো বা প্ল্যাটফর্ম বাইন্ডিং রিকোয়েস্ট স্কিমা।"""

    target_id: str = Field(..., description="Unique target identifier (e.g. secondary-agent-repo)")
    name: str = Field(..., description="Human readable target name")
    target_type: TargetPlatformType = Field(default=TargetPlatformType.GIT_REPOSITORY)
    url: str = Field(..., description="Git repository URL or Cloud endpoint")
    branch: str = Field(default="main", description="Git branch name")
    scope: PermissionScope = Field(
        default=PermissionScope.FULL_CONTROL,
        description="Permission scope (READ_ONLY / FULL_CONTROL)",
    )
    credentials_token: str = Field(
        default="",
        description="Deprecated: use a managed secret reference in metadata instead",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class TargetResponse(BaseModel):
    """টার্গেট রেসপন্স স্কিমা।"""

    id: str
    name: str
    target_type: str
    url: str
    branch: str
    scope: str
    is_read_only: bool
    can_write: bool


@router.post("/bind-target", response_model=TargetResponse, status_code=status.HTTP_201_CREATED)
async def bind_target_repository(
    req: BindTargetRequest,
    x_jit_otp: str | None = Header(None, alias="X-JIT-OTP"),
    user: dict = Depends(get_project_admin),
) -> TargetResponse:
    """ডাইনামিক্যালি নতুন একটি টার্গেট রেপো বা প্ল্যাটফর্ম বাইন্ড ও রেজিস্টার করে।"""
    # Guard: FastAPI DI ছাড়া (যেমন unit test) user ও x_jit_otp রেজলভড নাও হতে পারে
    user = user if isinstance(user, dict) else {"tenant_id": "test-tenant"}
    otp_value = x_jit_otp if isinstance(x_jit_otp, str) else None
    if not otp_value or not check_totp_code(otp_value):
        logger.warning("Rejected workspace bind without valid JIT OTP")
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Valid JIT OTP required")
    if req.credentials_token:
        logger.warning("Rejected direct credentials_token for target %s", req.target_id)
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="Direct credentials are not accepted; use a managed secret reference",
        )

    logger.info("Binding target '%s' with scope '%s'", req.target_id, req.scope)

    target = TargetEntity(
        id=req.target_id,
        name=req.name,
        target_type=req.target_type,
        url=req.url,
        branch=req.branch,
        scope=req.scope,
        credentials_token=req.credentials_token,
        metadata=req.metadata,
        tenant_id=user["tenant_id"],
    )

    registered = target_registry.register_target(target)

    # Prepare workspace folder on disk
    try:
        repo_manager.prepare_workspace(registered)
    except Exception as e:
        logger.warning(f"Workspace preparation deferred for target '{registered.id}': {e}")

    return TargetResponse(
        id=registered.id,
        name=registered.name,
        target_type=registered.target_type.value,
        url=registered.url,
        branch=registered.branch,
        scope=registered.scope.value,
        is_read_only=registered.is_read_only(),
        can_write=registered.can_write(),
    )


@router.get("/targets", response_model=list[TargetResponse])
async def list_target_repositories(user: dict = Depends(get_project_admin)) -> list[TargetResponse]:
    """রেজিস্টার্ড সমস্ত ১০০+ টার্গেট রেপো ও প্ল্যাটফর্মের তালিকা রিটার্ন করে।"""
    # Guard: FastAPI DI ছাড়া (যেমন unit test) user রেজলভড নাও হতে পারে
    user = user if isinstance(user, dict) else {"tenant_id": "test-tenant"}
    targets = target_registry.list_targets(user["tenant_id"])
    return [
        TargetResponse(
            id=t.id,
            name=t.name,
            target_type=t.target_type.value,
            url=t.url,
            branch=t.branch,
            scope=t.scope.value,
            is_read_only=t.is_read_only(),
            can_write=t.can_write(),
        )
        for t in targets
    ]
