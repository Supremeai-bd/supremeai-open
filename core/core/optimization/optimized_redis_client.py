import asyncio
import os

from core.logging_config import logger
from core.resilience.circuit_breaker import CircuitBreakerState

try:
    import redis.asyncio as aioredis
    from redis.exceptions import ConnectionError, RedisError, TimeoutError
except ImportError:
    # Graceful fallback if redis is not installed
    aioredis = None


class CircuitBreaker:
    """Simple circuit breaker for Redis connections."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0
        # Issue #684 (H-05): canonical breaker-state enum instead of raw literals.
        self.state = CircuitBreakerState.CLOSED

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = asyncio.get_event_loop().time()
        if self.failures >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning("Redis Circuit Breaker OPENED due to multiple failures")

    def record_success(self):
        if self.state != CircuitBreakerState.CLOSED:
            logger.info("Redis Circuit Breaker CLOSED (recovery successful)")
        self.failures = 0
        self.state = CircuitBreakerState.CLOSED

    def can_execute(self) -> bool:
        if self.state == CircuitBreakerState.CLOSED:
            return True
        if self.state == CircuitBreakerState.OPEN:
            if asyncio.get_event_loop().time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False
        # HALF_OPEN - allow one test request
        return True


class OptimizedRedisClient:
    """
    Optimized Redis client with connection pooling, circuit breaker,
    auto-reconnection with exponential backoff, and health monitoring.
    """

    def __init__(self, url: str | None = None, max_connections: int = 20):
        from core.config import settings

        self.url = url or getattr(settings, "redis_url", None)
        self.max_connections = max_connections
        self.pool: aioredis.ConnectionPool | None = None
        self.client: aioredis.Redis | None = None
        self.circuit_breaker = CircuitBreaker()
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the Redis connection pool."""
        if aioredis is None:
            logger.error(
                "redis[asyncio] is not installed. OptimizedRedisClient will run in fallback mode."
            )
            return

        async with self._lock:
            if self.pool is None:
                try:
                    self.pool = aioredis.ConnectionPool.from_url(
                        self.url,
                        max_connections=self.max_connections,
                        decode_responses=True,
                        socket_connect_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5")),
                        socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5")),
                        health_check_interval=30,
                    )
                    self.client = aioredis.Redis(connection_pool=self.pool)
                    # Ping to verify
                    await self.client.ping()
                    self.circuit_breaker.record_success()
                    logger.info("OptimizedRedisClient initialized successfully.")
                except Exception as e:
                    logger.error(f"Failed to initialize Redis pool: {e}")
                    self.circuit_breaker.record_failure()

    async def get_client(self) -> aioredis.Redis | None:
        """Get the active Redis client if circuit is closed/half-open."""
        if self.client is None:
            await self.initialize()

        if not self.circuit_breaker.can_execute():
            raise Exception("Circuit breaker is OPEN. Redis requests are temporarily blocked.")

        return self.client

    async def execute_with_retry(self, operation, *args, **kwargs):
        """Execute a Redis operation with retry and circuit breaking."""
        max_retries = 3
        base_backoff = 0.5

        for attempt in range(max_retries):
            try:
                client = await self.get_client()
                if client is None:
                    return None

                result = await getattr(client, operation)(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result
            except (ConnectionError, TimeoutError) as e:
                self.circuit_breaker.record_failure()
                logger.warning(
                    f"Redis operation {operation} failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(base_backoff * (2**attempt))
            except Exception as e:
                # Other non-connection errors shouldn't trigger circuit breaker directly
                logger.error(f"Redis error in {operation}: {e}")
                raise

    async def close(self):
        """Close the Redis connection pool."""
        async with self._lock:
            if self.pool is not None:
                await self.pool.disconnect()
                self.pool = None
                self.client = None
                logger.info("OptimizedRedisClient closed.")


# Global instance management
_global_redis_client: OptimizedRedisClient | None = None
_init_lock = asyncio.Lock()


async def get_redis_client(
    url: str | None = None, max_connections: int = 20
) -> OptimizedRedisClient:
    """Get or initialize the global OptimizedRedisClient."""
    global _global_redis_client
    async with _init_lock:
        if _global_redis_client is None:
            _global_redis_client = OptimizedRedisClient(url=url, max_connections=max_connections)
            await _global_redis_client.initialize()
        return _global_redis_client


async def close_redis_client():
    """Close the global OptimizedRedisClient."""
    global _global_redis_client
    if _global_redis_client is not None:
        await _global_redis_client.close()
        _global_redis_client = None
