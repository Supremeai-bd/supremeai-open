"""Policy Engine — full implementation (issue #4049).

বাংলা সারসংক্ষেপ:
------------------
Router একা যথেষ্ট নয় — Policy Engine বাধ্যতামূলক। কে কোন provider ব্যবহার
করবে, কোন task-এ, কত cost-এ, কোন security level-ে — এগুলো policy সিদ্ধান্ত।

এই module-এ:
  1. evaluate_routing() — 3-Tier boundary check (#4050 stub, preserved)
  2. enforce_routing() — enforce routing decision (#4050 stub, preserved)
  3. evaluate_policies() — full policy rule evaluation (NEW, #4049)
  4. enforce_policies() — full policy enforcement (NEW, #4049)

Policy rules are data-driven (YAML/DB), not hardcoded। #4050 3-Tier Routing-এর
stub এখানে preserved — backward compatible।
"""

from __future__ import annotations

from typing import Any

from core.logging_config import logger
from governance.policy_rules import get_active_rules, load_policy_rules
from governance.policy_types import PolicyAction, PolicyEvaluation, PolicyRule
from governance.routing_tiers import (
    DecisionResult,
    RoutingDecision,
    RoutingTier,
    is_blocked,
    make_routing_decision,
)

# ─── #4050 stub (preserved for backward compat) ─────────────────────────────


