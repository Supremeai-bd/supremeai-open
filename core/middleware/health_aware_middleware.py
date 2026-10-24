"""Health-aware middleware for SupremeAI - enhances system resilience by monitoring health status and adjusting behavior accordingly.

বাংলা মন্তব্য: এই মিডলওয়্যারটি সিস্টেমের স্বাস্থ্য অবস্থা পর্যবেক্ষণ করে এবং প্রয়োজনে রিকোয়েস্ট হ্যান্ডলিং সামঞ্জস্য করে।
"""

import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from core.cache.redis_manager import redis_manager
from core.logging_config import logger
from services.config_service import ConfigService

GLOBAL_HEALTH_CONFIG = {"health_threshold": 0.8}


async def sync_from_db(db: Any) -> None:
    """Sync global health middleware thresholds from the database configuration."""
    try:
        configs = await ConfigService.get_config(
            db, "middleware_health_threshold", GLOBAL_HEALTH_CONFIG
        )
        if configs:
            GLOBAL_HEALTH_CONFIG.update(configs)
            logger.info(
                f"✅ Synced middleware_health_threshold from DB. threshold={GLOBAL_HEALTH_CONFIG['health_threshold']}"
            )
    except Exception as e:
        logger.error(f"❌ Failed to sync middleware_health_threshold from DB: {e}")


