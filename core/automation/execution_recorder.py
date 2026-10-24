"""
SupremeAI Automation Execution Recorder
========================================
বাংলা: Plan Section 7 — automation execution lifecycle persistence।
AutomationExecution DB model-এ dispatch lifecycle রেকর্ড করে:
  - dispatch শুরু হলে PENDING record তৈরি
  - সম্পন্ন হলে status update (DELIVERED/FAILED/SKIPPED)
  - duration, http_status, external_execution_id, error সংরক্ষণ

নীতি (Plan Section 10 — core-operation isolation):
  DB write কখনো dispatch-কে block করে না। DB unavailable হলে
  recorder শুধু warning log করে এবং dispatch স্বাভাবিকভাবে চলে।
  এটা "best-effort persistence" — audit trail থাকলে ভালো, না থাকলেও
  core functionality unaffected।
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from core.logging_config import logger

from .models import AutomationEvent, AutomationResult, AutomationStatus

if TYPE_CHECKING:
    from core.orchestration.conversation_orchestrator import ExecutionRecord


def _fit36(value: str | None) -> str | None:
    """FIX (final-test 2026-09-13): event-id/idempotency values যেমন 'exec_<32hex>' বা
    'corr_<32hex>' ৩৭ অক্ষরের — কিন্তু automation_executions.event_id কলাম
    VARCHAR(36) (migration 7c4d9e1f2a3b অনুযায়ী, কিছু লাইভ DB-তে idempotency_key-ও
    36-ই আছে)। ফলে প্রতিটি orchestration persistence insert নীরবে
    StringDataRightTruncationError-এ ব্যর্থ হচ্ছিল। Prefix-শেড normalize —
    ৩২-অক্ষরের unique অংশ অক্ষত থাকে, তাই idempotency uniqueness প্রভাবিত হয় না।"""
    if value is None:
        return None
    value = str(value)
    if len(value) <= 36:
        return value
    # 'exec_xxx' / 'corr_xxx' / 'evt_xxx' স্টাইল prefix থাকলে শেড করো
    if "_" in value and len(value.split("_", 1)[1]) <= 36:
        return value.split("_", 1)[1]
    return value[:36]


class ExecutionRecorder:
    """
    Plan Section 7: AutomationExecution lifecycle DB persistence।

    বাংলা: প্রতিটি dispatch-এর জন্য একটি AutomationExecution row তৈরি/আপডেট
    করে। DB unavailable হলে graceful degradation — dispatch কখনো block হয় না।
    """

    # ------------------------------------------------------------------
    # Canonical Run bridge (M1-C, ERR-F01 wiring) — extend-not-replace.
    # বাংলা: প্রতিটি automation dispatch এখন ক্যানোনিকাল runs টেবিলেও পর্যবেক্ষিত
    # হয় (runs.bridges.observe_automation_run ব্যবহার করে) — একটাই execution
    # contract। নীতি একই (Plan Section 10): run-fabric লেখা কখনো dispatch
    # persistence-কে block করে না; ব্যর্থ হলে শুধু warning log। পুরনো DB-তে
    # runs/run_events টেবিল না থাকলেও আচরণ অপরিবর্তিত থাকে।
    # ------------------------------------------------------------------

    _RUN_ACTOR = "automation-recorder"

    async def _activate_run(self, session: Any, service: Any, run_id: Any) -> None:
        """Walk the legal pre-execution path to RUNNING.

        The strict state machine requires REQUESTED → POLICY_CHECKED →
        PLANNED → RUNNING (no skip-ahead edges); automation dispatches are
        pre-authorized by their policy layer, so the bridge stamps each
        step and lands the run in RUNNING.
        """
        from runs.state_machine import PLANNED, POLICY_CHECKED, RUNNING

        for state, note in (
            (POLICY_CHECKED, "dispatch pre-authorized (automation policy layer)"),
            (PLANNED, "dispatch recorded"),
            (RUNNING, "dispatch started"),
        ):
            await service.transition(
                session, run_id, state, actor=self._RUN_ACTOR, detail={"note": note}
            )

    async def _run_bridge_create(
        self, session: Any, event: AutomationEvent, execution_id: str
    ) -> None:
        """Best-effort: observe this dispatch as a canonical Run (REQUESTED → RUNNING).

        Runs in the SAME session AFTER the automation row is committed, so a
        run-fabric failure can never roll back the authoritative record.
        Idempotency key ``automation-obs:<event_id>`` keeps re-dispatched
        events from duplicating runs (RunService dedups on the key).
        """
        try:
            from runs.bridges import observe_automation_run
            from runs.service import RunService

            service = RunService()
            run = await observe_automation_run(
                session,
                service,
                user_id="system",  # automation dispatches are system-initiated
                execution_id=execution_id,
                workflow_key=event.workflow_key,
                trace_id=_fit36(event.trace_id),
                idempotency_key=f"automation-obs:{_fit36(event.event_id)}",
            )
            await self._activate_run(session, service, run.id)
            await session.commit()
            logger.debug(
                f"🔗 ExecutionRecorder: canonical run {str(run.id)[:8]} observing "
                f"event {event.event_id} (RUNNING)"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ ExecutionRecorder.run-bridge (create) skipped: {e!r} — "
                f"automation persistence unaffected"
            )

    async def _run_bridge_settle(
        self, session: Any, execution_id: str, result: AutomationResult
    ) -> None:
        """Best-effort: settle the observing Run when the dispatch completes.

        Mapping (AutomationStatus → run terminal state):
        DELIVERED → SUCCEEDED, FAILED → FAILED (+error surface),
        SKIPPED → CANCELLED (automation disabled/no provider).
        """
        try:
            from sqlalchemy import select

            from runs.models import Run
            from runs.service import RunService
            from runs.state_machine import CANCELLED, FAILED, SUCCEEDED

            target = {
                "DELIVERED": SUCCEEDED,
                "FAILED": FAILED,
                "SKIPPED": CANCELLED,
            }.get(result.status.value.upper())
            if target is None:
                return
            service = RunService()
            run = (
                await session.execute(
                    select(Run)
                    .where(Run.source_type == "automation", Run.source_ref == execution_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if run is None:
                logger.debug(
                    f"🔗 ExecutionRecorder.run-bridge: no observing run for "
                    f"execution {execution_id[:8]} (create step skipped?) — settle skipped"
                )
                return
            detail: dict[str, Any] = {
                "status": result.status.value,
                "provider": result.provider,
            }
            if result.message:
                detail["message"] = result.message[:512]
            updated = await service.transition(
                session, run.id, target, actor=self._RUN_ACTOR, detail=detail
            )
            if result.status.value.upper() == "FAILED" and result.message:
                updated.error = result.message[:1024]
            await session.commit()
            logger.debug(
                f"🔗 ExecutionRecorder: canonical run {str(run.id)[:8]} settled "
                f"→ {target} for event {result.event_id}"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ ExecutionRecorder.run-bridge (settle) skipped: {e!r} — "
                f"automation persistence unaffected"
            )

    async def record_start(self, event: AutomationEvent) -> str | None:
        """
        dispatch শুরু হলে PENDING record তৈরি করে।
        রিটার্ন: execution_id (DB row id) অথবা None (DB unavailable)।
        """
        execution_id = str(uuid4())
        try:
            from database.session import get_db_session_context
            from models.automation_execution import AutomationExecution

            async with get_db_session_context() as session:
                record = AutomationExecution(
                    id=execution_id,
                    event_id=_fit36(event.event_id),
                    workflow_key=event.workflow_key,
                    idempotency_key=_fit36(event.idempotency_key),
                    provider="pending",  # provider পরে record_completion-এ update হবে
                    status="PENDING",
                    attempt=1,
                    trace_id=event.trace_id,
                    started_at=datetime.now(UTC),
                )
                session.add(record)
                await session.commit()
                logger.debug(
                    f"📋 ExecutionRecorder: PENDING record created for event {event.event_id} "
                    f"(execution_id={execution_id[:8]})"
                )
                # M1-C: observe the dispatch as a canonical Run (best-effort,
                # AFTER the authoritative commit — see _run_bridge_create).
                await self._run_bridge_create(session, event, execution_id)
                return execution_id
        except Exception as e:
            # Plan Section 10: DB failure কখনো dispatch-কে block করে না
            logger.warning(
                f"⚠️ ExecutionRecorder.record_start failed (DB unavailable?): {e!r} — "
                f"dispatch will continue without DB persistence"
            )
            return None

    async def record_completion(
        self,
        execution_id: str | None,
        event: AutomationEvent,
        result: AutomationResult,
        provider_name: str,
        started_at: float | None = None,
    ) -> None:
        """
        dispatch সম্পন্ন হলে record update করে।
        execution_id None হলে (record_start fail করেছিল) কিছু করে না।
        """
        if execution_id is None:
            return  # record_start fail করেছিল — কিছু করার নেই

        try:
            from sqlalchemy import select

            from database.session import get_db_session_context
            from models.automation_execution import AutomationExecution, AutomationExecutionAttempt

            duration_ms = None
            if started_at is not None:
                duration_ms = int((time.time() - started_at) * 1000)

            async with get_db_session_context() as session:
                # fetch existing record
                stmt = select(AutomationExecution).where(AutomationExecution.id == execution_id)
                db_result = await session.execute(stmt)
                record = db_result.scalar_one_or_none()
                if record is None:
                    logger.warning(
                        f"⚠️ ExecutionRecorder: record {execution_id[:8]} not found — "
                        f"cannot update completion"
                    )
                    return

                # update fields
                record.status = result.status.value.upper()
                record.provider = provider_name
                record.attempt = result.attempt
                record.completed_at = datetime.now(UTC)
                record.duration_ms = duration_ms
                record.external_execution_id = result.execution_id

                # error fields (শুধু FAILED হলে)
                if result.status == AutomationStatus.FAILED:
                    record.error_message = result.message[:1024] if result.message else None
                else:
                    record.error_message = None

                # Create the attempt record (Plan Section 8: retry attempt history)
                attempt_record = AutomationExecutionAttempt(
                    execution_id=execution_id,
                    attempt=result.attempt,
                    status=result.status.value.upper(),
                    started_at=datetime.fromtimestamp(started_at, tz=UTC)
                    if started_at
                    else record.started_at,
                    completed_at=record.completed_at,
                    duration_ms=duration_ms,
                    http_status=None,  # This could be parsed from result if needed
                    error_message=record.error_message,
                )
                session.add(attempt_record)

                await session.commit()
                logger.debug(
                    f"📋 ExecutionRecorder: record updated for event {event.event_id} "
                    f"(status={result.status.value}, duration={duration_ms}ms)"
                )
                # M1-C: settle the observing canonical Run (best-effort, AFTER
                # the authoritative commit — see _run_bridge_settle).
                await self._run_bridge_settle(session, execution_id, result)
        except Exception as e:
            # Plan Section 10: DB failure কখনো dispatch-কে block করে না
            logger.warning(
                f"⚠️ ExecutionRecorder.record_completion failed: {e!r} — dispatch result unaffected"
            )

    async def persist_execution(
        self,
        record: ExecutionRecord,
        policy: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Durable bridge for the canonical orchestration `ExecutionRecord`.

        বাংলা: orchestration dispatch-এর ExecutionRecord কে automation_executions
        টেবিলে লেখে — correlation/tenant/project/conversation লিংক + evidence +
        policy decision সহ। Best-effort: DB unavailable হলে dispatch কখনো block হয়
        না (শুধু warning log) — core-operation isolation নীতি (Plan Section 10)।
        """
        if record is None:
            return None
        execution_id = str(uuid4())
        try:
            from database.session import get_db_session_context
            from models.automation_execution import AutomationExecution

            now = datetime.now(UTC)
            async with get_db_session_context() as session:
                db_record = AutomationExecution(
                    id=execution_id,
                    event_id=_fit36(record.execution_id),
                    workflow_key=f"orchestrator:{record.capability}",
                    idempotency_key=_fit36(record.correlation_id),
                    provider="orchestrator",
                    status=record.status.upper(),
                    attempt=1,
                    trace_id=record.correlation_id,
                    started_at=now,
                    completed_at=now,
                    correlation_id=record.correlation_id,
                    tenant_id=record.tenant_id,
                    project_id=record.project_id,
                    conversation_id=record.conversation_id,
                    capability=record.capability,
                    evidence=record.evidence or None,
                    policy=policy,
                )
                session.add(db_record)
                await session.commit()
                logger.debug(
                    f"📋 ExecutionRecorder: orchestration ExecutionRecord persisted "
                    f"(execution_id={execution_id[:8]}, capability={record.capability}, "
                    f"status={record.status})"
                )
                # M1-C: the orchestration path lands with its final status in one
                # step — observe the run and settle it to the mapped terminal state.
                await self._run_bridge_finalize(session, record, execution_id)
                return execution_id
        except Exception as e:
            # Plan Section 10: DB failure কখনো orchestration dispatch-কে block করে না
            logger.warning(
                f"⚠️ ExecutionRecorder.persist_execution failed (DB unavailable?): {e!r} — "
                f"orchestration continues without durable persistence"
            )
            return None

    async def _run_bridge_finalize(
        self, session: Any, record: ExecutionRecord, execution_id: str
    ) -> None:
        """Best-effort: observe an orchestration ExecutionRecord as a settled Run.

        Status mapping: failed → FAILED, skipped → CANCELLED, everything
        else → SUCCEEDED (the record lands post-dispatch, so there is no
        intermediate lifecycle to walk through).
        """
        try:
            from runs.bridges import observe_automation_run
            from runs.service import RunService
            from runs.state_machine import CANCELLED, FAILED, SUCCEEDED

            status = (record.status or "completed").strip().lower()
            target = {
                "failed": FAILED,
                "skipped": CANCELLED,
            }.get(status, SUCCEEDED)
            service = RunService()
            run = await observe_automation_run(
                session,
                service,
                user_id=record.user_id or "system",
                execution_id=execution_id,
                workflow_key=f"orchestrator:{record.capability}",
                trace_id=_fit36(record.correlation_id),
                correlation_id=_fit36(record.correlation_id),
                idempotency_key=f"orchestration-obs:{_fit36(record.correlation_id)}",
            )
            await self._activate_run(session, service, run.id)
            detail: dict[str, Any] = {"orchestration_status": status}
            if record.evidence:
                detail["evidence_events"] = len(record.evidence)
            updated = await service.transition(
                session, run.id, target, actor=self._RUN_ACTOR, detail=detail
            )
            if target == FAILED:
                updated.error = f"orchestration dispatch failed (status={status})"
            await session.commit()
            logger.debug(
                f"🔗 ExecutionRecorder: canonical run {str(run.id)[:8]} settled "
                f"→ {target} for orchestration {record.correlation_id}"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ ExecutionRecorder.run-bridge (finalize) skipped: {e!r} — "
                f"orchestration persistence unaffected"
            )


# Singleton instance
execution_recorder = ExecutionRecorder()
