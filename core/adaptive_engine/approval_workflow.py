"""Approval Workflow — admin decision memory + proposal batching (ROADMAP §9, §26–§27).

বাংলা: ROADMAP §26 — admin approval fatigue এড়াতে deduplication, priority
scoring, proposal batching, cooldowns ব্যবহার করা হয়। একই source/capability-এর
জন্য বারবার approval চাওয়া হবে না।

ROADMAP §27 — প্রতিটি decision (proposal, decision, reason, scope, time,
policy generated) persist থাকে, future planning signal হিসেবে কাজ করে।

এই module-টি বিদ্যমান models/pending_tasks.py-র উপরে একটি thin, ecosystem-aware
layer হিসেবে কাজ করে — কোনো existing HITL behavior কে replace করে না।
"""

from __future__ import annotations

import enum
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import get_conn, jdump, jload


class ProposalKind(enum.StrEnum):
    """ROADMAP §25 — what kind of thing needs approval."""

    NEW_SOURCE = "NEW_SOURCE"  # use a discovered source
    NEW_CAPABILITY = "NEW_CAPABILITY"  # build a missing capability
    CAPABILITY_PROMOTION = "CAPABILITY_PROMOTION"  # promote warm→hot
    CAPABILITY_ARCHIVE = "CAPABILITY_ARCHIVE"
    DEPLOYMENT = "DEPLOYMENT"  # production deploy/rollback
    DB_MIGRATION = "DB_MIGRATION"
    SECRET_ROTATION = "SECRET_ROTATION"
    HIGH_RISK_ACTION = "HIGH_RISK_ACTION"
    LEARNING_PROPOSAL = "LEARNING_PROPOSAL"


