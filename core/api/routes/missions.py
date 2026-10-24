"""Mission Orchestration API (Task 7-c) — /api/v1/missions.

Auth follows the exact sibling-router pattern (`api.dependencies.
get_current_user_token`); identity (owner/actor) is ALWAYS derived from the
authenticated principal, never from the request body. Sessions come from the
repo-standard `database.session.get_db_session` dependency and are committed
explicitly after writes (same pattern as selector_healing/billing routers).

Ownership: admins see every mission; any other principal only sees missions
they own. Cross-user access returns 404 (never 403) so mission existence is
not leaked.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_token
from core.logging_config import logger
from database.session import get_db_session, get_db_session_context
from missions.models import Mission, MissionTraceEvent
from missions.schemas import MissionCreate, MissionOut, TraceEventOut, TransitionRequest
from missions.service import MissionNotFound, MissionService
from missions.state_machine import STATES, IllegalTransition

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

#: Executor lane actually wired by this service (#1829): approved missions run
#: their goal through the production LLM gateway path (the same engine the
#: scheduled-tasks executor uses). The assigner label reflects that routing
#: decision instead of stamping a fake "auto-agent-v1" badge.
EXECUTOR_LANE_LABEL = "llm-gateway-direct"


def _llm_assigner(mission: Mission) -> str:  # noqa: ARG001 — hook signature keeps the seam
    """Real routing decision (#1829): this service executes goals through the
    LLM gateway executor, so the assigned-agent label names that lane."""
    return EXECUTOR_LANE_LABEL


async def _execute_mission_goal(mission_id: str) -> None:
    """Background executor (#1829): run the mission goal through the LLM
    gateway and advance its phases from the run's completion — approved
    missions no longer sit RUNNING until someone POSTs /advance manually.

    Uses its own session per step (never the request session) via
    ``get_db_session_context``; any execution error transitions the mission
    to FAILED with the reason recorded.
    """
    import asyncio

    from api.routes.scheduled_tasks import _execute_task_prompt

    try:
        async with get_db_session_context() as session:
            mission = await mission_service.get_mission(session, mission_id)
            goal_text = str(mission.goal_text or "")
            user_id = str(getattr(mission, "created_by", None) or "anonymous")
            phase_count = len(mission.phases or [])

        if not goal_text.strip():
            raise RuntimeError("mission has an empty goal_text — nothing to execute")

        await _execute_task_prompt(goal_text, user_id)

        # Completion callback: advance every phase (the last advance lands
        # the mission in SUCCEEDED via the state machine).
        for _ in range(max(1, phase_count)):
            async with get_db_session_context() as session:
                await mission_service.advance_phase(session, mission_id, actor="auto-executor")
        logger.info(f"✅ [missions] mission {mission_id} executed and completed autonomously")
    except Exception as exc:  # noqa: BLE001 — executor must translate errors to FAILED
        logger.error(f"❌ [missions] autonomous execution failed for {mission_id}: {exc}")
        try:
            async with get_db_session_context() as session:
                await mission_service.fail(
                    session, mission_id, reason=str(exc)[:500], actor="auto-executor"
                )
        except Exception as fail_exc:  # noqa: BLE001
            logger.error(
                f"❌ [missions] failed to record FAILED state for {mission_id}: {fail_exc}"
            )


def _spawn_autonomous_executor(mission_id: str) -> None:
    """Fire the background executor unless disabled (TESTING env or explicit off)."""
    if os.getenv("TESTING", "").lower() == "true":
        logger.debug(f"[missions] autonomous executor suppressed in TESTING for {mission_id}")
        return
    if os.getenv("MISSIONS_AUTONOMOUS_EXECUTION", "true").lower() == "false":
        return
    asyncio.create_task(_execute_mission_goal(mission_id))


#: Request-scoped service instance (assigner hook injectable for tests/ops).
mission_service = MissionService(assigner=_llm_assigner)

#: Roles allowed to read/operate on missions across all owners.
_ADMIN_ROLES = {"admin", "master_admin", "owner", "project_admin", "tenant_admin"}

#: SSE poll loop bounds (simple in-process polling; no pub/sub dependency).
_SSE_POLL_INTERVAL_S = 0.5
_SSE_MAX_ITERATIONS = 30


def _principal(user: dict) -> str:
    """Stable principal id from the authenticated token payload."""
    subject = str(user.get("sub") or user.get("user_id") or user.get("email") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Authenticated principal required"
        )
    return subject


def _is_admin(user: dict) -> bool:
    return str(user.get("role") or "").lower() in _ADMIN_ROLES


async def _owned_mission(session: AsyncSession, mission_id: str, user: dict) -> Any:
    """Load a mission the principal may access; 404 on missing OR foreign."""
    try:
        mid = uuid.UUID(mission_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found"
        ) from exc
    try:
        mission = await mission_service.get_mission(session, mid)
    except MissionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found"
        ) from exc
    if not _is_admin(user) and str(mission.owner_id) != _principal(user):
        # Do not leak existence of other users' missions.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")
    return mission


def _map_service_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, MissionNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")
    if isinstance(exc, IllegalTransition):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _finish(session: AsyncSession, mission: Any) -> MissionOut:
    """Serialize the mission FIRST, then commit.

    Serializing inside the endpoint's async context is what allows any
    server-generated attribute (e.g. ``updated_at`` via onupdate) to be
    lazily fetched through the greenlet; serializing after ``commit()`` would
    trigger that lazy fetch from pydantic outside the greenlet
    (MissingGreenlet).
    """
    out = MissionOut.model_validate(mission)
    return out


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
async def create_mission(
    payload: MissionCreate,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """Create a mission (state=planned) owned by the authenticated principal."""
    owner_id = _principal(user)
    try:
        mission = await mission_service.create_mission(
            session,
            owner_id=owner_id,
            title=payload.title,
            goal_text=payload.goal_text,
            strategy=payload.strategy,
            strategy_options=payload.strategy_options,
            phases=[p.model_dump() for p in payload.phases] if payload.phases else None,
            priority=payload.priority,
            agent_id=payload.agent_id,
        )
        out = _finish(session, mission)
        await session.commit()
    except (MissionNotFound, IllegalTransition, ValueError) as exc:
        raise _map_service_errors(exc) from exc
    return out


@router.get("", response_model=dict)
async def list_missions(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
    state: str | None = Query(default=None, description="Filter by mission state"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List missions (state filter + offset pagination); non-admins see only
    their own missions."""
    if state is not None and state not in STATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown mission state {state!r}; valid states: {sorted(STATES)}",
        )
    owner_id = None if _is_admin(user) else _principal(user)
    missions = await mission_service.list_missions(
        session, owner_id=owner_id, state=state, skip=skip, limit=limit
    )
    items = [MissionOut.model_validate(m) for m in missions]
    return {"items": items, "count": len(items), "skip": skip, "limit": limit}


@router.get("/{mission_id}", response_model=MissionOut)
async def get_mission(
    mission_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """Fetch one mission (404 for missing or foreign missions)."""
    mission = await _owned_mission(session, mission_id, user)
    return MissionOut.model_validate(mission)


async def _transition(
    session: AsyncSession,
    mission_id: str,
    user: dict,
    operation: str,
    payload: TransitionRequest | None = None,
):
    mission = await _owned_mission(session, mission_id, user)
    actor = _principal(user)
    reason = payload.reason if payload is not None else None
    try:
        if operation == "approve":
            return await mission_service.approve(session, mission.id, actor=actor)
        if operation == "start":
            started = await mission_service.start(session, mission.id, actor=actor)
            _spawn_autonomous_executor(str(mission.id))
            return started
        if operation == "advance":
            return await mission_service.advance_phase(session, mission.id, actor=actor)
        if operation == "fail":
            return await mission_service.fail(
                session, mission.id, reason or "unspecified failure", actor=actor
            )
        if operation == "repair":
            return await mission_service.request_repair(session, mission.id, actor=actor)
        if operation == "cancel":
            return await mission_service.cancel(session, mission.id, actor=actor, reason=reason)
    except (MissionNotFound, IllegalTransition, ValueError) as exc:
        raise _map_service_errors(exc) from exc
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)  # pragma: no cover


@router.post("/{mission_id}/approve", response_model=MissionOut)
async def approve_mission(
    mission_id: str,
    payload: TransitionRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """PLANNED → APPROVED → ASSIGNED (auto-assigns strategy + agent)."""
    mission = await _transition(session, mission_id, user, "approve", payload)
    out = _finish(session, mission)
    await session.commit()
    return out


@router.post("/{mission_id}/start", response_model=MissionOut)
async def start_mission(
    mission_id: str,
    payload: TransitionRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """ASSIGNED → RUNNING (Phase 01 in_progress); enqueues autonomous execution."""
    mission = await _transition(session, mission_id, user, "start", payload)
    out = _finish(session, mission)
    await session.commit()
    # #1829: approved+started missions execute autonomously — the background
    # executor owns its own sessions and advances phases on completion.
    _spawn_autonomous_executor(str(mission_id))
    return out


@router.post("/{mission_id}/advance", response_model=MissionOut)
async def advance_mission(
    mission_id: str,
    payload: TransitionRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """Complete current phase; starting the next, or SUCCEEDED on the last."""
    mission = await _transition(session, mission_id, user, "advance", payload)
    out = _finish(session, mission)
    await session.commit()
    return out


@router.post("/{mission_id}/fail", response_model=MissionOut)
async def fail_mission(
    mission_id: str,
    payload: TransitionRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """RUNNING → FAILED with a failure reason."""
    mission = await _transition(session, mission_id, user, "fail", payload)
    out = _finish(session, mission)
    await session.commit()
    return out


@router.post("/{mission_id}/repair", response_model=MissionOut)
async def repair_mission(
    mission_id: str,
    payload: TransitionRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """FAILED → REPAIRING → rotate strategy / reset phases → RUNNING (or
    terminal FAILED when no strategy options remain)."""
    mission = await _transition(session, mission_id, user, "repair", payload)
    out = _finish(session, mission)
    await session.commit()
    return out


@router.post("/{mission_id}/cancel", response_model=MissionOut)
async def cancel_mission(
    mission_id: str,
    payload: TransitionRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> MissionOut:
    """Cancel a planned/approved/assigned/running mission (terminal)."""
    mission = await _transition(session, mission_id, user, "cancel", payload)
    out = _finish(session, mission)
    await session.commit()
    return out


@router.get("/{mission_id}/trace", response_model=dict)
async def get_mission_trace(
    mission_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> dict:
    """The mission's trace events (audit trail), ordered by sequence number."""
    mission = await _owned_mission(session, mission_id, user)
    events = await mission_service.get_trace(session, mission.id)
    items = [TraceEventOut.model_validate(e) for e in events]
    return {"items": items, "count": len(items), "mission_id": str(mission.id)}


@router.get("/{mission_id}/trace/stream")
async def stream_mission_trace(
    mission_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(get_current_user_token),
) -> StreamingResponse:
    """SSE stream of the mission's trace events.

    Emits the existing events immediately, then polls for new ones
    (``asyncio.sleep(0.5)``, bounded at ~30 iterations) before closing with an
    ``end`` event. Ownership is enforced BEFORE the stream opens.
    """
    mission = await _owned_mission(session, mission_id, user)
    mission_id_uuid = mission.id
    # Release the DI session's read transaction before streaming: the SSE
    # poll loop opens its own short-lived sessions below.
    await session.rollback()

    async def event_stream() -> AsyncIterator[str]:
        last_seq = 0
        try:
            for _ in range(_SSE_MAX_ITERATIONS):
                async with get_db_session_context() as poll_session:
                    result = await poll_session.execute(
                        select(MissionTraceEvent)
                        .where(MissionTraceEvent.mission_id == mission_id_uuid)
                        .where(MissionTraceEvent.seq > last_seq)
                        .order_by(MissionTraceEvent.seq)
                    )
                    events = list(result.scalars().all())
                for evt in events:
                    last_seq = int(evt.seq)
                    data = TraceEventOut.model_validate(evt).model_dump(mode="json")
                    yield f"event: mission_trace\ndata: {json.dumps(data, default=str)}\n\n"
                await asyncio.sleep(_SSE_POLL_INTERVAL_S)
            yield "event: end\ndata: {}\n\n"
        except asyncio.CancelledError:  # client disconnected — normal close
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
