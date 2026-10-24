"""Policy rules loader — data-driven policy management (#4049).

বাংলা: policy rules data-driven — YAML/DB থেকে load হয়, hardcoded নয়।
নতুন rule যোগ করতে হলে YAML file-এ যোগ করুন, code change লাগে না।
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .policy_types import PolicyAction, PolicyRule, PolicyScope

# Default policy rules (can be overridden by YAML config or DB)
# বাংলা: এই rules হলো baseline — admin চাইলে override করতে পারে।
DEFAULT_POLICY_RULES: list[PolicyRule] = [
    PolicyRule(
        rule_id="deny-unhealthy-provider",
        name="Deny Unhealthy Provider",
        description="Deny routing to providers with UNHEALTHY status (must be healthy or degraded)",
        scope=PolicyScope.PROVIDER,
        action=PolicyAction.DENY,
        require_health_status=["healthy", "degraded"],
        priority=10,
    ),
    PolicyRule(
        rule_id="cost-limit-default",
        name="Default Cost Limit",
        description="Max $0.05 per call, $1.00 per task (default policy)",
        scope=PolicyScope.GLOBAL,
        action=PolicyAction.ALLOW,
        max_cost_per_call_usd=0.05,
        max_cost_per_task_usd=1.00,
        priority=50,
    ),
    PolicyRule(
        rule_id="cost-limit-coder",
        name="Coder Cost Limit",
        description="Coder agents: max $0.10 per call, $2.00 per task",
        scope=PolicyScope.AGENT,
        action=PolicyAction.ALLOW,
        agent_roles=["coder"],
        max_cost_per_call_usd=0.10,
        max_cost_per_task_usd=2.00,
        priority=40,
    ),
    PolicyRule(
        rule_id="security-high-clearance",
        name="High Security Clearance Required",
        description="Constitutional changes require high security clearance",
        scope=PolicyScope.GLOBAL,
        action=PolicyAction.REQUIRE_APPROVAL,
        task_types=["constitutional_change", "architecture_change"],
        require_security_clearance="high",
        priority=20,
    ),
    PolicyRule(
        rule_id="deny-blacklisted-provider",
        name="Deny Blacklisted Provider",
        description="Deny routing to blacklisted providers (e.g., rejected repos)",
        scope=PolicyScope.PROVIDER,
        action=PolicyAction.DENY,
        providers=["anthropic_tools"],  # rejected per #4063
        priority=5,
    ),
]


def load_policy_rules(config_path: str | Path | None = None) -> list[PolicyRule]:
    """Load policy rules from YAML config (falls back to defaults).

    বাংলা: YAML file থেকে rules load করে। file না থাকলে DEFAULT_POLICY_RULES।
    """
    if config_path is None:
        return DEFAULT_POLICY_RULES.copy()

    p = Path(config_path)
    if not p.exists():
        return DEFAULT_POLICY_RULES.copy()

    try:
        import yaml

        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return DEFAULT_POLICY_RULES.copy()

    rules: list[PolicyRule] = []
    for entry in data.get("rules", []) or []:
        try:
            rules.append(
                PolicyRule(
                    rule_id=entry.get("rule_id", ""),
                    name=entry.get("name", ""),
                    description=entry.get("description", ""),
                    scope=PolicyScope(entry.get("scope", "global")),
                    action=PolicyAction(entry.get("action", "allow")),
                    agent_roles=entry.get("agent_roles", []) or [],
                    task_types=entry.get("task_types", []) or [],
                    providers=entry.get("providers", []) or [],
                    max_cost_per_call_usd=entry.get("max_cost_per_call_usd"),
                    max_cost_per_task_usd=entry.get("max_cost_per_task_usd"),
                    require_health_status=entry.get("require_health_status", []) or [],
                    require_security_clearance=entry.get("require_security_clearance", ""),
                    priority=entry.get("priority", 100),
                    enabled=entry.get("enabled", True),
                )
            )
        except (ValueError, TypeError):
            continue  # skip invalid entries

    return rules if rules else DEFAULT_POLICY_RULES.copy()


def get_active_rules(rules: list[PolicyRule]) -> list[PolicyRule]:
    """Filter to only enabled rules, sorted by priority (lower = higher priority)."""
    active = [r for r in rules if r.enabled]
    return sorted(active, key=lambda r: r.priority)
