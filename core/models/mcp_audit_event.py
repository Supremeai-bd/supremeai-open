"""MCP Audit Event ORM model — tamper-evident per-agent audit trail (issue #928).

বাংলা: MCP Tower gap-4 — প্রতিটি agent-এর প্রতিটি tool call-এর verified,
tamper-evident audit record। Append-only ডিজাইন: application শুধু INSERT করে;
UPDATE/DELETE কখনোই করা হয় না (Supabase-এ RLS দিয়েও deny —
docs/governance/mcp_audit_retention.md)।

Hash chain: প্রতিটি event-এ `prev_hash` (আগের event-এর entry_hash, tenant-scope)
এবং `entry_hash` = sha256(prev_hash + canonical JSON payload) — চেইনের যেকোনো
record বদলালে `audit_verify` ধরে ফেলে (core/kernel/audit_chain.py)।

Constitution Compliance:
  - Law #19 (Observable): per-agent, per-tool, per-args verified trail
  - Law #12 (Verify Before Trust): audit_verify + anomaly rules
  - Law #1 (Centralized): single chain store — core/kernel/audit_chain.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import UUID, Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class MCPAuditEvent(Base):
    """One tamper-evident audit event for one MCP tool call (issue #928)."""

    __tablename__ = "mcp_audit_events"
    __table_args__ = (
        Index("ix_mcp_audit_events_tenant_ts", "tenant_id", "ts"),
        Index("ix_mcp_audit_events_agent_ts", "agent_id", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # ── Who / what context ──────────────────────────────────────────────
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    client_role: Mapped[str] = mapped_column(String(64), nullable=False, default="agent")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    server: Mapped[str] = mapped_column(String(255), nullable=False, default="supremeai-mcp")

    # ── What ────────────────────────────────────────────────────────────
    tool: Mapped[str] = mapped_column(String(255), nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    result_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── HITL context ────────────────────────────────────────────────────
    hitl_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hitl_approver: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Tamper-evidence chain ───────────────────────────────────────────
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
