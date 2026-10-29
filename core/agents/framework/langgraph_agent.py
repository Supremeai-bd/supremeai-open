"""Backward compatibility shim for core.agents.framework.langgraph_agent.

Canonical domain module: core.agents.framework.autonomous_task_orchestrator
"""

from core.agents.framework.autonomous_task_orchestrator import (
    AutonomousTaskOrchestrator,  # noqa: F401 — deliberate re-export (facade __all__)
    SupremeOrchestrator,  # noqa: F401 — deliberate re-export (facade __all__)
)

__all__ = ["SupremeOrchestrator", "AutonomousTaskOrchestrator"]
