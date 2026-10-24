"""MCP Audit Logger — Structured audit trail for every MCP tool call.

বাংলা মন্তব্য: প্রতিটি MCP tool call এর evaluation result এখানে log হয়।
Dual-target: file logger (always) + Supabase mcp_audit_log table (if available).

Constitution Compliance:
  - Law #19 (Observable): every tool call traced with decision + risk + latency
  - Law #12 (Verify Before Trust): audit log enables post-hoc verification
  - Law #1 (Centralized): single audit sink for all Python MCP servers
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime, timezone
from typing import Any

from core.logging_config import logger

_AUDIT_FLUSH_THRESHOLD = 50


class MCPAuditEntry:
    """Single audit record for one tool call evaluation."""

    def __init__(
        self,
        tool_name: str,
        decision: str,
        risk_level: str,
        latency_ms: float = 0.0,
        error: str | None = None,
        tenant_id: str | None = None,
        agent_id: str = "unknown",
        client_role: str = "agent",
        provider: str = "unknown",
        args_hash: str = "",
        result_status: str = "ok",
        result_ref: str | None = None,
        hitl_required: bool = False,
        hitl_approver: str | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.timestamp = datetime.now(UTC).isoformat()
        self.tool_name = tool_name
        self.decision = decision
        self.risk_level = risk_level
        self.latency_ms = round(latency_ms, 2)
        self.error = error
        # ── MCP Tower gap-4 (issue #928): per-agent verified-audit fields ──
        self.agent_id = agent_id or "unknown"
        self.client_role = client_role or "agent"
        self.provider = provider or "unknown"
        self.args_hash = args_hash
        self.result_status = result_status or ("error" if error else "ok")
        self.result_ref = result_ref
        self.hitl_required = hitl_required
        self.hitl_approver = hitl_approver
        normalized_tenant_id = str(tenant_id or "").strip()
        if not normalized_tenant_id or normalized_tenant_id == "default":
            raise ValueError("MCP audit requires an explicit tenant_id")
        self.tenant_id = normalized_tenant_id
        self.server = os.getenv("MCP_SERVER_NAME", "supremeai-mcp")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "decision": self.decision,
            "risk_level": self.risk_level,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "tenant_id": self.tenant_id,
            "server": self.server,
            "agent_id": self.agent_id,
            "client_role": self.client_role,
            "provider": self.provider,
            "args_hash": self.args_hash,
            "result_status": self.result_status,
            "result_ref": self.result_ref,
            "hitl": {"required": self.hitl_required, "approver": self.hitl_approver},
        }


class MCPAuditLogger:
    """Buffered audit logger — writes to file + optional Supabase."""

    def __init__(self) -> None:
        self._buffer: list[MCPAuditEntry] = []
        self._supabase_ok = False
        self._check_supabase()

    def _check_supabase(self) -> None:
        try:
            from database.supabase_client import db

            self._supabase_ok = db.is_connected() if hasattr(db, "is_connected") else True
        except Exception:
            self._supabase_ok = False

    def log(self, entry: MCPAuditEntry) -> None:
        # Always log to file (structured JSON)
        logger.info(
            "mcp_audit",
            extra={"mcp_audit": entry.to_dict()},
        )
        self._buffer.append(entry)
        if len(self._buffer) >= _AUDIT_FLUSH_THRESHOLD:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        if self._supabase_ok:
            try:
                from database.supabase_client import db

                rows = [e.to_dict() for e in self._buffer]
                # upsert into mcp_audit_log table (created via migration)
                db.client.table("mcp_audit_log").upsert(rows).execute()
            except Exception as e:
                logger.debug(f"MCP audit flush to Supabase failed: {e}")
        self._buffer.clear()


# ── Singleton ──────────────────────────────────────────────────────────

_global_audit_logger: MCPAuditLogger | None = None


def get_audit_logger() -> MCPAuditLogger:
    """Returns the singleton MCPAuditLogger instance."""
    global _global_audit_logger
    if _global_audit_logger is None:
        _global_audit_logger = MCPAuditLogger()
    return _global_audit_logger


def audit_tool_call(
    tool_name: str,
    decision: str,
    risk_level: str,
    latency_ms: float = 0.0,
    error: str | None = None,
    tenant_id: str | None = None,
    agent_id: str = "unknown",
    client_role: str = "agent",
    provider: str = "unknown",
    args_hash: str = "",
    result_status: str = "ok",
    result_ref: str | None = None,
    hitl_required: bool = False,
    hitl_approver: str | None = None,
) -> None:
    """Convenience: create entry + log in one call."""
    logger_instance = get_audit_logger()
    # বাংলা মন্তব্য: tenant_id অবশ্যই entry-তে যাবে — MCPAuditEntry এক্সপ্লিসিট টেন্যান্ট
    # কনটেক্সট ছাড়া ValueError ছুড়ে দেয় (Constitution Law #19: observable audit trail)।
    entry = MCPAuditEntry(
        tool_name=tool_name,
        decision=decision,
        risk_level=risk_level,
        latency_ms=latency_ms,
        error=error,
        tenant_id=tenant_id,
        agent_id=agent_id,
        client_role=client_role,
        provider=provider,
        args_hash=args_hash,
        result_status=result_status,
        result_ref=result_ref,
        hitl_required=hitl_required,
        hitl_approver=hitl_approver,
    )
    logger_instance.log(entry)
