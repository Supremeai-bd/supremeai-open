"""Backward compatibility shim for core.agents.framework.langgraph_agent.

Canonical domain module: core.agents.framework.autonomous_task_orchestrator
"""

# noqa: F401 - deliberate compat facade (docstring-declared backward-compatibility
# shim; zero in-repo consumers; kept for satellite import surface stability).
from core.agents.framework.autonomous_task_orchestrator import (  # noqa: F401
    AutonomousTaskOrchestrator,
    SupremeOrchestrator,
)

__all__ = ["SupremeOrchestrator", "AutonomousTaskOrchestrator"]
