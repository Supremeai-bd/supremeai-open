import asyncio

from core.logging_config import logger

DEFAULT_QUEUE_MAXSIZE = 1000  # backpressure limit — env দিয়ে override করা যাবে


class PubSub:
    def __init__(self, queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE):
        self.subscribers: dict[str, set[asyncio.Queue]] = {}
        self._queue_maxsize = queue_maxsize
        self._lock = asyncio.Lock()  # subscribe/unsubscribe/publish-এর মধ্যে consistency

    async def subscribe(self, channel: str) -> asyncio.Queue:
        async with self._lock:
            queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
            self.subscribers.setdefault(channel, set()).add(queue)
            return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        async with self._lock:
            if channel in self.subscribers:
                self.subscribers[channel].discard(queue)
                if not self.subscribers[channel]:
                    del self.subscribers[channel]

    async def publish(self, channel: str, message: dict):
        async with self._lock:
            targets = list(self.subscribers.get(channel, ()))  # snapshot — safe iteration

        if not targets:
            logger.debug(f"[PubSub] No subscribers for channel '{channel}', message dropped.")
            return

        async def _deliver(q: asyncio.Queue):
            try:
                await asyncio.wait_for(q.put(message), timeout=2.0)
            except (TimeoutError, asyncio.QueueFull):
                logger.warning(
                    f"[PubSub] Slow consumer on '{channel}' — message dropped for one subscriber."
                )

        await asyncio.gather(*(_deliver(q) for q in targets), return_exceptions=True)


# Global Instance
global_pubsub = PubSub()
