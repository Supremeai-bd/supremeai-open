"""Shared, tightly-bounded synchronous Postgres connection pool.

Why this exists: `checkpoint_manager`, `error_pattern_db`, `audit_logger`, and
`memory_service` were previously each opening/closing a fresh sqlite3
connection on every single call, writing to plain files on Render's
ephemeral local disk. That meant their state was silently wiped on every
container restart or redeploy.

Rather than routing them through the app's main *async* SQLAlchemy engine
(which would require converting every caller to async — a large, risky
blast-radius change), these subsystems are synchronous by design and callers
expect that. So we give them their own small psycopg2 pool, pointed at the
*same* Supabase pooler connection string the async engine uses
(SUPABASE_DATABASE_URL_POOLER), with a deliberately tiny ceiling so they
can never crowd out the app's primary request-serving connections.

Ripple-Effect Guard: this module is additive. It does not touch
`database/session.py` or the async engine's pool sizing in any way.

---
PATCH v4 (2026-08-30):
- Production logs showed `ReadOnlySqlTransaction: cannot execute CREATE TABLE
  in a read-only transaction` cascading to ERROR + CRITICAL on every boot.
  Root cause: Supabase production pooler (the URL in `SUPABASE_DATABASE_URL_POOLER`)
  is read-only in our prod tenant, but `pooled_pg.execute()` was running
  DDL (CREATE TABLE IF NOT EXISTS) against it via `services.memory_service`,
  `tools.checkpoint_manager`, etc. — all of which then fell back to SQLite
  (silent data loss across restarts).
- Fix: introduce a separate `SUPABASE_DATABASE_URL_WRITER` env var. DDL calls
  go through `execute_ddl()` which only targets the writer URL. DML/query
  calls continue through `execute()` against the pooler (read traffic).
  If no writer URL is configured, `execute_ddl()` logs a single warning
  and returns without raising — callers should treat it as best-effort.
"""

from __future__ import annotations

import atexit
import os
import threading
from contextlib import contextmanager
from typing import Any

from core.errors.error_bus import with_error_bus

# psycopg2 মডিউল না থাকলে যেন সার্ভিস ক্র্যাশ না করে, সে জন্য সেফ ইমপোর্ট ফলব্যাক ব্যবহার করা হলো।
try:
    import psycopg2
    import psycopg2.pool
except ImportError:
    psycopg2 = None
from core.config import settings
from core.logging_config import logger

# Deliberately small: these 4 subsystems are secondary telemetry/state, not
# primary request traffic. They must never meaningfully compete with the
# User (max 15) / Admin (max 3) pools already budgeted in database/session.py.
_MIN_CONN = 1
_MAX_CONN = int(os.getenv("PERSISTENCE_PG_POOL_MAX") or "4")

# PATCH v4: separate writer pool for DDL (CREATE TABLE, ALTER, etc.).
# Production Supabase pooler is read-only; DDL against it fails with
# ReadOnlySqlTransaction and cascades to CRITICAL silent-pattern escalation.
_writer_pool_lock = threading.Lock()
_writer_pool: Any = None
_writer_pool_unavailable = False
_writer_not_configured_warned = False  # sticky — warn once per process

_pool_lock = threading.Lock()
_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_unavailable = False  # sticky flag once we've confirmed no PG URL is configured


def _resolve_dsn() -> str | None:
    """Return the DSN for read/write operations via the pooler.

    PATCH v4: still used by `execute()` (DML) and `query()`. DDL callers
    must use `_resolve_writer_dsn()` instead.
    """
    dsn = settings.supabase_database_url
    if not dsn or dsn.startswith("sqlite"):
        return None
    return dsn


def _resolve_writer_dsn() -> str | None:
    """PATCH v4: return the DSN to use for DDL (CREATE TABLE / ALTER).

    Priority:
      1. `SUPABASE_DATABASE_URL_WRITER` env var (canonical writer endpoint).
      2. `SUPABASE_DATABASE_URL` env var (direct connection, not pooled — typically writable).
      3. None — caller must skip DDL silently.

    We intentionally do NOT fall back to `SUPABASE_DATABASE_URL_POOLER` here,
    because in production that endpoint is read-only and DDL against it
    raises `ReadOnlySqlTransaction` (the original bug).
    """
    writer_url = os.getenv("SUPABASE_DATABASE_URL_WRITER") or os.getenv("SUPABASE_DATABASE_URL")
    if not writer_url or writer_url.startswith("sqlite"):
        return None
    return writer_url


def _get_writer_pool() -> Any:
    """PATCH v4: lazy-init a dedicated psycopg2 pool for DDL operations."""
    global _writer_pool, _writer_pool_unavailable, _writer_not_configured_warned
    if psycopg2 is None:
        return None
    if _writer_pool is not None:
        return _writer_pool
    if _writer_pool_unavailable:
        return None
    with _writer_pool_lock:
        if _writer_pool is not None:
            return _writer_pool
        dsn = _resolve_writer_dsn()
        if not dsn:
            _writer_pool_unavailable = True
            if not _writer_not_configured_warned:
                logger.warning(
                    "persistence.pooled_pg: no WRITER DSN configured "
                    "(set SUPABASE_DATABASE_URL_WRITER) — DDL/bootstrap will be skipped. "
                    "Read-only pooler DDL errors silenced."
                )
                _writer_not_configured_warned = True
            return None
        try:
            _writer_pool = psycopg2.pool.ThreadedConnectionPool(
                _MIN_CONN, _MAX_CONN, dsn, connect_timeout=10
            )
            logger.info(
                "persistence.pooled_pg: writer pool initialized (max=%d connections).",
                _MAX_CONN,
            )
        except Exception as exc:
            logger.error(f"persistence.pooled_pg: failed to initialize writer pool: {exc}")
            _writer_pool_unavailable = True
            return None
    return _writer_pool


