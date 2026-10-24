"""core/degraded_mode.py
=======================
Single source of truth for the P0 "Self-Evolution Zero-Cost" safety policy:

* production detection (``is_production``)
* the opt-in DB-degradation escape hatch (``allow_db_degradation``)
* whether the main SQLAlchemy engine is running degraded (``db_degraded``)
* whether a subsystem may fall back to a local SQLite file (``sqlite_fallback_allowed``)

Design contract (Sprint 1 "P0 Safety"):

1. Dev/test behaviour is IDENTICAL to pre-gate behaviour — every SQLite
   fallback keeps working when ``sqlite_fallback_allowed()`` returns True.
2. In production, SQLite fallbacks are FAIL-CLOSED: the subsystem must not
   silently land on an ephemeral SQLite file. It either
   - disables the feature loudly (``SQLiteFallbackDisabledError`` /
     ``available=False`` / empty or 503-style responses), or
   - degrades to a bounded IN-PROCESS buffer (``InMemoryRing`` /
     ``InMemoryDocumentStore``) so events remain gettable in-process.
3. The CRITICAL refusal warning is emitted exactly ONCE per feature so logs
   stay actionable without spamming.
4. Boot must never crash because of the gate: gates are evaluated lazily at
   first USE of the persistence layer, not at import time.

Wave 0.1 hard-fail (issue #1224): the ``SUPABASE_ALLOW_DB_DEGRADATION=true``
escape hatch NO LONGER permits SQLite fallback in production — SQLite fallbacks
there are refused unconditionally (silent ephemeral-writer data loss is dead).
The flag still governs the degraded REST-only boot (``database/session.py``)
and dev/staging behaviour.
"""

from __future__ import annotations

import os
import sys
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from core.logging_config import logger

__all__ = [
    "DEFAULT_IN_MEMORY_MAXLEN",
    "InMemoryDocumentStore",
    "InMemoryRing",
    "SQLiteFallbackDisabledError",
    "allow_db_degradation",
    "db_degraded",
    "is_production",
    "is_test_context",
    "require_sqlite_allowed",
    "reset_warned_features",
    "sqlite_fallback_allowed",
]

# Bounded size of every in-process degraded buffer (events survive only for
# the lifetime of the process and are dropped FIFO beyond this cap).
DEFAULT_IN_MEMORY_MAXLEN = 5000

# The one canonical opt-in flag plus legacy aliases accepted for backwards
# compatibility with earlier patch iterations.
_DEGRADATION_FLAGS = (
    "SUPABASE_ALLOW_DB_DEGRADATION",  # canonical (database/session.py contract)
    "ALLOW_DB_DEGRADATION",  # legacy alias
)

_PRODUCTION_ENVS = {"production", "prod"}
_TEST_ENVS = {"test", "testing"}
_NON_PROD_STRICT_ENVS = _PRODUCTION_ENVS | {"staging"}

# Features already warned about (module-level so the CRITICAL fires ONCE).
_warned_features: set[str] = set()
_warn_lock = threading.Lock()


def _effective_env() -> str:
    """Resolve the effective environment string.

    Prefers the canonical ``settings.env`` (pydantic ``ENV`` alias) and falls
    back to the raw env var so the check works even when core.config cannot be
    imported (circular-import safety / very early boot).
    """
    env = ""
    try:
        from core.config import settings  # imported lazily to avoid import cycles

        env = (getattr(settings, "env", "") or "").lower()
    except Exception:  # pragma: no cover - defensive: config unavailable
        env = ""
    if not env:
        env = (os.getenv("ENV", "") or "").lower()
    return env


def is_production() -> bool:
    """True when running in a production environment (settings.env or $ENV)."""
    return _effective_env() in _PRODUCTION_ENVS


