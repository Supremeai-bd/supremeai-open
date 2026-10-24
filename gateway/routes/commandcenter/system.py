from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin

# #1656: typed payloads replacing bare dict — schema corruption prevention.
# Rejects unknown fields (Pydantic default) + validates value constraints.


class ConfigUpdatePayload(BaseModel):
    """Payload for POST /system/config."""

    model_config = {"extra": "forbid"}  # #1656: reject unknown fields

    key: str = Field(..., min_length=1, max_length=255, description="Config key to update")
    value: str | int | float | bool | list | dict = Field(..., description="Config value")


class FlagsUpdatePayload(BaseModel):
    """Payload for POST /system/flags."""

    model_config = {"extra": "forbid"}

    flag: str = Field(..., min_length=1, max_length=100, description="Feature flag name")
    enabled: bool = Field(
        ..., strict=True, description="Flag state — strict bool (no string coercion)"
    )


class DeployGateTogglePayload(BaseModel):
    """Payload for POST /system/deploy-gate."""

    model_config = {"extra": "forbid"}

    locked: bool = Field(..., description="Whether the deploy gate is locked")
    reason: str | None = Field(default=None, max_length=500, description="Optional lock reason")


router = APIRouter(
    prefix="",
    tags=["Command Center"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/system/config")
# Issue #1665: these handlers return static/aggregated data with no
# await — plain `def` routes (FastAPI runs them in the threadpool)
# instead of `async def` coroutines that never await. HTTP contract
# unchanged; only the event-loop scheduling semantics are corrected.

def get_config():
    return []


@router.post("/system/config")
def update_config(payload: ConfigUpdatePayload):
    return {"message": "updated"}


@router.get("/system/flags")
def get_flags():
    return []


@router.post("/system/flags")
def update_flags(payload: FlagsUpdatePayload):
    return {"message": "updated"}


@router.get("/system/workspaces")
def get_workspaces():
    return []


@router.get("/system/backups")
def get_backups():
    return []


@router.post("/system/backups")
def create_backup():
    return {"message": "backup created"}


@router.post("/system/backups/{backup_id}/restore")
def restore_backup(backup_id: str):
    return {"message": "restore initiated"}


@router.get("/system/deploy-gate")
def get_deploy_gate():
    return {"status": "UNLOCKED"}


@router.post("/system/deploy-gate")
def toggle_deploy_gate(payload: DeployGateTogglePayload):
    return {"message": "updated"}
