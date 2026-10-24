"""DecisionMetadata ORM model (#4052 — Roadmap v2 §3.2, agentmemory-inspired).

বাংলা নোট: এটা "agent কী সিদ্ধান্ত নিয়েছে" শুধু রেকর্ড করে না —
"সিদ্ধান্তটি আসলে কাজ করেছিল কি না" (`verification`), সিদ্ধান্তের সময়ের
policy অবস্থা (`policy_context`) এবং প্রোভেন্যান্স চেইন (`supersedes`) ধরে
রাখে। এটাই memory system বনাম learning system-এর পার্থক্য।

Storage সিদ্ধান্ত (PR-তে ঘোষিত deviation): issue-টি `prisma/schema.prisma`
বলেছিল, কিন্তু backend-এর পার্সিস্টেন্ট স্টোর হলো SQLAlchemy/Alembic
(models/*.py + alembic_migrations/) — Prisma schema শুধু mission-control
dashboard app-এর। Backend-native টেবিলই সঠিক বাসা (local SQLite + prod
Postgres দুটোতেই চলে, 512MB free-tier বান্ধব)।

Supersede সেমান্টিক্স: পুরোনো সিদ্ধান্ত কখনো DELETE হয় না — শুধু
`status='deprecated'` হয়, নতুন সিদ্ধান্ত `supersedes`-এ রেফারেন্স রাখে
(provenance chain preserved — acceptance #5)।
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, String, Text

from models.base import Base, TimestampMixin

# Acceptance #1: 13-field decision metadata schema + identity/status columns।
DECISION_OUTCOMES = ("success", "fail", "partial", "pending")
DECISION_STATUSES = ("active", "deprecated")


class DecisionMetadata(Base, TimestampMixin):
    """One governed agent decision — evidence, verification and provenance।"""

    __tablename__ = "decision_metadata"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(64), index=True, nullable=True)

    # who / what
    agent_type = Column(String(50), index=True, nullable=False)  # coder|planner|ci|...
    task_type = Column(String(50), index=True, nullable=False)  # ci_fix|code_review|...
    decision = Column(String(255), nullable=False)  # "chose_provider_X"
    why = Column(Text, nullable=False)  # rationale — fail-honest, no empty why

    # evidence + confidence
    evidence = Column(JSON, nullable=False, default=list)  # ["benchmark_run: ...", ...]
    confidence = Column(Float, nullable=True)  # 0.0..1.0 (optional)

    # outcome + lifecycle
    outcome = Column(String(20), index=True, default="pending", nullable=False)
    reusability = Column(String(20), default="medium", nullable=False)  # low|medium|high
    expiry = Column(DateTime(timezone=True), nullable=True)  # optional TTL hint (#4053 input)

    # the 3 v2 fields (acceptance #3/#4/#5)
    policy_context = Column(JSON, nullable=True)  # active-policy snapshot at decision time
    verification = Column(Text, nullable=True)  # populated POST-task ("pytest passed, CI green")
    supersedes = Column(String(36), ForeignKey("decision_metadata.id"), index=True, nullable=True)

    # provenance lifecycle: active → deprecated (never deleted)
    status = Column(String(20), index=True, default="active", nullable=False)

    def to_dict(self) -> dict:
        """JSON-safe dict — timestamps ISO-8601।"""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "agent_type": self.agent_type,
            "task_type": self.task_type,
            "decision": self.decision,
            "why": self.why,
            "evidence": self.evidence or [],
            "confidence": self.confidence,
            "outcome": self.outcome,
            "reusability": self.reusability,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "policy_context": self.policy_context,
            "verification": self.verification,
            "supersedes": self.supersedes,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def utcnow() -> datetime:
    return datetime.now(UTC)
