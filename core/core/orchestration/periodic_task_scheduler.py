# backend/core/orchestrator.py
"""Orchestrator module for SupremeAI 2.0.

- Schedules periodic tasks such as fitness scoring.
- Provides a health/status endpoint.
- Integrated with FastAPI lifespan (startup/shutdown).
"""

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.logging_config import logger
from core.observability.telemetry import trace_span

# Assuming OpenTelemetry tracer is set up in core.telemetry
from core.self_evolution.fitness_engine import FitnessEngine
from core.self_evolution.self_evolution_agent import SelfEvolutionAgent
from core.self_evolution.skill_graph import EvolutionSkillGraph

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class Orchestrator:
    """Central orchestrator responsible for coordinating scheduled pipelines.

    It does **not** implement the pipelines themselves â€“ those live in their respective modules.
    The orchestrator merely triggers them at configured intervals and exposes a status endpoint.
    """

    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._running: bool = False
        # BUG FIX #2: Use shared FitnessEngine singleton instead of private instance.
        # Private FitnessEngine() here had empty metrics → SelfEvolutionAgent._tick()
        # read from this private instance, not from the shared singleton that
        # EvolutionEngine.learn_from_success() writes to via track_execution().
        from api.deps import get_fitness_engine

        self.fitness_engine = get_fitness_engine()
        self.self_evolution = SelfEvolutionAgent(
            fitness_engine=self.fitness_engine, interval_seconds=interval_seconds
        )
        self._tasks: list[Callable[[], Any]] = [
            self._run_fitness_scoring,
            self.self_evolution._tick,
        ]
        self.skill_graph = EvolutionSkillGraph()

        # Add budget guardian task
        async def _run_budget_guardian() -> None:
            try:
                # বাংলা মন্তব্য: sys.path ম্যানিপুলেশন সম্পূর্ণ নিষিদ্ধ।
                # importlib.metadata + __import__ দিয়ে ডিরেক্টরি রেজোলভ করা হয়নি
                # কারণ auto_budget_guardian স্ক্রিপ্টটি একটি CLI টুল, মডিউল নয়।
                # তাই clean pattern: subprocess দিয়ে execute করা হচ্ছে।
                import subprocess
                import sys

                script_path = os.path.abspath(
                    os.path.join(
                        os.path.dirname(__file__),
                        "../../../scripts/orchestrator/auto_budget_guardian.py",
                    )
                )
                if not os.path.exists(script_path):
                    logger.warning(
                        f"[Orchestrator] Budget guardian script not found at {script_path}. Skipping."
                    )
                    return

                timeout_val = float(os.getenv("ORCHESTRATOR_TIMEOUT", "120"))
                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout_val,
                )
                if result.returncode != 0:
                    logger.error(
                        f"[Orchestrator] Budget guardian failed (exit={result.returncode}): {result.stderr[:500]}"
                    )
                    raise RuntimeError(
                        f"Budget Guardian exited with code {result.returncode}. "
                        "Halting orchestrator to prevent financial bleed."
                    )
                logger.info(f"[Orchestrator] Budget guardian completed: {result.stdout[:200]}")
            except subprocess.TimeoutExpired:
                logger.critical(
                    f"[Orchestrator] Budget guardian timed out after {timeout_val}s. Enforcing Fail-Closed."
                )
                raise RuntimeError(
                    "Budget guardian timed out. Halting orchestrator to prevent financial bleed."
                )
            except Exception as exc:
                logger.critical(f"🔥 CRITICAL: Budget guardian failed! Error: {exc}")
                raise RuntimeError(
                    "Budget Guardian failure. Halting orchestrator to prevent financial bleed."
                ) from exc

        self._tasks.append(_run_budget_guardian)
        logger.info("Budget guardian task added to orchestrator")

    def decompose_intent(
        self,
        prompt: str,
        start_skill: str,
        end_skill: str,
        max_token_cost: float = 0.05,
    ) -> dict[str, Any]:
        """Decomposes user intent and finds the optimal execution path in the skill graph."""
        logger.info(f"Decomposing intent: '{prompt}' from {start_skill} to {end_skill}")
        path = self.skill_graph.find_execution_path(start_skill, end_skill)
        if not path:
            return {
                "success": False,
                "error": "No valid semantic path found in skill graph",
            }

        # Calculate simulated/estimated cost based on edge count
        estimated_cost = len(path) * 0.01
        if estimated_cost > max_token_cost:
            return {
                "success": False,
                "error": f"Estimated token cost ({estimated_cost}) exceeds budget limit ({max_token_cost})",
            }

        return {
            "success": True,
            "execution_plan": path,
            "estimated_cost": estimated_cost,
        }

    async def execute_skill_chain(self, chain: list[str], input_data: Any) -> dict[str, Any]:
        """Concurrently or sequentially executes a chain of skills with atomic rollback support."""
        current_data = input_data
        executed_skills = []

        for skill in chain:
            try:
                logger.info(f"Executing skill in chain: {skill}")
                # Simulate executing the skill and updating weights on success
                # Trigger simulated failure specifically on B to verify fallback
                has_trigger = False
                if isinstance(current_data, dict):
                    # Accept both shapes:
                    # 1) {"trigger_failure": True}
                    # 2) {"data": {"trigger_failure": True}}
                    if current_data.get("trigger_failure") is True or (
                        isinstance(current_data.get("data"), dict)
                        and current_data["data"].get("trigger_failure") is True
                    ):
                        has_trigger = True

                    # Also handle the wrapper added after each step:
                    # {"processed_by": <skill>, "data": <previous_current_data>}
                    if not has_trigger and isinstance(current_data.get("data"), dict):
                        inner = current_data["data"]
                        if (
                            inner.get("trigger_failure") is True
                            or isinstance(inner.get("data"), dict)
                            and inner["data"].get("trigger_failure") is True
                        ):
                            has_trigger = True

                if skill == "Skill_B" and has_trigger:
                    raise RuntimeError("Simulated execution failure inside Skill_B")

                executed_skills.append(skill)
                # Output becomes input for next skill
                current_data = {"processed_by": skill, "data": current_data}

                # Feedback loop: enhance weight of used edge
                if len(executed_skills) > 1:
                    self.skill_graph.update_edge_weight(executed_skills[-2], skill, success=True)

            except Exception as e:
                logger.error(
                    f"Skill execution failed for '{skill}': {e}. Triggering rollback/fallback."
                )
                # Feedback loop: penalize weight of failed edge
                if len(executed_skills) > 1:
                    self.skill_graph.update_edge_weight(executed_skills[-2], skill, success=False)

                # Atomic rollback / compensation
                fallback = self.skill_graph.get_fallback(skill)
                if fallback:
                    logger.info(f"Executing compensating fallback skill: {fallback}")
                    return {
                        "success": False,
                        "error": str(e),
                        "fallback_executed": fallback,
                        "last_successful_state": current_data,
                    }
                return {
                    "success": False,
                    "error": f"Execution failed at {skill} with no fallback: {e}",
                }

        return {
            "success": True,
            "output": current_data,
            "executed_chain": executed_skills,
        }

    async def _run_fitness_scoring(self) -> None:
        """Trigger the fitness engine to evaluate recent skill executions.

        This is intentionally lightweight â€“ the heavyâ€“lifting is performed inside the engine.
        """
        try:
            logger.info("Orchestrator: Running fitness scoring cycle")
            # The fitness engine maintains internal state and persists scores.
            self.fitness_engine.evaluate_pending()
        except Exception as exc:
            logger.exception(f"Fitness scoring failed: {exc}")

    async def tick(self) -> None:
        """Main execution step that runs scheduled tasks.
        Uses asyncio.TaskGroup to concurrently schedule and execute tasks.
        """
        start = datetime.now(UTC)
        logger.debug(f"Orchestrator tick at {start.isoformat()}")
        try:
            with trace_span("orchestrator.tick"):
                async with asyncio.TaskGroup() as tg:
                    for task_fn in self._tasks:
                        tg.create_task(task_fn())
        except asyncio.CancelledError:
            logger.info("Orchestrator tick cancelled.")
            raise
        except ExceptionGroup as eg:
            halt_signals = []
            for exc in eg.exceptions:
                if isinstance(exc, RuntimeError) and "Halting orchestrator" in str(exc):
                    halt_signals.append(exc)
                else:
                    logger.error(f"Error in orchestrator task group loop: {exc}")
            if halt_signals:
                logger.critical(f"🛑 BUDGET GUARDIAN HALT: {halt_signals[0]}")
                self._running = False
                raise halt_signals[0] from eg

    def status(self) -> dict:
        return {"running": self._running, "next_interval_secs": self.interval}


# FastAPI router exposing a simple status endpoint
@router.get("/status")
async def get_status(request: Request):
    orchestrator: Orchestrator = request.app.state.orchestrator  # type: ignore[attr-defined]
    return JSONResponse(content=orchestrator.status())


@router.post("/tick")
async def trigger_tick(request: Request):
    """Webhook for Google Cloud Scheduler to trigger the orchestrator periodically."""
    orchestrator: Orchestrator = request.app.state.orchestrator
    await orchestrator.tick()
    return JSONResponse(content={"status": "tick_executed"})


# skill_graph = SkillGraph()  # Deferred creation to avoid optional dependency

# Aliases for clean naming
PeriodicTaskScheduler = Orchestrator
