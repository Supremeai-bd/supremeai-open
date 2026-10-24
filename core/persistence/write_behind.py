"""Write-behind batching for high-frequency, low-value-per-row writes.

Design goal: reduce "one pooled connection checkout per write" (which is
what directly caused the pool-exhaustion concern for audit_logger and
checkpoint_manager, which write far more often than error_pattern_db or
memory_service) down to "one checkout per batch".

Failure-mode honesty, stated plainly (do not remove this comment when
touching this file — it's the load-bearing tradeoff of this whole design):
  - A crash or SIGKILL between flushes loses at most `flush_interval`
    seconds / `max_batch` rows of buffered writes for that specific
    batcher. This is the same worst-case window the Redis-mirroring
    proposal had, but WITHOUT that design's split-brain-across-replicas
    risk, since each replica flushes directly to the single shared
    Postgres source of truth rather than serializing a whole local file.
  - `flush_all()` is called from the FastAPI lifespan shutdown hook on
    graceful termination, so the common case (deploys, scale-downs) loses
    nothing.
"""

from __future__ import annotations

import atexit
import queue
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

from core.logging_config import logger
from core.persistence import pooled_pg


@dataclass
class _PendingWrite:
    sql: str
    params: tuple


class WriteBehindBatcher:
    """One instance per logical table/writer. Thread-safe."""

    def __init__(self, name: str, flush_interval: float = 2.0, max_batch: int = 200):
        self.name = name
        self.flush_interval = flush_interval
        self.max_batch = max_batch
        self._queue: queue.Queue[_PendingWrite] = queue.Queue()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name=f"write-behind-{name}", daemon=True)
        self._thread.start()
        _registry.append(self)

    def submit(self, sql: str, params: tuple) -> None:
        self._queue.put(_PendingWrite(sql=sql, params=params))

    def enqueue(self, payload: dict) -> None:
        """multi_db_router.py-স্টাইল dict payload-কে প্রকৃত outbox row হিসেবে গ্রহণ করে।

        বাংলা মন্তব্য: এটাই আসল Transactional Outbox Pattern entry-point —
        payload-কে outbox_events টেবিলে insert করার SQL-এ রূপান্তর করে
        submit()-এ পাঠায়, যাতে বিদ্যমান background flush thread এবং
        idempotency-safe executemany() ব্যবহার হয় (Patch 14 fix)।
        """
        sql = (
            "INSERT INTO outbox_events "
            "(target_db, query_text, idempotency_key, created_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (idempotency_key) DO NOTHING"
        )
        params = (
            payload.get("target_db"),
            payload.get("query"),
            payload.get("idempotency_key"),
            payload.get("timestamp"),
        )
        self.submit(sql, params)

    def _drain(self, limit: int) -> list[_PendingWrite]:
        items: list[_PendingWrite] = []
        while len(items) < limit:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return items

    def _run(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self.flush_interval)
            self.flush()

    def flush(self) -> int:
        """Drain and write everything currently queued, grouped by SQL text so
        each distinct statement gets one executemany() call. Returns rows flushed."""
        with self._lock:
            items = self._drain(limit=max(self.max_batch, self._queue.qsize()))
            if not items:
                return 0
            grouped: dict[str, list[tuple]] = defaultdict(list)
            for item in items:
                grouped[item.sql].append(item.params)
            try:
                for sql, params_list in grouped.items():
                    pooled_pg.executemany(sql, params_list)
                return len(items)
            except Exception as exc:
                # Anti-Silent-Failure: log loudly. Requeue so a transient
                # Postgres blip (e.g. pooler reconnect) doesn't silently
                # drop rows — they'll be retried on the next flush cycle.
                logger.error(
                    f"write_behind[{self.name}]: flush failed ({len(items)} rows), requeueing: {exc}"
                )
                for item in items:
                    self._queue.put(item)
                return 0

    def stop(self) -> None:
        self._stop_event.set()
        self.flush()


_registry: list[WriteBehindBatcher] = []


def flush_all() -> None:
    """Called from the app shutdown hook (see core/lifespan.py) and at
    process exit as a last-resort safety net."""
    for batcher in _registry:
        try:
            n = batcher.flush()
            if n:
                logger.info(f"write_behind[{batcher.name}]: flushed {n} rows on shutdown.")
        except Exception as exc:
            logger.error(f"write_behind[{batcher.name}]: shutdown flush failed: {exc}")


atexit.register(flush_all)