class ProposalPriority(enum.StrEnum):
    """ROADMAP §26 — priority scoring so only meaningful proposals reach admin."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProposalState(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    EXECUTED = "EXECUTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class ProposalStateError(RuntimeError):
    """Raised when an illegal proposal state transition is requested."""


class ProposalCooldownError(RuntimeError):
    """Raised when a proposal is submitted during its active cooldown window."""


# বাংলা: কোন risk level-এর জন্য approval করা বাধ্যতামূলক (ROADMAP §28)।
_MANDATORY_APPROVAL: set[str] = {
    "high",
    "critical",
    "privileged",
    "production",
    "destructive",
}


class ApprovalProposal(BaseModel):
    """ROADMAP §26 — a single proposal awaiting admin decision."""

    proposal_id: str = Field(default_factory=lambda: f"prop-{uuid.uuid4().hex[:16]}")
    kind: ProposalKind
    title: str
    description: str
    priority: ProposalPriority = ProposalPriority.MEDIUM
    state: ProposalState = ProposalState.PENDING
    risk_level: str = "medium"
    # বাংলা: dedup key — একই প্রস্তাব দ্বিতীয়বার submit হলে existing pending proposal-কে supersede করবে।
    dedup_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    cost_estimate: dict[str, Any] = Field(default_factory=dict)
    proposed_by: str = "system"
    tenant_id: str | None = None
    correlation_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = Field(
        default_factory=lambda: (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    )
    # ROADMAP §27 — decision memory
    resolved_by: str | None = None
    resolved_at: str | None = None
    decision_reason: str | None = None
    policy_generated: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    """Admin decision on a proposal (ROADMAP §9, §27)."""

    proposal_id: str
    decision: ProposalState  # APPROVED | REJECTED | DEFERRED
    resolved_by: str
    reason: str | None = None
    policy_scope: str | None = None  # if decision becomes reusable policy
    policy_value: str | None = None


class ApprovalWorkflow:
    """Admin decision memory + anti-fatigue (ROADMAP §9, §26, §27)."""

    TABLE = "ecosystem_proposals"
    DECISION_TABLE = "ecosystem_decision_memory"

    # বাংলা: ROADMAP §26 — একই dedup_key-র জন্য কত সময় পর্যন্ত নতুন proposal এড়ানো যাবে।
    DEFAULT_COOLDOWN_SECONDS = 3600  # 1 hour

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    proposal_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'MEDIUM',
                    state TEXT NOT NULL DEFAULT 'PENDING',
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    dedup_key TEXT,
                    payload TEXT NOT NULL DEFAULT '{{}}',
                    evidence TEXT NOT NULL DEFAULT '[]',
                    cost_estimate TEXT NOT NULL DEFAULT '{{}}',
                    proposed_by TEXT NOT NULL DEFAULT 'system',
                    tenant_id TEXT,
                    correlation_id TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    resolved_by TEXT,
                    resolved_at TEXT,
                    decision_reason TEXT,
                    policy_generated TEXT NOT NULL DEFAULT '{{}}'
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_state "
                f"ON {self.TABLE}(state, priority)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_dedup ON {self.TABLE}(dedup_key)"
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.DECISION_TABLE} (
                    memory_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    dedup_key TEXT,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    scope TEXT,
                    time TEXT NOT NULL,
                    policy_generated TEXT NOT NULL DEFAULT '{{}}'
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.DECISION_TABLE}_dedup "
                f"ON {self.DECISION_TABLE}(dedup_key)"
            )
            conn.commit()

    # -- create ------------------------------------------------------------

    def propose(self, proposal: ApprovalProposal) -> ApprovalProposal:
        """ROADMAP §26 — dedup against existing PENDING / recent decision memory."""
        if proposal.dedup_key:
            existing = self._find_active_by_dedup(proposal.dedup_key)
            if existing is not None:
                # বাংলা: ROADMAP §26 — একই dedup_key এখনো pending → reuse করো, নতুন না করো।
                return existing
            # check recent decision memory for cooldown suppression
            if self._recent_decision_matches(proposal.dedup_key, self.DEFAULT_COOLDOWN_SECONDS):
                return ApprovalProposal(
                    proposal_id=proposal.proposal_id,
                    kind=proposal.kind,
                    title=proposal.title,
                    description="[suppressed by cooldown] " + proposal.description,
                    priority=ProposalPriority.LOW,
                    state=ProposalState.SUPERSEDED,
                    dedup_key=proposal.dedup_key,
                )
        with get_conn() as conn:
            conn.execute(self._insert_sql(), self._row(proposal))
            conn.commit()
        return proposal

    def decide(self, decision: ApprovalDecision) -> ApprovalProposal:
        """ROADMAP §27 — record the decision + persist it as reusable memory."""
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT state, expires_at, dedup_key, kind FROM {self.TABLE} "
                f"WHERE proposal_id = ?",
                (decision.proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(decision.proposal_id)
            current = ProposalState(row["state"])
            if current != ProposalState.PENDING:
                raise ValueError(f"Proposal {decision.proposal_id} already resolved ({current})")
            # ROADMAP §9 — expired proposals can't be decided
            if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
                raise ValueError("proposal_expired")
            now = datetime.now(UTC).isoformat()
            policy_generated = (
                {
                    "scope": decision.policy_scope,
                    "value": decision.policy_value,
                    "decision": decision.decision,
                    "reason": decision.reason,
                }
                if decision.policy_scope
                else {}
            )
            conn.execute(
                f"UPDATE {self.TABLE} SET state = ?, resolved_by = ?, "
                f"resolved_at = ?, decision_reason = ?, policy_generated = ? "
                f"WHERE proposal_id = ?",
                (
                    decision.decision,
                    decision.resolved_by,
                    now,
                    decision.reason,
                    jdump(policy_generated),
                    decision.proposal_id,
                ),
            )
            # ROADMAP §27 — persist decision memory
            memory_id = f"mem-{uuid.uuid4().hex[:16]}"
            conn.execute(
                f"INSERT INTO {self.DECISION_TABLE} "
                f"(memory_id, proposal_id, kind, dedup_key, decision, reason, "
                f"scope, time, policy_generated) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    memory_id,
                    decision.proposal_id,
                    row["kind"],
                    row["dedup_key"],
                    decision.decision,
                    decision.reason,
                    decision.policy_scope,
                    now,
                    jdump(policy_generated),
                ),
            )
            conn.commit()
        return self.get(decision.proposal_id)  # type: ignore[return-value]

    def mark_executed(self, proposal_id: str, *, executed_by: str) -> ApprovalProposal:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET state = ?, resolved_by = ?, "
                f"resolved_at = ? WHERE proposal_id = ? AND state = ?",
                (
                    ProposalState.EXECUTED,
                    executed_by,
                    datetime.now(UTC).isoformat(),
                    proposal_id,
                    ProposalState.APPROVED,
                ),
            )
            conn.commit()
        return self.get(proposal_id)  # type: ignore[return-value]

    # -- read --------------------------------------------------------------

    def get(self, proposal_id: str) -> ApprovalProposal | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list_pending(
        self,
        *,
        kind: ProposalKind | None = None,
        priority: ProposalPriority | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalProposal]:
        clauses = ["state = ?"]
        params: list[Any] = [ProposalState.PENDING]
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        if tenant_id is not None:
            clauses.append("(tenant_id IS NULL OR tenant_id = ?)")
            params.append(tenant_id)
        params.append(limit)
        # বাংলা: ROADMAP §26 — CRITICAL → HIGH → MEDIUM → LOW ক্রমে admin দেখে।
        order = "CASE priority WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END"
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE {' AND '.join(clauses)} "
                f"ORDER BY {order}, created_at ASC LIMIT ?",
                params,
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def list_decisions(
        self,
        *,
        dedup_key: str | None = None,
        proposal_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if dedup_key:
            clauses.append("dedup_key = ?")
            params.append(dedup_key)
        if proposal_id:
            clauses.append("proposal_id = ?")
            params.append(proposal_id)
        params.append(limit)
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.DECISION_TABLE} "
                f"{('WHERE ' + ' AND '.join(clauses)) if clauses else ''} "
                f"ORDER BY time DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    # -- risk-aware gating --------------------------------------------------

    def requires_approval(self, risk_level: str, kind: ProposalKind) -> bool:
        """ROADMAP §28 — high-risk actions always require explicit approval."""
        return risk_level.lower() in _MANDATORY_APPROVAL or kind in {
            ProposalKind.DEPLOYMENT,
            ProposalKind.DB_MIGRATION,
            ProposalKind.SECRET_ROTATION,
            ProposalKind.HIGH_RISK_ACTION,
        }

    # -- internals ----------------------------------------------------------

    def _find_active_by_dedup(self, dedup_key: str) -> ApprovalProposal | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} "
                f"WHERE dedup_key = ? AND state = ? ORDER BY created_at DESC LIMIT 1",
                (dedup_key, ProposalState.PENDING),
            ).fetchone()
        return self._from_row(row) if row else None

    def _recent_decision_matches(self, dedup_key: str, cooldown: int) -> bool:
        cutoff = (datetime.now(UTC) - timedelta(seconds=cooldown)).isoformat()
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT 1 FROM {self.DECISION_TABLE} WHERE dedup_key = ? AND time >= ? LIMIT 1",
                (dedup_key, cutoff),
            ).fetchone()
        return row is not None

    def _insert_sql(self) -> str:
        cols = (
            "proposal_id, kind, title, description, priority, state, risk_level, "
            "dedup_key, payload, evidence, cost_estimate, proposed_by, tenant_id, "
            "correlation_id, created_at, expires_at, resolved_by, resolved_at, "
            "decision_reason, policy_generated"
        )
        placeholders = ", ".join(["?"] * 20)
        return f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

    def _row(self, p: ApprovalProposal) -> tuple[Any, ...]:
        return (
            p.proposal_id,
            p.kind,
            p.title,
            p.description,
            p.priority,
            p.state,
            p.risk_level,
            p.dedup_key,
            jdump(p.payload),
            jdump(p.evidence),
            jdump(p.cost_estimate),
            p.proposed_by,
            p.tenant_id,
            p.correlation_id,
            p.created_at,
            p.expires_at,
            p.resolved_by,
            p.resolved_at,
            p.decision_reason,
            jdump(p.policy_generated),
        )

    def _from_row(self, row: Any) -> ApprovalProposal:
        return ApprovalProposal(
            proposal_id=row["proposal_id"],
            kind=ProposalKind(row["kind"]),
            title=row["title"],
            description=row["description"],
            priority=ProposalPriority(row["priority"]),
            state=ProposalState(row["state"]),
            risk_level=row["risk_level"],
            dedup_key=row["dedup_key"],
            payload=jload(row["payload"], {}),
            evidence=jload(row["evidence"], []),
            cost_estimate=jload(row["cost_estimate"], {}),
            proposed_by=row["proposed_by"],
            tenant_id=row["tenant_id"],
            correlation_id=row["correlation_id"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            resolved_by=row["resolved_by"],
            resolved_at=row["resolved_at"],
            decision_reason=row["decision_reason"],
            policy_generated=jload(row["policy_generated"], {}),
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_wf: ApprovalWorkflow | None = None


def get_approval_workflow() -> ApprovalWorkflow:
    global _wf
    if _wf is None:
        _wf = ApprovalWorkflow()
    return _wf


__all__ = [
    "ProposalKind",
    "ProposalPriority",
    "ProposalState",
    "ApprovalProposal",
    "ApprovalDecision",
    "ApprovalWorkflow",
    "get_approval_workflow",
    "ProposalStateError",
    "ProposalCooldownError",
]
