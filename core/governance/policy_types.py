"""Policy types — typed schema for Policy Engine (#4049).

বাংলা: Policy Engine-এর typed schema। প্রতিটি policy rule একটি PolicyRule
dataclass — condition + action + scope।
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PolicyAction(StrEnum):
    """What the policy does when triggered."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"  # Tier-3
    RATE_LIMIT = "rate_limit"
    LOG_ONLY = "log_only"  # advisory


class PolicyScope(StrEnum):
    """What the policy applies to."""

    AGENT = "agent"  # per-agent policy
    TASK_TYPE = "task_type"  # per-task-type policy
    PROVIDER = "provider"  # per-provider policy
    TENANT = "tenant"  # per-tenant policy
    GLOBAL = "global"  # applies everywhere


@dataclass(frozen=True)
class PolicyRule:
    """A single policy rule — condition + action + scope."""

    rule_id: str
    name: str
    description: str
    scope: PolicyScope
    action: PolicyAction
    # Conditions (all must match for rule to trigger)
    agent_roles: list[str] = field(default_factory=list)  # empty = all roles
    task_types: list[str] = field(default_factory=list)  # empty = all tasks
    providers: list[str] = field(default_factory=list)  # empty = all providers
    # Constraints
    max_cost_per_call_usd: float | None = None
    max_cost_per_task_usd: float | None = None
    require_health_status: list[str] = field(default_factory=list)  # ["healthy", "degraded"]
    require_security_clearance: str = ""  # "low", "medium", "high"
    # Metadata
    priority: int = 100  # lower = higher priority
    enabled: bool = True
    created_at: str = ""
    created_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope.value,
            "action": self.action.value,
            "agent_roles": self.agent_roles,
            "task_types": self.task_types,
            "providers": self.providers,
            "max_cost_per_call_usd": self.max_cost_per_call_usd,
            "max_cost_per_task_usd": self.max_cost_per_task_usd,
            "require_health_status": self.require_health_status,
            "require_security_clearance": self.require_security_clearance,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    """Result of evaluating a request against all policies."""

    allowed: bool
    matched_rules: list[PolicyRule]
    denial_reason: str = ""
    cost_limit_usd: float | None = None
    required_security_clearance: str = ""
    requires_approval: bool = False  # Tier-3

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "matched_rules": [r.to_dict() for r in self.matched_rules],
            "denial_reason": self.denial_reason,
            "cost_limit_usd": self.cost_limit_usd,
            "required_security_clearance": self.required_security_clearance,
            "requires_approval": self.requires_approval,
        }
