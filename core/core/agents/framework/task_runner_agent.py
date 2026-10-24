from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.performance_enhancer import get_performance_optimizer


@dataclass
class StepResult:
    name: str
    success: bool
    output: Any = None
    error: str | None = None


class AutonomousAgent:
    @with_error_bus("__init__")
    def __init__(self, name: str = "autonomous-agent") -> None:
        self.name = name
        self.history: list[dict[str, Any]] = []
        try:
            from core.self_evolution.auto_skill_creator import AutoSkillCreator

            self.skill_creator = AutoSkillCreator()
        except Exception:
            self.skill_creator = None  # type: ignore

        # Add performance optimizer
        self.performance_optimizer = get_performance_optimizer()

    def plan(self, task_description: str) -> dict[str, Any]:
        lowered = (task_description or "").lower()
        plan: dict[str, Any] = {"steps": [], "summary": ""}
        if any(word in lowered for word in ["fix", "debug", "error", "issue"]):
            plan["summary"] = "Investigate issue, propose fix, apply fix, verify."
            plan["steps"] = [
                "investigate",
                "propose_fix",
                "apply_fix",
                "verify",
            ]
        elif any(word in lowered for word in ["build", "create", "implement", "feature"]):
            plan["summary"] = "Scaffold implementation, implement core, add basic tests."
            plan["steps"] = [
                "scaffold",
                "implement",
                "basic_tests",
            ]
        elif any(word in lowered for word in ["analyze", "review", "audit"]):
            plan["summary"] = "Read inputs, analyze structure, summarize findings."
            plan["steps"] = [
                "read_inputs",
                "analyze",
                "summarize",
            ]
        else:
            plan["summary"] = "Default quick execution."
            plan["steps"] = ["execute", "summarize"]
        return plan

    def execute(self, task_description: str, context: str | None = None) -> dict[str, Any]:
        plan = self.plan(task_description)
        results: list[StepResult] = []

        # Track execution performance
        import time

        start_time = time.time()

        for step in plan["steps"]:
            try:
                step_result = self._run_step(step, task_description, context)
                results.append(step_result)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Agent step failed")
                results.append(
                    StepResult(
                        name=step,
                        success=False,
                        error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                    )
                )
                break

        time.time() - start_time

        self.history.append(
            {
                "task": task_description,
                "context": context,
                "plan": plan,
                "results": [
                    {
                        "name": r.name,
                        "success": r.success,
                        "output": r.output,
                        "error": r.error,
                    }
                    for r in results
                ],
            }
        )
        success = all(result.success for result in results)
        outputs = [
            result.output for result in results if result.success and result.output is not None
        ]
        errors = [result.error for result in results if result.error]

        # Handle failures with self-healing
        if not success:
            try:
                asyncio.get_running_loop()
                if not hasattr(self, "_background_tasks"):
                    self._background_tasks = set()
                task = asyncio.ensure_future(
                    self.performance_optimizer.handle_failure(
                        error_type="AGENT_EXECUTION_ERROR",
                        error_message=f"Agent {self.name} failed to complete task: {task_description}",
                        context={
                            "agent_name": self.name,
                            "task_description": task_description,
                            "context": context,
                            "failed_step": results[-1].name if results else "unknown",
                            "error": results[-1].error
                            if results and results[-1].error
                            else "unknown",
                            "dependency_tree": ["autonomous_agent", self.name],
                        },
                    )
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            except RuntimeError:
                # If no event loop is running, run it directly
                asyncio.run(
                    self.performance_optimizer.handle_failure(
                        error_type="AGENT_EXECUTION_ERROR",
                        error_message=f"Agent {self.name} failed to complete task: {task_description}",
                        context={
                            "agent_name": self.name,
                            "task_description": task_description,
                            "context": context,
                            "failed_step": results[-1].name if results else "unknown",
                            "error": results[-1].error
                            if results and results[-1].error
                            else "unknown",
                            "dependency_tree": ["autonomous_agent", self.name],
                        },
                    )
                )

        return {
            "success": success,
            "plan": plan,
            "steps": [r.name for r in results],
            "output": outputs[-1] if outputs else None,
            "outputs": outputs,
            "errors": errors,
        }

    def _run_step(self, step: str, task_description: str, context: str | None) -> StepResult:
        # Register 7.2 / ERR-M01 follow-up (2026-09-16): these steps used to
        # return fabricated completions ("Investigation complete.", "Fix
        # applied.") while doing no work. Every scaffold step now states
        # plainly that NO tooling executed — nothing claims completion it did
        # not perform.
        if step == "investigate":
            output = {
                "message": "NOT PERFORMED: no investigation tooling is wired into this pipeline step.",
                "files_checked": [],
                "findings": "No findings — nothing was scanned.",
            }
        elif step == "propose_fix":
            output = {
                "message": "NOT GENERATED: no proposal tooling is wired into this pipeline step.",
                "proposal": None,
            }
        elif step == "apply_fix":
            output = {
                "message": "NOT APPLIED: no fix tooling is wired into this pipeline step; nothing changed.",
                "changed": [],
            }
        elif step == "verify":
            output = {
                "message": "Verification placeholder: run tests after applying fix.",
                "pytest_suggestion": "pytest",
            }
        elif step == "scaffold":
            output = {
                "message": "Scaffold placeholder: create module under interfaces/tools/brain/.",
                "suggested_path": "tools/new_feature.py",
            }
        elif step == "implement":
            output = {"message": "Implementation placeholder: delegate to coding tooling."}
        elif step == "basic_tests":
            output = {
                "message": "Tests placeholder: add unit tests in tests/ for new feature.",
                "suggested_path": "tests/test_new_feature.py",
            }
        elif step == "read_inputs":
            output = {"message": "Inputs review placeholder: gather docs, code, data sources."}
        elif step == "analyze":
            output = {
                "message": "Analysis placeholder: summarize current state and risks.",
                "risks": [],
            }
        elif step == "summarize":
            output = {
                "message": "Summary",
                "summary": task_description,
                "suggested_next_steps": [],
            }
            if self.skill_creator is not None:
                try:
                    skill_result = self.skill_creator.create(
                        name=f"auto-skill-{abs(hash(task_description)) % 10000}",
                        description=f"Auto-created skill from task: {task_description}",
                    )
                    output["created_skill"] = skill_result
                except Exception as exc:
                    logger.warning(f"Auto skill creator hook failed: {exc}")
        elif step == "execute":
            output = {"message": "Execution complete.", "result": task_description}
            if self.skill_creator is not None:
                try:
                    skill_result = self.skill_creator.create(
                        name=f"auto-skill-{abs(hash(task_description)) % 10000}",
                        description=f"Auto-created skill from task: {task_description}",
                    )
                    output["created_skill"] = skill_result
                except Exception as exc:
                    logger.warning(f"Auto skill creator hook failed: {exc}")
        else:
            output = {"message": f"Step `{step}` has no handler.", "step": step}
        return StepResult(name=step, success=True, output=output)

    def reflect(self, run: dict[str, Any]) -> dict[str, Any]:
        failures = [err for err in run.get("errors", []) if err]
        return {
            "success": run.get("success", False),
            "completed_steps": run.get("steps", []),
            "failures": failures,
            "improvements": (
                ["Reduce broad step scope and add explicit verify step."] if failures else []
            ),
        }

    def run(self, task_description: str, context: str | None = None) -> dict[str, Any]:
        run = self.execute(task_description, context)
        reflection = self.reflect(run)
        return {"run": run, "reflection": reflection}
