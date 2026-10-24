"""
backend/external_agents/control/policy_engine.py
================================================
ISSUE-1573 (Part 4): the compliance Policy Engine consulted before every
dispatch.

Decisions (fail-closed by design):
    ALLOWED        — proceed
    POLICY_BLOCKED — provider/mode combination is forbidden (hard stop)
    HITL_REQUIRED  — policy-checked channel failed a compliance check; a
                     human must approve before dispatch

Rules enforced, in order:
    1. provider known to the registry (unknown → POLICY_BLOCKED)
    2. provider permitted by the TASK's allowed_providers
    3. provider not blocked by user/operator config
    4. execution mode actually supported by the provider capabilities
    5. browser_channel policy_checked providers must pass every registered
       compliance check — a failure escalates to HITL, never proceeds
"""

from __future__ import annotations

import os
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from external_agents.contracts.task_contract import TaskContract
from external_agents.providers.registry import (
    ChannelPolicy,
    ExecutionMode,
    ProviderRegistry,
)

__all__ = [
    "PolicyDecision",
    "PolicyEngine",
    "PolicyVerdict",
    "UserChannelConfig",
    "browser_channel_allowed_by_config",
]

ComplianceCheck = Callable[[TaskContract, ExecutionMode], tuple[bool, str]]


class PolicyDecision(StrEnum):
    ALLOWED = "ALLOWED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    HITL_REQUIRED = "HITL_REQUIRED"


class PolicyVerdict(BaseModel):
    decision: PolicyDecision
    provider: str
    mode: ExecutionMode
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecision.ALLOWED


class UserChannelConfig(BaseModel):
    """Operator-side channel configuration (env-driven defaults)."""

    blocked_providers: list[str] = Field(default_factory=list)
    allow_browser_channel: bool = Field(
        default_factory=lambda: (
            os.getenv("EXTERNAL_AGENTS_ALLOW_BROWSER_CHANNEL", "true").lower()
            in {"1", "true", "yes"}
        )
    )
    require_hitl_for_browser_channel: bool = Field(
        default_factory=lambda: (
            os.getenv("EXTERNAL_AGENTS_BROWSER_CHANNEL_REQUIRE_HITL", "false").lower()
            in {"1", "true", "yes"}
        )
    )


def browser_channel_allowed_by_config(config: UserChannelConfig) -> bool:
    return config.allow_browser_channel


class PolicyEngine:
    """Evaluate provider × mode × task × user-config BEFORE dispatch."""

    def __init__(
        self,
        registry: ProviderRegistry,
        user_config: UserChannelConfig | None = None,
        compliance_checks: list[ComplianceCheck] | None = None,
    ) -> None:
        self.registry = registry
        self.user_config = user_config or UserChannelConfig()
        self._compliance_checks: list[ComplianceCheck] = list(compliance_checks or [])

    def register_compliance_check(self, check: ComplianceCheck) -> None:
        self._compliance_checks.append(check)

    # ------------------------------------------------------------------
    def evaluate(
        self,
        provider: str,
        mode: ExecutionMode,
        task: TaskContract | None = None,
    ) -> PolicyVerdict:
        provider_name = provider.value if hasattr(provider, "value") else str(provider)

        def blocked(reason: str, **details: Any) -> PolicyVerdict:
            return PolicyVerdict(
                decision=PolicyDecision.POLICY_BLOCKED,
                provider=provider_name,
                mode=mode,
                reason=reason,
                details=details,
            )

        # 1. known provider (fail-closed)
        from external_agents.contracts.task_contract import AgentProvider

        try:
            provider_enum = AgentProvider(provider_name)
        except ValueError:
            return blocked(f"unknown provider '{provider_name}'")
        if not self.registry.has(provider_enum):
            return blocked(f"provider '{provider_name}' is not registered")

        # 2. task-level allowlist
        if task is not None:
            allowed = [p.value for p in task.allowed_providers]
            if allowed and provider_name not in allowed:
                return blocked(
                    f"provider '{provider_name}' not in task allowed_providers {allowed}"
                )

        # 3. operator blocklist
        if provider_name in self.user_config.blocked_providers:
            return blocked(f"provider '{provider_name}' is blocked by user config")

        cap = self.registry.get(provider_enum)

        # 4. capability support (fail-closed on unsupported modes)
        if not cap.supports(mode):
            if (
                mode is ExecutionMode.BROWSER_CHANNEL
                and cap.browser_channel is ChannelPolicy.DISALLOWED
            ):
                return blocked(
                    f"provider '{provider_name}' forbids the browser channel "
                    "(browser_channel=false in capability matrix)"
                )
            return blocked(
                f"provider '{provider_name}' does not support execution mode '{mode.value}'"
            )

        # 5. browser-channel policy gate
        if mode is ExecutionMode.BROWSER_CHANNEL:
            if not self.user_config.allow_browser_channel:
                return blocked("browser channel disabled by user config")
            if cap.browser_channel is ChannelPolicy.POLICY_CHECKED:
                failed = []
                for check in self._compliance_checks:
                    ok, note = (
                        check(task, mode)
                        if task is not None
                        else check(TaskContract(goal="policy probe"), mode)
                    )
                    if not ok:
                        failed.append(note)
                if failed:
                    if self.user_config.require_hitl_for_browser_channel:
                        return PolicyVerdict(
                            decision=PolicyDecision.HITL_REQUIRED,
                            provider=provider_name,
                            mode=mode,
                            reason="policy-checked browser channel failed compliance — human approval required",
                            details={"failed_checks": failed},
                        )
                    return blocked(
                        "policy-checked browser channel failed compliance: " + "; ".join(failed),
                        failed_checks=failed,
                    )
            if self.user_config.require_hitl_for_browser_channel:
                return PolicyVerdict(
                    decision=PolicyDecision.HITL_REQUIRED,
                    provider=provider_name,
                    mode=mode,
                    reason="operator policy requires HITL approval for every browser dispatch",
                )

        return PolicyVerdict(
            decision=PolicyDecision.ALLOWED,
            provider=provider_name,
            mode=mode,
            reason="all policy gates passed",
        )

    def evaluate_preferred(self, task: TaskContract) -> dict[str, PolicyVerdict]:
        """Convenience: evaluate each task-allowed provider on its preferred mode."""
        return {
            p.value: self.evaluate(p.value, self.registry.preferred_mode(p), task)
            for p in task.allowed_providers
        }
