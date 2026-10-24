"""FCC circle centers — one local coordinator per capability circle.

Each center owns its domain locally (registry, permissions, retries,
health, caching, events, adapter selection) and never imports another
center. Cross-circle traffic goes through the Global Governance Core
(``core.circles.governance_core``) using the canonical envelopes.

Boundary enforcement: ``tests/test_fcc_boundaries.py`` fails the build if
a center imports another center, or if the governance core grows domain
imports.
"""

from __future__ import annotations

from collections.abc import Iterator

from core.circles.centers.admin_center import AdminCenter
from core.circles.centers.artifact_center import ArtifactCenter
from core.circles.centers.base import (
    CenterHealth,
    CircleCenter,
    LocalCapability,
    RetryPolicy,
)
from core.circles.centers.browser_center import BrowserCenter
from core.circles.centers.evolution_center import EvolutionCenter
from core.circles.centers.gateway_center import GatewayCenter
from core.circles.centers.llm_center import LLMCenter
from core.circles.centers.mcp_center import MCPCenter
from core.circles.centers.memory_center import MemoryCenter
from core.circles.centers.realtime_center import RealtimeCenter
from core.circles.centers.task_center import TaskCenter
from core.circles.contracts import CircleName

_CENTER_TYPES: tuple[type[CircleCenter], ...] = (
    GatewayCenter,
    LLMCenter,
    MemoryCenter,
    TaskCenter,
    BrowserCenter,
    MCPCenter,
    AdminCenter,
    RealtimeCenter,
    ArtifactCenter,
    EvolutionCenter,
)


def build_default_centers() -> tuple[CircleCenter, ...]:
    """Construct one instance of every FCC circle center."""
    return tuple(center_type() for center_type in _CENTER_TYPES)


def iter_center_types() -> Iterator[type[CircleCenter]]:
    return iter(_CENTER_TYPES)


def center_types_by_circle() -> dict[CircleName, type[CircleCenter]]:
    return {center_type.circle: center_type for center_type in _CENTER_TYPES}


__all__ = [
    "AdminCenter",
    "ArtifactCenter",
    "BrowserCenter",
    "CenterHealth",
    "CircleCenter",
    "EvolutionCenter",
    "GatewayCenter",
    "LLMCenter",
    "LocalCapability",
    "MCPCenter",
    "MemoryCenter",
    "RealtimeCenter",
    "RetryPolicy",
    "TaskCenter",
    "build_default_centers",
    "center_types_by_circle",
    "iter_center_types",
]
