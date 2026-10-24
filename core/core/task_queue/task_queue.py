import asyncio
import json
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from core.logging_config import logger

# Placeholder URL tokens that indicate "Redis not really configured".
# Booting a BLPOP loop against these burns Upstash free-tier quota (10k
# commands/day) with zero useful work (R2-03).
_PLACEHOLDER_TOKENS = ("<your-redis-url>", "<your", "example.com", "localhost_placeholder")


def redis_configured() -> bool:
    """Return True only when a real REDIS_URL is present (R2-03 guard)."""
    try:
        from core.config import settings

        url = getattr(settings, "redis_url", None) or os.environ.get("REDIS_URL", "")
    except Exception:  # noqa: BLE001 — settings may be unavailable very early
        url = os.environ.get("REDIS_URL", "")
    if not url:
        return False
    lowered = url.lower()
    return not any(token in lowered for token in _PLACEHOLDER_TOKENS)


class RedisTaskQueue:
    """
    G6: Redis-backed distributed task queue for long LLM operations.
    Replaces local asyncio.Tasks for better scaling and load balancing.

    R2-03 (Upstash quota protection):
    - The worker loop is LAZY: it only runs while there is (recent) work.
      An always-on `BLPOP every 5s` alone consumed ~17k commands/day —
      more than the entire Upstash free-tier daily quota — even with zero tasks.
    - `enqueue()` auto-starts the worker on demand.
    - Errors back off exponentially (1s→60s) instead of hammering Redis
      at 1 retry/second (86k cmds/day when Redis is down).
    """

    IDLE_SHUTDOWN_SECONDS = 300  # stop worker after 5 min without a task
    MAX_BLPOP_TIMEOUT = 30  # single long-poll ceiling (Upstash caps blocking cmds)

    def __init__(self, queue_name: str = "supreme_task_queue"):
        self.queue_name = queue_name
        self.redis = None
        self._handlers: dict[str, Callable[[dict], Awaitable[Any]]] = {}
        self._worker_task: asyncio.Task | None = None

    async def _get_redis(self):
        if not self.redis:
            import redis.asyncio as aioredis

            from core.config import settings

            redis_url = getattr(settings, "redis_url", None) or os.environ.get(
                "REDIS_URL", "redis://<your-redis-url>"
            )
            self.redis = aioredis.from_url(redis_url, decode_responses=True)
        return self.redis

    def ensure_worker_started(self) -> None:
        """Start the worker loop lazily (first enqueue). No-op if running."""
        if self._worker_task is not None and not self._worker_task.done():
            return
        if not redis_configured():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop (e.g. import time) — enqueue() will retry later
        self._worker_task = loop.create_task(self.worker_loop())
        logger.info("✅ Task queue worker started lazily (on-demand, quota-safe).")

    async def enqueue(self, task_type: str, payload: dict, user_id: str) -> str:
        if not redis_configured():
            logger.warning(
                "TaskQueue.enqueue rejected: no real REDIS_URL configured "
                "(task dropped — configure REDIS_URL to enable background tasks)"
            )
            # Fail soft: returning an id keeps callers working, status stays 'pending'
            return str(uuid.uuid4())
        redis = await self._get_redis()
        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "task_type": task_type,
            "user_id": user_id,
            "payload": payload,
            "status": "pending",
        }
        await redis.rpush(self.queue_name, json.dumps(task_data))
        # Store metadata for polling status
        await redis.set(f"task:{task_id}", json.dumps(task_data), ex=86400)
        logger.info(f"Queued task {task_id} of type {task_type} for user {user_id}")
        self.ensure_worker_started()
        return task_id

    def register_handler(self, task_type: str, handler: Callable[[dict], Awaitable[Any]]):
        self._handlers[task_type] = handler

    async def worker_loop(self):
        """Quota-safe worker: runs only while work is (recently) arriving."""
        try:
            redis = await self._get_redis()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Task queue worker not started (Redis unavailable): {exc}")
            self._worker_task = None
            return
        logger.info(f"Task queue worker listening on {self.queue_name}...")
        idle_seconds = 0.0
        error_backoff = 1.0

        while idle_seconds < self.IDLE_SHUTDOWN_SECONDS:
            try:
                try:
                    result = await asyncio.wait_for(
                        redis.blpop(self.queue_name, timeout=self.MAX_BLPOP_TIMEOUT),
                        timeout=self.MAX_BLPOP_TIMEOUT + 5,
                    )
                except TimeoutError:
                    result = None
                if result:
                    error_backoff = 1.0
                    idle_seconds = 0.0
                    _, task_json = result
                    task_data = json.loads(task_json)
                    # Run in background to avoid blocking other pop requests; track and log errors
                    from core.utils.background_tasks import safe_create_task

                    safe_create_task(
                        self._process_task(task_data),
                        name=f"task_queue_{task_data.get('task_id', 'unknown')}",
                    )
                else:
                    idle_seconds += self.MAX_BLPOP_TIMEOUT
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Exponential backoff: 1s → 2s → 4s … capped at 60s
                logger.error(f"Worker loop error: {e} (retry in {error_backoff:.0f}s)")
                await asyncio.sleep(error_backoff)
                error_backoff = min(error_backoff * 2, 60.0)
                idle_seconds += error_backoff

        logger.info(
            f"Task queue worker idle for {self.IDLE_SHUTDOWN_SECONDS}s — stopping "
            "(auto-restarts on next enqueue; saves Upstash free-tier commands)."
        )
        self._worker_task = None

    async def _process_task(self, task_data: dict):
        task_id = task_data["task_id"]
        task_type = task_data["task_type"]
        redis = await self._get_redis()

        handler = self._handlers.get(task_type)
        if not handler:
            logger.error(f"No handler for task type {task_type}")
            task_data["status"] = "failed"
            task_data["error"] = "No handler"
            await redis.set(f"task:{task_id}", json.dumps(task_data), ex=86400)
            return

        try:
            task_data["status"] = "processing"
            await redis.set(f"task:{task_id}", json.dumps(task_data), ex=86400)

            result = await handler(task_data)

            task_data["status"] = "completed"
            task_data["result"] = result
            await redis.set(f"task:{task_id}", json.dumps(task_data), ex=86400)

            # #1832: কমপ্লিশন নোটিফিকেশন এখন লাইভ SSE চ্যানেলে যায়
            # (dashboard_events — /api/dashboard/stream-এর সাবস্ক্রাইবাররা পায়)।
            # আগের unmounted WS ম্যানেজার broadcast
            # করত — কোনো সাবস্ক্রাইবার থাকা অসম্ভব, নোটিফিকেশন নীরবে হারাত।
            try:
                from core.messaging.pubsub import global_pubsub

                await global_pubsub.publish(
                    "dashboard_events",
                    {
                        "type": "task_completed",
                        "task_id": task_id,
                        "user_id": task_data.get("user_id", "unknown"),
                        "result": result,
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            task_data["status"] = "failed"
            task_data["error"] = str(e)
            await redis.set(f"task:{task_id}", json.dumps(task_data), ex=86400)


task_queue = RedisTaskQueue()
