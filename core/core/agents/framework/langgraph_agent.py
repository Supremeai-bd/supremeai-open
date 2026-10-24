"""Backward compatibility shim for core.agents.framework.langgraph_agent.

Canonical domain module: core.agents.framework.autonomous_task_orchestrator
"""

from core.agents.framework.autonomous_task_orchestrator import (
    AutonomousTaskOrchestrator,
    SupremeOrchestrator,
)

__all__ = ["SupremeOrchestrator", "AutonomousTaskOrchestrator"]
