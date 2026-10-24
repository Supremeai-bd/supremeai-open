"""SupremeAI Worker — Render Service 2 (Phase 10, ROADMAP §32).

বাংলা: Background task executor. Redis queue থেকে task নেয়, execute করে।
Core API থেকে আলাদা — heavy runtime এখানে, Core API light থাকে।
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("supremeai.worker")
logger.info(f">>> booting SupremeAI ecosystem worker (env={os.getenv('ENV', 'production')})")

REDIS_URL = os.getenv("REDIS_URL", "")
_CORE_API_URL_RAW = os.getenv("CORE_API_URL", "")
env = os.getenv("ENV", "production").lower()

if not _CORE_API_URL_RAW:
    if env == "local":
        # Local development fallback — production must set CORE_API_URL explicitly.
        _CORE_API_URL_RAW = "http://localhost:8000"
    else:
        logger.error(
            "CORE_API_URL is not configured. Worker cannot reach Core API in production. "
            "Please set the CORE_API_URL environment variable."
        )

CORE_API_URL = _CORE_API_URL_RAW
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2.0"))
WORKER_ID = f"worker-{os.getpid()}"


async def poll_and_execute() -> None:
    """Phase 10 — poll Redis queue, execute tasks (ROADMAP §32)."""
    if not REDIS_URL:
        logger.warning("REDIS_URL not set — worker idling")
        while True:
            await asyncio.sleep(60)
        return
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.error("redis package not installed")
        sys.exit(1)
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.ping()
    logger.info(">>> Redis connected")
    logger.info(f">>> worker {WORKER_ID} polling 'ecosystem:tasks'")
    while True:
        try:
            result = await r.blpop("ecosystem:tasks", timeout=30)
            if result is None:
                continue
            _, task_json = result
            task = json.loads(task_json)
            logger.info(f">>> task: {task.get('task_id', '?')} — {task.get('goal', '?')[:50]}")
            await _execute(task, r)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


async def _execute(task: dict, redis) -> None:
    await asyncio.sleep(1)
    result = {
        "task_id": task.get("task_id"),
        "status": "completed",
        "result": {"message": f"processed by {WORKER_ID}"},
        "completed_at": time.time(),
    }
    await redis.lpush("ecosystem:results", json.dumps(result))
    logger.info(f">>> task {task.get('task_id')} done")


async def heartbeat() -> None:
    if not REDIS_URL:
        return
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        while True:
            await r.hset(
                "ecosystem:workers",
                WORKER_ID,
                json.dumps({"id": WORKER_ID, "last_heartbeat": time.time()}),
            )
            await asyncio.sleep(10)
    except Exception as e:
        logger.debug(f"heartbeat: {e}")


async def health_server() -> None:
    from aiohttp import web

    async def health(request):
        return web.json_response({"status": "ok", "worker_id": WORKER_ID})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8001")))
    await site.start()
    logger.info(f">>> health server on port {os.getenv('PORT', '8001')}")


async def main():
    await asyncio.gather(health_server(), poll_and_execute(), heartbeat())


if __name__ == "__main__":
    asyncio.run(main())