class HealthAwareMiddleware(BaseHTTPMiddleware):
    """Health-aware middleware that adjusts behavior based on system health."""

    def __init__(self, app):
        super().__init__(app)
        self.health_cache_ttl = 5  # 5 seconds cache
        self.degraded_endpoints: list[str] = []

    async def dispatch(self, request: Request, call_next):
        # Skip health checks for health endpoints themselves
        if request.url.path in [
            "/health",
            "/api/v1/health",
            "/health/",
            "/api/v1/health/",
            "/live",
            "/ready",
            "/health/advanced",
        ]:
            return await call_next(request)

        # Check system health
        health_status = await self._get_cached_health()

        # If system is degraded, handle accordingly
        if health_status.get("status") == "degraded":
            # Add to request state for downstream processing
            request.state.system_degraded = True

            # For non-critical endpoints, allow with warning
            if not self._is_critical_endpoint(request.url.path):
                response = await call_next(request)

                # Add health warning header
                if hasattr(response, "headers"):
                    response.headers["X-SupremeAI-Health-Warning"] = "System is currently degraded"
                return response
            else:
                # For critical endpoints in degraded state, potentially limit functionality
                logger.warning(
                    f"Critical endpoint {request.url.path} accessed during degraded system state"
                )

        # Normal processing
        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            # Log the error and potentially adjust health status
            logger.error(f"Error in request processing: {e!s}")
            await self._update_error_health_metric(str(e))
            raise

        # Calculate response time and update health metrics
        process_time = time.time() - start_time
        await self._update_response_time_metric(process_time)

        # Add health info to response headers
        if hasattr(response, "headers"):
            response.headers["X-Response-Time"] = f"{process_time:.4f}"
            response.headers["X-SupremeAI-Health-Status"] = health_status.get("status", "unknown")

        return response

    async def _get_cached_health(self) -> dict[str, Any]:
        """Get cached health status or compute fresh if expired."""
        if not redis_manager or not redis_manager.client:
            # Fallback if Redis is not available
            return {"status": "degraded", "reason": "redis_unavailable"}

        try:
            cached_health = await redis_manager.get_cache("system_health_status")
            if cached_health:
                import json

                cached_data = json.loads(cached_health)
                # Check if cache is still valid
                if time.time() - cached_data.get("timestamp", 0) < self.health_cache_ttl:
                    return cached_data.get("data", {"status": "unknown"})

            # Compute fresh health status
            fresh_health = await self._compute_health_status()
            # Cache the result
            await redis_manager.set_cache(
                "system_health_status",
                f'{{"data": {json.dumps(fresh_health)}, "timestamp": {time.time()}}}',
                ex_seconds=self.health_cache_ttl,
            )
            return fresh_health
        except Exception as e:
            logger.error(f"Error getting cached health: {e!s}")
            return {"status": "degraded", "reason": "health_check_failed"}

    async def _compute_health_status(self) -> dict[str, Any]:
        """Compute the current system health status."""
        import psutil

        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk_usage = psutil.disk_usage("/")

            # Check Redis connectivity
            redis_connected = True
            if redis_manager and redis_manager.client:
                try:
                    await redis_manager.client.ping()
                except Exception as e:
                    logger.warning(f"Redis health check failed: {e}")
                    redis_connected = False
            else:
                redis_connected = False

            # Check database connectivity
            db_connected = await self._check_db_connectivity()

            # Calculate overall health score
            health_score = self._calculate_health_score(
                cpu_percent,
                memory.percent,
                disk_usage.percent,
                redis_connected,
                db_connected,
            )

            status = (
                "healthy"
                if health_score >= GLOBAL_HEALTH_CONFIG["health_threshold"]
                else "degraded"
            )

            return {
                "status": status,
                "health_score": health_score,
                "metrics": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": disk_usage.percent,
                    "redis_connected": redis_connected,
                    "db_connected": db_connected,
                },
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"Error computing health status: {e!s}")
            return {"status": "degraded", "reason": f"computation_error: {e!s}"}

    async def _check_db_connectivity(self) -> bool:
        """Check database connectivity."""
        try:
            # বাংলা: এখানে ৩টি বাগ ছিল — (১) get_db_pool() ভুল মডিউল (database.session)
            # থেকে import হচ্ছিল, আসলে সেটি database.pgbouncer_pool-এ সংজ্ঞায়িত;
            # (২) get_db_pool() একটি async ফাংশন, কিন্তু await ছাড়া কল করায় coroutine
            # অবজেক্ট পাওয়া যেত (যা সবসময় truthy, তাই `if db_pool` চেক অকার্যকর ছিল);
            # (৩) .acquire() একটি plain coroutine রিটার্ন করে, async context manager নয় —
            # তাই `async with db_pool.acquire()` AttributeError দিত। ফলে এই DB
            # connectivity check সবসময় ব্যর্থ হয়ে health score কমিয়ে দিত।
            from database.pgbouncer_pool import get_db_pool

            db_pool = await get_db_pool()
            if db_pool:
                async with db_pool.connection() as conn:
                    await conn.fetchval("SELECT 1")
                    return True
        except Exception as e:
            logger.warning(f"DB connectivity check failed: {e!s}")
        return False

    def _calculate_health_score(
        self,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        redis_connected: bool,
        db_connected: bool,
    ) -> float:
        """Calculate overall health score based on various factors."""
        # Start with perfect score
        score = 1.0

        # Deduct points based on resource usage
        if cpu_percent > 85:
            score -= min(0.5, (cpu_percent - 85) / 100)  # Heavy penalty for high CPU
        elif cpu_percent > 75:
            score -= min(0.2, (cpu_percent - 75) / 100)  # Moderate penalty for moderate CPU

        if memory_percent > 90:
            score -= min(0.5, (memory_percent - 90) / 100)  # Heavy penalty for high memory
        elif memory_percent > 80:
            score -= min(0.2, (memory_percent - 80) / 100)  # Moderate penalty for moderate memory

        if disk_percent > 90:
            score -= min(0.5, (disk_percent - 90) / 100)  # Heavy penalty for high disk usage
        elif disk_percent > 80:
            score -= min(0.2, (disk_percent - 80) / 100)  # Moderate penalty for moderate disk usage

        # Heavy penalties for service unavailability
        if not redis_connected:
            score -= 0.3
        if not db_connected:
            score -= 0.3

        # Ensure score stays within bounds
        return max(0.0, min(1.0, score))

    async def _update_response_time_metric(self, response_time: float):
        """Update response time metrics for health assessment."""
        if redis_manager and redis_manager.client:
            try:
                # Track average response time over time
                await redis_manager.client.lpush("metrics:response_times", response_time)
                await redis_manager.client.ltrim(
                    "metrics:response_times", 0, 99
                )  # Keep last 100 samples
            except Exception as e:
                logger.warning(f"Could not update response time metric: {e!s}")

    async def _update_error_health_metric(self, error_message: str):
        """Update error metrics for health assessment."""
        if redis_manager and redis_manager.client:
            try:
                import time

                error_entry = {
                    "timestamp": time.time(),
                    "error": error_message[:200],
                }  # Truncate long messages
                await redis_manager.client.lpush("metrics:error_log", str(error_entry))
                await redis_manager.client.ltrim("metrics:error_log", 0, 49)  # Keep last 50 errors
            except Exception as e:
                logger.warning(f"Could not update error metric: {e!s}")

    def _is_critical_endpoint(self, path: str) -> bool:
        """Determine if the endpoint is critical for system operation."""
        critical_paths = [
            "/api/v1/chat",
            "/api/v1/agent",
            "/api/v1/execute",
            "/api/v1/task",
            "/api/v1/model",
            "/health/advanced",
        ]

        return any(path.startswith(cp) for cp in critical_paths)