def allow_db_degradation() -> bool:
    """Whether the operator explicitly opted into persistence-less degradation.

    Canonical flag: ``SUPABASE_ALLOW_DB_DEGRADATION=true`` (the same flag the
    main engine in database/session.py honours for the degraded REST-only
    boot). Legacy alias ``ALLOW_DB_DEGRADATION`` is also accepted.
    Wave 0.1 (issue #1224): this flag no longer permits SQLite fallback in
    production — :func:`sqlite_fallback_allowed` hard-fails there unconditionally.
    """
    for flag in _DEGRADATION_FLAGS:
        if (os.getenv(flag, "") or "").strip().lower() == "true":
            return True
    return False


def db_degraded() -> bool:
    """True when the main engine is intentionally running WITHOUT SQL access.

    Production + explicit opt-in flag + no pooler URL configured = the exact
    "degraded REST-only boot" condition implemented in database/session.py.
    """
    return (
        is_production()
        and allow_db_degradation()
        and not (os.getenv("SUPABASE_DATABASE_URL_POOLER", "") or "").strip()
    )


def is_test_context() -> bool:
    """True in unit-test / CI contexts (pytest loaded, CI env, ENV=test).

    Production ALWAYS wins: even when pytest is loaded, a production
    environment is never considered a test context (mirrors
    utils.environment.is_test_environment).
    """
    if (os.getenv("ENV", "") or "").lower() in _NON_PROD_STRICT_ENVS:
        return False
    if _effective_env() in _NON_PROD_STRICT_ENVS:
        return False
    if (
        "pytest" in sys.modules
        or os.getenv("CI") == "true"
        or os.getenv("GITHUB_ACTIONS") == "true"
    ):
        return True
    return _effective_env() in _TEST_ENVS or (os.getenv("TESTING", "") or "").lower() == "true"


def _warn_once(feature: str) -> None:
    """Emit the P0 CRITICAL refusal warning exactly once per feature."""
    with _warn_lock:
        already = feature in _warned_features
        if not already:
            _warned_features.add(feature)
    if not already:
        logger.critical(
            f"P0: SQLite fallback refused for feature={feature} — persistence unavailable "
            f"in production — SUPABASE_ALLOW_DB_DEGRADATION no longer permits SQLite "
            f"fallback; provision a durable backend"
        )


def sqlite_fallback_allowed(feature: str) -> bool:
    """May *feature* fall back to a local SQLite file?

    True  — dev/test/staging.
    False — production (unconditionally, even with the degradation flag set):
            SQLite must NOT be opened. The first refusal per feature logs a
            CRITICAL "P0:" message.
    """
    if not is_production():
        return True
    # Wave 0.1 (issue #1224): production hard-fail — the degradation flag no
    # longer opens the SQLite-fallback escape hatch. The flag-as-escape only
    # ever produced a silent data-loss window (ephemeral writers) in prod.
    if is_test_context():
        return True
    _warn_once(feature)
    return False


def require_sqlite_allowed(feature: str) -> None:
    """Fail-closed variant of :func:`sqlite_fallback_allowed`.

    Raises :class:`SQLiteFallbackDisabledError` when the SQLite fallback for
    *feature* is refused in production. Callers MUST either catch this and
    mark themselves unavailable/degraded, or let it surface as a loud
    request-scoped failure — it must never silently fall through to SQLite.
    """
    if not sqlite_fallback_allowed(feature):
        raise SQLiteFallbackDisabledError(
            f"[P0] SQLite fallback refused for feature={feature!r} in production — "
            f"persistence unavailable. SUPABASE_ALLOW_DB_DEGRADATION no longer permits "
            f"SQLite fallback; provision a durable backend."
        )


def reset_warned_features() -> None:
    """Clear the once-per-feature warning cache (testing helper)."""
    with _warn_lock:
        _warned_features.clear()


class SQLiteFallbackDisabledError(RuntimeError):
    """Raised when a subsystem attempts a SQLite fallback refused by policy."""


