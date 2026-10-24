"""
SupremeAI Performance Optimizer
===============================

Performance optimization module implementing various optimization strategies:
- Caching mechanisms
- Database query optimization
- Memory management
- Async processing
- Resource pooling

Bengali:
পারফরমেন্স অপটিমাইজার
বিভিন্ন অপটিমাইজেশন কৌশল বাস্তবায়ন:
- ক্যাশিং ব্যবস্থা
- ডাটাবেস কুয়ারি অপটিমাইজেশন
- মেমরি ব্যবস্থাপনা
- অ্যাসিংক্রোনাস প্রসেসিং
- রিসোর্স পুলিং
"""

import asyncio
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]
import gc
from concurrent.futures import ThreadPoolExecutor
from functools import wraps


class OptimizationLevel(Enum):
    """Levels of optimization to apply."""

    LIGHT = "light"  # Minimal optimizations
    MODERATE = "moderate"  # Balanced optimizations
    AGGRESSIVE = "aggressive"  # Maximum optimizations


@dataclass
class PerfMetrics:
    """Performance metrics collected during optimization."""

    request_count: int = 0
    total_time: float = 0.0
    avg_response_time: float = 0.0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    db_queries: int = 0
    db_avg_time: float = 0.0
    timestamp: float = 0.0


class LRUCache:
    """Simple LRU Cache implementation for performance optimization."""

    def __init__(self, maxsize: int = 128, ttl: int = 300):
        self.cache: dict[str, Any] = {}
        self.maxsize = maxsize
        self.ttl = ttl  # Time to live in seconds
        self.access_order: dict[str, float] = {}  # Track access times

    def get(self, key: str) -> Any | None:
        """Get value from cache if it exists and hasn't expired."""
        if key in self.cache:
            item = self.cache[key]
            timestamp, value = item

            # Check if expired
            if time.time() - timestamp > self.ttl:
                del self.cache[key]
                del self.access_order[key]
                return None

            # Update access time
            self.access_order[key] = time.time()
            return value

        return None

    def put(self, key: str, value: Any):
        """Put value in cache, evicting LRU item if necessary."""
        current_time = time.time()

        # Check if we need to evict
        if len(self.cache) >= self.maxsize:
            # Find LRU item (earliest access time)
            if self.access_order:
                lru_key = min(self.access_order, key=lambda k: self.access_order[k])
                del self.cache[lru_key]
                del self.access_order[lru_key]

        # Add new item
        self.cache[key] = (current_time, value)
        self.access_order[key] = current_time

    def invalidate(self, key: str):
        """Remove a specific key from cache."""
        if key in self.cache:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]

    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()
        self.access_order.clear()

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {"size": len(self.cache), "maxsize": self.maxsize, "ttl": self.ttl}


