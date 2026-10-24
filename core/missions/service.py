"""Mission orchestration service (Task 7-c).

Every public method takes an ``AsyncSession`` (the repo-standard SQLAlchemy
session — routes pass ``Depends(get_db_session)`` from
``database/session.py``) and performs its mission + trace writes on that ONE
session so a state change and its audit event commit atomically.

Agent assignment is an injectable hook: ``MissionService(assigner=...)``
where ``assigner: Callable[[Mission], str]``. The default stub performs NO
LLM call — it labels the mission ``auto-agent-v1`` (and the strategy-rotation
logic picks the next ``strategy_options`` entry itself), matching the plan's
"Autonomous Fulfillment" flow without coupling the core to any provider.

Every state change:
1. mutates the mission row,
2. appends a ``MissionTraceEvent`` (seq = max(seq)+1 per mission, explicit
   flush so it is correct even on ``autoflush=False`` sessions),
3. emits one structured log line carrying ``mission_id``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import logger
from missions.models import Mission, MissionTraceEvent
from missions.state_machine import (
    APPROVED,
    ASSIGNED,
    CANCELLED,
    FAILED,
    PLANNED,
    REPAIRING,
    RUNNING,
    SUCCEEDED,
    IllegalTransition,
    assert_transition,
    requires_phase_reset,
)

#: Label stamped on missions by the default (no-LLM) assigner stub.
DEFAULT_AGENT_LABEL = "auto-agent-v1"

PHASE_PENDING = "pending"
PHASE_IN_PROGRESS = "in_progress"
PHASE_COMPLETED = "completed"


def _default_assigner(mission: Mission) -> str:  # noqa: ARG001 — hook signature
    """Default no-LLM assigner: always labels the mission auto-agent-v1."""
    return DEFAULT_AGENT_LABEL


class MissionNotFound(LookupError):
    """Raised when a mission id does not exist (routes map this to 404)."""


class MissionService:
    """Mission lifecycle service — all DB access via the injected AsyncSession."""

    def __init__(self, assigner: Callable[[Mission], str] | None = None) -> None:
        self._assigner = assigner or _default_assigner

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _trace(
        self,
        session: AsyncSession,
        mission: Mission,
        event: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Append a trace event (seq = max+1) on the SAME session/transaction."""
        last_seq = await session.scalar(
            select(func.max(MissionTraceEvent.seq)).where(
                MissionTraceEvent.mission_id == mission.id
            )
        )
        evt = MissionTraceEvent(
            mission_id=mission.id,
            seq=(last_seq or 0) + 1,
            phase=mission.current_phase,
            event=event,
            detail=detail,
        )
        session.add(evt)
        # Explicit flush: sessions built by database.session use autoflush=False,
        # so the next max(seq) query must be able to see this row.
        await session.flush()
        logger.info(
            f"[MissionOrchestrator] event={event} mission_id={mission.id} "
            f"seq={evt.seq} phase={evt.phase} state={mission.state} "
            f"detail={detail or {}}"
        )

    async def get_mission(self, session: AsyncSession, mission_id: Any) -> Mission:
        """Fetch a mission by id (UUID or UUID-string); raise MissionNotFound."""
        mid = mission_id
        if isinstance(mid, str):
            try:
                mid = uuid.UUID(mid)
            except ValueError as exc:
                raise MissionNotFound(f"mission {mission_id!r} not found") from exc
        mission = await session.get(Mission, mid)
        if mission is None:
            raise MissionNotFound(f"mission {mission_id!r} not found")
        return mission

    @staticmethod
    def _set_phases(mission: Mission, phases: list[dict[str, Any]]) -> None:
        """Reassign the phases JSON (reassignment, not in-place mutation, so
        SQLAlchemy always sees the change on any session configuration)."""
        mission.phases = phases

    @staticmethod
    def _normalize_phases(
        phases: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Normalize user-supplied phases to [{name, status, note}] (pending)."""
        if not phases:
            return [{"name": "execute", "status": PHASE_PENDING, "note": ""}]
        return [
            {
                "name": str(p.get("name") or "phase"),
                "status": PHASE_PENDING,
                "note": str(p.get("note") or ""),
            }
            for p in phases
        ]

    @staticmethod
    def _choose_strategy(mission: Mission) -> str | None:
        """Autonomous Fulfillment: pick the first candidate strategy option,
        falling back to an explicitly-set strategy."""
        options = mission.strategy_options or []
        if options:
            return str(options[0])
        return mission.strategy or None

    def _assign_agent(self, mission: Mission) -> str:
        """Run the (injectable) assigner hook; never calls any LLM by default."""
        return self._assigner(mission) or DEFAULT_AGENT_LABEL

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------
    async def create_mission(
        self,
        session: AsyncSession,
        *,
        owner_id: str,
        title: str,
        goal_text: str,
        strategy: str | None = None,
        strategy_options: list[str] | None = None,
        phases: list[dict[str, Any]] | None = None,
        priority: int = 5,
        agent_id: str | None = None,
    ) -> Mission:
        """Create a mission in the PLANNED state (the plan's "Requirement")."""
        if not owner_id:
            raise ValueError("owner_id (the authenticated principal) is required")
        options = [str(o).strip() for o in (strategy_options or []) if str(o).strip()]
        mission = Mission(
            title=title,
            goal_text=goal_text,
            strategy=strategy,
            strategy_options=options,
            phases=self._normalize_phases(phases),
            current_phase=0,
            state=PLANNED,
            priority=priority,
            owner_id=owner_id,
            agent_id=agent_id,
        )
        session.add(mission)
        await session.flush()
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={"from": None, "to": PLANNED, "actor": owner_id},
        )
        return mission

    async def approve(
        self, session: AsyncSession, mission_id: Any, *, actor: str | None = None
    ) -> Mission:
        """PLANNED → APPROVED, then Autonomous Fulfillment auto-assigns the
        strategy + agent and completes APPROVED → ASSIGNED (single call)."""
        mission = await self.get_mission(session, mission_id)
        assert_transition(mission.state, APPROVED)
        previous = mission.state
        mission.state = APPROVED
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={"from": previous, "to": APPROVED, "actor": actor},
        )

        # Autonomous Fulfillment: choose a strategy, then an agent.
        chosen = mission.strategy or self._choose_strategy(mission)
        if chosen is None:
            raise IllegalTransition(
                f"mission {mission.id} cannot be assigned: no strategy and no "
                "strategy_options to choose from"
            )
        mission.strategy = chosen
        mission.agent_id = self._assign_agent(mission)
        await self._trace(
            session,
            mission,
            "agent_assigned",
            detail={
                "agent_id": mission.agent_id,
                "strategy": mission.strategy,
                "actor": actor,
            },
        )

        # The strategy guard: only APPROVED→ASSIGNED when a strategy is chosen.
        assert_transition(mission.state, ASSIGNED, strategy_chosen=bool(mission.strategy))
        previous = mission.state
        mission.state = ASSIGNED
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={"from": previous, "to": ASSIGNED, "actor": actor},
        )
        return mission

    async def start(
        self, session: AsyncSession, mission_id: Any, *, actor: str | None = None
    ) -> Mission:
        """ASSIGNED → RUNNING; marks Phase 01 in_progress."""
        mission = await self.get_mission(session, mission_id)
        assert_transition(mission.state, RUNNING)
        previous = mission.state
        mission.state = RUNNING
        mission.current_phase = 0
        if mission.phases:
            phases = [dict(p) for p in mission.phases]
            phases[0]["status"] = PHASE_IN_PROGRESS
            self._set_phases(mission, phases)
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={"from": previous, "to": RUNNING, "actor": actor},
        )
        if mission.phases:
            await self._trace(
                session,
                mission,
                "phase_started",
                detail={"phase": 0, "name": mission.phases[0].get("name"), "actor": actor},
            )
        return mission

    async def advance_phase(
        self, session: AsyncSession, mission_id: Any, *, actor: str | None = None
    ) -> Mission:
        """Complete the current phase and start the next one; completing the
        last phase transitions the mission to SUCCEEDED.

        বাংলা (M06 P-A ৮/৮ RunType adoption): প্রতিটি mission-advance ক্যানোনিকাল
        ``run_type="mission"`` রান হিসেবেও পর্যবেক্ষিত — নিজস্ব session-এ
        (আয়োজক mission-ট্রানজেকশন স্পর্শ নয়), flag-gated, best-effort।
        IllegalTransition-সহ ব্যর্থতা রান-কে FAILED settle করেই ছড়ায়।
        """
        from runs.run_scope import observe_run

        async with observe_run(
            run_type="mission",
            user_id=actor or "system",
            title=f"mission:{mission_id}:advance",
            source_type="mission",
            source_ref=str(mission_id),
        ) as run_ctx:
            mission = await self._advance_phase_impl(session, mission_id, actor=actor)
            if run_ctx is not None:
                run_ctx.finish("succeeded")
            return mission

    async def _advance_phase_impl(
        self, session: AsyncSession, mission_id: Any, *, actor: str | None = None
    ) -> Mission:
        """Original advance_phase body — run-observation wrapper-এর ভিতরে চলে।"""
        mission = await self.get_mission(session, mission_id)
        if mission.state != RUNNING:
            raise IllegalTransition(
                f"advance_phase requires state {RUNNING!r} (got {mission.state!r})"
            )

        current_idx = mission.current_phase
        phases = [dict(p) for p in mission.phases]
        if current_idx >= len(phases):
            raise IllegalTransition(f"phase index {current_idx} out of range")

        phases[current_idx]["status"] = PHASE_COMPLETED
        self._set_phases(mission, phases)
        await self._trace(
            session,
            mission,
            "phase_completed",
            detail={
                "phase": current_idx,
                "name": phases[current_idx].get("name"),
                "actor": actor,
            },
        )

        next_idx = current_idx + 1
        if next_idx < len(phases):
            mission.current_phase = next_idx
            phases[next_idx]["status"] = PHASE_IN_PROGRESS
            self._set_phases(mission, phases)
            await self._trace(
                session,
                mission,
                "phase_started",
                detail={
                    "phase": next_idx,
                    "name": phases[next_idx].get("name"),
                    "actor": actor,
                },
            )
            return mission

        # Last phase completed → SUCCEEDED.
        assert_transition(mission.state, SUCCEEDED)
        mission.state = SUCCEEDED
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={"from": RUNNING, "to": SUCCEEDED, "actor": actor},
        )
        return mission

    async def fail(
        self,
        session: AsyncSession,
        mission_id: Any,
        reason: str,
        *,
        actor: str | None = None,
    ) -> Mission:
        """RUNNING → FAILED with a recorded failure reason."""
        mission = await self.get_mission(session, mission_id)
        assert_transition(mission.state, FAILED)
        previous = mission.state
        mission.failure_reason = reason
        mission.state = FAILED
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={
                "from": previous,
                "to": FAILED,
                "reason": reason,
                "phase": mission.current_phase,
                "actor": actor,
            },
        )
        return mission

    async def request_repair(
        self, session: AsyncSession, mission_id: Any, *, actor: str | None = None
    ) -> Mission:
        """FAILED → REPAIRING → (rotate strategy, reset phases) → RUNNING.

        - Increments ``repair_count`` and rotates ``strategy`` to the next
          entry of ``strategy_options`` (the plan's self-correction loop).
        - Resets the phase cursor to 0 and all phase statuses to pending
          (REPAIRING → RUNNING must reset the current phase).
        - When no alternative strategy options remain, the mission goes to
          terminal FAILED instead (and no repair is counted).
        """
        mission = await self.get_mission(session, mission_id)
        # Guard: FAILED → REPAIRING requires repair_count < MAX_REPAIRS.
        assert_transition(mission.state, REPAIRING, repair_count=mission.repair_count)

        previous = mission.state
        mission.state = REPAIRING
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={"from": previous, "to": REPAIRING, "actor": actor},
        )

        options = [str(o) for o in (mission.strategy_options or [])]
        current = mission.strategy
        nxt: str | None = None
        if len(options) >= 2:
            idx = options.index(current) if current in options else -1
            candidate = options[(idx + 1) % len(options)]
            if candidate != current:
                nxt = candidate

        if nxt is None:
            # Repair options exhausted → terminal FAILED.
            assert_transition(mission.state, FAILED)  # REPAIRING → FAILED edge
            mission.state = FAILED
            mission.failure_reason = (
                f"repair exhausted after {mission.repair_count} attempt(s): "
                "no alternative strategy_options remaining"
            )
            await self._trace(
                session,
                mission,
                "repair_triggered",
                detail={
                    "exhausted": True,
                    "repair_count": mission.repair_count,
                    "to": FAILED,
                    "actor": actor,
                },
            )
            await self._trace(
                session,
                mission,
                "state_transition",
                detail={"from": REPAIRING, "to": FAILED, "terminal": True, "actor": actor},
            )
            return mission

        # Rotate the strategy and reset phase progress.
        old_strategy = mission.strategy
        mission.repair_count += 1
        mission.strategy = nxt
        mission.current_phase = 0
        mission.failure_reason = None
        self._set_phases(
            mission,
            [{**dict(p), "status": PHASE_PENDING} for p in (mission.phases or [])],
        )
        await self._trace(
            session,
            mission,
            "repair_triggered",
            detail={
                "exhausted": False,
                "repair_count": mission.repair_count,
                "old_strategy": old_strategy,
                "new_strategy": nxt,
                "phase_reset": True,
                "actor": actor,
            },
        )

        mission.agent_id = self._assign_agent(mission)
        await self._trace(
            session,
            mission,
            "agent_assigned",
            detail={"agent_id": mission.agent_id, "strategy": mission.strategy, "actor": actor},
        )

        if requires_phase_reset(REPAIRING, RUNNING):
            # Reset already performed above (current_phase = 0, phases pending).
            assert_transition(mission.state, RUNNING)
        mission.state = RUNNING
        await self._trace(
            session,
            mission,
            "state_transition",
            detail={"from": REPAIRING, "to": RUNNING, "actor": actor},
        )
        return mission

    async def cancel(
        self,
        session: AsyncSession,
        mission_id: Any,
        *,
        actor: str | None = None,
        reason: str | None = None,
    ) -> Mission:
        """Cancel from PLANNED/APPROVED/ASSIGNED/RUNNING (terminal)."""
        mission = await self.get_mission(session, mission_id)
        assert_transition(mission.state, CANCELLED)
        previous = mission.state
        mission.state = CANCELLED
        await self._trace(
            session,
            mission,
            "cancelled",
            detail={"from": previous, "reason": reason, "actor": actor},
        )
        return mission

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    async def list_missions(
        self,
        session: AsyncSession,
        *,
        owner_id: str | None = None,
        state: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Mission]:
        """List missions (optionally filtered by owner and state), newest first."""
        query = select(Mission).order_by(Mission.created_at.desc(), Mission.id)
        if owner_id:
            query = query.where(Mission.owner_id == owner_id)
        if state:
            query = query.where(Mission.state == state)
        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_trace(self, session: AsyncSession, mission_id: Any) -> list[MissionTraceEvent]:
        """Return the mission's trace events ordered by per-mission sequence."""
        mission = await self.get_mission(session, mission_id)
        result = await session.execute(
            select(MissionTraceEvent)
            .where(MissionTraceEvent.mission_id == mission.id)
            .order_by(MissionTraceEvent.seq)
        )
        return list(result.scalars().all())