class InMemoryRing:
    """Bounded, thread-safe in-process event buffer for degraded (no-DB) mode.

    Used by subsystems that must stay functional in production without any
    durable backend: events are kept in-process (FIFO, capped at ``maxlen``)
    and remain retrievable until the process exits. NEVER a durable store.
    """

    def __init__(self, maxlen: int = DEFAULT_IN_MEMORY_MAXLEN):
        self._maxlen = maxlen
        self._deque: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, item: Any) -> None:
        with self._lock:
            self._deque.append(item)

    def snapshot(self) -> list:
        """Return a shallow copy of the buffered items (oldest first)."""
        with self._lock:
            return list(self._deque)

    def remove_matching(self, predicate: Callable[[Any], bool]) -> int:
        """Drop all items for which ``predicate(item)`` is True. Returns count."""
        with self._lock:
            kept = [item for item in self._deque if not predicate(item)]
            removed = len(self._deque) - len(kept)
            self._deque = deque(kept, maxlen=self._maxlen)
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._deque)


# ── Minimal in-process document store (Firestore-shaped) ─────────────────────
# Used by core/utils/firestore_helpers.py when Firestore is unavailable AND the
# SQLite fallback is refused: documents stay queryable in-process only.


class _InMemoryDocumentSnapshot:
    def __init__(self, data: dict | None):
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict:
        return dict(self._data) if self._data else {}


class _InMemoryDocumentRef:
    def __init__(self, store: InMemoryDocumentStore, collection: str, doc_id: str):
        self._store = store
        self._collection = collection
        self.id = doc_id

    def _col(self) -> dict[str, dict]:
        return self._store._documents.setdefault(self._collection, {})

    def set(self, data: dict, merge: bool = False) -> None:
        with self._store._lock:
            col = self._col()
            if merge and self.id in col:
                col[self.id].update(data)
            else:
                col[self.id] = dict(data)
            self._store._evict_locked(self._collection)

    def update(self, data: dict) -> None:
        with self._store._lock:
            col = self._col()
            if self.id in col:
                col[self.id].update(data)
            else:
                col[self.id] = dict(data)
            self._store._evict_locked(self._collection)

    def get(self) -> _InMemoryDocumentSnapshot:
        with self._store._lock:
            col = self._col()
            if self.id in col:
                return _InMemoryDocumentSnapshot(dict(col[self.id]))
        return _InMemoryDocumentSnapshot(None)

    def delete(self) -> None:
        with self._store._lock:
            self._col().pop(self.id, None)

    def collection(self, name: str) -> _InMemoryCollection:
        return self._store.collection(f"{self._collection}/{self.id}/{name}")


class _InMemoryQuery:
    def __init__(self, docs: list[dict], ids: list[str]):
        self._docs = docs
        self._ids = ids

    def where(self, field: str, op: str, value: Any) -> _InMemoryQuery:
        ops = {
            "==": lambda d: d.get(field) == value,
            "!=": lambda d: d.get(field) != value,
            ">": lambda d: d.get(field, 0) > value,
            "<": lambda d: d.get(field, 0) < value,
            ">=": lambda d: d.get(field, 0) >= value,
            "<=": lambda d: d.get(field, 0) <= value,
        }
        if op not in ops:
            raise ValueError(f"InMemoryDocumentStore: unsupported operator {op!r}")
        pred = ops[op]
        pairs = [(d, i) for d, i in zip(self._docs, self._ids, strict=True) if pred(d)]
        self._docs = [p[0] for p in pairs]
        self._ids = [p[1] for p in pairs]
        return self

    def order_by(self, field: str, direction: str = "ASCENDING") -> _InMemoryQuery:
        reverse = str(direction).upper().startswith("DESC")
        pairs = sorted(
            zip(self._docs, self._ids, strict=True),
            key=lambda p: (p[0].get(field) is None, p[0].get(field)),
            reverse=reverse,
        )
        self._docs = [p[0] for p in pairs]
        self._ids = [p[1] for p in pairs]
        return self

    def limit(self, count: int) -> _InMemoryQuery:
        self._docs = self._docs[:count]
        self._ids = self._ids[:count]
        return self

    def stream(self) -> list:
        return [_InMemoryQueryDoc(d, i) for d, i in zip(self._docs, self._ids, strict=True)]


