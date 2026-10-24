# backend/evolution/canary_manager.py
"""Real Canary Rollout Controller and Automatic Rollback Gate."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.logging_config import logger
from evolution.change_proposal import (
    ChangeProposalManager,
    ProposalState,
    get_change_manager,
)


@dataclass
class CanaryTrial:
    proposal_id: str
    sample_ratio: float = 0.10
    total_trials: int = 0
    successful_trials: int = 0
    failed_trials: int = 0
    total_latency_ms: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)

    @property
    def success_rate(self) -> float:
        return (self.successful_trials / self.total_trials) if self.total_trials > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return (self.total_latency_ms / self.total_trials) if self.total_trials > 0 else 0.0


class CanaryRolloutController:
    """Manages progressive canary deployments of AI ChangeProposals with automatic rollback."""

    def __init__(self, proposal_manager: ChangeProposalManager | None = None) -> None:
        self.proposal_manager = proposal_manager or get_change_manager()
        self.active_canaries: dict[str, CanaryTrial] = {}

    def deploy_canary(self, proposal_id: str, sample_ratio: float = 0.10) -> bool:
        proposal = self.proposal_manager.proposals.get(proposal_id)
        if not proposal:
            return False

        trial = CanaryTrial(proposal_id=proposal_id, sample_ratio=sample_ratio)
        self.active_canaries[proposal_id] = trial
        proposal.advance_state(ProposalState.CANARY_ACTIVE)
        logger.info(
            f"🐤 Canary active for [{proposal_id}] with traffic ratio: {sample_ratio * 100}%"
        )
        return True

    def should_route(
        self,
        proposal_id: str,
        client_context: str | None = None,
        force_canary: bool = False,
    ) -> bool:
        """Evaluate if an incoming request should route to the canary or baseline.

        Uses deterministic hash-bucketing on client_context (e.g. user_id, session_id,
        or IP) to ensure session stickiness across the trial period. If no context
        is provided, evaluates pseudo-randomly against the trial's sample_ratio.
        """
        trial = self.active_canaries.get(proposal_id)
        if not trial:
            return False

        if force_canary:
            return True

        if client_context:
            digest = hashlib.md5(f"{proposal_id}:{client_context}".encode()).hexdigest()
            bucket = int(digest, 16) % 100
            return bucket < (trial.sample_ratio * 100)

        return random.random() < trial.sample_ratio

    def route_request(
        self,
        proposal_id: str,
        headers: dict[str, str] | None = None,
        client_id: str | None = None,
    ) -> bool:
        """Route request by inspecting headers and client identification.

        Supports edge / client overrides:
        - Header 'X-Canary: true' or 'X-Canary: <proposal_id>' forces canary.
        - Header 'X-Canary: false' or 'X-Canary: none' forces baseline.
        """
        if headers:
            hdr_map = {k.lower(): v for k, v in headers.items()}
            canary_hdr = hdr_map.get("x-canary", "").lower()
            if canary_hdr in ("true", "1", proposal_id.lower()):
                return self.should_route(proposal_id, force_canary=True)
            if canary_hdr in ("false", "0", "none"):
                return False

            client_context = client_id or hdr_map.get("x-user-id") or hdr_map.get("x-request-id")
        else:
            client_context = client_id

        return self.should_route(proposal_id, client_context=client_context)

    def record_observation(self, proposal_id: str, success: bool, latency_ms: float = 0.0) -> None:
        trial = self.active_canaries.get(proposal_id)
        if not trial:
            return

        trial.total_trials += 1
        trial.total_latency_ms += latency_ms
        if success:
            trial.successful_trials += 1
        else:
            trial.failed_trials += 1

        # Check for immediate regression trigger
        if trial.total_trials >= 3 and trial.success_rate < 0.60:
            self.trigger_rollback(
                proposal_id, reason=f"High failure rate in canary ({trial.success_rate * 100:.1f}%)"
            )

    def get_canary_stats(self, proposal_id: str) -> dict[str, Any]:
        trial = self.active_canaries.get(proposal_id)
        if not trial:
            return {"active": False, "success_rate": 0.0, "total_trials": 0}
        return {
            "active": True,
            "success_rate": trial.success_rate,
            "total_trials": trial.total_trials,
            "avg_latency_ms": trial.avg_latency_ms,
        }

    def evaluate_and_promote(
        self,
        proposal_id: str,
        min_trials: int = 5,
        min_success_rate: float = 0.85,
    ) -> bool:
        trial = self.active_canaries.get(proposal_id)
        proposal = self.proposal_manager.proposals.get(proposal_id)
        if not trial or not proposal:
            return False

        if trial.total_trials < min_trials:
            logger.info(
                f"⏳ Canary for [{proposal_id}] still accumulating samples ({trial.total_trials}/{min_trials})"
            )
            return False

        if trial.success_rate >= min_success_rate:
            proposal.canary_success_rate = trial.success_rate
            proposal.advance_state(ProposalState.PROMOTED)
            self.active_canaries.pop(proposal_id, None)
            logger.info(
                f"🎉 Canary PASSED! Proposal [{proposal_id}] promoted to production ({trial.success_rate * 100:.1f}%)"
            )
            return True
        else:
            self.trigger_rollback(
                proposal_id,
                reason=f"Failed minimum canary success threshold ({trial.success_rate * 100:.1f}% < {min_success_rate * 100}%)",
            )
            return False

    def trigger_rollback(self, proposal_id: str, reason: str) -> None:
        self.active_canaries.pop(proposal_id, None)
        self.proposal_manager.rollback(proposal_id, reason)
        logger.warning(f"🚨 ROLLBACK TRIGGERED on [{proposal_id}]: {reason}")


# Global Singleton
_canary_controller: CanaryRolloutController | None = None


def get_canary_controller() -> CanaryRolloutController:
    global _canary_controller
    if _canary_controller is None:
        _canary_controller = CanaryRolloutController()
    return _canary_controller
