"""ai_memory retention & TTL pruning utilities (issue #1109).

Single home for the data-lifecycle operations on the ``ai_memory`` table:

* :func:`get_retention_days` — resolved TTL (env ``AI_MEMORY_RETENTION_DAYS``,
  default 180; validated >= 1, mirrors the SQL contract in
  ``database/supabase/ai_memory_phase_c.sql`` Part 8).
* :func:`cleanup_expired` — delete embeddings older than the TTL. RPC-first
  (``fn_ai_memory_retention_cleanup`` — the SECURITY DEFINER function owned by
  service_role), with a direct-DELETE fallback for deployments where the
  Supabase REST client is not configured.
* :func:`delete_user_memories` — GDPR erasure path ("right to erasure"):
  removes ALL rows owned by a user, reporting how many were deleted.
* :func:`retention_stats` — observability: row counts by staleness bucket.

Design rules (constitution: honest failures, no silent no-ops):
- RPC-first: the SQL function is the canonical implementation; the Python
  fallback exists so TTL hygiene does not depend on a configured REST client.
- Every function returns what actually happened (mode used, rows deleted);
  callers log it — a cleanup that deleted 0 rows is still a success, but a
  cleanup that could not run raises.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from core.logging_config import logger

RETENTION_RPC = "fn_ai_memory_retention_cleanup"
DEFAULT_RETENTION_DAYS = 180

# Staleness buckets (days) for retention_stats — small fixed set, cheap COUNTs.
_STATS_BUCKETS: tuple[tuple[str, int], ...] = (
    ("fresh_lt_7d", 7),
    ("week_to_30d", 30),
    ("30d_to_90d", 90),
    ("older_than_90d", -1),  # everything past 90 days
)


@dataclass(frozen=True)
class CleanupResult:
    """Outcome of a retention pass — honest, inspectable, loggable."""

    deleted: int
    mode: str  # "rpc" | "direct"
    retention_days: int
    error: str | None = None


def get_retention_days() -> int:
    """Resolve the TTL in days.

    ``AI_MEMORY_RETENTION_DAYS`` (default 180) must be a positive integer —
    mirrors ``fn_ai_memory_retention_cleanup``'s fail-closed ``p_days >= 1``
    guard. An invalid value raises (config error must not be silently
    downgraded to the default: a typo like ``0`` would disable TTL hygiene
    while looking enabled).
    """
    raw = os.getenv("AI_MEMORY_RETENTION_DAYS")
    if raw is None or raw == "":
        return DEFAULT_RETENTION_DAYS
    try:
        days = int(raw)
    except ValueError as exc:
        raise ValueError(f"AI_MEMORY_RETENTION_DAYS must be an integer (got {raw!r})") from exc
    if days < 1:
        raise ValueError(f"AI_MEMORY_RETENTION_DAYS must be >= 1 (got {days})")
    return days


async def _table_delete_expired(days: int) -> int:
    """Direct-DELETE fallback (Supabase Postgres REST unavailable).

    core/db.py is async-only (async_sessionmaker + AsyncSession); retention
    callers are coroutines, so this runs on the event loop via the async
    engine. SQLAlchemy 2.0 delete() construct → rowcount = rows deleted.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    from core.db import get_session_factory
    from models.ai_memory import AIMemory

    cutoff = datetime.now(UTC) - timedelta(days=days)
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            delete(AIMemory).where(AIMemory.created_at < cutoff)  # type: ignore[arg-type]
        )
        await session.commit()
        return int(result.rowcount or 0)


