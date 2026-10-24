# backend/runtime/planner.py
"""Canonical Planner Subsystem for SupremeAI Control Plane."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from core.logging_config import logger
from core.task_contract import RiskLevel, TaskContract, VerificationPolicy


class StepStatus(StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """Individual atomic execution unit within a plan."""

    step_id: str
    objective: str
    dependencies: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    expected_output: str = ""
    verification_policy: VerificationPolicy = VerificationPolicy.STANDARD
    status: StepStatus = StepStatus.PENDING
    result: Any | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "objective": self.objective,
            "dependencies": self.dependencies,
            "required_capabilities": self.required_capabilities,
            "status": self.status.value,
            "risk_level": self.risk_level.value,
            "expected_output": self.expected_output,
            "error": self.error,
        }


@dataclass
class Plan:
    """Hierarchical execution blueprint decomposed from a TaskContract."""

    task_id: str
    plan_id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:10]}")
    steps: list[PlanStep] = field(default_factory=list)
    estimated_cost_usd: float = 0.05
    estimated_tokens: int = 2000
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "steps": [s.to_dict() for s in self.steps],
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_tokens": self.estimated_tokens,
            "created_at": self.created_at.isoformat(),
        }


class CanonicalPlanner:
    """Decomposes high-level TaskContracts into verifiable execution graphs."""

    def __init__(self) -> None:
        pass

    async def create_plan(self, task: TaskContract) -> Plan:
        """Analyze task and produce a structured, multi-step Plan."""
        logger.info(f"🧠 [Planner] Generating plan for Task [{task.task_id}]: {task.goal[:60]}")

        steps: list[PlanStep] = []

        # 1. Understanding & Context Extraction Step
        step_1 = PlanStep(
            step_id=f"{task.task_id}_step_1",
            objective="Analyze constraints and retrieve required domain context",
            required_capabilities=task.required_capabilities,
            risk_level=RiskLevel.LOW,
            expected_output="Domain parameters and synthesized constraints",
        )
        steps.append(step_1)

        # 2. Main Execution Step
        step_2 = PlanStep(
            step_id=f"{task.task_id}_step_2",
            objective=f"Execute primary goal: {task.goal}",
            dependencies=[step_1.step_id],
            required_capabilities=task.required_capabilities,
            allowed_tools=task.allowed_tools,
            risk_level=task.risk_level,
            expected_output="Target solution matching success criteria",
            verification_policy=task.verification_policy,
        )
        steps.append(step_2)

        # 3. Verification Step
        step_3 = PlanStep(
            step_id=f"{task.task_id}_step_3",
            objective="Validate solution against AST syntax, schema, and security criteria",
            dependencies=[step_2.step_id],
            risk_level=RiskLevel.LOW,
            expected_output="Objective verification report",
            verification_policy=task.verification_policy,
        )
        steps.append(step_3)

        plan = Plan(task_id=task.task_id, steps=steps)
        task.plan_steps = [s.to_dict() for s in steps]
        return plan


# Global Singleton
_planner_instance: CanonicalPlanner | None = None


def get_planner() -> CanonicalPlanner:
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = CanonicalPlanner()
    return _planner_instance
