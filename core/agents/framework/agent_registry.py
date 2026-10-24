"""
SupremeAI Unified Agent Framework & Registry
============================================
Consolidates agent execution across:
- backend/agents/ (domain agents: churn, security, insight, terminal)
- backend/core/agents/live/ (browser, vision, benchmark)
- backend/core/agents/framework/ (department, orchestrator, pydantic)

Canonical entry point for agent lifecycle (create -> active -> paused -> archived)
per AGENTS.md and SUPREMEAI_CORE_CONSTITUTION.md.
"""

from __future__ import annotations

from typing import Any

from core.logging_config import logger

# Canonical Agent Registry
_AGENT_REGISTRY: dict[str, Any] = {}


def register_agent(name: str, agent_class: Any, description: str = "") -> None:
    """Register an agent class into the central registry."""
    key = name.lower().strip()
    _AGENT_REGISTRY[key] = {
        "class": agent_class,
        "description": description,
        "name": name,
    }
    logger.debug(f"[AgentRegistry] Registered agent: {name}")


def get_agent(name: str) -> Any | None:
    """Retrieve an agent class by name."""
    entry = _AGENT_REGISTRY.get(name.lower().strip())
    return entry["class"] if entry else None


def list_registered_agents() -> list[dict[str, str]]:
    """List all registered agents in the unified framework."""
    return [
        {"name": info["name"], "description": info["description"]}
        for info in _AGENT_REGISTRY.values()
    ]


# Auto-register core live agents
try:
    from core.agents.live.browser_agent import BrowserAgent

    register_agent("browser_agent", BrowserAgent, "Playwright browser automation & web extraction")
except ImportError as exc:
    logger.warning(f"[AgentRegistry] Optional agent 'browser_agent' unavailable: {exc}")

try:
    from core.agents.live.vision_agent import VisionAgent

    register_agent("vision_agent", VisionAgent, "Visual analysis and UI inspection")
except ImportError as exc:
    logger.warning(f"[AgentRegistry] Optional agent 'vision_agent' unavailable: {exc}")

# Auto-register specialized agents
try:
    from agents.churn_prophet import ChurnProphet

    register_agent("churn_prophet", ChurnProphet, "Customer retention risk & behavioral scorer")
except ImportError as exc:
    logger.warning(f"[AgentRegistry] Optional agent 'churn_prophet' unavailable: {exc}")

try:
    from agents.insight_mage import InsightMage

    register_agent("insight_mage", InsightMage, "Data anomaly detection and metrics insight")
except ImportError as exc:
    logger.warning(f"[AgentRegistry] Optional agent 'insight_mage' unavailable: {exc}")

try:
    from agents.code_vulnerability_scanner_agent import CodeVulnerabilityScannerAgent

    register_agent(
        "vulnerability_scanner",
        CodeVulnerabilityScannerAgent,
        "Automated code security and vulnerability scanner",
    )
except ImportError as exc:
    logger.warning(f"[AgentRegistry] Optional agent 'vulnerability_scanner' unavailable: {exc}")

try:
    from core.agents.framework.agent_department import CodingAgent, ReviewAgent

    register_agent("coding_agent", CodingAgent, "Specialized software engineer agent")
    register_agent("review_agent", ReviewAgent, "Specialized code review & quality agent")
except ImportError as exc:
    logger.warning(
        f"[AgentRegistry] Optional agents 'coding_agent'/'review_agent' unavailable: {exc}"
    )
