"""backend/core/circles/governance/__init__.py — Governance Circle Boundary Facade.

Governs:
- Auth, Tenant isolation, Security, RBAC, Admin decisions, Audit journal
"""

from __future__ import annotations

from typing import Any

from core.circles.contracts import CircleName
from core.circles.registry import circle_registry


class GovernanceCircleFacade:
    """Bounded facade for Governance & Policy operations."""

    name = CircleName.ADMIN

    @classmethod
    def get_audit_trail(cls, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve structured governance event log."""
        return [
            {
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "circle": ev.circle.value if hasattr(ev.circle, "value") else str(ev.circle),
                "timestamp": ev.timestamp,
            }
            for ev in circle_registry.events()[-limit:]
        ]


governance_circle = GovernanceCircleFacade()
