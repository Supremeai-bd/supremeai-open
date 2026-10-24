"""Canonical Run service (M1-B) — lifecycle + budget enforcement boundary.

Every public method takes an ``AsyncSession`` (repo-standard, routes pass
``Depends(get_db_session)``) and performs run + event writes on that ONE
session so a state change and its audit event commit atomically (same
discipline as :mod:`missions.service`).

Every state change:
1. validates the transition against :mod:`runs.state_machine` (pure guard
   BEFORE any mutation — an illegal transition never touches the row),
2. mutates the run row (status + lifecycle timestamps),
3. checks budgets where relevant (admission control before a retry;
   verdict recorded on the run's event stream),
4. appends a ``RunEvent`` (seq = max(seq)+1 per run, explicit flush so the
   next max(seq) query sees it even on ``autoflush=False`` sessions),
5. emits one structured log line carrying ``run_id``.

Retry flow (roadmap M1): ``classify_failure`` records the 8-class
classification + error; ``request_retry`` consults the retry budget and the
state-machine guard together, then moves RUNNING → RETRYING; the caller
re-enters RUNNING when the next attempt actually starts.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import logger
from runs.budgets import BudgetDimension, BudgetSnapshot, check_budgets
from runs.models import Run, RunEvent, RunType
from runs.retry import RetryClass, is_retryable
from runs.state_machine import (
    CANCELLED,
    FAILED,
    FINALIZED,
    RETRYING,
    RUNNING,
    TERMINAL_STATES,
    WAITING_APPROVAL,
    IllegalTransition,
    assert_transition,
)

#: States from which cancellation is legal (pre-execution + running cluster).
CANCELLABLE_STATES = (
    "requested",
    "policy_checked",
    "planned",
    "running",
    "waiting_approval",
    "retrying",
    "degraded",
    "blocked",
)


class RunNotFound(LookupError):
    """Raised when a run id does not exist (routes map this to 404)."""


class RunService:
    """Run lifecycle service — all DB access via the injected AsyncSession.

    Stateless per-run (all run state lives in the rows); the approval hook
    is injectable per instance (same pattern as ``MissionService``'s
    assigner hook) so production can wire the existing HITL manager while
    tests stay offline.
    """

    def __init__(self, approval_hook: Any | None = None) -> None:
        # approval_hook: runs.hitl.ApprovalHook (suspend -> record_id) or None.
        # None means "WAITING_APPROVAL reachable without external record" —
        # acceptable for direct-API callers; subsystem bridges pass a hook.
        self._approval_hook = approval_hook

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _emit(
        self,
        session: AsyncSession,
        run: Run,
        event: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Append a run event (seq = max+1) on the SAME session/transaction."""
        last_seq = await session.scalar(
            select(func.max(RunEvent.seq)).where(RunEvent.run_id == run.id)
        )
        evt = RunEvent(
            run_id=run.id,
            seq=(last_seq or 0) + 1,
            event=event,
            detail=detail,
        )
        session.add(evt)
        # Explicit flush: database.session builds autoflush=False sessions,
        # so the next max(seq) query must be able to see this row.
        await session.flush()
        logger.info(
            f"[RunService] event={event} run_id={run.id} seq={evt.seq} "
            f"status={run.status} detail={detail or {}}"
        )

    async def get_run(self, session: AsyncSession, run_id: Any) -> Run:
        """Fetch a run by id (UUID or UUID-string); raise RunNotFound."""
        rid = run_id
        if isinstance(rid, str):
            try:
                rid = uuid.UUID(rid)
            except ValueError as exc:
                raise RunNotFound(f"run {run_id!r} not found") from exc
        run = await session.get(Run, rid)
        if run is None:
            raise RunNotFound(f"run {run_id!r} not found")
        return run

    def _budget_snapshot(
        self,
        run: Run,
        *,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        """Snapshot the run's budget limits + consumption for enforcement."""
        wall_clock_ms = 0
        if run.started_at is not None:
            started = run.started_at
            if started.tzinfo is None:
                # sqlite round-trip: naive values were written as UTC
                # (client-side _utcnow defaults) — interpret back as UTC.
                started = started.replace(tzinfo=UTC)
            end = now or datetime.now(UTC)
            wall_clock_ms = max(0, int((end - started).total_seconds() * 1000))
        return BudgetSnapshot(
            max_wall_clock_ms=run.max_wall_clock_ms,
            max_tokens=run.max_tokens,
            max_tool_calls=run.max_tool_calls,
            max_retries=run.max_retries,
            tokens_used=run.tokens_used,
            tool_calls_used=run.tool_calls_used,
            retries_used=run.retries_used,
            wall_clock_ms_used=wall_clock_ms,
        )

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    async def create_run(
        self,
        session: AsyncSession,
        *,
        run_type: str,
        user_id: str,
        title: str | None = None,
        workspace_id: str | None = None,
        chat_id: str | None = None,
        mission_id: uuid.UUID | str | None = None,
        parent_run_id: uuid.UUID | str | None = None,
        source_type: str | None = None,
        source_ref: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        max_wall_clock_ms: int | None = None,
        max_tokens: int | None = None,
        max_tool_calls: int | None = None,
        max_retries: int | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> Run:
        """Create a run in REQUESTED state + ``run_created`` event.

        Idempotency: when ``idempotency_key`` is supplied and a run with the
        same key exists, the EXISTING run is returned unchanged (the caller
        cannot double-create). ``run_type`` is validated against
        :class:`runs.models.RunType` values up front.
        """
        if run_type not in {rt.value for rt in RunType}:
            raise ValueError(
                f"invalid run_type {run_type!r}; allowed: {sorted(rt.value for rt in RunType)}"
            )

        if idempotency_key:
            existing = await session.scalar(
                select(Run).where(Run.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return existing

        def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
            if value is None or isinstance(value, uuid.UUID):
                return value
            return uuid.UUID(value)

        run = Run(
            run_type=run_type,
            user_id=user_id,
            title=title,
            workspace_id=workspace_id,
            chat_id=chat_id,
            mission_id=_as_uuid(mission_id),
            parent_run_id=_as_uuid(parent_run_id),
            source_type=source_type,
            source_ref=source_ref,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            correlation_id=correlation_id,
            max_wall_clock_ms=max_wall_clock_ms,
            max_tokens=max_tokens,
            max_tool_calls=max_tool_calls,
            max_retries=max_retries,
            artifacts=artifacts if artifacts is not None else [],
        )
        session.add(run)
        await session.flush()
        await self._emit(
            session,
            run,
            "run_created",
            detail={
                "run_type": run_type,
                "user_id": user_id,
                "idempotency_key": idempotency_key,
            },
        )
        return run

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def transition(
        self,
        session: AsyncSession,
        run_id: Any,
        to: str,
        *,
        actor: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> Run:
        """Move the run to ``to`` after the pure guard validates the edge.

        Stamps lifecycle timestamps: ``started_at`` on first entry to
        RUNNING, ``terminal_at`` on any terminal state, ``finalized_at`` on
        FINALIZED. Appends ``status_transition`` (or ``finalized``).
        """
        run = await self.get_run(session, run_id)
        assert_transition(run.status, to)  # IllegalTransition → 409 upstream

        from_status = run.status
        run.status = to
        now = datetime.now(UTC)
        if to == RUNNING and run.started_at is None:
            run.started_at = now
        elif to == FINALIZED:
            run.finalized_at = now
        elif to in TERMINAL_STATES:
            run.terminal_at = now

        event = "finalized" if to == FINALIZED else "status_transition"
        await self._emit(
            session,
            run,
            event,
            detail={"from": from_status, "to": to, "actor": actor, **(detail or {})},
        )
        return run

    async def check_run_budgets(
        self,
        session: AsyncSession,
        run_id: Any,
        *,
        actor: str | None = None,
    ) -> BudgetSnapshot:
        """Evaluate budgets for an active run; record violation events.

        Returns the snapshot. When a dimension is exceeded, a
        ``budget_exceeded`` event is appended (the caller decides the
        reaction — typically FAILED with resource_exhausted classification).
        """
        run = await self.get_run(session, run_id)
        snapshot = self._budget_snapshot(run)
        verdict = check_budgets(snapshot)
        if not verdict.ok:
            await self._emit(
                session,
                run,
                "budget_exceeded",
                detail={
                    "actor": actor,
                    "violations": [v.value for v in verdict.violations],
                    **snapshot.as_detail(),
                },
            )
        return snapshot

    async def record_usage(
        self,
        session: AsyncSession,
        run_id: Any,
        *,
        tokens: int = 0,
        tool_calls: int = 0,
        actor: str | None = None,
    ) -> Run:
        """Increment consumption counters (idempotent-free, caller-owned).

        Admission control: if the increment would exceed a capped budget,
        counters are NOT mutated and a ``budget_exceeded`` event is recorded
        — the caller receives the run unchanged and must treat the attempt
        as refused (this is what keeps the prod budget-violation metric
        clean: overspend never lands).
        """
        run = await self.get_run(session, run_id)
        snapshot = self._budget_snapshot(run)
        verdict = check_budgets(
            BudgetSnapshot(
                max_wall_clock_ms=snapshot.max_wall_clock_ms,
                max_tokens=snapshot.max_tokens,
                max_tool_calls=snapshot.max_tool_calls,
                max_retries=snapshot.max_retries,
                tokens_used=snapshot.tokens_used + tokens,
                tool_calls_used=snapshot.tool_calls_used + tool_calls,
                retries_used=snapshot.retries_used,
                wall_clock_ms_used=snapshot.wall_clock_ms_used,
            )
        )
        if not verdict.ok:
            await self._emit(
                session,
                run,
                "budget_exceeded",
                detail={
                    "actor": actor,
                    "attempted": {"tokens": tokens, "tool_calls": tool_calls},
                    "violations": sorted(v.value for v in verdict.violations),
                },
            )
            return run

        run.tokens_used += tokens
        run.tool_calls_used += tool_calls
        await self._emit(
            session,
            run,
            "usage_recorded",
            detail={"tokens": tokens, "tool_calls": tool_calls, "actor": actor},
        )
        return run

    # ------------------------------------------------------------------
    # Failure / retry
    # ------------------------------------------------------------------
    async def classify_failure(
        self,
        session: AsyncSession,
        run_id: Any,
        retry_class: RetryClass | str,
        *,
        error: str | None = None,
        actor: str | None = None,
    ) -> Run:
        """Record the 8-class failure classification + error surface."""
        run = await self.get_run(session, run_id)
        rc = str(retry_class)
        try:
            RetryClass(rc)
        except ValueError as exc:
            raise ValueError(
                f"invalid retry_class {rc!r}; allowed: {[c.value for c in RetryClass]}"
            ) from exc
        run.retry_class = rc
        if error is not None:
            run.error = error
        await self._emit(
            session,
            run,
            "retry_classified",
            detail={"retry_class": rc, "error": error, "actor": actor},
        )
        return run

    async def request_retry(
        self,
        session: AsyncSession,
        run_id: Any,
        *,
        retry_class: RetryClass | str | None = None,
        actor: str | None = None,
    ) -> Run:
        """Schedule a retry: RUNNING → RETRYING under budget + guard.

        Uses the run's recorded ``retry_class`` unless an explicit one is
        passed. Raises IllegalTransition when the classification is not
        retryable or the retry budget is exhausted (callers then go to
        FAILED).
        """
        run = await self.get_run(session, run_id)
        rc = str(retry_class) if retry_class is not None else run.retry_class
        snapshot = self._budget_snapshot(run)
        assert_transition(
            run.status,
            "retrying",
            retry_class=rc,
            retries_used=snapshot.retries_used,
            max_retries=snapshot.max_retries,
        )
        run.status = RETRYING
        run.retries_used += 1
        await self._emit(
            session,
            run,
            "retry_scheduled",
            detail={
                "retry_class": rc,
                "retries_used": run.retries_used,
                "actor": actor,
            },
        )
        return run

    # ------------------------------------------------------------------
    # Cancellation + finalization
    # ------------------------------------------------------------------
    async def cancel(
        self,
        session: AsyncSession,
        run_id: Any,
        *,
        actor: str | None = None,
        reason: str | None = None,
    ) -> Run:
        """Cancel a run from any cancellable state (idempotent if terminal)."""
        run = await self.get_run(session, run_id)
        if run.status in TERMINAL_STATES:
            # Already finished (e.g. raced with success): keep first outcome,
            # record the attempted cancellation for the audit trail.
            await self._emit(
                session,
                run,
                "cancel_ignored",
                detail={"actor": actor, "reason": reason, "status": run.status},
            )
            return run
        assert_transition(run.status, CANCELLED)
        run.status = CANCELLED
        run.terminal_at = datetime.now(UTC)
        await self._emit(
            session,
            run,
            "cancelled",
            detail={"actor": actor, "reason": reason},
        )
        return run

    async def finalize(
        self,
        session: AsyncSession,
        run_id: Any,
        *,
        actor: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> Run:
        """Seal a terminal run into FINALIZED (audit-locked)."""
        run = await self.get_run(session, run_id)
        return await self.transition(
            session,
            run.id,
            FINALIZED,
            actor=actor,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # HITL (M1-C): reuse the existing HITL manager contract
    # ------------------------------------------------------------------
    async def request_approval(
        self,
        session: AsyncSession,
        run_id: Any,
        *,
        payload: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> Run:
        """Suspend the run for human approval (RUNNING -> WAITING_APPROVAL).

        Calls the injectable approval hook (existing HITL manager contract:
        ``suspend(target_resource, payload) -> record_id``) and records the
        external record id + payload hash on the run's event stream. When
        the external decision lands, callers resolve via ``transition``
        (-> RUNNING approved / -> FAILED rejected) — see ``resolve_approval``.
        """
        from runs.hitl import make_approval_detail

        run = await self.get_run(session, run_id)
        assert_transition(run.status, WAITING_APPROVAL)

        record_id: str | None = None
        if self._approval_hook is not None:
            record_id = await self._approval_hook.suspend(
                f"run:{run.id}", payload or {"run_id": str(run.id)}
            )

        run.status = WAITING_APPROVAL
        run.retry_class = str(RetryClass.approval_required)
        await self._emit(
            session,
            run,
            "approval_requested",
            detail={"actor": actor, **make_approval_detail(record_id or "", payload)},
        )
        return run

    async def resolve_approval(
        self,
        session: AsyncSession,
        run_id: Any,
        *,
        approved: bool,
        actor: str | None = None,
        reason: str | None = None,
    ) -> Run:
        """Close the HITL loop: WAITING_APPROVAL -> RUNNING (or FAILED)."""
        run = await self.get_run(session, run_id)
        target = RUNNING if approved else FAILED
        assert_transition(run.status, target)
        from_status = run.status
        run.status = target
        if not approved:
            run.terminal_at = datetime.now(UTC)
        await self._emit(
            session,
            run,
            "approval_resolved",
            detail={
                "from": from_status,
                "to": target,
                "approved": approved,
                "actor": actor,
                "reason": reason,
            },
        )
        return run
