# backend/api/routes/agent.py
"""Autonomous Agent Execution Route (canonical execution surface — ``/api/v1/agents``).

ERR-H07 CONTRACT (2026-09-16): the backend intentionally exposes TWO agent
surfaces — do not merge them casually:

- ``/api/agents``        (``api.routes.agents``, USER token)  → read-only
  catalog + status + research tools for human users / the Studio client.
- ``/api/v1/agents``     (THIS module, INTEGRATION JWT via
  ``verify_autonomous_agent_token``) → the single canonical EXECUTION
  surface for autonomous agent tasks (frontend ``agentService`` and
  external integrations).

Both prefixes are versioned deliberately; a drift-guard contract test
(``backend/tests/api/test_agent_execute_contract.py``) pins the mount
sites so a third surface or a silent prefix change fails CI.

Provides:
- POST /api/v1/agents/execute: autonomous agent task execution.
  - ``auto_execute=true``  → full execution, offloaded to a worker thread
    (ERR-H08 fix: ``AutonomousAgent.execute`` is synchronous and used to
    block the event loop for the whole run).
  - ``auto_execute=false`` → honest PLAN-ONLY response (the field used to
    be declared but never read — the route pretended to support a mode it
    did not implement). No steps are run in this mode.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.dependencies import verify_autonomous_agent_token
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

router = APIRouter(prefix="/api/v1/agents", tags=["Autonomous Agents"])


# Strict Pydantic Schema for Input Validation
class AgentTaskRequest(BaseModel):
    task_id: str = Field(..., description="Unique ID for the task")
    prompt: str = Field(..., min_length=10, max_length=5000)
    auto_execute: bool = Field(
        default=False,
        description=(
            "true → run the task now (offloaded to a worker thread); "
            "false → return the plan only, nothing is executed."
        ),
    )


class AgentTaskResponse(BaseModel):
    status: str
    result: str


def _render_plan(plan: dict) -> str:
    """Human-readable plan text (verbatim from the planner, no embellishment)."""
    lines = [plan.get("summary") or "Plan generated."]
    steps = plan.get("steps") or []
    if steps:
        lines.extend(f"{i}. {step}" for i, step in enumerate(steps, start=1))
    return "\n".join(lines)


@router.post("/execute", response_model=AgentTaskResponse)
@with_error_bus("execute_agent_task")
async def execute_agent_task(
    request: Request,
    payload: AgentTaskRequest,
    user: dict = Depends(verify_autonomous_agent_token),
) -> AgentTaskResponse:
    """
    Triggers an autonomous agent task safely.

    বাংলা মন্তব্য: API রাউটারটি হবে একদম পরিষ্কার (Clean Architecture)।
    এটি সরাসরি লজিক এক্সিকিউট না করে সার্ভিসের কাছে কাজ ডেলিগেট করবে।
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    # Issue #685 (Domain 15): explicit correlation-aware log for this
    # high-traffic execution surface (the id is also auto-injected into every
    # loguru record by SupremeContextMiddleware's contextualize scope).
    logger.info(
        "[agent.execute] task_id=%s auto_execute=%s correlation_id=%s",
        payload.task_id,
        payload.auto_execute,
        correlation_id,
    )

    try:
        from fastapi.concurrency import run_in_threadpool

        from brain.autonomous_agent import AutonomousAgent

        agent = AutonomousAgent(name=f"agent-route-{payload.task_id}")

        if not payload.auto_execute:
            # ERR-H08: the field used to be declared-but-never-read; plan-only
            # mode is now real — nothing is executed when auto_execute=false.
            plan = await run_in_threadpool(agent.plan, payload.prompt)
            return AgentTaskResponse(status="planned", result=_render_plan(plan))

        # ERR-H08: AutonomousAgent.execute is fully synchronous (plan + step
        # runner). Calling it inline blocked the event loop for the entire
        # run — now offloaded to the threadpool.
        exec_res = await run_in_threadpool(agent.execute, payload.prompt)
        response_text = exec_res.get("output") or f"Task {payload.task_id} completed successfully."

        return AgentTaskResponse(
            status="success" if exec_res.get("success") else "failed", result=response_text
        )

    except Exception as exc:
        # Route expected/unexpected errors to the ErrorBus and return safe HTTP response
        error_event_bus.emit(
            ErrorEvent(
                module="AgentExecutionRoute",
                error_type="TASK_EXECUTION_FAILED",
                message=str(exc)[:500],
                severity="ERROR",
                context={
                    "task_id": payload.task_id,
                    "correlation_id": correlation_id,
                    "user": user.get("sub", "unknown"),
                },
                structured_context=ErrorContext(
                    module="api.routes.agent",
                    request_id=correlation_id,
                    task_id=payload.task_id,
                    env="production",
                ),
            )
        )
        raise HTTPException(
            status_code=500,
            detail="Autonomous task failed. The system has logged the error for self-healing.",
        ) from exc
