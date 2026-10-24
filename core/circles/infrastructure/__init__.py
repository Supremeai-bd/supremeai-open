"""backend/core/circles/infrastructure/__init__.py — Infrastructure Circle Boundary Facade.

Governs:
- Database, Redis, Queues, Cache, Cloudflare, Network egress
"""

from __future__ import annotations

from core.circles.contracts import CircleName


class InfrastructureCircleFacade:
    """Bounded facade for Infrastructure operations."""

    name = CircleName.GATEWAY


infrastructure_circle = InfrastructureCircleFacade()
