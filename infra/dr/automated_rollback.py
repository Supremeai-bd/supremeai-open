"""
SupremeAI Fail-Closed Automated Rollback Engine
Monitors post-deployment verification and triggers instant reversion
if health checks fail to prevent broken states from persisting.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger("infra.automated_rollback")


class RollbackStatus(str, Enum):
    IDLE = "IDLE"
    DEPLOYING = "DEPLOYING"
    VERIFYING = "VERIFYING"
    STABLE = "STABLE"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


@dataclass
class RollbackEvent:
    deployment_id: str
    target_version: str
    rollback_version: str
    trigger_reason: str
    status: RollbackStatus
    executed_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AutomatedRollback:
    """Automates fail-closed deployment rollbacks based on health check feedback."""

    def __init__(
        self,
        revert_action: Callable[[str, str], bool] | None = None,
    ):
        self._revert_action = revert_action or self._default_revert_action
        self.history: list[RollbackEvent] = []
        self.current_status: RollbackStatus = RollbackStatus.IDLE

    def _default_revert_action(self, deployment_id: str, rollback_version: str) -> bool:
        """Simulated fail-closed revert action."""
        logger.info(
            "Executing automated revert for deployment %s to version %s",
            deployment_id,
            rollback_version,
        )
        return True

    def deploy_and_verify(
        self,
        deployment_id: str,
        target_version: str,
        last_stable_version: str,
        verification_fn: Callable[[], bool],
    ) -> RollbackStatus:
        """Deploys a target version, runs verification, and auto-rolls back if verification fails."""
        self.current_status = RollbackStatus.DEPLOYING

        # Verification phase
        self.current_status = RollbackStatus.VERIFYING
        verification_passed = False
        try:
            verification_passed = verification_fn()
        except (
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            TimeoutError,
            ConnectionError,
        ) as e:
            logger.error("Verification raised exception: %s", e)
            verification_passed = False

        if verification_passed:
            self.current_status = RollbackStatus.STABLE
            return self.current_status

        # Fail-closed automated rollback
        self.current_status = RollbackStatus.ROLLING_BACK
        revert_ok = False
        try:
            revert_ok = self._revert_action(deployment_id, last_stable_version)
        except (
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            TimeoutError,
            ConnectionError,
        ) as e:
            logger.error("Revert action failed: %s", e)
            revert_ok = False

        if revert_ok:
            self.current_status = RollbackStatus.ROLLED_BACK
        else:
            self.current_status = RollbackStatus.FAILED

        event = RollbackEvent(
            deployment_id=deployment_id,
            target_version=target_version,
            rollback_version=last_stable_version,
            trigger_reason="Post-deployment health verification check failed",
            status=self.current_status,
        )
        self.history.append(event)
        return self.current_status

    def get_latest_event(self) -> RollbackEvent | None:
        """Returns the most recent rollback event."""
        return self.history[-1] if self.history else None
