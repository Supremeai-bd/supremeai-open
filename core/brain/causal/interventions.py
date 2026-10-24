# backend/brain/causal/interventions.py
"""
Causal Intervention Tracker
Logs system/agent interventions (deployments, config changes, scaling) to serve as raw data for causal inference.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class InterventionType(Enum):
    DEPLOYMENT = "deployment"
    CONFIG_CHANGE = "config_change"
    SCALING = "scaling"
    MANUAL_ACTION = "manual_action"
    EXTERNAL_EVENT = "external_event"


@dataclass
class Intervention:
    """Model tracking a system/agent change or intervention."""

    id: str
    timestamp: datetime
    type: InterventionType
    actor: str  # agent/user/system
    target_service: str
    description: str
    before_state: dict[str, Any]  # Metrics snapshot before change
    after_state: dict[str, Any]  # Metrics snapshot after change
    confidence: float = 1.0


class InterventionTracker:
    """Tracks and retrieves system interventions for causal graph construction."""

    def __init__(self, db_session=None):
        self.interventions: list[Intervention] = []
        self.db = db_session

    async def log_intervention(self, intervention: Intervention):
        """Log intervention with before/after state metrics."""
        self.interventions.append(intervention)

        if self.db and hasattr(self.db, "collection"):
            await self.db.collection("interventions").add(intervention.__dict__)

    async def get_natural_experiments(
        self, service: str, time_window_hours: int = 72
    ) -> list[Intervention]:
        """Find natural experiment data points for causal analysis."""
        cutoff = datetime.utcnow() - timedelta(hours=time_window_hours)
        return [
            i for i in self.interventions if i.target_service == service and i.timestamp > cutoff
        ]
