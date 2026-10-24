"""Durable persistence for the governed scout crawler (MASTER_PLAN Phase 1).

বাংলা: আগে crawl policy/history শুধু crawler_admin.py-র module-level dict/list-এ
থাকত — restart মানেই governance state হারানো। এই মডিউল DB-first, memory-fallback
প্যাটার্নে (Graceful Degradation) সব scout state durable রাখে:

  1. প্রথমে Supabase Postgres (crawl_policies / crawl_history / crawl_events —
     migration 2026_09_13_090000) ব্যবহার করে;
  2. DB না থাকলে বা fail করলে in-memory store-এ degrade করে — সঙ্গে WARNING log,
     কখনো চুপচাপ ডেটা হারায় না (No Silent Failure);
  3. সব অপারেশন tenant-scoped — কোনো টেন্যান্ট অন্য টেন্যান্টের policy/history
     দেখতে পারে না (tenant isolation)।

Supabase REST client (sync) হওয়ায় এখানকার অপারেশনগুলোও sync; কলকারী async route
থেকে সরাসরি কল করলেও এগুলো ছোট payload — codebase-এর established idiom
(যেমন connections.py → db.upsert) অনুসরণ করে।
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.logging_config import logger
from scout.models import CrawlHistoryRecord, CrawlPolicy

# ---------------------------------------------------------------------------
# In-memory fallback store (ক্যাপসহ — memory-DoS প্রতিরোধ, আগের মতোই)
# ---------------------------------------------------------------------------
_MAX_TENANTS = 500
_MAX_POLICIES_PER_TENANT = 50
_MAX_HISTORY = 1000
_MAX_EVENTS = 2000

_MEMORY_POLICIES: dict[str, list[dict[str, Any]]] = {}
_MEMORY_HISTORY: list[dict[str, Any]] = []
_MEMORY_EVENTS: list[dict[str, Any]] = []


def _client() -> Any | None:
    """Returns the Supabase REST client, or None when storage is unavailable."""
    try:
        from database.supabase_client import db

        client = getattr(db, "client", None)
        return client
    except Exception:  # pragma: no cover - degraded environments
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _rows(res: Any) -> list[dict[str, Any]]:
    """Validates a Supabase response and returns its data rows.

    বাংলা: test env-এ db.client প্রায়ই MagicMock হয় (offline/mock mode) —
    যার .data truthy কিন্তু list নয়। Shape verify না করলে write 'সফল' হয়ে
    চুপচাপ ডেটা হারায় (silent failure)। এই হেল্পার তা আটকে দেয় — নন-লিস্ট
    response মানে degraded mode → caller কে memory fallback-এ যেতে বাধ্য করে।
    """
    data = getattr(res, "data", None)
    if data is None:
        return []
    if not isinstance(data, list):
        raise RuntimeError("persistence response is not a real list (mock/degraded client)")
    return data


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------
async def list_policies(tenant_id: str) -> list[CrawlPolicy]:
    client = _client()
    if client is not None:
        try:
            res = (
                client.table("crawl_policies")
                .select("*")
                .eq("tenant_id", tenant_id)
                .order("created_at", desc=False)
                .execute()
            )
            return [CrawlPolicy(**row) for row in _rows(res)]
        except Exception as exc:
            logger.warning("crawler persistence degraded (list_policies): %s", exc)
    rows = _MEMORY_POLICIES.get(tenant_id, [])
    return [CrawlPolicy(**row) for row in rows]


async def get_policy(policy_id: str, tenant_id: str) -> CrawlPolicy | None:
    client = _client()
    if client is not None:
        try:
            res = (
                client.table("crawl_policies")
                .select("*")
                .eq("id", policy_id)
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )
            rows = _rows(res)
            return CrawlPolicy(**rows[0]) if rows else None
        except Exception as exc:
            logger.warning("crawler persistence degraded (get_policy): %s", exc)
    for row in _MEMORY_POLICIES.get(tenant_id, []):
        if row.get("id") == policy_id:
            return CrawlPolicy(**row)
    return None


async def get_active_policy(tenant_id: str) -> CrawlPolicy | None:
    """Returns the tenant's most recent active policy, or None (fail-closed)."""
    policies = await list_policies(tenant_id)
    active = [p for p in policies if p.is_active]
    return active[-1] if active else None


async def upsert_policy(policy: CrawlPolicy) -> None:
    policy.updated_at = datetime.now(UTC)
    row = policy.model_dump(mode="json")
    client = _client()
    if client is not None:
        try:
            _rows(client.table("crawl_policies").upsert(row).execute())
            return
        except Exception as exc:
            logger.warning("crawler persistence degraded (upsert_policy): %s", exc)
    tenant_rows = _MEMORY_POLICIES.setdefault(policy.tenant_id, [])
    for i, existing in enumerate(tenant_rows):
        if existing.get("id") == policy.id:
            tenant_rows[i] = row
            return
    if len(_MEMORY_POLICIES) >= _MAX_TENANTS and policy.tenant_id not in _MEMORY_POLICIES:
        raise RuntimeError("policy tenant cap reached; persistence unavailable")
    if len(tenant_rows) >= _MAX_POLICIES_PER_TENANT:
        raise RuntimeError("policy per-tenant cap reached; delete old policies first")
    tenant_rows.append(row)


