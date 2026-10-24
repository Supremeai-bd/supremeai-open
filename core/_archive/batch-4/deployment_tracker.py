"""Deployment Tracker — delegates to canonical adaptive_engine.deployment_tracker.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.deployment_tracker import (
    DeploymentNotFoundError,
    DeploymentRecord,
    DeploymentStateError,
    DeploymentStatus,
    DeploymentTracker,
    get_deployment_tracker,
)

__all__ = [
    "DeploymentStatus",
    "DeploymentRecord",
    "DeploymentTracker",
    "get_deployment_tracker",
    "DeploymentStateError",
    "DeploymentNotFoundError",
]