async def cleanup_expired(
    retention_days: int | None = None,
    supabase_client: Any = None,
) -> CleanupResult:
    """Delete ai_memory rows older than the TTL. RPC-first, direct fallback.

    Args:
        retention_days: explicit TTL override; defaults to
            :func:`get_retention_days`.
        supabase_client: optional injected client (tests); defaults to the
            shared Supabase REST client via ``services.memory_service``.
    """
    days = retention_days if retention_days is not None else get_retention_days()
    if days < 1:
        raise ValueError(f"retention_days must be >= 1 (got {days})")

    # ── RPC path (canonical) ─────────────────────────────────────────────
    try:
        if supabase_client is None:
            from services.memory_service import _get_supabase

            supabase_client = _get_supabase()
        if supabase_client is not None:
            import asyncio as _asyncio

            def _rpc(client: Any = supabase_client) -> Any:
                return client.rpc(RETENTION_RPC, {"p_days": days}).execute()

            result = await _asyncio.to_thread(_rpc)
            deleted = int(result.data) if result.data is not None else 0
            logger.info(f"🧹 ai_memory retention (rpc): deleted={deleted} ttl_days={days}")
            return CleanupResult(deleted=deleted, mode="rpc", retention_days=days)
    except Exception as exc:  # noqa: BLE001 — fall through to direct mode
        logger.warning(
            f"ai_memory retention RPC unavailable ({exc.__class__.__name__}: {exc}); "
            "falling back to direct DELETE"
        )

    # ── Direct path (fallback) ───────────────────────────────────────────
    deleted = await _table_delete_expired(days)
    logger.info(f"🧹 ai_memory retention (direct): deleted={deleted} ttl_days={days}")
    return CleanupResult(deleted=deleted, mode="direct", retention_days=days)


async def _asyncio_to_thread(fn):
    import asyncio

    return await asyncio.to_thread(fn)


async def delete_user_memories(user_id: str, supabase_client: Any = None) -> CleanupResult:
    """GDPR erasure: delete EVERY ai_memory row owned by ``user_id``.

    Used by the self-service data-erasure endpoint
    (``DELETE /api/preferences/memory/user-data``) and by admins executing a
    deletion request. RPC-first (``fn_ai_memory_retention_cleanup`` only
    supports TTL deletes, so user erasure is a direct scoped DELETE on the
    REST client), SQLAlchemy fallback otherwise.
    """
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id is required for memory erasure")

    try:
        if supabase_client is None:
            from database.supabase_client import db as supabase_db

            supabase_client = supabase_db.client
        if supabase_client is not None:
            resp = await _asyncio_to_thread(
                lambda: supabase_client.table("ai_memory").delete().eq("user_id", user_id).execute()
            )
            deleted = len(resp.data) if resp.data is not None else 0
            logger.info(f"🧹 ai_memory GDPR erasure: user={user_id} deleted={deleted}")
            return CleanupResult(deleted=deleted, mode="rpc", retention_days=0)
    except Exception as exc:  # noqa: BLE001 — direct fallback below
        logger.warning(
            f"ai_memory GDPR erasure REST path failed "
            f"({exc.__class__.__name__}: {exc}); falling back to direct DELETE"
        )

    from sqlalchemy import delete

    from core.db import get_session_factory
    from models.ai_memory import AIMemory

    factory = get_session_factory()

    async def _direct() -> int:
        async with factory() as session:
            result = await session.execute(
                delete(AIMemory).where(AIMemory.user_id == user_id)  # type: ignore[arg-type]
            )
            await session.commit()
            return int(result.rowcount or 0)

    deleted = await _direct()
    logger.info(f"🧹 ai_memory GDPR erasure (direct): user={user_id} deleted={deleted}")
    return CleanupResult(deleted=deleted, mode="direct", retention_days=0)


async def retention_stats(supabase_client: Any = None) -> dict[str, Any]:
    """Row counts by staleness bucket — observability for the TTL policy."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from core.db import get_session_factory
    from models.ai_memory import AIMemory

    factory = get_session_factory()

    async def _counts() -> dict[str, int]:
        now = datetime.now(UTC)
        out: dict[str, int] = {}
        async with factory() as session:
            for name, horizon in _STATS_BUCKETS:
                stmt = select(func.count()).select_from(AIMemory)
                if horizon > 0:
                    stmt = stmt.where(AIMemory.created_at >= now - timedelta(days=horizon))
                else:  # older than the previous bucket's horizon (90d)
                    stmt = stmt.where(AIMemory.created_at < now - timedelta(days=90))
                count = await session.scalar(stmt)
                out[name] = int(count or 0)
        return out

    return await _counts()