class AsyncLRUCache:
    """Async version of LRU Cache."""

    def __init__(self, maxsize: int = 128, ttl: int = 300):
        self.cache: dict[str, Any] = {}
        self.maxsize = maxsize
        self.ttl = ttl
        self.access_order: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Asynchronously get value from cache."""
        async with self._lock:
            if key in self.cache:
                timestamp, value = self.cache[key]

                if time.time() - timestamp > self.ttl:
                    del self.cache[key]
                    if key in self.access_order:
                        del self.access_order[key]
                    return None

                self.access_order[key] = time.time()
                return value

            return None

    async def put(self, key: str, value: Any):
        """Asynchronously put value in cache."""
        async with self._lock:
            current_time = time.time()

            if len(self.cache) >= self.maxsize:
                if self.access_order:
                    lru_key = min(self.access_order, key=lambda k: self.access_order[k])
                    del self.cache[lru_key]
                    if lru_key in self.access_order:
                        del self.access_order[lru_key]

            self.cache[key] = (current_time, value)
            self.access_order[key] = current_time

    async def invalidate(self, key: str):
        """Asynchronously remove a specific key."""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                if key in self.access_order:
                    del self.access_order[key]


class QueryOptimizer:
    """Database query optimizer for reducing query execution time."""

    def __init__(self):
        self.query_cache = LRUCache(maxsize=1000, ttl=300)
        self.query_stats = {}
        self.index_suggestions = {}

    def analyze_query(self, query: str) -> dict[str, Any]:
        """Analyze a query for optimization opportunities."""
        suggested_optimizations: list[str] = []
        analysis: dict[str, Any] = {
            "table_scan": "FULL SCAN" in query.upper(),
            "missing_indexes": [],
            "joins": query.upper().count("JOIN"),
            "complexity_score": self._calculate_complexity(query),
            "suggested_optimizations": suggested_optimizations,
        }

        # Simple heuristics for optimization suggestions
        if "WHERE" not in query.upper():
            suggested_optimizations.append("Consider adding WHERE clause for filtering")

        if "ORDER BY" in query.upper() and "LIMIT" not in query.upper():
            suggested_optimizations.append("Consider adding LIMIT for better performance")

        return analysis

    def _calculate_complexity(self, query: str) -> int:
        """Calculate a basic complexity score for the query."""
        score = 0
        query_upper = query.upper()

        # Count expensive operations
        score += query_upper.count("JOIN") * 10
        score += query_upper.count("UNION") * 15
        score += query_upper.count("DISTINCT") * 5
        score += query_upper.count("GROUP BY") * 8
        score += query_upper.count("ORDER BY") * 3

        # Length also contributes to complexity
        score += len(query) // 100

        return min(score, 100)  # Cap at 100

    async def optimize_query(self, query: str, params: dict | None = None) -> str:
        """Optimize a query based on analysis."""
        # Check cache first
        cache_key = f"query:{hash(query)}"
        cached_result = self.query_cache.get(cache_key)
        if cached_result:
            return cached_result

        # Analyze the query
        self.analyze_query(query)

        # Apply optimizations based on analysis
        optimized_query = query

        # Add suggestions to stats
        if query not in self.query_stats:
            self.query_stats[query] = {"executions": 0, "avg_time": 0.0, "last_executed": 0}

        self.query_stats[query]["executions"] += 1

        # Cache the optimized query
        self.query_cache.put(cache_key, optimized_query)

        return optimized_query

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for the query optimizer."""
        return {
            "hits": getattr(self.query_cache, "hits", 0),
            "misses": getattr(self.query_cache, "misses", 0),
            "size": len(self.query_cache.cache),
            "max_size": self.query_cache.maxsize,
        }


class AsyncPoolManager:
    """Manager for async resource pools to optimize resource usage."""

    def __init__(
        self,
        max_connections: int = 10,
        pool_name: str = "default",
        min_connections: int = 2,
        max_idle_time: int = 300,
    ):
        self.max_connections = max_connections
        self.pool_name = pool_name
        self.min_connections = min_connections
        self.max_idle_time = max_idle_time
        self.available_connections: Any = asyncio.Queue()
        self.active_connections: set[Any] = set()
        self._initialized = False
        self._all_connections: list[Any] = []

    def acquire_connection(self):
        """Synchronous wrapper for acquiring a connection."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If called inside an existing running event loop
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(self.acquire())).result()

        return asyncio.run(self.acquire())

    def release_connection(self, conn):
        """Synchronous wrapper for releasing a connection."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(self.release(conn))).result()

        return asyncio.run(self.release(conn))

    def get_pool_stats(self) -> dict[str, Any]:
        """Get pool statistics (synchronous)."""
        stats = self.stats()
        return {
            "available": stats.get("available", 0),
            "active": stats.get("active", 0),
            "current_size": len(self._all_connections),
            "max": self.max_connections,
        }

    async def initialize(self):
        """Initialize the connection pool."""
        if self._initialized:
            return

        for _ in range(self.max_connections):
            # Create a mock connection object (replace with actual connection logic)
            conn = await self._create_connection()
            await self.available_connections.put(conn)
            self._all_connections.append(conn)

        self._initialized = True

    async def _create_connection(self):
        """Create a new connection."""

        # In real implementation, this would create actual database connections
        # For now, returning a mock object
        class MockConnection:
            def __init__(self):
                self.id = id(self)
                self.busy = False

            async def execute(self, query: str):
                # Simulate query execution
                await asyncio.sleep(0.01)  # Simulate network delay
                return f"Result for {query}"

        return MockConnection()

    async def acquire(self):
        """Acquire a connection from the pool."""
        if not self._initialized:
            await self.initialize()

        conn = await self.available_connections.get()
        self.active_connections.add(conn)
        conn.busy = True
        return conn

    async def release(self, conn):
        """Release a connection back to the pool."""
        if conn in self.active_connections:
            self.active_connections.remove(conn)
            conn.busy = False
            await self.available_connections.put(conn)

    def stats(self) -> dict[str, int]:
        """Get pool statistics."""
        return {
            "available": self.available_connections.qsize(),
            "active": len(self.active_connections),
            "max": self.max_connections,
        }


