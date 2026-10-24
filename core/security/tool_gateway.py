"""Tool Policy Gateway — the ONE canonical policy decision boundary for tool execution.

AUD-3.2 / AUD-3.3 / AUD-3.8 (P0):

The deep audit found that tool executions were scattered across at least six
entry points (HTTP ``/agent/action``, swarm orchestration, MCP remote tools,
ToolForge ``exec()``, skill ``exec()``, automation dispatcher) with **no shared
policy gate**. Tenant/user/role/risk/budget checks — when present at all — were
per-route discipline, and the security audit logger had zero production callers.

This module defines the single enforcement point every side-effecting tool
invocation must pass through *before* execution:

1. **Identity** — an authenticated principal (user id) is mandatory.
2. **Tenant** — tenant binding (defaults to the user id for single-user tenancy).
3. **Role** — risk-elevated tools require the admin role.
4. **Risk** — unknown/unclassified tools default to ``high`` risk (fail-closed).
5. **Budget** — per-tenant cost budget is consulted through ``cost_guard``.
6. **Audit** — request, decision, execution and failure events are emitted to
   the central security audit log.

Usage::

    decision = await tool_policy_gateway.evaluate(
        tool_name="slack.send",
        user={"sub": "user-1", "role": "user"},
        risk="medium",
        estimated_cost=0.01,
    )
    if not decision.allowed:
        raise ToolPolicyViolation(decision)

    async with tool_policy_gateway.audited_execution(...):
        ...run the tool...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.contracts.security_policy import SEVERITY_LEVELS
from core.logging_config import logger

# Issue #684 (H-04): severity ranking now comes from the single canonical
# ladder in core.contracts.security_policy (ascending: higher == more severe).
# The previous local copy (with a stale "lower number == more sensitive"
# comment that contradicted its own values) was removed.

# Role required per risk level (AUD-3.3): only admins may invoke high/critical tools.
_ROLE_REQUIRED_BY_RISK = {"high": "admin", "critical": "admin"}


class ToolPolicyViolation(Exception):
    """Raised when a tool invocation is denied by the policy gateway."""

    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason or "Tool invocation denied by policy")


@dataclass
class PolicyDecision:
    """Result of a policy evaluation (AUD-3.2: one decision shape everywhere)."""

    allowed: bool
    tool_name: str
    user_id: str | None
    tenant_id: str | None
    role: str
    risk: str
    reason: str
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "tool_name": self.tool_name,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "role": self.role,
            "risk": self.risk,
            "reason": self.reason,
            "checks": dict(self.checks),
        }


def _audit(event: str, decision: PolicyDecision, detail: dict[str, Any] | None = None) -> None:
    """Emit a security audit event for the tool lifecycle (AUD-3.8).

    Best-effort: auditing must never break the execution path, but every event
    is always written to the structured log at minimum.
    """
    payload = {"tool": decision.tool_name, **(detail or {})}
    try:
        import asyncio
        import inspect

        from core.security.audit_logger import log_security_event

        coro = log_security_event(
            event_type=f"tool.{event}",
            user_id=decision.user_id,
            details={"decision": decision.to_dict(), **payload},
            severity="INFO" if decision.allowed else "WARNING",
        )
        # Support both running-loop (async callers) and sync callers.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            task = loop.create_task(coro)
            # Do not let audit failures surface as unhandled task exceptions.
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        else:
            new_loop = asyncio.new_event_loop()
            try:
                new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
    except Exception as exc:
        logger.bind(event_type=f"tool.{event}").info(
            f"🛡️ Tool audit (fallback): {decision.tool_name} user={decision.user_id} "
            f"allowed={decision.allowed} detail={exc}"
        )


class ToolPolicyGateway:
    """Single policy decision boundary for production tool execution (AUD-3.2)."""

    def __init__(self) -> None:
        # AUD-3.6: registry of explicit risk classifications. Tools not listed
        # here are treated as HIGH RISK (fail-closed) — they then require an
        # admin role until an owner classifies them.
        self._risk_registry: dict[str, str] = {}

    # -- registration -------------------------------------------------------
    def register_tool(self, tool_name: str, risk: str) -> None:
        """Classify a tool's risk level (audited at startup/plugin load)."""
        if risk not in SEVERITY_LEVELS:
            raise ValueError(f"Unknown risk level '{risk}' for tool {tool_name}")
        self._risk_registry[tool_name] = risk

    def get_risk(self, tool_name: str, declared_risk: str | None = None) -> str:
        registered_risk = self._risk_registry.get(tool_name)
        if registered_risk is None:
            return "high"  # fail-closed default for unclassified tools
        if declared_risk not in SEVERITY_LEVELS:
            return registered_risk
        # Callers may refine a classification upward, never downgrade it.
        return max((registered_risk, declared_risk), key=SEVERITY_LEVELS.__getitem__)

    # -- the canonical decision ---------------------------------------------
    async def evaluate(
        self,
        tool_name: str,
        user: dict[str, Any] | None,
        risk: str | None = None,
        estimated_cost: float = 0.0,
        action: str = "execute",
    ) -> PolicyDecision:
        """Run tenant+user+role+risk+budget checks before a tool executes."""
        user_id = (user or {}).get("sub")
        role = str((user or {}).get("role", "")).lower()
        tenant_id = (user or {}).get("tenant_id") or user_id
        effective_risk = self.get_risk(tool_name, risk)

        checks: dict[str, bool] = {}
        reason_parts: list[str] = []

        # 1) Identity (P0): no anonymous tool execution.
        checks["identity"] = bool(user_id)
        if not checks["identity"]:
            reason_parts.append("unauthenticated caller")

        # 2) Tenant binding (P0).
        checks["tenant"] = bool(tenant_id)
        if not checks["tenant"]:
            reason_parts.append("missing tenant binding")

        # 3) Role vs risk (P0): high/critical tools are admin-only.
        required_role = _ROLE_REQUIRED_BY_RISK.get(effective_risk)
        checks["role"] = required_role is None or role == required_role
        if not checks["role"]:
            reason_parts.append(
                f"risk '{effective_risk}' requires role '{required_role}' (caller role: '{role or 'none'}')"
            )

        # 4) Budget (P1, AUD-3.6): consult the shared cost guard when identity exists.
        checks["budget"] = True
        if user_id and estimated_cost > 0:
            try:
                from core.cost_guard import cost_guard as _cost_guard

                checks["budget"] = await _cost_guard.check_budget(
                    tenant_id=str(tenant_id), estimated_cost=estimated_cost
                )
                if not checks["budget"]:
                    reason_parts.append("tenant budget exhausted")
            except Exception as exc:
                # Cost guard outage must not silently allow spend: log and
                # treat as allowed only for low-risk tools.
                logger.warning(f"[ToolPolicyGateway] budget check error: {exc}")
                checks["budget"] = effective_risk in ("low", "medium")

        allowed = all(checks.values())
        decision = PolicyDecision(
            allowed=allowed,
            tool_name=tool_name,
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            risk=effective_risk,
            reason="allowed" if allowed else "; ".join(reason_parts),
            checks=checks,
        )
        _audit("decision", decision, {"action": action})
        return decision

    # -- convenience enforcement wrapper ------------------------------------
    async def enforce(
        self,
        tool_name: str,
        user: dict[str, Any] | None,
        risk: str | None = None,
        estimated_cost: float = 0.0,
    ) -> PolicyDecision:
        """Evaluate and raise :class:`ToolPolicyViolation` when denied."""
        decision = await self.evaluate(
            tool_name=tool_name,
            user=user,
            risk=risk,
            estimated_cost=estimated_cost,
        )
        if not decision.allowed:
            raise ToolPolicyViolation(decision)
        return decision

    def audited_execution(
        self,
        tool_name: str,
        user: dict[str, Any] | None,
        risk: str | None = None,
        estimated_cost: float = 0.0,
    ) -> _AuditedExecution:
        """Combined enforce + execution/failure audit events (AUD-3.8).

        Usage::

            async with tool_policy_gateway.audited_execution(
                tool_name="mcp.search", user=user
            ) as decision:
                ...run the tool...
        """
        return _AuditedExecution(self, tool_name, user, risk, estimated_cost)


class _AuditedExecution:
    """Async context manager: enforce policy, then audit execution/failure."""

    def __init__(
        self,
        gateway: ToolPolicyGateway,
        tool_name: str,
        user: dict[str, Any] | None,
        risk: str | None,
        estimated_cost: float,
    ) -> None:
        self._gateway = gateway
        self._tool = tool_name
        self._user = user
        self._risk = risk
        self._cost = estimated_cost
        self.decision: PolicyDecision | None = None

    async def __aenter__(self) -> PolicyDecision:
        self.decision = await self._gateway.enforce(self._tool, self._user, self._risk, self._cost)
        _audit("execution", self.decision, {"phase": "start"})
        return self.decision

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self.decision is not None:
            _audit(
                "failure" if exc_type else "execution",
                self.decision,
                {"phase": "end", "error": str(exc)[:200] if exc else None},
            )
        return False  # never swallow tool exceptions


# Module-level singleton (one canonical boundary per process).
tool_policy_gateway = ToolPolicyGateway()
