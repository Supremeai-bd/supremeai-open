import threading
import time

from core.logging_config import logger
from database.supabase_client import db


class LogBatcherError(Exception):
    pass


class SupremeLogBatcher:
    def __init__(self, max_batch_size: int = 100, flush_interval_secs: int = 5):
        self.max_batch_size = max_batch_size
        self.flush_interval_secs = flush_interval_secs
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._last_flush_time = time.time()

    def append_log(self, level: str, message: str, metadata: dict | None = None) -> None:
        log_entry = {
            "level": level,
            "message": message,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }

        with self._lock:
            self._buffer.append(log_entry)
            buffer_size = len(self._buffer)

        if buffer_size >= self.max_batch_size:
            self.flush_buffer()

    def flush_buffer(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            batch_to_process = list(self._buffer)
            self._buffer.clear()

        try:
            for log in batch_to_process:
                db.append_evolution_log(log)

            self._last_flush_time = time.time()
            logger.debug(
                f"Successfully flushed {len(batch_to_process)} system logs to infrastructure ledger."
            )

        except Exception as e:
            with self._lock:
                self._buffer = batch_to_process + self._buffer

            err_msg = f"Failed to flush log batch of size {len(batch_to_process)}. Re-queueing tokens: {e}"
            logger.error(f"🚨 [LOG_BATCHER_LEAK]: {err_msg}")
            raise LogBatcherError(err_msg) from e