async def delete_policy(policy_id: str, tenant_id: str) -> bool:
    client = _client()
    if client is not None:
        try:
            res = (
                client.table("crawl_policies")
                .delete()
                .eq("id", policy_id)
                .eq("tenant_id", tenant_id)
                .execute()
            )
            return bool(_rows(res))
        except Exception as exc:
            logger.warning("crawler persistence degraded (delete_policy): %s", exc)
    rows = _MEMORY_POLICIES.get(tenant_id, [])
    for i, existing in enumerate(rows):
        if existing.get("id") == policy_id:
            rows.pop(i)
            return True
    return False


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
async def record_history(record: CrawlHistoryRecord) -> None:
    row = record.model_dump(mode="json")
    client = _client()
    if client is not None:
        try:
            _rows(client.table("crawl_history").insert(row).execute())
            return
        except Exception as exc:
            logger.warning("crawler persistence degraded (record_history): %s", exc)
    _MEMORY_HISTORY.append(row)
    if len(_MEMORY_HISTORY) > _MAX_HISTORY:
        del _MEMORY_HISTORY[: len(_MEMORY_HISTORY) - _MAX_HISTORY]


async def record_crawl_response(response: Any) -> CrawlHistoryRecord:
    """Maps a CrawlResponse to a durable CrawlHistoryRecord and stores it.

    বাংলা: governed crawl শেষ হলে এটি ডাকতে হয় — এতেই scout প্রথমবারের মতো
    admin history/audit-এ সত্যিকারের ডেটা দেখায় (B2 battlefield fuel)।
    """
    record = CrawlHistoryRecord(
        id=response.history_id or str(uuid.uuid4()),
        task_id=response.task_id,
        tenant_id=response.tenant_id,
        query=response.query,
        sources_crawled=[page.url for page in response.pages][:100],
        total_pages_fetched=response.total_fetched,
        duplicate_pages_skipped=response.total_duplicates_skipped,
        extractive_summary=(response.extractive_summary or "")[:4000],
        token_reduction_pct=response.token_reduction_pct,
    )
    await record_history(record)
    return record


async def list_history(
    tenant_id: str, task_id: str | None = None, limit: int = 20
) -> list[CrawlHistoryRecord]:
    client = _client()
    if client is not None:
        try:
            q = client.table("crawl_history").select("*").eq("tenant_id", tenant_id)
            if task_id:
                q = q.eq("task_id", task_id)
            res = q.order("created_at", desc=True).limit(limit).execute()
            return [CrawlHistoryRecord(**row) for row in _rows(res)]
        except Exception as exc:
            logger.warning("crawler persistence degraded (list_history): %s", exc)
    rows = [
        row
        for row in _MEMORY_HISTORY
        if row.get("tenant_id") == tenant_id and (task_id is None or row.get("task_id") == task_id)
    ]
    return [CrawlHistoryRecord(**row) for row in rows[-limit:]]


# ---------------------------------------------------------------------------
# Events (telemetry)
# ---------------------------------------------------------------------------
async def record_event(
    tenant_id: str,
    task_id: str,
    event_type: str,
    message: str = "",
    severity: str = "INFO",
    metadata: dict[str, Any] | None = None,
) -> None:
    row = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "task_id": task_id,
        "event_type": event_type,
        "message": message[:2000],
        "severity": severity,
        "metadata": metadata or {},
        "created_at": _now_iso(),
    }
    client = _client()
    if client is not None:
        try:
            _rows(client.table("crawl_events").insert(row).execute())
            return
        except Exception as exc:
            logger.warning("crawler persistence degraded (record_event): %s", exc)
    _MEMORY_EVENTS.append(row)
    if len(_MEMORY_EVENTS) > _MAX_EVENTS:
        del _MEMORY_EVENTS[: len(_MEMORY_EVENTS) - _MAX_EVENTS]


async def list_events(
    tenant_id: str,
    task_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = _client()
    if client is not None:
        try:
            q = client.table("crawl_events").select("*").eq("tenant_id", tenant_id)
            if task_id:
                q = q.eq("task_id", task_id)
            if event_type:
                q = q.eq("event_type", event_type)
            res = q.order("created_at", desc=True).limit(limit).execute()
            return list(_rows(res))
        except Exception as exc:
            logger.warning("crawler persistence degraded (list_events): %s", exc)
    rows = [
        row
        for row in _MEMORY_EVENTS
        if row.get("tenant_id") == tenant_id
        and (task_id is None or row.get("task_id") == task_id)
        and (event_type is None or row.get("event_type") == event_type)
    ]
    return rows[-limit:]