def performance_monitor(func: Callable) -> Callable:
    """Decorator to monitor performance of functions."""

    @wraps(func)
    @with_error_bus("async_wrapper")
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()

        # Start tracing memory
        tracemalloc.start()
        start_snapshot = tracemalloc.take_snapshot()

        try:
            result = await func(*args, **kwargs)
        except Exception:
            raise
        finally:
            end_time = time.time()
            end_snapshot = tracemalloc.take_snapshot()

            # Calculate memory usage
            top_stats = end_snapshot.compare_to(start_snapshot, "lineno")
            memory_diff = sum(stat.size_diff for stat in top_stats[:10])

            # Log performance metrics
            execution_time = end_time - start_time
            logger.info(
                f"Function {func.__name__} executed in {execution_time:.4f}s, "
                f"memory change: {memory_diff / 1024:.2f}KB"
            )

            tracemalloc.stop()

        return result

    @wraps(func)
    @with_error_bus("sync_wrapper")
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()

        # Start tracing memory
        tracemalloc.start()
        start_snapshot = tracemalloc.take_snapshot()

        try:
            result = func(*args, **kwargs)
        except Exception:
            raise
        finally:
            end_time = time.time()
            end_snapshot = tracemalloc.take_snapshot()

            # Calculate memory usage
            top_stats = end_snapshot.compare_to(start_snapshot, "lineno")
            memory_diff = sum(stat.size_diff for stat in top_stats[:10])

            # Log performance metrics
            execution_time = end_time - start_time
            logger.info(
                f"Function {func.__name__} executed in {execution_time:.4f}s, "
                f"memory change: {memory_diff / 1024:.2f}KB"
            )

            tracemalloc.stop()

        return result

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


class PerformanceOptimizer:
    """Main performance optimizer class."""

    def __init__(self, level: OptimizationLevel = OptimizationLevel.MODERATE):
        self.level = level
        self.cache = AsyncLRUCache(maxsize=1000 if level == OptimizationLevel.AGGRESSIVE else 500)
        self.query_optimizer = QueryOptimizer()
        self.pool_manager = AsyncPoolManager(
            max_connections=20 if level == OptimizationLevel.AGGRESSIVE else 10
        )
        self.metrics = PerfMetrics()
        self.executor = ThreadPoolExecutor(
            max_workers=4 if level == OptimizationLevel.AGGRESSIVE else 2
        )

        # System monitoring
        self.monitoring_task = None
        self.is_monitoring = False

    async def start_monitoring(self):
        """Start system performance monitoring."""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitor_system())

    async def stop_monitoring(self):
        """Stop system performance monitoring."""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")

    async def _monitor_system(self):
        """Monitor system resources continuously."""
        while self.is_monitoring:
            try:
                # Collect system metrics
                self.metrics.cpu_usage = psutil.cpu_percent(interval=1)
                self.metrics.memory_usage = psutil.virtual_memory().percent

                # Update timestamp
                self.metrics.timestamp = time.time()

                # Log metrics periodically
                if self.metrics.request_count % 100 == 0:
                    logger.info(
                        f"System metrics - CPU: {self.metrics.cpu_usage}%, "
                        f"Memory: {self.metrics.memory_usage}%"
                    )

                await asyncio.sleep(5)  # Monitor every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(5)

    def cache_result(self, ttl: int = 300):
        """Decorator to cache function results."""

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Create cache key
                key_parts = [func.__name__, *list(args), *sorted(kwargs.items())]
                cache_key = str(hash(str(key_parts)))

                # Try to get from cache
                cached_result = await self.cache.get(cache_key)
                if cached_result is not None:
                    self.metrics.cache_hits += 1
                    return cached_result

                self.metrics.cache_misses += 1

                # Execute function and cache result
                result = await func(*args, **kwargs)
                await self.cache.put(cache_key, result)

                return result

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Create cache key
                key_parts = [func.__name__, *list(args), *sorted(kwargs.items())]
                cache_key = str(hash(str(key_parts)))

                # Try to get from cache
                cached_result = self.cache.cache.get(cache_key)
                if cached_result is not None:
                    _, value = cached_result
                    self.metrics.cache_hits += 1
                    return value

                self.metrics.cache_misses += 1

                # Execute function and cache result
                result = func(*args, **kwargs)

                # Use sync cache for sync functions
                self.cache.cache[cache_key] = (time.time(), result)
                if cache_key in self.cache.access_order:
                    self.cache.access_order[cache_key] = time.time()
                else:
                    self.cache.access_order[cache_key] = time.time()

                # Manage cache size
                if len(self.cache.cache) > self.cache.maxsize:
                    # Remove oldest item
                    oldest_key = min(self.cache.access_order, key=self.cache.access_order.get)
                    del self.cache.cache[oldest_key]
                    del self.cache.access_order[oldest_key]

                return result

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    async def optimize_database_access(self, query: str, params: dict | None = None):
        """Optimize database access patterns."""
        self.metrics.db_queries += 1

        start_time = time.time()
        optimized_query = await self.query_optimizer.optimize_query(query, params)
        execution_time = time.time() - start_time

        self.metrics.db_avg_time = (
            self.metrics.db_avg_time * (self.metrics.db_queries - 1) + execution_time
        ) / self.metrics.db_queries

        return optimized_query

    def get_performance_report(self) -> dict[str, Any]:
        """Generate a performance optimization report."""
        return {
            "optimization_level": self.level.value,
            "current_metrics": {
                "request_count": self.metrics.request_count,
                "avg_response_time": self.metrics.avg_response_time,
                "cache_hit_rate": self.metrics.cache_hits
                / max(1, self.metrics.cache_hits + self.metrics.cache_misses),
                "db_avg_time": self.metrics.db_avg_time,
                "cpu_usage": self.metrics.cpu_usage,
                "memory_usage": self.metrics.memory_usage,
            },
            "cache_stats": self.cache.stats() if hasattr(self.cache, "stats") else {},
            "pool_stats": self.pool_manager.stats(),
            "query_stats": self.query_optimizer.query_stats,
        }

    def cleanup_memory(self):
        """Perform memory cleanup operations."""
        # Force garbage collection
        collected = gc.collect()
        logger.info(f"Garbage collected {collected} objects")

        # Clear expired cache entries
        current_time = time.time()
        expired_keys = []

        for key, (timestamp, _) in self.cache.cache.items():
            if current_time - timestamp > self.cache.ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self.cache.cache[key]
            if key in self.cache.access_order:
                del self.cache.access_order[key]

    async def batch_process(
        self, items: list[Any], processor: Callable, batch_size: int = 10
    ) -> list[Any]:
        """Process items in batches for better performance."""
        results: list[dict[str, Any]] = []

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]

            # Process batch concurrently
            batch_results = await asyncio.gather(
                *[processor(item) for item in batch], return_exceptions=True
            )

            for idx, result in enumerate(batch_results):
                if isinstance(result, BaseException):
                    logger.warning(f"Batch processor failed for item {idx}: {result}")
                    results.append({"error": str(result)})
                else:
                    results.append(result)

        return results


