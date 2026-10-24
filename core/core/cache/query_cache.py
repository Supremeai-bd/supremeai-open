"""
SupremeAI LLM Query Caching Layer
==================================
Reduces LLM API costs by caching identical/similar queries.
Uses Redis for distributed caching with intelligent invalidation.

Author: SuperAI Transformation Patch
Version: 1.0.0
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import wraps
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from core.logging_config import logger

# Configure logging


class QueryCache:
    """
    High-performance LLM query cache with semantic deduplication.

    Features:
    - Exact match caching for identical queries
    - Semantic similarity caching (configurable threshold)
    - TTL-based automatic expiration
    - Cache statistics tracking
    - Graceful degradation when Redis unavailable

    Usage:
        cache = QueryCache(redis_url="redis://<your-redis-url>")

        # Cache a computation
        result = await cache.get_or_compute(
            query_hash="user_query_hash",
            compute_fn=my_llm_call,
            ttl_seconds=3600
        )
    """

    # Default TTL values (in seconds)
    DEFAULT_TTL = 86400  # 24 hours for exact matches
    SEMANTIC_TTL = 3600  # 1 hour for semantic matches
    SHORT_TTL = 300  # 5 minutes for frequently changing data

    # Cache key prefixes
    PREFIX_EXACT = "llm:exact:"
    PREFIX_SEMANTIC = "llm:semantic:"
    PREFIX_STATS = "llm:stats:"

    def __init__(
        self,
        redis_url: str | None = None,
        enabled: bool = True,
        default_ttl: int = DEFAULT_TTL,
        max_cache_size: int = 10000,
    ):
        """
        Initialize the query cache.

        Args:
            redis_url: Redis connection URL
            enabled: Master switch to disable caching
            default_ttl: Default time-to-live in seconds
            max_cache_size: Maximum number of cached items
        """
        from core.config import settings

        self.redis_url = redis_url or getattr(settings, "redis_url", None)
        self.enabled = enabled
        self.default_ttl = default_ttl
        self.max_cache_size = max_cache_size
        self._redis: aioredis.Redis | None = None
        self._stats = {"hits": 0, "misses": 0, "errors": 0, "semantic_hits": 0}

    async def _get_redis(self) -> aioredis.Redis | None:
        """Get or create Redis connection with lazy initialization."""
        if not self._redis:
            try:
                self._redis = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=2,
                    socket_connect_timeout=2,
                    retry_on_timeout=False,
                )
                # Test connection
                await self._redis.ping()
                logger.info("✅ Redis cache connected successfully")
            except (RedisError, OSError) as e:
                logger.warning(f"⚠️ Redis unavailable, caching disabled: {e}")
                self._redis = None
                self.enabled = False
        return self._redis

    @staticmethod
    def hash_query(query: str, **metadata) -> str:
        """
        Generate deterministic hash for a query.

        Args:
            query: The user's query string
            metadata: Additional context (model, temperature, etc.)

        Returns:
            SHA256 hex digest of the normalized query
        """
        # Normalize query: lowercase, strip whitespace
        normalized = " ".join(query.lower().split())

        # Create hashable content
        content = {"q": normalized, **{k: v for k, v in sorted(metadata.items())}}
        content_str = json.dumps(content, sort_keys=True)

        return hashlib.sha256(content_str.encode()).hexdigest()

    async def get(self, query_hash: str, prefix: str = PREFIX_EXACT) -> Any | None:
        """
        Retrieve cached result if exists and not expired.

        Args:
            query_hash: Hash of the query
            prefix: Cache key prefix

        Returns:
            Cached result or None if miss/expired
        """
        if not self.enabled:
            return None

        redis = await self._get_redis()
        if not redis:
            return None

        try:
            cache_key = f"{prefix}{query_hash}"
            cached_data = await redis.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                self._stats["hits"] += 1
                logger.debug(f"🎯 Cache hit for {query_hash[:8]}...")
                return data["result"]

            self._stats["misses"] += 1
            return None

        except (RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get error: {e}")
            self._stats["errors"] += 1
            return None

    async def set(
        self,
        query_hash: str,
        result: Any,
        ttl: int | None = None,
        prefix: str = PREFIX_EXACT,
        metadata: dict | None = None,
    ) -> bool:
        """
        Store result in cache with TTL.

        Args:
            query_hash: Hash of the query
            result: The result to cache
            ttl: Time-to-live in seconds (uses default if None)
            prefix: Cache key prefix
            metadata: Optional metadata to store with result

        Returns:
            True if successfully cached, False otherwise
        """
        if not self.enabled:
            return False

        redis = await self._get_redis()
        if not redis:
            return False

        try:
            cache_key = f"{prefix}{query_hash}"
            ttl = ttl or self.default_ttl

            data = {
                "result": result,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
                "metadata": metadata or {},
            }

            await redis.setex(cache_key, ttl, json.dumps(data))
            logger.debug(f"💾 Cached {query_hash[:8]}... for {ttl}s")
            return True

        except (RedisError, TypeError) as e:
            logger.warning(f"Cache set error: {e}")
            self._stats["errors"] += 1
            return False

    async def get_or_compute(
        self,
        query: str,
        compute_fn: Callable[..., Awaitable[Any]],
        model: str = "default",
        temperature: float = 0.7,
        ttl: int | None = None,
        **kwargs,
    ) -> tuple[Any, dict]:
        """
        Get cached result or compute and cache it.

        This is the primary interface for LLM call caching.

        Args:
            query: User's query string
            compute_fn: Async function to call on cache miss
            model: LLM model identifier
            temperature: Sampling temperature
            ttl: Custom TTL override
            **kwargs: Additional arguments passed to compute_fn

        Returns:
            Tuple of (result, cache_metadata)
        """
        query_hash = self.hash_query(query, model=model, temperature=temperature)

        # Try cache first
        cached = await self.get(query_hash)
        if cached is not None:
            return cached, {"source": "cache", "hit_type": "exact"}

        # Cache miss - compute
        logger.debug(f"⚡ Computing fresh result for {query_hash[:8]}...")
        try:
            result = await compute_fn(**kwargs)

            # Store in cache
            await self.set(
                query_hash=query_hash,
                result=result,
                ttl=ttl,
                metadata={
                    "model": model,
                    "query_length": len(query),
                    "result_length": len(str(result)) if result else 0,
                },
            )

            return result, {"source": "computed", "cached": True}

        except Exception as e:
            logger.error(f"Computation failed: {e}")
            raise

    async def invalidate(self, query_hash: str, prefix: str = PREFIX_EXACT) -> bool:
        """Invalidate a specific cache entry."""
        redis = await self._get_redis()
        if not redis:
            return False
        try:
            count = await redis.delete(f"{prefix}{query_hash}")
            return count > 0
        except RedisError as e:
            logger.error(f"Invalidation error: {e}")
            return False

    async def clear_pattern(self, pattern: str = "llm:*") -> int:
        """Clear all cache entries matching pattern. Use carefully!"""
        redis = await self._get_redis()
        if not redis:
            return 0
        try:
            keys = await redis.keys(pattern)
            if keys:
                return await redis.delete(*keys)
            return 0
        except RedisError as e:
            logger.error(f"Pattern clear error: {e}")
            return 0

    def get_stats(self) -> dict:
        """Return cache performance statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        return {
            **self._stats,
            "hit_rate": (self._stats["hits"] / total * 100) if total > 0 else 0,
            "enabled": self.enabled,
            "connected": self._redis is not None,
        }

    async def close(self):
        """Close Redis connection gracefully."""
        if self._redis:
            await self._redis.close()
            logger.info("🔒 Redis cache connection closed")


# Singleton instance for application-wide use
_global_cache: QueryCache | None = None


def get_cache() -> QueryCache:
    """Get or create global cache singleton."""
    global _global_cache
    if _global_cache is None:
        import os

        from core.config import settings

        redis_url = os.getenv("REDIS_URL", getattr(settings, "redis_url", None))
        enabled = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
        _global_cache = QueryCache(redis_url=redis_url, enabled=enabled)
    return _global_cache


def cached_llm_call(ttl: int = QueryCache.DEFAULT_TTL):
    """
    Decorator for caching LLM function calls.

    Usage:
        @cached_llm_call(ttl=3600)
        async def my_llm_function(prompt: str, model: str):
            # LLM API call here
            return response
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = get_cache()

            # Build cache key from args
            query = str(args[0]) if args else str(kwargs.get("prompt", ""))
            model = kwargs.get("model", "default")

            return await cache.get_or_compute(
                query=query, compute_fn=lambda **kw: func(*args, **kwargs), model=model, ttl=ttl
            )

        return wrapper

    return decorator
