"""Facade — renamed/moved to core.agents.legacy.system_health_agent (Phase 1 consolidation, 2026-08-25).
This is the system-health monitoring base class (memory/DB/API/security checks + self-healing loop) --
NOT the same as the former backend/brain/autonomous_agent.py (task-execution step-runner, now
core.agents.framework.task_runner_agent). The two were distinct classes that happened to share a filename.
"""

from core.agents.legacy.system_health_agent import (  # noqa: F401
    APIHealthAgent,
    AutonomousAgent,
    DatabaseHealthAgent,
    MemoryHealthAgent,
    SecurityHealthAgent,
)
