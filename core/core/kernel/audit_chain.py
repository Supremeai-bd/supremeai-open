"""MCP audit hash-chain core + async store — tamper-evident per-agent audit (issue #928).

বাংলা: MCP Tower gap-4। প্রতিটি tool call → একটি append-only `MCPAuditEvent`
row, যার `entry_hash = sha256(prev_hash + canonical_payload)` — tenant-scope
hash chain। চেইনের যেকোনো record বদলালে/মুছলে `verify()` ধরে ফেলে।

Surface:
  - compute_entry_hash(prev_hash, payload) — canonical sha256 (deterministic)
  - MCPAuditChainStore.append()   — একটি event chain-এ যোগ (INSERT-only)
  - MCPAuditChainStore.query()    — per-agent/tenant/tool/time-window filter
  - MCPAuditChainStore.verify()   — chain integrity + anomaly flags
  - anomaly_flags()               — failure-rate threshold → needs-human-review

Storage: SQLAlchemy async (prod = postgres/Supabase; tests = sqlite+aiosqlite)।
Append-only চুক্তি: এই module কখনো UPDATE/DELETE ইস্যু করে না; Supabase-এ RLS
দিয়েও deny করার SQL — docs/governance/mcp_audit_retention.md।
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.logging_config import logger
from models.mcp_audit_event import MCPAuditEvent

__all__ = [
    "compute_entry_hash",
    "canonical_payload",
    "args_fingerprint",
    "MCPAuditChainStore",
    "get_audit_chain_store",
]

# Anomaly rule (issue #928 acceptance: ≥1 live rule) — failure-rate threshold:
# শেষ _ANOMALY_WINDOW টি event-এ এক agent-এর _ANOMALY_FAILURE_RATIO বা তার বেশি
# failed/policy_blocked হলে needs-human-review flag।
_ANOMALY_WINDOW = 20
_ANOMALY_FAILURE_RATIO = 0.5


def canonical_payload(payload: dict[str, Any]) -> str:
    """Deterministic canonical JSON (sorted keys, compact separators, UTF-8)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_entry_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    """entry_hash = sha256(prev_hash + canonical_json(payload)) — hex digest."""
    h = hashlib.sha256()
    h.update((prev_hash or "").encode("utf-8"))
    h.update(canonical_payload(payload).encode("utf-8"))
    return h.hexdigest()


def args_fingerprint(arguments: dict[str, Any] | None) -> str:
    """sha256 of canonical args JSON — মূল args কখনো সরাসরি সংরক্ষণ করা হয় না
    (secrets লিক এড়াতে); শুধু fingerprint রাখা হয় (issue #928 schema: args_hash)।"""
    return compute_entry_hash("", canonical_payload(arguments or {}))


def _normalize_ts(ts: datetime | None) -> str | None:
    """Dialect-অজঞ্ঞান সামঞ্জস্যপূর্ণ ts স্ট্রিং (UTC, ISO-8601)।

    বাংলা: sqlite naive datetime ফেরত দেয়, postgres aware — দুটোকেই একই
    ক্যানোনিকাল ফর্মে আনলে hash pre/post-commit হুবহু মেলে (chain integrity
    নির্ভর করে এই নির্ধারণের উপর)।
    """
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).isoformat()


def _event_payload(event: MCPAuditEvent) -> dict[str, Any]:
    """entry_hash-য় যেসব ক্ষেত্র ঢোকে — এগুলোই tamper-evident সীমা।"""
    return {
        "ts": _normalize_ts(event.ts),
        "tenant_id": event.tenant_id,
        "agent_id": event.agent_id,
        "client_role": event.client_role,
        "provider": event.provider,
        "server": event.server,
        "tool": event.tool,
        "args_hash": event.args_hash,
        "result_status": event.result_status,
        "result_ref": event.result_ref,
        "error": event.error,
        "hitl_required": event.hitl_required,
        "hitl_approver": event.hitl_approver,
    }


def _row_to_dict(event: MCPAuditEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "ts": _normalize_ts(event.ts),
        "tenant_id": event.tenant_id,
        "agent_id": event.agent_id,
        "client_role": event.client_role,
        "provider": event.provider,
        "server": event.server,
        "tool": event.tool,
        "args_hash": event.args_hash,
        "result_status": event.result_status,
        "result_ref": event.result_ref,
        "error": event.error,
        "hitl": {"required": event.hitl_required, "approver": event.hitl_approver},
        "prev_hash": event.prev_hash,
        "entry_hash": event.entry_hash,
    }


