"""
SupremeAI Database Configuration — Optimized Connection Pool
v4.0: Connection pooling, slow query logging, health checks
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import settings
from core.logging_config import logger

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SLOW_QUERY_THRESHOLD_MS = float(__import__("os").getenv("SLOW_QUERY_MS", "200"))
# বাংলা মন্তব্য: Render Free tier (512 MiB) মেমরি চাপ কমাতে ডিফল্ট pool size
# 10/5 থেকে কমিয়ে 3/2 করা হলো (database/session.py ও pgbouncer_pool.py-এর
# ছোট bracket-এর সাথে সামঞ্জস্যপূর্ণ)। env var দিয়ে override করা যায়।
POOL_SIZE = int(__import__("os").getenv("DB_POOL_SIZE", "3"))
MAX_OVERFLOW = int(__import__("os").getenv("DB_MAX_OVERFLOW", "2"))
POOL_RECYCLE = int(__import__("os").getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def _get_database_url() -> str:
    """Get database URL from environment with validation.

    Audit fix (patch v3 session): previously read the nonexistent
    ``settings.database_url`` attribute → AttributeError on every call → the
    critical ``database`` readiness check failed silently (``/ready`` was
    permanently 503 in all environments). Now uses the canonical
    ``settings.supabase_database_url`` (SUPABASE_DATABASE_URL_POOLER, the same
    field every other module consumes) with a direct ``DATABASE_URL`` env
    fallback, then the SQLite dev fallback.
    """
    import os

    url = ""
    try:
        url = settings.supabase_database_url or ""
    except AttributeError:
        url = ""
    if not url:
        # Direct env fallback - Render commonly provisions DATABASE_URL directly.
        url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("Production database URL is required; SQLite fallback is disabled")

    # Convert postgres:// to postgresql+asyncpg:// for async
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


def _random_name_connection_class():
    """asyncpg-এর ডিফল্ট sequential prepared-statement নামের বদলে UUID-based random
    নাম — PgBouncer transaction pooling-এ ভিন্ন connection-এর নাম-সংঘর্ষ এড়াতে
    (দেখুন database/session.py-এর একই fix, একই root cause বিশ্লেষণ)।"""
    from uuid import uuid4

    from asyncpg import Connection as _AsyncpgConnection

    class RandomNameConnection(_AsyncpgConnection):
        def _get_unique_id(self, prefix: str) -> str:
            return f"__asyncpg_{prefix}_{uuid4().hex}__"

    return RandomNameConnection


@lru_cache
def get_engine():
    """
    Create async database engine with optimized connection pool.

    Pool Settings:
      - pool_size: Number of permanent connections (default: 10)
      - max_overflow: Extra connections beyond pool_size (default: 5)
      - pool_recycle: Recycle connections after N seconds (default: 3600)
      - pool_pre_ping: Verify connections before use
    """
    db_url = _get_database_url()
    is_sqlite = db_url.startswith("sqlite")
    engine_kwargs: dict = {
        "echo": os.getenv("DB_ECHO", "false").lower() == "true",
        "pool_pre_ping": True,  # Detect stale connections
    }
    if not is_sqlite:
        # pool_size / max_overflow are NOT supported for SQLite
        engine_kwargs["pool_size"] = POOL_SIZE
        engine_kwargs["max_overflow"] = MAX_OVERFLOW
        engine_kwargs["pool_recycle"] = POOL_RECYCLE
        # বাংলা মন্তব্য (BUG FIX v2 — 2026-08-30): শুধু statement_cache_size=0 যথেষ্ট
        # নয় — SQLAlchemy-এর asyncpg dialect cache নির্বিশেষে সবসময় named prepared
        # statement তৈরি করতে Connection.prepare() সরাসরি কল করে, এবং asyncpg-এর
        # ডিফল্ট sequential নাম জেনারেটর PgBouncer transaction pooling-এ ভিন্ন
        # connection-এর মধ্যে নাম-সংঘর্ষ তৈরি করতে পারে। UUID-based random নাম
        # (connection_class) দিয়ে এই সংঘর্ষ সম্পূর্ণ এড়ানো হলো।
        engine_kwargs["connect_args"] = {
            "statement_cache_size": 0,
            "connection_class": _random_name_connection_class(),
        }

    engine = create_async_engine(db_url, **engine_kwargs)

    # Register slow query listener
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._query_start_time = time.monotonic()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total = (time.monotonic() - context._query_start_time) * 1000
        if total > SLOW_QUERY_THRESHOLD_MS:
            stmt_preview = statement[:100] + "..." if len(statement) > 100 else statement
            logger.warning(
                f"🐌 SLOW QUERY ({total:.0f}ms > {SLOW_QUERY_THRESHOLD_MS}ms): {stmt_preview}"
            )

    logger.info(
        f"Database engine created (pool={POOL_SIZE}, overflow={MAX_OVERFLOW}, "
        f"slow_query_threshold={SLOW_QUERY_THRESHOLD_MS}ms)"
    )

    return engine


# ---------------------------------------------------------------------------
# Lazy engine initialization — avoids crashing on import if DB is unavailable
# ---------------------------------------------------------------------------
_engine = None
_async_session_factory = None


def get_session_factory():
    """Return the module-level session factory, initializing lazily."""
    global _engine, _async_session_factory, engine, async_session_factory
    if _async_session_factory is None:
        _engine = get_engine()
        _async_session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        # Audit fix (patch v3 session): the backward-compat module-level names
        # were documented as "resolved on first use" but never actually
        # assigned — ``from core.db import engine`` always yielded None.
        engine = _engine
        async_session_factory = _async_session_factory
    return _async_session_factory


# Keep backward-compat references (filled lazily)
engine = None  # type: ignore[assignment]  # resolved on first use via get_session_factory()
async_session_factory = None  # type: ignore[assignment]


async def get_db() -> Generator[AsyncSession, None, None]:
    """Dependency injection for FastAPI routes."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def db_session() -> AsyncSession:  # type: ignore[override]
    """Context manager for non-FastAPI usage."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def check_db_health() -> dict[str, bool | str]:
    """Check database connectivity and performance."""
    eng = engine or get_engine()
    if eng is None:
        return {"healthy": False, "error": "Database engine not initialized", "latency_ms": 0}
    try:
        start = time.monotonic()
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = (time.monotonic() - start) * 1000

        return {
            "healthy": True,
            "latency_ms": round(latency_ms, 2),
            "pool_size": POOL_SIZE,
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "healthy": False,
            "error": str(e)[:200],
        }