def evaluate_routing(
    action: str,
    provider: str,
    task_type: str,
    agent_id: str,
    reason: str = "",
    approval_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> RoutingDecision:
    """Evaluate a routing request through the 3-Tier boundary (#4050 stub).

    বাংলা: 3-Tier routing decision — preserved from #4050।
    """
    decision = make_routing_decision(
        action=action,
        provider=provider,
        task_type=task_type,
        agent_id=agent_id,
        reason=reason,
        approval_id=approval_id,
        details=details,
    )

    log_data = {
        "decision_id": decision.decision_id,
        "tier": decision.tier.value,
        "result": decision.result.value,
        "provider": decision.provider,
        "task_type": decision.task_type,
        "agent_id": decision.agent_id,
        "reason": decision.reason,
        "policy_reference": decision.policy_reference,
        "approval_id": decision.approval_id,
    }

    if decision.tier == RoutingTier.ADMIN_ONLY and not approval_id:
        logger.warning(f"RoutingDecision BLOCKED (Tier-3 needs approval): {log_data}")
    elif decision.tier == RoutingTier.GOVERNED_AUTOMATIC:
        logger.info(f"RoutingDecision GOVERNED: {log_data}")
    else:
        logger.debug(f"RoutingDecision AUTO: {log_data}")

    return decision


def enforce_routing(decision: RoutingDecision) -> bool:
    """Enforce a routing decision — returns True if allowed, False if blocked.

    বাংলা: #4050 stub — preserved for backward compat।
    """
    if is_blocked(decision):
        logger.warning(
            f"Routing ENFORCED DENY: decision={decision.decision_id} "
            f"tier={decision.tier.value} action_blocked={decision.reason}"
        )
        return False
    return True


# ─── #4049 full Policy Engine ───────────────────────────────────────────────


def evaluate_policies(
    agent_role: str,
    provider: str,
    task_type: str,
    cost_per_call_usd: float = 0.0,
    health_status: str = "healthy",
    security_clearance: str = "low",
    rules: list[PolicyRule] | None = None,
) -> PolicyEvaluation:
    """Evaluate a request against all policy rules.

    বাংলা: একটি provider call request-কে সব policy rules-এর বিরুদ্ধে evaluate করে।
    DENY rule match হলে → denied। REQUIRE_APPROVAL → Tier-3। ALLOW → allowed (with constraints)।

    Args:
        agent_role: role of the agent (coder, ci, auditor, etc.)
        provider: provider name (groq, openai, cerebras, etc.)
        task_type: task type (ci_fix, code_review, etc.)
        cost_per_call_usd: estimated cost per call
        health_status: provider health status (from #4046)
        security_clearance: agent's security clearance level
        rules: policy rules (loads defaults if None)

    Returns:
        PolicyEvaluation with allowed + matched_rules + constraints
    """
    if rules is None:
        rules = load_policy_rules()

    active_rules = get_active_rules(rules)
    matched: list[PolicyRule] = []
    denial_reason = ""
    cost_limit: float | None = None
    required_clearance = ""
    requires_approval = False

    for rule in active_rules:
        if not _rule_matches(rule, agent_role, provider, task_type):
            continue
        matched.append(rule)

        # Check health status first — a DENY rule with require_health_status
        # only denies when health is NOT in the allowed list
        if rule.action == PolicyAction.DENY and rule.require_health_status:
            if health_status not in rule.require_health_status:
                denial_reason = (
                    f"Denied by rule '{rule.name}' ({rule.rule_id}) — "
                    f"health '{health_status}' not in allowed {rule.require_health_status}"
                )
                logger.warning(f"PolicyEngine DENY (health): {denial_reason}")
                return PolicyEvaluation(
                    allowed=False,
                    matched_rules=matched,
                    denial_reason=denial_reason,
                )
            # Health is OK — this DENY rule doesn't trigger, continue to next rule
            continue

        # Check if provider is blacklisted (DENY with providers list)
        if rule.action == PolicyAction.DENY and rule.providers:
            denial_reason = f"Denied by rule '{rule.name}' ({rule.rule_id}) — provider blacklisted"
            logger.warning(f"PolicyEngine DENY (blacklist): {denial_reason}")
            return PolicyEvaluation(
                allowed=False,
                matched_rules=matched,
                denial_reason=denial_reason,
            )

        # REQUIRE_APPROVAL — Tier-3
        if rule.action == PolicyAction.REQUIRE_APPROVAL:
            requires_approval = True
            if rule.require_security_clearance and rule.require_security_clearance not in ("low",):
                required_clearance = rule.require_security_clearance

        # Check cost limits (ALLOW rules with max_cost_per_call_usd)
        if rule.max_cost_per_call_usd is not None:
            if cost_per_call_usd > rule.max_cost_per_call_usd:
                denial_reason = (
                    f"Cost ${cost_per_call_usd} exceeds limit ${rule.max_cost_per_call_usd} "
                    f"(rule '{rule.name}')"
                )
                logger.warning(f"PolicyEngine DENY (cost): {denial_reason}")
                return PolicyEvaluation(
                    allowed=False,
                    matched_rules=matched,
                    denial_reason=denial_reason,
                )
            if cost_limit is None or rule.max_cost_per_call_usd < cost_limit:
                cost_limit = rule.max_cost_per_call_usd

    allowed = not denial_reason
    return PolicyEvaluation(
        allowed=allowed,
        matched_rules=matched,
        denial_reason=denial_reason,
        cost_limit_usd=cost_limit,
        required_security_clearance=required_clearance,
        requires_approval=requires_approval,
    )


def _rule_matches(
    rule: PolicyRule,
    agent_role: str,
    provider: str,
    task_type: str,
) -> bool:
    """Check if a rule matches the request context.

    বাংলা: rule-এর conditions (agent_roles, task_types, providers) match করে কিনা।
    empty list = match all (wildcard)।
    """
    if rule.agent_roles and agent_role not in rule.agent_roles:
        return False
    if rule.task_types and task_type not in rule.task_types:
        return False
    if rule.providers and provider not in rule.providers:
        return False
    return True


def enforce_policies(
    agent_role: str,
    provider: str,
    task_type: str,
    cost_per_call_usd: float = 0.0,
    health_status: str = "healthy",
    security_clearance: str = "low",
    rules: list[PolicyRule] | None = None,
) -> bool:
    """Enforce policy rules — returns True if allowed, False if denied.

    বাংলা: পুরো Policy Engine enforcement। denied হলে False, allowed হলে True।
    """
    evaluation = evaluate_policies(
        agent_role=agent_role,
        provider=provider,
        task_type=task_type,
        cost_per_call_usd=cost_per_call_usd,
        health_status=health_status,
        security_clearance=security_clearance,
        rules=rules,
    )

    if not evaluation.allowed:
        logger.warning(
            f"Policy ENFORCED DENY: provider={provider} task={task_type} "
            f"reason={evaluation.denial_reason}"
        )
        return False

    if evaluation.requires_approval:
        logger.info(
            f"Policy requires approval (Tier-3): provider={provider} task={task_type} "
            f"clearance={evaluation.required_security_clearance}"
        )
        # In production, this would block until admin approval
        # For now, log + return False (caller must get approval first)
        return False

    return True