class MCPAuditChainStore:
    """Async, append-only, tenant-scoped hash-chain audit store (issue #928)."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_maker = session_maker  # None → repo-র default engine (lazy)

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        if self._session_maker is not None:
            async with self._session_maker() as s:
                yield s
            return
        from database.session import get_db_session_context

        async with get_db_session_context() as s:
            yield s

    async def append(
        self,
        *,
        tenant_id: str,
        tool: str,
        agent_id: str = "unknown",
        client_role: str = "agent",
        provider: str = "unknown",
        args_hash: str = "",
        result_status: str = "ok",
        result_ref: str | None = None,
        error: str | None = None,
        hitl_required: bool = False,
        hitl_approver: str | None = None,
        server: str = "supremeai-mcp",
    ) -> dict[str, Any]:
        """একটি event chain-এ append করে — কখনোই update/delete করে না।"""
        async with self._session() as s:
            prev = ""
            last = (
                await s.execute(
                    select(MCPAuditEvent)
                    .where(MCPAuditEvent.tenant_id == tenant_id)
                    .order_by(MCPAuditEvent.ts.desc(), MCPAuditEvent.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last is not None:
                prev = last.entry_hash

            event = MCPAuditEvent(
                id=uuid4(),
                ts=datetime.now(UTC),
                tenant_id=tenant_id,
                agent_id=agent_id or "unknown",
                client_role=client_role or "agent",
                provider=provider or "unknown",
                server=server,
                tool=tool,
                args_hash=args_hash,
                result_status=result_status or "ok",
                result_ref=result_ref,
                error=error,
                hitl_required=hitl_required,
                hitl_approver=hitl_approver,
                prev_hash=prev,
                entry_hash="",
            )
            event.entry_hash = compute_entry_hash(prev, _event_payload(event))
            s.add(event)
            await s.commit()
            return _row_to_dict(event)

    async def query(
        self,
        tenant_id: str,
        *,
        agent_id: str | None = None,
        tool: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """audit_query — per-agent/tenant/tool/time-window (acceptance: <1s per-agent report)."""
        stmt: Select = select(MCPAuditEvent).where(MCPAuditEvent.tenant_id == tenant_id)
        if agent_id:
            stmt = stmt.where(MCPAuditEvent.agent_id == agent_id)
        if tool:
            stmt = stmt.where(MCPAuditEvent.tool == tool)
        if since is not None:
            stmt = stmt.where(MCPAuditEvent.ts >= since)
        if until is not None:
            stmt = stmt.where(MCPAuditEvent.ts <= until)
        stmt = stmt.order_by(MCPAuditEvent.ts.desc(), MCPAuditEvent.id.desc()).limit(
            min(limit, 1000)
        )
        async with self._session() as s:
            rows = (await s.execute(stmt)).scalars().all()
            return [_row_to_dict(r) for r in rows]

    async def verify(
        self,
        tenant_id: str,
        *,
        limit: int = 1000,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """audit_verify — hash-chain integrity + anomaly flags একসাথে।"""
        stmt: Select = select(MCPAuditEvent).where(MCPAuditEvent.tenant_id == tenant_id)
        if since is not None:
            stmt = stmt.where(MCPAuditEvent.ts >= since)
        stmt = stmt.order_by(MCPAuditEvent.ts.asc(), MCPAuditEvent.id.asc()).limit(min(limit, 5000))
        async with self._session() as s:
            rows: Sequence[MCPAuditEvent] = (await s.execute(stmt)).scalars().all()

        checked = 0
        broken: list[dict[str, Any]] = []
        prev = ""
        for r in rows:
            expected = compute_entry_hash(prev, _event_payload(r))
            checked += 1
            if r.entry_hash != expected:
                broken.append({"event_id": str(r.id), "reason": "entry_hash_mismatch"})
            elif checked > 1 and r.prev_hash != prev:
                broken.append({"event_id": str(r.id), "reason": "prev_hash_link_broken"})
            prev = r.entry_hash

        flags = self.anomaly_flags([_row_to_dict(r) for r in rows])
        return {
            "tenant_id": tenant_id,
            "checked": checked,
            "chain_intact": not broken,
            "tampered_events": broken,
            "anomaly_flags": flags,
        }

    @staticmethod
    def anomaly_flags(
        events: list[dict[str, Any]],
        window: int = _ANOMALY_WINDOW,
        threshold: float = _ANOMALY_FAILURE_RATIO,
    ) -> list[dict[str, Any]]:
        """Anomaly rule #1 (live): per-agent failure-rate spike → needs-human-review।

        বাংলা: শেষ `window` টি event-এ (ts-ascending order ধরে) এক agent-এর
        failed/policy_blocked অনুপাত ≥ `threshold` হলে flag।
        """
        by_agent: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_agent.setdefault(e.get("agent_id", "unknown"), []).append(e)
        flags: list[dict[str, Any]] = []
        for agent, evs in by_agent.items():
            tail = evs[-window:]
            if len(tail) < 3:  # খুব অল্প sample-এ রায় দেওয়া বোকামি
                continue
            fails = sum(
                1 for e in tail if e.get("result_status") in ("error", "policy_blocked", "failed")
            )
            ratio = fails / len(tail)
            if ratio >= threshold:
                flags.append(
                    {
                        "rule": "failure_rate_spike",
                        "agent_id": agent,
                        "window": len(tail),
                        "failures": fails,
                        "ratio": round(ratio, 3),
                        "threshold": threshold,
                        "action": "needs-human-review",
                    }
                )
        return flags


# ── Singleton ──────────────────────────────────────────────────────────────

_chain_store: MCPAuditChainStore | None = None


def get_audit_chain_store() -> MCPAuditChainStore:
    """Singleton — prod-এ repo default engine ব্যবহার করে (lazy import)।"""
    global _chain_store
    if _chain_store is None:
        _chain_store = MCPAuditChainStore()
    return _chain_store


_logger_ref = logger  # Law #19: module-স্কোপ reference — import-time side effect নেই