def _get_pool() -> Any:
    global _pool, _pool_unavailable
    if psycopg2 is None:
        return None
    if _pool is not None:
        return _pool
    if _pool_unavailable:
        return None
    with _pool_lock:
        if _pool is not None:
            return _pool
        dsn = _resolve_dsn()
        if not dsn:
            _pool_unavailable = True
            logger.warning(
                "persistence.pooled_pg: no Postgres DSN configured — "
                "checkpoint/audit/error-pattern/memory subsystems will run degraded (in-process only)."
            )
            return None
        try:
            _pool = psycopg2.pool.ThreadedConnectionPool(
                _MIN_CONN, _MAX_CONN, dsn, connect_timeout=10
            )
            logger.info(f"persistence.pooled_pg: initialized (max={_MAX_CONN} connections).")
        except Exception as exc:
            logger.error(f"persistence.pooled_pg: failed to initialize pool: {exc}")
            _pool_unavailable = True
            return None
    return _pool


@contextmanager
def get_conn():
    """Checkout a pooled connection. Raises if Postgres isn't configured/reachable —
    callers are expected to catch and fall back gracefully (see each subsystem's
    in-process fallback behavior)."""
    pool = _get_pool()
    if pool is None:
        raise RuntimeError("Postgres persistence pool unavailable")
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextmanager
def get_writer_conn():
    """PATCH v4: checkout a connection from the WRITER pool (for DDL).

    Raises `RuntimeError` if the writer pool is not configured — callers
    MUST catch and skip DDL silently (do NOT fall back to the read-only
    pool, that is the original bug).
    """
    pool = _get_writer_pool()
    if pool is None:
        raise RuntimeError("Postgres WRITER pool unavailable")
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@with_error_bus("execute")
def execute(sql: str, params: tuple = ()) -> None:
    """Execute a DML statement (INSERT/UPDATE/DELETE) against the pooler.

    PATCH v4: this is the read-write path for runtime DML. The pooler URL
    *is* writable for DML in our Supabase tenant (only DDL is blocked).
    """
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def execute_ddl(sql: str, params: tuple = ()) -> None:
    """PATCH v4: execute a DDL statement (CREATE/ALTER/DROP) against the WRITER.

    Why a separate function: Supabase production pooler is read-only for DDL.
    Routing DDL through `execute()` caused `ReadOnlySqlTransaction` errors
    that cascaded to CRITICAL silent-pattern escalation on every boot.

    Behaviour when the writer pool is unavailable:
      - Logs a single warning (sticky `_writer_not_configured_warned`)
      - Returns silently (no exception)
      - Caller should treat DDL as best-effort and rely on out-of-band
        migrations (Alembic `upgrade head` in CI/deploy).

    NOT decorated with `@with_error_bus` because DDL failures on read-only
    replicas are an expected, non-actionable condition — wrapping them
    would re-introduce the silent-pattern escalation we are fixing here.
    """
    try:
        with get_writer_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
    except RuntimeError:
        # Writer pool not configured — already warned above, swallow silently.
        return
    except Exception as exc:
        # DDL failure on a writable endpoint IS actionable — log as WARNING
        # (not ERROR, to avoid silent-pattern escalation cascading to CRITICAL).
        logger.warning("persistence.pooled_pg.execute_ddl: DDL failed (writer endpoint): %s", exc)


@with_error_bus("executemany")
def executemany(sql: str, params_list: list[tuple]) -> None:
    if not params_list:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.executemany(sql, params_list)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def query(sql: str, params: tuple = ()) -> list[tuple]:
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()


def query_dicts(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
        finally:
            cur.close()


def is_configured() -> bool:
    # বাংলা মন্তব্য: কানেকশন পুল ইনিশিয়ালাইজ না করে শুধুমাত্র কনফিগারেশন চেক করার জন্য
    return _resolve_dsn() is not None


def is_available() -> bool:
    return _get_pool() is not None


def writer_is_available() -> bool:
    """PATCH v4: cheap probe — is a writer DSN configured?

    Does NOT actually open the pool; useful for callers that want to decide
    whether to attempt DDL at all (e.g. `bootstrap_schema()`).
    """
    return _resolve_writer_dsn() is not None


def close_pool() -> None:
    global _pool, _writer_pool
    with _pool_lock, _writer_pool_lock:
        if _pool is not None:
            try:
                _pool.closeall()
                logger.info("persistence.pooled_pg: pool closed.")
            except Exception as exc:
                logger.warning(f"persistence.pooled_pg: error closing pool: {exc}")
            _pool = None
        if _writer_pool is not None:
            try:
                _writer_pool.closeall()
                logger.info("persistence.pooled_pg: writer pool closed.")
            except Exception as exc:
                logger.warning(f"persistence.pooled_pg: error closing writer pool: {exc}")
            _writer_pool = None


atexit.register(close_pool)
