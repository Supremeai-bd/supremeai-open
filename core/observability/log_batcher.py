import asyncio
from collections import deque

from sqlalchemy import insert

from core.logging_config import logger
from database.session import get_db_session
from models.execution_log import ExecutionLog


class LogBatcherService:
    def __init__(self, flush_interval: float = 2.0, batch_size: int = 50):
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        self.queue: asyncio.Queue = asyncio.Queue()
        self.buffer = deque()
        self.running = False
        self.task: asyncio.Task | None = None
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run())
        logger.info("LogBatcherService started.")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            import contextlib

            with contextlib.suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        await self._flush()
        logger.info("LogBatcherService stopped.")

    def emit(self, log_entry: dict):
        """
        Produce a log entry into the queue.
        log_entry must be a dict matching ExecutionLog schema.
        """
        self.queue.put_nowait(log_entry)

        # Publish to SSE subscribers
        session_id = str(log_entry.get("session_id"))
        self.publish(session_id, log_entry)

    def publish(self, session_id: str, log_entry: dict) -> None:
        """SSE-only fanout — DB persistence ছাড়াই subscriber-দের কাছে পাঠায়।

        বাংলা: reasoning_step-এর মতো transient stream event-এর জন্য — এদের
        execution_logs টেবিলের schema নেই, তাই queue দিয়ে পাঠালে _flush()
        insert fail করে poison re-queue তৈরি হত। (Phase 1 reasoning stream)
        """
        session_id = str(session_id or log_entry.get("session_id") or "")
        if session_id in self._subscribers:
            for sub_queue in self._subscribers[session_id]:
                sub_queue.put_nowait(log_entry)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        q = asyncio.Queue()
        self._subscribers[session_id].append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue):
        if session_id in self._subscribers:
            import contextlib

            with contextlib.suppress(ValueError):
                self._subscribers[session_id].remove(q)
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]

    async def _run(self):
        while self.running:
            try:
                # Wait for at least one item, up to flush_interval
                item = await asyncio.wait_for(self.queue.get(), timeout=self.flush_interval)
                self.buffer.append(item)

                # Drain queue up to batch_size
                while len(self.buffer) < self.batch_size:
                    try:
                        next_item = self.queue.get_nowait()
                        self.buffer.append(next_item)
                    except asyncio.QueueEmpty:
                        break

                if len(self.buffer) >= self.batch_size:
                    await self._flush()
            except TimeoutError:
                if self.buffer:
                    await self._flush()
            except Exception as e:
                logger.error(f"Critical error in LogBatcherService: {e}")
                # সেলফ-হিলিং: ডাটা লস রোধে বাফার রিকিউ করা হচ্ছে
                while self.buffer:
                    item = self.buffer.popleft()
                    self.queue.put_nowait(item)

    async def _flush(self):
        if not self.buffer:
            return

        batch = list(self.buffer)
        self.buffer.clear()

        try:
            # Execute DB insertion in a new isolated session
            async for session in get_db_session():
                await session.execute(insert(ExecutionLog), batch)
                await session.commit()
                break  # Just run once
            logger.debug(f"Flushed {len(batch)} log entries to database.")
        except Exception as e:
            logger.error(f"Failed to flush log entries to database: {e}")
            # Re-queue on failure (in a real system, might use a dead-letter queue)
            for item in batch:
                self.queue.put_nowait(item)


# Global instance
batcher = LogBatcherService()
