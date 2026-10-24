import asyncio
import time
from collections import OrderedDict
from typing import Any


class OptimizedAsyncLRUCache:
    """
    Optimized Async LRU Cache for SupremeAI.
    Uses collections.OrderedDict for O(1) eviction and LRU tracking.
    Async-safe with asyncio.Lock. Supports lazy TTL expiration.
    """

    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self.cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.maxsize = maxsize
        self.ttl = ttl
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> Any | None:
        """Get a value from cache asynchronously."""
        async with self._lock:
            if key not in self.cache:
                self.misses += 1
                return None

            timestamp, value = self.cache[key]
            if time.time() - timestamp > self.ttl:
                # Lazy expiration
                self.cache.pop(key)
                self.misses += 1
                return None

            # Move to end to mark as recently used
            self.cache.move_to_end(key)
            self.hits += 1
            return value

    async def put(self, key: str, value: Any) -> None:
        """Put a value into cache asynchronously."""
        async with self._lock:
            if key in self.cache:
                # Update existing and move to end
                self.cache[key] = (time.time(), value)
                self.cache.move_to_end(key)
            else:
                if len(self.cache) >= self.maxsize:
                    # O(1) eviction of oldest item (FIFO)
                    self.cache.popitem(last=False)
                self.cache[key] = (time.time(), value)

    async def invalidate(self, key: str) -> None:
        """Remove a specific key from cache."""
        async with self._lock:
            if key in self.cache:
                self.cache.pop(key)

    def clear(self) -> None:
        """Clear all entries in the cache (sync method since it doesn't await)."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {
            "size": len(self.cache),
            "maxsize": self.maxsize,
            "ttl": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": self.hits / (self.hits + self.misses)
            if (self.hits + self.misses) > 0
            else 0,
        }


# Factory and Singleton Pattern Implementation
_GLOBAL_CACHES: dict[str, OptimizedAsyncLRUCache] = {}


def create_optimized_cache(maxsize: int = 1000, ttl: int = 300) -> OptimizedAsyncLRUCache:
    """Create and return a new OptimizedAsyncLRUCache instance."""
    return OptimizedAsyncLRUCache(maxsize=maxsize, ttl=ttl)


def get_cache(name: str, maxsize: int = 1000, ttl: int = 300) -> OptimizedAsyncLRUCache:
    """Get or create a named singleton cache."""
    if name not in _GLOBAL_CACHES:
        _GLOBAL_CACHES[name] = OptimizedAsyncLRUCache(maxsize=maxsize, ttl=ttl)
    return _GLOBAL_CACHES[name]
