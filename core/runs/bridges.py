"""Evidence bridges — existing subsystems observed as canonical Runs (M1-C).

Roadmap M1 exit criteria: "missions + one tool path + one MCP path
observable as Runs in a test DB." Doctrine: **extend, not replace** — these
are thin adapters that CREATE/OBSERVE canonical runs anchored to existing
subsystem rows; the subsystems keep their own behavior, no rewrite, no
duplicate execution machinery.

Bridges:

- :func:`observe_mission_run` — a Mission's execution becomes a run anchored
  via ``mission_id`` (the M1-A extend-anchor FK).
- :func:`observe_tool_run` — one tool-call path (any ``tools``-registry
  invocation) observed with ``source_type="tool"``.
- :func:`observe_mcp_run` — one MCP invocation path observed with
  ``source_type="mcp"`` (the mcp-hub policy layer keeps its own enforcement;
  the run is the observability record).
- :func:`observe_automation_run` — an ``automation_executions`` dispatch
  observed with ``source_type="automation"`` (its evidence/policy columns
  stay authoritative for that subsystem; the run carries correlation).

All bridges funnel through :class:`runs.service.RunService` so idempotency,
lifecycle, budgets and the audit stream are enforced at ONE boundary.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runs.models import Run
from runs.service import RunService

#: Evidence source_type values used by the M1 bridges.
SOURCE_MISSION = "mission"
SOURCE_TOOL = "tool"
SOURCE_MCP = "mcp"
SOURCE_AUTOMATION = "automation"
#: M02 P-B (ERR-F01): scheduled-task execution observed as a canonical run.
SOURCE_SCHEDULED_TASK = "scheduled_task"


async def observe_mission_run(
    session: AsyncSession,
    service: RunService,
    *,
    mission_id: uuid.UUID | str,
    user_id: str,
    title: str | None = None,
    idempotency_key: str | None = None,
    **budget_limits: Any,
) -> Run:
    """Observe a Mission execution as its canonical run (extend-anchor)."""
    return await service.create_run(
        session,
        run_type="mission",
        user_id=user_id,
        title=title,
        mission_id=mission_id,
        source_type=SOURCE_MISSION,
        source_ref=str(mission_id),
        idempotency_key=idempotency_key,
        **budget_limits,
    )


async def observe_tool_run(
    session: AsyncSession,
    service: RunService,
    *,
    user_id: str,
    tool_name: str,
    tool_call_ref: str | None = None,
    chat_id: str | None = None,
    workspace_id: str | None = None,
    idempotency_key: str | None = None,
    **budget_limits: Any,
) -> Run:
    """Observe one tool-call execution as a canonical run.

    ``tool_call_ref`` should be the caller's tool-call id (or any stable
    reference into the invoking path) so the run bridges back to the exact
    invocation.
    """
    return await service.create_run(
        session,
        run_type="tool",
        user_id=user_id,
        title=f"tool:{tool_name}",
        chat_id=chat_id,
        workspace_id=workspace_id,
        source_type=SOURCE_TOOL,
        source_ref=tool_call_ref or tool_name,
        idempotency_key=idempotency_key,
        **budget_limits,
    )


async def observe_mcp_run(
    session: AsyncSession,
    service: RunService,
    *,
    user_id: str,
    server: str,
    tool: str,
    invocation_ref: str | None = None,
    chat_id: str | None = None,
    workspace_id: str | None = None,
    idempotency_key: str | None = None,
    **budget_limits: Any,
) -> Run:
    """Observe one MCP tool invocation as a canonical run.

    The mcp-hub policy layer (PR #305) keeps its own quota/one-time-token
    enforcement; this run is the canonical observability + budget record.
    """
    return await service.create_run(
        session,
        run_type="mcp",
        user_id=user_id,
        title=f"mcp:{server}/{tool}",
        chat_id=chat_id,
        workspace_id=workspace_id,
        source_type=SOURCE_MCP,
        source_ref=invocation_ref or f"{server}/{tool}",
        idempotency_key=idempotency_key,
        **budget_limits,
    )


async def observe_automation_run(
    session: AsyncSession,
    service: RunService,
    *,
    user_id: str,
    execution_id: str,
    workflow_key: str | None = None,
    provider: str | None = None,
    trace_id: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    **budget_limits: Any,
) -> Run:
    """Observe an ``automation_executions`` dispatch as a canonical run.

    The automation row stays authoritative for its subsystem (its
    ``evidence``/``policy`` columns are untouched); the run carries the
    correlation so dispatches show up in the unified execution view.
    """
    title = f"automation:{workflow_key or 'dispatch'}"
    if provider:
        title = f"{title}@{provider}"
    return await service.create_run(
        session,
        run_type="automation",
        user_id=user_id,
        title=title,
        source_type=SOURCE_AUTOMATION,
        source_ref=execution_id,
        trace_id=trace_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        **budget_limits,
    )


async def observe_task_run(
    session: AsyncSession,
    service: RunService,
    *,
    task_id: str,
    user_id: str,
    title: str | None = None,
    idempotency_key: str | None = None,
    **budget_limits: Any,
) -> Run:
    """Observe one scheduled-task execution as its canonical run (M02 P-B).

    বাংলা মন্তব্য: ERR-F01 সেতু-সত্য — scheduled_tasks-এর প্রকৃত নির্বাহ (M22 P-A
    sweep পথ) এখন Run fabric-এ পর্যবেক্ষণযোগ্য; M05/M06/M17-এর run-তথ্য-খোঁজা
    এখান থেকেই মেলে। scheduled_tasks row-ই তার সাবসিস্টেমের authority — রান শুধু
    পর্যবেক্ষণ/বাজেট-রেকর্ড (extend, not replace)। run_type="agent" (একজন agent
    prompt নির্বাহ করে), source_ref=task_id, source_type=scheduled_task।
    """
    return await service.create_run(
        session,
        run_type="agent",
        user_id=user_id,
        title=title or f"scheduled-task:{task_id}",
        source_type=SOURCE_SCHEDULED_TASK,
        source_ref=str(task_id),
        idempotency_key=idempotency_key,
        **budget_limits,
    )
