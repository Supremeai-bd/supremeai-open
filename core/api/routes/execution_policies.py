import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_current_admin
from core.logging_config import logger
from database.session import get_db_session
from models.execution_policy import ExecutionPolicy

router = APIRouter(
    prefix="/api/admin/execution-policies",
    tags=["Execution Policies"],
    dependencies=[Depends(get_current_admin)],
)


class ExecutionPolicyUpdate(BaseModel):
    max_timeout_ms: int | None = Field(None, ge=1000, description="Max timeout in ms")
    max_compute_usd: float | None = Field(None, ge=0.0)
    max_retries: int | None = Field(None, ge=0)
    cb_failure_threshold: int | None = Field(None, ge=1)
    cooldown_window_sec: int | None = Field(None, ge=1)


@router.get("/")
async def get_policies(session: AsyncSession = Depends(get_db_session)):
    try:
        result = await session.execute(select(ExecutionPolicy))
        policies = result.scalars().all()

        formatted = []
        for pol in policies:
            formatted.append(
                {
                    "id": str(pol.id),
                    "scope": pol.scope.value,
                    "target_name": "*",
                    "max_timeout_ms": pol.max_timeout_seconds * 1000,
                    "max_compute_usd": float(pol.max_serverless_compute_budget_usd),
                    "max_retries": pol.max_retries,
                    "cb_failure_threshold": pol.circuit_breaker_failure_threshold,
                    "cooldown_window_sec": pol.circuit_breaker_cooldown_seconds,
                }
            )
        return {"items": formatted}
    except Exception as e:
        logger.exception(f"Failed to fetch execution policies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@router.put("/{policy_id}")
async def update_policy(
    policy_id: str,
    updates: ExecutionPolicyUpdate,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        pid = uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid policy UUID")

    try:
        result = await session.execute(select(ExecutionPolicy).where(ExecutionPolicy.id == pid))
        pol = result.scalars().first()
        if not pol:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

        # Update fields dynamically if they are provided
        if updates.max_timeout_ms is not None:
            pol.max_timeout_seconds = updates.max_timeout_ms // 1000
        if updates.max_compute_usd is not None:
            pol.max_serverless_compute_budget_usd = updates.max_compute_usd
        if updates.max_retries is not None:
            pol.max_retries = updates.max_retries
        if updates.cb_failure_threshold is not None:
            pol.circuit_breaker_failure_threshold = updates.cb_failure_threshold
        if updates.cooldown_window_sec is not None:
            pol.circuit_breaker_cooldown_seconds = updates.cooldown_window_sec

        await session.commit()

        return {
            "id": str(pol.id),
            "scope": pol.scope.value,
            "target_name": "*",
            "max_timeout_ms": pol.max_timeout_seconds * 1000,
            "max_compute_usd": float(pol.max_serverless_compute_budget_usd),
            "max_retries": pol.max_retries,
            "cb_failure_threshold": pol.circuit_breaker_failure_threshold,
            "cooldown_window_sec": pol.circuit_breaker_cooldown_seconds,
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.exception(f"Failed to update execution policy {policy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e
