"""Facade — renamed/moved to core.agents.framework.task_runner_agent (Phase 1 consolidation, 2026-08-25).
This is the task-execution step-runner (StepResult + skill-creator integration) -- NOT the same as
the former backend/agents/autonomous_agent.py (system-health monitor, now
core.agents.legacy.system_health_agent). The two were distinct classes that happened to share a filename.
"""

from core.agents.framework.task_runner_agent import AutonomousAgent, StepResult  # noqa: F401
