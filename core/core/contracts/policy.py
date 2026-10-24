"""Central policy evaluation boundary for capability execution.

বাংলা: capability, actor, tenant এবং approval এক জায়গায় evaluate হয়;
caller সরাসরি provider permission bypass করতে পারে না।
"""

from __future__ import annotations

from collections.abc import Callable

from core.contracts.canonical import PolicyDecision, PolicyEvaluation


class PolicyEvaluator:
    def __init__(self, rules: dict[str, Callable[[str, str], bool]] | None = None) -> None:
        self._rules = rules or {}

    def evaluate(
        self,
        *,
        capability_id: str,
        actor_id: str,
        tenant_id: str,
        required_permissions: tuple[str, ...] = (),
        granted_permissions: frozenset[str] = frozenset(),
        approval_id: str | None = None,
    ) -> PolicyEvaluation:
        if not actor_id or not tenant_id:
            return PolicyEvaluation(
                PolicyDecision.DENY, capability_id, actor_id, tenant_id, "missing_identity"
            )
        missing = [
            permission
            for permission in required_permissions
            if permission not in granted_permissions
        ]
        if missing:
            return PolicyEvaluation(
                PolicyDecision.REQUIRE_APPROVAL,
                capability_id,
                actor_id,
                tenant_id,
                f"missing_permissions:{','.join(missing)}",
                approval_id,
            )
        rule = self._rules.get(capability_id)
        if rule is not None and not rule(actor_id, tenant_id):
            return PolicyEvaluation(
                PolicyDecision.DENY, capability_id, actor_id, tenant_id, "rule_denied"
            )
        return PolicyEvaluation(
            PolicyDecision.ALLOW, capability_id, actor_id, tenant_id, "policy_allowed"
        )


__all__ = ["PolicyEvaluator"]
