# backend/runtime/task_runtime.py
"""Canonical Task Runtime (The Authoritative Control Plane).

Orchestrates:
TaskContract -> TaskStateMachine -> Planner -> BudgetGuard -> TaskExecutor -> VerifierEngine -> Memory -> TaskResult
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.integration_layer import SupremeAIIntegrator
from core.logging_config import logger
from core.task_contract import TaskContract, TaskStatus, VerificationPolicy
from runtime.budget_guard import BudgetExceededError, BudgetGuard
from runtime.planner import CanonicalPlanner, Plan, get_planner
from runtime.task_context import TaskContext
from runtime.task_executor import TaskExecutor
from runtime.task_result import TaskResult, VerificationSummary

if TYPE_CHECKING:
    # M0-C (AUDIT F5): verification/verifier.py imports runtime.task_result at
    # module level, so a module-level import of verification here makes
    # `import verification` fail with a partially-initialized circular import
    # (order-dependent). Keep the type for static checks only and resolve the
    # engine lazily at construction time.
    from verification.verifier import VerifierEngine


class TaskRuntime:
    """Canonical Task Runtime governing all execution across SupremeAI."""

    def __init__(
        self,
        ai_system: SupremeAIIntegrator | None = None,
        verifier: VerifierEngine | None = None,
        planner: CanonicalPlanner | None = None,
    ) -> None:
        self.ai_system = ai_system
        if verifier:
            self.verifier = verifier
        else:
            # M0-C (AUDIT F5): function-scope import breaks the
            # verification <-> runtime import cycle at runtime.
            from verification.verifier import get_verifier

            self.verifier = get_verifier()
        self.planner = planner or get_planner()
        self.executor = TaskExecutor(ai_system=self.ai_system)
        self.experience_ledger: list[dict[str, Any]] = []

    async def execute_task(
        self,
        task: TaskContract,
        context: TaskContext | None = None,
    ) -> TaskResult:
        """Execute task through the canonical 5-stage lifecycle."""
        start_time = time.perf_counter()
        ctx = context or TaskContext()
        logger.info(f"🚀 [Runtime] Initiating task execution: {task.task_id}")

        try:
            if not ctx.tenant_id:
                raise ValueError("Task execution requires an authenticated tenant_id")

            # Stage 0: Pre-execution Budget Gate
            BudgetGuard.check_pre_execution(task)

            # Stage 1: Planning / Decomposition
            task.transition_to(TaskStatus.PLANNING)
            ctx.checkpoint("planning_started")
            plan: Plan = await self.planner.create_plan(task)
            ctx.checkpoint(
                "planning_completed", {"plan_id": plan.plan_id, "steps_count": len(plan.steps)}
            )

            # Stage 2: Execution
            task.transition_to(TaskStatus.EXECUTING)
            ctx.checkpoint("execution_started")

            exec_res = await asyncio.wait_for(
                self.executor.execute(task, ctx),
                timeout=task.budget.max_execution_seconds,
            )

            if not exec_res.get("success"):
                task.fail(exec_res.get("error", "Execution failed"))
                return self._create_result(task, exec_res, start_time)

            candidate_output = exec_res.get("output")

            # Enforce budget accumulation
            BudgetGuard.record_and_enforce(
                task,
                prompt_tokens=ctx.token_usage.get("prompt", 0),
                completion_tokens=ctx.token_usage.get("completion", 0),
                cost_usd=ctx.cost_usd,
                tool_calls=1,
            )

            # Stage 3: Verification Gate
            task.transition_to(TaskStatus.VERIFYING)
            ctx.checkpoint("verification_started")

            ver_report = await self.verifier.verify(task, candidate_output, ctx)

            # Stage 4: Completion & Experience Ledgering
            if ver_report.verified:
                task.complete(candidate_output, confidence=task.confidence or 0.95)
            else:
                if task.verification_policy == VerificationPolicy.STRICT:
                    task.fail(f"Verification failed: {', '.join(ver_report.failures)}")
                else:
                    task.complete(candidate_output, confidence=task.confidence or 0.70)

            # Record into Experience Ledger
            self._record_experience(task, ctx, ver_report)

            return self._create_result(task, exec_res, start_time, ver_report)

        except BudgetExceededError as budget_err:
            task.fail(f"Budget exceeded: {budget_err}")
            return TaskResult(
                task_id=task.task_id,
                success=False,
                answer="",
                confidence=0.0,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                error=str(budget_err),
            )
        except TimeoutError:
            task.fail(f"Task exceeded budget timeout ({task.budget.max_execution_seconds}s)")
            return TaskResult(
                task_id=task.task_id,
                success=False,
                answer="",
                confidence=0.0,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                error="Timeout exceeded",
            )
        except Exception as exc:
            task.fail(str(exc))
            logger.error(f"💥 Runtime error on [{task.task_id}]: {exc}", exc_info=True)
            return TaskResult(
                task_id=task.task_id,
                success=False,
                answer="",
                confidence=0.0,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                error=str(exc),
            )

    def _create_result(
        self,
        task: TaskContract,
        exec_res: dict[str, Any],
        start_time: float,
        ver_report: VerificationSummary | None = None,
    ) -> TaskResult:
        total_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return TaskResult(
            task_id=task.task_id,
            success=task.status == TaskStatus.COMPLETED,
            answer=task.result or "",
            confidence=task.confidence or 0.95,
            execution_time_ms=total_time_ms,
            provider_used=exec_res.get("provider_used", "Gemini"),
            verification=ver_report or VerificationSummary(),
            components_used=exec_res.get("components_used", ["reasoning_engine"]),
            error=task.error,
            metadata={
                "task_status": task.status.value,
                "risk_level": task.risk_level.value,
                "tokens_used": task.budget.tokens_used,
                "plan_steps_count": len(task.plan_steps),
            },
        )

    def _record_experience(
        self,
        task: TaskContract,
        context: TaskContext,
        ver_report: VerificationSummary,
    ) -> None:
        """Store immutable execution experience in ledger for continual learning."""
        experience = {
            "experience_id": f"exp_{task.task_id}",
            "task_id": task.task_id,
            "goal": task.goal,
            "success": task.status == TaskStatus.COMPLETED,
            "confidence": task.confidence,
            "verification_score": ver_report.score,
            "verification_passed": ver_report.verified,
            "provider_used": context.active_provider,
            "tokens_used": context.token_usage["total"],
            "timestamp": datetime.now().isoformat(),
        }
        self.experience_ledger.append(experience)
        if len(self.experience_ledger) > 1000:
            self.experience_ledger.pop(0)


# Global Singleton
_task_runtime_instance: TaskRuntime | None = None


def get_task_runtime(ai_system: SupremeAIIntegrator | None = None) -> TaskRuntime:
    global _task_runtime_instance
    if _task_runtime_instance is None:
        _task_runtime_instance = TaskRuntime(ai_system=ai_system)
    elif ai_system and not _task_runtime_instance.ai_system:
        _task_runtime_instance.ai_system = ai_system
        _task_runtime_instance.executor.ai_system = ai_system
    return _task_runtime_instance
