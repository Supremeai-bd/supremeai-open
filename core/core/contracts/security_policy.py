"""Local authorization, approval, and sandbox policy primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .canonical import ApprovalRequest, ApprovalStatus, ExecutionContext


class PolicyDenied(PermissionError):
    pass


class SandboxMode(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE = "workspace"
    PRIVILEGED = "privileged"


@dataclass(frozen=True)
class Actor:
    actor_id: str
    tenant_id: str
    roles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CapabilityPolicy:
    capability: str
    allowed_roles: frozenset[str]
    minimum_approval_risk: str = "high"
    sandbox: SandboxMode = SandboxMode.READ_ONLY


# Issue #684 (H-04): single canonical severity ladder for the low/medium/high/
# critical vocabulary. This was previously redefined per module with drifting
# integer scales (core.security.tool_gateway.RISK_LEVELS, local severity_order
# maps in the secret scanner and digital twin — some ranking critical=3, others
# critical=4), so a numeric comparison against one module's constant silently
# mismatched another's. Rank ascending: higher == more severe. Modules that need
# an extra tier (e.g. "info") derive from this mapping instead of redefining it.
SEVERITY_LEVELS: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_RISK_ORDER = SEVERITY_LEVELS


def authorize(
    actor: Actor,
    context: ExecutionContext,
    policy: CapabilityPolicy,
    approval: ApprovalRequest | None = None,
) -> None:
    if actor.tenant_id != context.tenant_id or actor.actor_id != context.actor_id:
        raise PolicyDenied("actor does not belong to execution tenant")
    if not actor.roles.intersection(policy.allowed_roles):
        raise PolicyDenied("actor lacks capability role")
    if _RISK_ORDER.get(context.risk_level, 99) >= _RISK_ORDER[policy.minimum_approval_risk]:
        if (
            approval is None
            or approval.status is not ApprovalStatus.APPROVED
            or approval.context.execution_id != context.execution_id
        ):
            raise PolicyDenied("explicit approval required")


def validate_workspace_path(root: Path, requested: Path) -> Path:
    root_resolved = root.resolve()
    target = (root / requested).resolve() if not requested.is_absolute() else requested.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise PolicyDenied("path escapes workspace sandbox")
    return target


__all__ = [
    "Actor",
    "CapabilityPolicy",
    "SEVERITY_LEVELS",
    "PolicyDenied",
    "SandboxMode",
    "authorize",
    "validate_workspace_path",
]