# Global performance optimizer instance
_performance_optimizer: PerformanceOptimizer | None = None


def get_performance_optimizer(
    level: OptimizationLevel = OptimizationLevel.MODERATE,
) -> PerformanceOptimizer:
    """Get or create the global performance optimizer instance."""
    global _performance_optimizer
    if _performance_optimizer is None:
        _performance_optimizer = PerformanceOptimizer(level)

    return _performance_optimizer


async def demo_performance_optimization():
    """Demonstrate performance optimization features."""
    logger.debug("Initializing Performance Optimizer...")

    optimizer = get_performance_optimizer(OptimizationLevel.MODERATE)
    await optimizer.start_monitoring()

    # Demonstrate caching
    @optimizer.cache_result(ttl=60)
    async def expensive_calculation(n: int) -> int:
        """Simulate an expensive calculation."""
        await asyncio.sleep(0.1)  # Simulate work
        return n * n

    logger.debug("Testing cached function...")
    start = time.time()
    result1 = await expensive_calculation(5)
    first_call_time = time.time() - start

    start = time.time()
    result2 = await expensive_calculation(5)  # Should be cached
    second_call_time = time.time() - start

    logger.debug(f"First call: {first_call_time:.4f}s, Result: {result1}")
    logger.debug(f"Second call (cached): {second_call_time:.4f}s, Result: {result2}")
    logger.debug(f"Speed improvement: {first_call_time / second_call_time:.2f}x")

    # Demonstrate query optimization
    logger.debug("\nTesting query optimization...")
    optimized = await optimizer.optimize_database_access("SELECT * FROM users WHERE id = 1")
    logger.debug(f"Optimized query: {optimized}")

    # Get performance report
    report = optimizer.get_performance_report()
    logger.debug(f"\nPerformance Report: {report['current_metrics']}")

    # Stop monitoring
    await optimizer.stop_monitoring()
    logger.debug("\nPerformance optimization demo completed!")


if __name__ == "__main__":
    asyncio.run(demo_performance_optimization())
