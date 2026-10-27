"""3-Tier Auto-Routing boundary (issue #4050 — Roadmap v2 Phase 5.2).

বাংলা সারসংক্ষেপ:
------------------
সব routing automatic নয় — কিছু সিদ্ধান্ত admin ছাড়া চলবে না। 99.99% automatic
/ 0.01% admin boundary principle।

৩টি tier:
  1. Automatic — latency weight, temp health, cost optimization, retry/fallback
     → System (no human)। zero-latency, zero-human, logged only on anomaly।
  2. Governed-automatic — provider preference, model selection, benchmark routing
     → System (within admin-set policy bounds)। logged with policy reference।
  3. Admin-only — constitutional changes, security-sensitive providers, permission
     escalation, new external capability adoption, architecture changes
     → Human (admin decision gate)। BLOCKED until admin approval।

প্রতিটি routing decision তার tier-এ tag হয়। Tier-3 without approval → denial।
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RoutingTier(StrEnum):
    """3-Tier routing boundary (Roadmap v2 §5.2)."""

    AUTOMATIC = "automatic"  # Tier-1: system, no human
    GOVERNED_AUTOMATIC = "governed_automatic"  # Tier-2: system within admin bounds
    ADMIN_ONLY = "admin_only"  # Tier-3: human approval required


class DecisionResult(StrEnum):
    """Outcome of a routing decision."""

    ALLOW = "allow"
    DENY = "deny"
    PENDING_APPROVAL = "pending_approval"  # Tier-3 awaiting admin


@dataclass(frozen=True)
class RoutingDecision:
    """A single routing decision with tier classification + audit trail."""

    decision_id: str
    tier: RoutingTier
    result: DecisionResult
    provider: str
    task_type: str
    agent_id: str
    reason: str
    policy_reference: str = ""  # which policy rule governed this
    approval_id: str | None = None  # for Tier-3 approved decisions
    timestamp: str = field(default_factory=lambda: _dt.datetime.utcnow().isoformat() + "Z")
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "tier": self.tier.value,
            "result": self.result.value,
            "provider": self.provider,
            "task_type": self.task_type,
            "agent_id": self.agent_id,
            "reason": self.reason,
            "policy_reference": self.policy_reference,
            "approval_id": self.approval_id,
            "timestamp": self.timestamp,
            "details": self.details,
        }


# ─── Tier classification rules ──────────────────────────────────────────────

# Tier-1 (Automatic) — system decisions, no human needed
TIER1_ACTIONS = {
    "latency_weight_adjustment",  # adjust latency weight based on p95
    "temporary_provider_health",  # skip unhealthy provider
    "cost_optimization",  # pick cheaper provider within bounds
    "retry_fallback",  # retry with fallback provider
    "load_balancing",  # round-robin / least-connections
}

# Tier-2 (Governed-automatic) — system within admin-set bounds
TIER2_ACTIONS = {
    "provider_preference",  # prefer provider X for task Y
    "model_selection",  # pick model within allowed set
    "benchmark_routing",  # route based on Evaluation Engine scores
    "capacity_scaling",  # scale within limits
}

# Tier-3 (Admin-only) — human approval required
TIER3_ACTIONS = {
    "constitutional_change",  # modify AGENTS.md (Single Door SSOT)
    "security_sensitive_provider",  # new provider with data exposure risk
    "permission_escalation",  # grant new scope to agent
    "new_external_capability",  # adopt new external repo
    "architecture_change",  # modify system architecture
    "cost_limit_increase",  # raise cost ceiling
    "routing_weight_override",  # override default weights
}


def classify_tier(action: str) -> RoutingTier:
    """Classify a routing action into its tier.

    বাংলা: action নাম থেকে tier classify করে। অজানা action = Tier-3 (fail-safe)।
    """
    if action in TIER1_ACTIONS:
        return RoutingTier.AUTOMATIC
    if action in TIER2_ACTIONS:
        return RoutingTier.GOVERNED_AUTOMATIC
    if action in TIER3_ACTIONS:
        return RoutingTier.ADMIN_ONLY
    # Unknown action → fail-safe to Tier-3 (require admin review)
    return RoutingTier.ADMIN_ONLY


def make_routing_decision(
    action: str,
    provider: str,
    task_type: str,
    agent_id: str,
    reason: str,
    policy_reference: str = "",
    approval_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> RoutingDecision:
    """Make a routing decision with tier classification.

    বাংলা: একটি routing decision তৈরি করে। Tier-3 without approval → DENY।
    """
    tier = classify_tier(action)
    decision_id = f"rd-{uuid.uuid4().hex[:12]}"

    if tier == RoutingTier.ADMIN_ONLY and not approval_id:
        # Tier-3 without approval → pending
        result = DecisionResult.PENDING_APPROVAL
        reason = f"Tier-3 action requires admin approval: {reason}"
    elif tier == RoutingTier.ADMIN_ONLY and approval_id:
        # Tier-3 with approval → allow
        result = DecisionResult.ALLOW
    else:
        # Tier-1 + Tier-2 → allow (within bounds)
        result = DecisionResult.ALLOW

    return RoutingDecision(
        decision_id=decision_id,
        tier=tier,
        result=result,
        provider=provider,
        task_type=task_type,
        agent_id=agent_id,
        reason=reason,
        policy_reference=policy_reference,
        approval_id=approval_id,
        details=details or {},
    )


def is_blocked(decision: RoutingDecision) -> bool:
    """Check if a routing decision blocks the action."""
    return decision.result == DecisionResult.PENDING_APPROVAL
