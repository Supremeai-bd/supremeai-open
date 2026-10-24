"""Compatibility bridge: re-export all specialized swarm agent roles from swarm_agent_roles.py."""

from core.orchestration.swarm_agent_roles import (  # noqa: F401
    ArchitectureAgent,
    CodeGeneratorAgent,
    GuardianAgent,
    IntegrationAgent,
    QAAgent,
    ReflectionAgent,
    ResearchAgent,
    SwarmAgentBase,
    ToolExecutorAgent,
    ToolSynthesizerAgent,
)

__all__ = [
    "SwarmAgentBase",
    "ArchitectureAgent",
    "CodeGeneratorAgent",
    "QAAgent",
    "GuardianAgent",
    "ToolExecutorAgent",
    "ToolSynthesizerAgent",
    "ResearchAgent",
    "ReflectionAgent",
    "IntegrationAgent",
]