class _InMemoryQueryDoc:
    """Stream item exposing ``.id`` and ``.to_dict()`` (Firestore-ish)."""

    def __init__(self, data: dict, doc_id: str):
        self._data = data
        self.id = doc_id

    def to_dict(self) -> dict:
        return dict(self._data)


class _InMemoryCollection:
    def __init__(self, store: InMemoryDocumentStore, name: str):
        self._store = store
        self._name = name

    def document(self, doc_id: str | None = None) -> _InMemoryDocumentRef:
        import uuid as _uuid

        return _InMemoryDocumentRef(self._store, self._name, doc_id or _uuid.uuid4().hex)

    def add(self, data: dict) -> tuple:
        import uuid as _uuid

        doc_id = _uuid.uuid4().hex
        self.document(doc_id).set(data)
        return ("", self.document(doc_id))

    def _docs(self) -> tuple[list[dict], list[str]]:
        with self._store._lock:
            col = self._store._documents.get(self._name, {})
            ids = list(col.keys())
            docs = [dict(col[i]) for i in ids]
        return docs, ids

    def where(self, field: str, op: str, value: Any) -> _InMemoryQuery:
        docs, ids = self._docs()
        return _InMemoryQuery(docs, ids).where(field, op, value)

    def order_by(self, field: str, direction: str = "ASCENDING") -> _InMemoryQuery:
        docs, ids = self._docs()
        return _InMemoryQuery(docs, ids).order_by(field, direction)

    def limit(self, count: int) -> _InMemoryQuery:
        docs, ids = self._docs()
        return _InMemoryQuery(docs, ids).limit(count)

    def stream(self) -> list:
        docs, ids = self._docs()
        return _InMemoryQuery(docs, ids).stream()


class _InMemoryTransaction:
    """No-op transaction object: callers may commit/rollback safely."""

    def __init__(self):
        self._ops: list = []

    def set(self, ref: Any, data: dict, merge: bool = False) -> None:
        ref.set(data, merge=merge)

    def commit(self) -> bool:
        return True

    def rollback(self) -> None:
        return None


class _InMemoryBatch:
    def __init__(self):
        self._ops: list = []

    def set(self, ref: Any, data: dict, merge: bool = False) -> None:
        self._ops.append((ref, data, merge))

    def commit(self) -> None:
        for ref, data, merge in self._ops:
            ref.set(data, merge=merge)
        self._ops.clear()


class InMemoryDocumentStore:
    """Bounded in-process Firestore-shaped document store (NOT durable).

    Kept per-process; per-collection documents are capped at ``max_docs`` with
    FIFO eviction. Provides the small subset of the Firestore client API used
    by the codebase (collection/document/set/get/update/delete/add/where/
    order_by/limit/stream/batch/transaction).
    """

    def __init__(self, max_docs: int = DEFAULT_IN_MEMORY_MAXLEN):
        self._max_docs = max_docs
        self._documents: dict[str, dict[str, dict]] = {}
        self._lock = threading.Lock()

    def _evict_locked(self, collection: str) -> None:
        col = self._documents.get(collection)
        if col is None:
            return
        overflow = len(col) - self._max_docs
        if overflow > 0:
            for doc_id in list(col.keys())[:overflow]:
                col.pop(doc_id, None)

    def collection(self, name: str) -> _InMemoryCollection:
        return _InMemoryCollection(self, name)

    def transaction(self) -> _InMemoryTransaction:
        return _InMemoryTransaction()

    def batch(self) -> _InMemoryBatch:
        return _InMemoryBatch()
