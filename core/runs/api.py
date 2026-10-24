"""Canonical Run API (M1-C) — /api/v1/runs.

The **async boundary**: long operations receive an immediate ``run_id`` ack
(``RunAck`` with a poll path) and progress is observed on the run — the
queue choice is deliberately NOT baked in (roadmap M1: contract only).

Auth follows the exact sibling-router pattern (``api.dependencies.
get_current_user_token``; identity derived from the authenticated principal,
never the body). Ownership: admins see every run; other principals only
their own; foreign runs 404 (no existence leak) — same policy as missions.

Sessions come from ``database.session.get_db_session`` and are committed
explicitly after writes (repo pattern).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_token
from database.session import get_db_session
from runs.models import Run, RunEvent
from runs.schemas import (
    RunAck,
    RunCancelRequest,
    RunClassifyRequest,
    RunCreate,
    RunEventOut,
    RunOut,
    RunRetryRequest,
    RunTransitionRequest,
    RunUsageRequest,
)
from runs.service import RunNotFound, RunService
from runs.state_machine import IllegalTransition

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

#: Request-scoped service instance (approval hook injectable for tests/ops).
run_service = RunService()

#: Roles allowed to read/operate on runs across all owners (missions parity).
_ADMIN_ROLES = {"admin", "master_admin", "owner", "project_admin", "tenant_admin"}


def _principal(user: dict) -> str:
    subject = str(user.get("sub") or user.get("user_id") or user.get("email") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Authenticated principal required"
        )
    return subject


def _is_admin(user: dict) -> bool:
    return str(user.get("role") or "").lower() in _ADMIN_ROLES


def _conflict(exc: IllegalTransition) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


async def _owned_run(session: AsyncSession, run_id: str, user: dict) -> Any:
    """Load a run the principal may access; 404 on missing OR foreign."""
    try:
        rid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    try:
        run = await run_service.get_run(session, rid)
    except RunNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    if not _is_admin(user) and run.user_id != _principal(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("", response_model=RunAck, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreate,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> RunAck:
    """Create a run — returns the ``run_id`` ack immediately (async boundary).

    Identity (``user_id``) is always the authenticated principal. If the
    caller supplies an ``idempotency_key`` that already exists, the existing
    run's ack is returned (200 semantics via 201-with-same-id).
    """
    principal = _principal(user)
    try:
        run = await run_service.create_run(
            session,
            run_type=payload.run_type,
            user_id=principal,
            title=payload.title,
            workspace_id=payload.workspace_id,
            chat_id=payload.chat_id,
            mission_id=payload.mission_id,
            parent_run_id=payload.parent_run_id,
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            idempotency_key=payload.idempotency_key,
            trace_id=payload.trace_id,
            correlation_id=payload.correlation_id,
            max_wall_clock_ms=payload.max_wall_clock_ms,
            max_tokens=payload.max_tokens,
            max_tool_calls=payload.max_tool_calls,
            max_retries=payload.max_retries,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return RunAck(run_id=run.id, status=run.status, poll=f"/api/v1/runs/{run.id}")


@router.get("", response_model=list[RunOut])
async def list_runs(
    status_filter: str | None = Query(None, alias="status"),
    run_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> list[RunOut]:
    """List runs. Non-admin principals see only their own (404-policy parity)."""
    query = select(Run).order_by(Run.created_at.desc()).limit(limit)
    if not _is_admin(user):
        query = query.where(Run.user_id == _principal(user))
    if status_filter:
        query = query.where(Run.status == status_filter)
    if run_type:
        query = query.where(Run.run_type == run_type)
    rows = (await session.execute(query)).scalars().all()
    return [RunOut.model_validate(r) for r in rows]


@router.get("/{run_id}", response_model=RunOut)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> RunOut:
    """Observe one run (the poll target of the async-boundary ack)."""
    run = await _owned_run(session, run_id, user)
    return RunOut.model_validate(run)


@router.get("/{run_id}/events", response_model=list[RunEventOut])
async def list_run_events(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> list[RunEventOut]:
    """The run's ordered audit event stream."""
    run = await _owned_run(session, run_id, user)
    rows = (
        (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq)
            )
        )
        .scalars()
        .all()
    )
    return [RunEventOut.model_validate(e) for e in rows]


@router.post("/{run_id}/transition", response_model=RunOut)
async def transition_run(
    run_id: str,
    payload: RunTransitionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> RunOut:
    """Move the run to a legal next state (409 on illegal transitions)."""
    run = await _owned_run(session, run_id, user)
    try:
        updated = await run_service.transition(
            session,
            run.id,
            payload.to,
            actor=payload.actor or _principal(user),
            detail=payload.detail,
        )
    except IllegalTransition as exc:
        raise _conflict(exc) from exc
    await session.commit()
    return RunOut.model_validate(updated)


@router.post("/{run_id}/usage", response_model=RunOut)
async def record_usage(
    run_id: str,
    payload: RunUsageRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> RunOut:
    """Report consumption; admission control refuses budget overspend."""
    run = await _owned_run(session, run_id, user)
    await run_service.record_usage(
        session,
        run.id,
        tokens=payload.tokens,
        tool_calls=payload.tool_calls,
        actor=payload.actor or _principal(user),
    )
    await session.commit()
    await session.refresh(run)
    return RunOut.model_validate(run)


@router.post("/{run_id}/classify", response_model=RunOut)
async def classify_failure(
    run_id: str,
    payload: RunClassifyRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> RunOut:
    """Record the 8-class failure classification + error surface."""
    run = await _owned_run(session, run_id, user)
    try:
        updated = await run_service.classify_failure(
            session,
            run.id,
            payload.retry_class,
            error=payload.error,
            actor=payload.actor or _principal(user),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return RunOut.model_validate(updated)


@router.post("/{run_id}/retry", response_model=RunOut)
async def request_retry(
    run_id: str,
    payload: RunRetryRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> RunOut:
    """Schedule a retry (RUNNING -> RETRYING) under budget + guard."""
    run = await _owned_run(session, run_id, user)
    try:
        updated = await run_service.request_retry(
            session,
            run.id,
            retry_class=payload.retry_class,
            actor=payload.actor or _principal(user),
        )
    except IllegalTransition as exc:
        raise _conflict(exc) from exc
    await session.commit()
    return RunOut.model_validate(updated)


@router.post("/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: str,
    payload: RunCancelRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> RunOut:
    """Cancel a run from any cancellable state (idempotent if terminal)."""
    run = await _owned_run(session, run_id, user)
    updated = await run_service.cancel(
        session, run.id, actor=payload.actor or _principal(user), reason=payload.reason
    )
    await session.commit()
    return RunOut.model_validate(updated)
