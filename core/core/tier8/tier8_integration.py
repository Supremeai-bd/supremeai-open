"""Tier-8 Integration Wiring — Drop-in for lifespan.py or app.py.

This module provides a single async function `init_tier8()` that
registers all four Tier-8 agents with the existing SupremeAI
service registry, event bus, and health monitor.

No hardcoded values. All config via env vars or ConfigProxy.
"""

from __future__ import annotations

import os
from typing import Any

from core.health.health_monitor import get_health_monitor
from core.messaging.event_bus import EventBus
from core.services import ServiceRegistry
from core.tier8 import (
    get_agent_evolution_engine,
    get_self_improvement_agent,
    get_skill_marketplace_curator,
    get_swarm_coordination_agent,
)


async def init_tier8(registry: ServiceRegistry | None = None) -> dict[str, Any]:
    """Initialize all Tier-8 agents and wire into the service mesh.

    Args:
        registry: Optional ServiceRegistry instance. If None, uses global.

    Returns:
        Status dict with agent states.
    """
    if registry is None:
        registry = ServiceRegistry()

    # Initialize agents
    self_improve = get_self_improvement_agent()
    evolution = get_agent_evolution_engine()
    swarm = get_swarm_coordination_agent()
    marketplace = get_skill_marketplace_curator()

    # Wire into service registry
    # বাংলা মন্তব্য: ServiceRegistry-তে রেজিস্টার করার সময় async factory পাঠানো প্রয়োজন কারণ get() মেথডটি এটিকে await করে
    async def get_self_improve() -> Any:
        return self_improve

    async def get_evolution() -> Any:
        return evolution

    async def get_swarm() -> Any:
        return swarm

    async def get_marketplace() -> Any:
        return marketplace

    registry.register("self_improvement_agent", get_self_improve)
    registry.register("agent_evolution_engine", get_evolution)
    registry.register("swarm_coordination_agent", get_swarm)
    registry.register("skill_marketplace_curator", get_marketplace)

    # Wire into health monitor
    health = get_health_monitor()
    health.register_probe("tier8_self_improve", lambda: self_improve.execute(action="status"))
    health.register_probe("tier8_evolution", lambda: evolution.execute(action="status"))
    health.register_probe("tier8_swarm", lambda: swarm.execute(action="status"))
    health.register_probe("tier8_marketplace", lambda: marketplace.execute(action="status"))

    # Subscribe to event bus for cross-agent communication
    event_bus = EventBus()
    await event_bus.register_listener("tier8.heartbeat", _on_tier8_heartbeat)

    # Auto-start if configured
    if os.getenv("TIER8_AUTO_START", "true").lower() == "true":
        await self_improve.execute(action="start")
        await evolution.execute(action="start")
        await swarm.execute(action="start")
        await marketplace.execute(action="start")

    return {
        "status": "initialized",
        "agents": {
            "self_improvement": await self_improve.execute(action="status"),
            "evolution": await evolution.execute(action="status"),
            "swarm": await swarm.execute(action="status"),
            "marketplace": await marketplace.execute(action="status"),
        },
    }


async def shutdown_tier8() -> dict[str, str]:
    """Gracefully shutdown all Tier-8 agents."""
    await get_self_improvement_agent().execute(action="stop")
    await get_agent_evolution_engine().execute(action="stop")
    await get_swarm_coordination_agent().execute(action="stop")
    await get_skill_marketplace_curator().execute(action="stop")
    return {"status": "shutdown_complete"}


async def _on_tier8_heartbeat(event: dict[str, Any]) -> None:
    """Handle cross-agent heartbeat events."""
    # Placeholder for future mesh-wide coordination logic
    pass
