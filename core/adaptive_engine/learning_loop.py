"""Proactive Internet Learning Loop (ROADMAP §25, §57, §58).

বাংলা: ROADMAP §57 — সবশেষে একটি সম্পূর্ণ loop:
  INTERNET/APPROVED SOURCES → DISCOVERY → SOURCE CHECK → POLICY/ALLOWLIST →
  RESEARCH → KNOWLEDGE/GAP SIGNAL → CAPABILITY OPPORTUNITY →
  PRACTICALITY/RISK/COST → PROPOSAL → ADMIN/POLICY DECISION →
  BUILD/ACQUIRE → VALIDATE → REGISTER → REUSE।

ROADMAP §58 — knowledge learning এবং capability creation আলাদা। নতুন API
আবিষ্কার মানেই এখনই integration বানানো নয়।

ROADMAP §25 — proactive evolution signals: repeated user requests, failed tasks,
manual workarounds, system incidents, new APIs/repositories/standards,
performance gaps, resource limitations।
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import get_conn, jdump, jload


class LearningStage(enum.StrEnum):
    """ROADMAP §57 — pipeline stages."""

    DISCOVERY = "DISCOVERY"
    SOURCE_CHECK = "SOURCE_CHECK"
    POLICY_GATE = "POLICY_GATE"
    RESEARCH = "RESEARCH"
    KNOWLEDGE_RECORDED = "KNOWLEDGE_RECORDED"
    GAP_SIGNAL = "GAP_SIGNAL"
    CAPABILITY_OPPORTUNITY = "CAPABILITY_OPPORTUNITY"
    PRACTICALITY_ANALYSIS = "PRACTICALITY_ANALYSIS"
    PROPOSAL = "PROPOSAL"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    REGISTERED = "REGISTERED"
    REUSED = "REUSED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class LearningStageError(RuntimeError):
    """Raised when an illegal learning stage transition occurs."""


class EvolutionSignal(BaseModel):
    """ROADMAP §25 — proactive evolution signals."""

    signal_id: str = Field(default_factory=lambda: f"sig-{uuid.uuid4().hex[:16]}")
    kind: str  # repeated_request | failed_task | manual_workaround | incident | new_api | new_repo | new_standard | perf_gap | resource_limit
    description: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    capability_hint: str | None = None
    source_url: str | None = None
    priority: str = "MEDIUM"
    detected_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    proposed_capability_id: str | None = None


class LearningOpportunity(BaseModel):
    """A capability opportunity surfaced by learning (ROADMAP §57)."""

    opportunity_id: str = Field(default_factory=lambda: f"opp-{uuid.uuid4().hex[:16]}")
    requirement: str
    signal_id: str | None = None
    source_url: str | None = None
    usefulness: str = "unknown"  # high | medium | low | experimental
    feasibility: str = "unknown"
    risk: str = "medium"
    cost: str = "medium"
    maintenance: str = "low"
    reuse_existing_id: str | None = None  # if an existing capability covers it
    proposal_id: str | None = None
    stage: LearningStage = LearningStage.GAP_SIGNAL
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class LearningLoop:
    """Coordinates discovery → proposal → approval → register → reuse (ROADMAP §57)."""

    SIGNAL_TABLE = "ecosystem_evolution_signals"
    OPP_TABLE = "ecosystem_learning_opportunities"

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.SIGNAL_TABLE} (
                    signal_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    description TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '[]',
                    capability_hint TEXT,
                    source_url TEXT,
                    priority TEXT NOT NULL DEFAULT 'MEDIUM',
                    detected_at TEXT NOT NULL,
                    proposed_capability_id TEXT
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.OPP_TABLE} (
                    opportunity_id TEXT PRIMARY KEY,
                    requirement TEXT NOT NULL,
                    signal_id TEXT,
                    source_url TEXT,
                    usefulness TEXT NOT NULL DEFAULT 'unknown',
                    feasibility TEXT NOT NULL DEFAULT 'unknown',
                    risk TEXT NOT NULL DEFAULT 'medium',
                    cost TEXT NOT NULL DEFAULT 'medium',
                    maintenance TEXT NOT NULL DEFAULT 'low',
                    reuse_existing_id TEXT,
                    proposal_id TEXT,
                    stage TEXT NOT NULL DEFAULT 'GAP_SIGNAL',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.OPP_TABLE}_stage ON {self.OPP_TABLE}(stage)"
            )
            conn.commit()

    # -- signals -----------------------------------------------------------

    def record_signal(self, signal: EvolutionSignal) -> EvolutionSignal:
        with get_conn() as conn:
            conn.execute(
                f"INSERT INTO {self.SIGNAL_TABLE} "
                f"(signal_id, kind, description, evidence, capability_hint, "
                f"source_url, priority, detected_at, proposed_capability_id) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    signal.signal_id,
                    signal.kind,
                    signal.description,
                    jdump(signal.evidence),
                    signal.capability_hint,
                    signal.source_url,
                    signal.priority,
                    signal.detected_at,
                    signal.proposed_capability_id,
                ),
            )
            conn.commit()
        return signal

    def list_signals(self, *, limit: int = 50) -> list[EvolutionSignal]:
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.SIGNAL_TABLE} ORDER BY detected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._signal_from_row(r) for r in rows]

    # -- opportunities ------------------------------------------------------

    def surface_opportunity(self, opp: LearningOpportunity) -> LearningOpportunity:
        """ROADMAP §57 — capability opportunity (gap or improvement)."""
        with get_conn() as conn:
            conn.execute(
                self._opp_insert_sql(),
                self._opp_row(opp),
            )
            conn.commit()
        return opp

    def advance_stage(
        self, opportunity_id: str, to_stage: LearningStage, *, note: str | None = None
    ) -> LearningOpportunity:
        """ROADMAP §57 — move an opportunity through the pipeline."""
        now = datetime.now(UTC).isoformat()
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.OPP_TABLE} SET stage = ?, updated_at = ? WHERE opportunity_id = ?",
                (to_stage, now, opportunity_id),
            )
            conn.commit()
        return self.get_opportunity(opportunity_id)  # type: ignore[return-value]

    def get_opportunity(self, opportunity_id: str) -> LearningOpportunity | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.OPP_TABLE} WHERE opportunity_id = ?",
                (opportunity_id,),
            ).fetchone()
        return self._opp_from_row(row) if row else None

    def list_opportunities(
        self, *, stage: LearningStage | None = None, limit: int = 50
    ) -> list[LearningOpportunity]:
        if stage is not None:
            with get_conn() as conn:
                rows = conn.execute(
                    f"SELECT * FROM {self.OPP_TABLE} WHERE stage = ? "
                    f"ORDER BY updated_at DESC LIMIT ?",
                    (stage, limit),
                ).fetchall()
        else:
            with get_conn() as conn:
                rows = conn.execute(
                    f"SELECT * FROM {self.OPP_TABLE} ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._opp_from_row(r) for r in rows]

    # -- internals ----------------------------------------------------------

    def _opp_insert_sql(self) -> str:
        cols = (
            "opportunity_id, requirement, signal_id, source_url, usefulness, "
            "feasibility, risk, cost, maintenance, reuse_existing_id, "
            "proposal_id, stage, created_at, updated_at"
        )
        placeholders = ", ".join(["?"] * 14)
        return f"INSERT INTO {self.OPP_TABLE} ({cols}) VALUES ({placeholders})"

    def _opp_row(self, o: LearningOpportunity) -> tuple[Any, ...]:
        return (
            o.opportunity_id,
            o.requirement,
            o.signal_id,
            o.source_url,
            o.usefulness,
            o.feasibility,
            o.risk,
            o.cost,
            o.maintenance,
            o.reuse_existing_id,
            o.proposal_id,
            o.stage,
            o.created_at,
            o.updated_at,
        )

    def _opp_from_row(self, row: Any) -> LearningOpportunity:
        return LearningOpportunity(
            opportunity_id=row["opportunity_id"],
            requirement=row["requirement"],
            signal_id=row["signal_id"],
            source_url=row["source_url"],
            usefulness=row["usefulness"],
            feasibility=row["feasibility"],
            risk=row["risk"],
            cost=row["cost"],
            maintenance=row["maintenance"],
            reuse_existing_id=row["reuse_existing_id"],
            proposal_id=row["proposal_id"],
            stage=LearningStage(row["stage"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _signal_from_row(self, row: Any) -> EvolutionSignal:
        return EvolutionSignal(
            signal_id=row["signal_id"],
            kind=row["kind"],
            description=row["description"],
            evidence=jload(row["evidence"], []),
            capability_hint=row["capability_hint"],
            source_url=row["source_url"],
            priority=row["priority"],
            detected_at=row["detected_at"],
            proposed_capability_id=row["proposed_capability_id"],
        )

    def compute_ewc_loss_penalty(
        self, current_weights: dict, old_weights: dict, fisher_info: dict, ewc_lambda: float = 0.5
    ) -> float:
        # Compatibility stub for test_phase3_intelligence.py
        penalty = 0.0
        for name in current_weights:
            if name in old_weights and name in fisher_info:
                penalty += fisher_info[name] * (current_weights[name] - old_weights[name]) ** 2
        return (ewc_lambda / 2.0) * penalty


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_loop: LearningLoop | None = None


def get_learning_loop() -> LearningLoop:
    global _loop
    if _loop is None:
        _loop = LearningLoop()
    return _loop


__all__ = [
    "LearningStage",
    "EvolutionSignal",
    "LearningOpportunity",
    "LearningLoop",
    "get_learning_loop",
    "LearningStageError",
]
