"""Governance — Shared Autonomous Engine. ROADMAP §28, §54.

Phase 6: Risk classification, budget enforcement, action authorization.
Safe actions auto-allowed; HIGH/CRITICAL require approval (§28).
"""

from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from adaptive_engine._store import get_conn, jdump, jload

logger = logging.getLogger(__name__)


class ActionRisk(enum.StrEnum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BudgetKind(enum.StrEnum):
    TIME = "TIME"
    MEMORY = "MEMORY"
    COMPUTE = "COMPUTE"
    DEPENDENCY = "DEPENDENCY"
    CRAWL = "CRAWL"
    CAPABILITY_CREATION = "CAPABILITY_CREATION"
    RETRY = "RETRY"
    DEPLOYMENT = "DEPLOYMENT"


@dataclass
class Budgets:
    """Conservative defaults — ROADMAP §54."""

    time_seconds: float = 60.0
    memory_mb: float = 256.0
    compute_units: float = 1.0
    dependency_depth: int = 3
    crawl_pages: int = 5
    capability_creation_count: int = 1
    retry_count: int = 2
    deployment_count: int = 1
    used: dict[str, float] = field(default_factory=dict)

    def _budget_for(self, kind: BudgetKind) -> float:
        return {
            BudgetKind.TIME: self.time_seconds,
            BudgetKind.MEMORY: self.memory_mb,
            BudgetKind.COMPUTE: self.compute_units,
            BudgetKind.DEPENDENCY: float(self.dependency_depth),
            BudgetKind.CRAWL: float(self.crawl_pages),
            BudgetKind.CAPABILITY_CREATION: float(self.capability_creation_count),
            BudgetKind.RETRY: float(self.retry_count),
            BudgetKind.DEPLOYMENT: float(self.deployment_count),
        }[kind]

    def remaining(self, kind: BudgetKind) -> float:
        return self._budget_for(kind) - self.used.get(kind, 0.0)

    def use(self, kind: BudgetKind, amount: float) -> bool:
        if self.remaining(kind) < amount:
            return False
        self.used[kind] = self.used.get(kind, 0.0) + amount
        return True


@dataclass
class RiskDecision:
    allowed: bool
    risk_level: ActionRisk
    reason: str
    budget_check_passed: bool
    requires_approval: bool
    remaining_budget: dict[str, float] = field(default_factory=dict)


_SAFE_ACTIONS: set[str] = {
    "read",
    "list",
    "get",
    "observe",
    "search",
    "inspect",
    "query",
    "trace",
    "analyze",
    "health",
    "metrics",
    "logs",
}
_HIGH_RISK_ACTIONS: set[str] = {
    "deploy",
    "rollback",
    "restart",
    "delete",
    "migration",
    "secret_rotation",
    "capability_creation",
    "high_risk_action",
    "external_action",
    "promotion",
    "archive",
}


class GovernanceEngine:
    """Phase 6 — Shared Autonomous Engine. ROADMAP §28."""

    TABLE = "ecosystem_governance_decisions"

    def __init__(self, *, budgets: Budgets | None = None) -> None:
        self.budgets = budgets or Budgets()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(f"""CREATE TABLE IF NOT EXISTS {self.TABLE} (
                decision_id TEXT PRIMARY KEY, action TEXT NOT NULL,
                risk_level TEXT NOT NULL, allowed INTEGER NOT NULL,
                budget_check_passed INTEGER NOT NULL, requires_approval INTEGER NOT NULL,
                reason TEXT, budget_used TEXT DEFAULT '{{}}',
                remaining_budget TEXT DEFAULT '{{}}', correlation TEXT DEFAULT '{{}}',
                created_at TEXT NOT NULL)""")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_risk ON {self.TABLE}(risk_level)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_action ON {self.TABLE}(action)"
            )
            conn.commit()

    def classify(self, action: str, *, context: dict[str, Any] | None = None) -> ActionRisk:
        ctx = context or {}
        a = action.lower().strip()
        if a in _SAFE_ACTIONS:
            return ActionRisk.SAFE
        if a in _HIGH_RISK_ACTIONS:
            return ActionRisk.HIGH
        explicit_risk = ctx.get("risk_level")
        if explicit_risk:
            try:
                return ActionRisk(str(explicit_risk).upper())
            except ValueError as val_err:
                logger.debug(f"Invalid explicit risk {explicit_risk!r}: {val_err}")
        if ctx.get("requires_approval"):
            return ActionRisk.HIGH
        if ctx.get("external"):
            return ActionRisk.MEDIUM
        return ActionRisk.LOW

    def authorize(
        self,
        action: str,
        *,
        context: dict[str, Any] | None = None,
        budget_use: dict[BudgetKind, float] | None = None,
    ) -> RiskDecision:
        risk = self.classify(action, context=context)
        budget_ok = True
        if budget_use:
            for kind, amt in budget_use.items():
                if self.budgets.remaining(kind) < amt:
                    budget_ok = False
                    break
        requires_approval = risk in {ActionRisk.HIGH, ActionRisk.CRITICAL} or not budget_ok
        allowed = (risk in {ActionRisk.SAFE, ActionRisk.LOW}) and budget_ok
        if allowed:
            reason = "auto-allowed"
        elif requires_approval:
            reason = "requires_approval"
        else:
            reason = "denied"
        remaining = {k.value: self.budgets.remaining(k) for k in BudgetKind}
        decision = RiskDecision(
            allowed=allowed,
            risk_level=risk,
            reason=reason,
            budget_check_passed=budget_ok,
            requires_approval=requires_approval,
            remaining_budget=remaining,
        )
        self._record(action, decision, {k.value: v for k, v in (budget_use or {}).items()})
        return decision

    def record_budget_use(self, kind: BudgetKind, amount: float) -> bool:
        ok = self.budgets.use(kind, amount)
        if ok:
            decision = RiskDecision(
                allowed=True,
                risk_level=ActionRisk.SAFE,
                reason=f"used {amount} of {kind.value}",
                budget_check_passed=True,
                requires_approval=False,
                remaining_budget={k.value: self.budgets.remaining(k) for k in BudgetKind},
            )
            self._record(f"budget_use:{kind.value}", decision, {kind.value: amount})
        return ok

    def list_decisions(
        self, *, action: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """GO1 — recent authz decisions, newest first (admin contract)."""
        clauses: list[str] = []
        params: list[Any] = []
        if action:
            clauses.append("action = ?")
            params.append(action)
        params.append(limit)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["allowed"] = bool(d.get("allowed"))
            d["budget_check_passed"] = bool(d.get("budget_check_passed"))
            d["requires_approval"] = bool(d.get("requires_approval"))
            d["budget_used"] = jload(d.get("budget_used"), {})
            d["remaining_budget"] = jload(d.get("remaining_budget"), {})
            d["correlation"] = jload(d.get("correlation"), {})
            out.append(d)
        return out

    def budget_summary(self) -> list[dict[str, Any]]:
        """GO2 — current budget state per BudgetKind (admin contract)."""
        return [
            {
                "kind": kind.value,
                "limit": self.budgets._budget_for(kind),
                "used": self.budgets.used.get(kind, 0.0),
                "remaining": self.budgets.remaining(kind),
            }
            for kind in BudgetKind
        ]

    def _record(self, action: str, d: RiskDecision, budget_used: dict[str, float]) -> None:
        with get_conn() as conn:
            conn.execute(
                f"INSERT INTO {self.TABLE} (decision_id, action, risk_level, allowed, "
                "budget_check_passed, requires_approval, reason, budget_used, "
                "remaining_budget, correlation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"gov-{uuid.uuid4().hex[:16]}",
                    action,
                    d.risk_level,
                    int(d.allowed),
                    int(d.budget_check_passed),
                    int(d.requires_approval),
                    d.reason,
                    jdump(budget_used),
                    jdump(d.remaining_budget),
                    jdump({}),
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()


_engine: GovernanceEngine | None = None


def get_governance_engine() -> GovernanceEngine:
    global _engine
    if _engine is None:
        _engine = GovernanceEngine()
    return _engine


__all__ = [
    "ActionRisk",
    "BudgetKind",
    "Budgets",
    "RiskDecision",
    "GovernanceEngine",
    "get_governance_engine",
]
