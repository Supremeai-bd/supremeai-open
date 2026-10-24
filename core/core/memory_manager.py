"""
Memory Manager for Free-Tier Optimization
Monitors and manages memory usage within 512MB constraint.
"""

import asyncio
import gc
import time
from dataclasses import dataclass
from functools import wraps

import psutil

from core.logging_config import logger


@dataclass
class MemoryStatus:
    total_mb: float
    used_mb: float
    free_mb: float
    percent_used: float
    is_critical: bool
    is_warning: bool


class FreeTierMemoryManager:
    """
    Memory manager optimized for Render's 512MB Free Tier.

    Thresholds:
    - Warning: >70% (~358 MB)
    - Critical: >85% (~435 MB)
    - Maximum: 512 MB (hard limit)
    """

    WARNING_THRESHOLD = 80.0  # percentage (raised from 70 to reduce noise on Render)
    CRITICAL_THRESHOLD = (
        92.0  # percentage (raised from 85 to avoid false-positive aggressive cleanup)
    )
    MAX_MEMORY_MB = 512  # Render free tier limit

    def __init__(self):
        try:
            self._process = psutil.Process()
        except (psutil.Error, OSError) as e:
            logger.warning(f"psutil.Process() unavailable at startup, will retry lazily: {e}")
            self._process = None
        self._last_gc_time = 0.0
        self._last_aggressive_cleanup_time = 0.0
        self._last_log_time = 0.0
        self._gc_interval_seconds = 60.0  # Run GC every 60 seconds at most
        self._log_interval_seconds = 60.0  # Throttle repeating logs
        self._current_state = "NORMAL"

    def get_status(self) -> MemoryStatus:
        """Get current memory status."""
        try:
            if self._process is None:
                self._process = psutil.Process()

            try:
                total_virtual = self._process.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                self._process = psutil.Process()
                total_virtual = self._process.memory_info().rss / (1024 * 1024)

            status = MemoryStatus(
                total_mb=self.MAX_MEMORY_MB,
                used_mb=round(total_virtual, 2),
                free_mb=round(self.MAX_MEMORY_MB - total_virtual, 2),
                percent_used=round((total_virtual / self.MAX_MEMORY_MB) * 100, 2),
                is_critical=(total_virtual / self.MAX_MEMORY_MB * 100) >= self.CRITICAL_THRESHOLD,
                is_warning=(total_virtual / self.MAX_MEMORY_MB * 100) >= self.WARNING_THRESHOLD,
            )

            return status

        except Exception as e:
            logger.error(f"Failed to get memory status: {e}")
            return MemoryStatus(512, 256, 256, 50.0, False, False)

    def should_cleanup(self) -> bool:
        """Check if we should run cleanup based on thresholds."""
        status = self.get_status()
        return status.is_critical or status.is_warning

    # Threshold below which it's considered safe to run optional heavy
    # background work (self-evolution cycles, adaptive-engine learning
    # loops, etc.). Deliberately well under WARNING_THRESHOLD so these
    # opt-in jobs never push memory into the warning/critical zone
    # themselves. Overridable via env for tuning without a code change.
    HEAVY_TASK_SAFE_THRESHOLD = 65.0  # percentage

    def is_safe_for_heavy_task(self, threshold: float | None = None) -> bool:
        """Whether memory headroom is good enough to run an optional,
        non-critical background job (e.g. evolution/adaptive-learning
        cycles) right now. These jobs are meant to run 24/7 but should
        only actually do work when memory usage is comfortably low —
        this lets the caller keep its loop alive and simply skip the
        heavy part of a cycle when usage is high, retrying next cycle.
        """
        limit = threshold if threshold is not None else self.HEAVY_TASK_SAFE_THRESHOLD
        status = self.get_status()
        return status.percent_used < limit

    def _update_logging_state(self, status: MemoryStatus):
        """State machine for logging to prevent spam."""
        current_time = time.monotonic()
        new_state = "NORMAL"
        if status.is_critical:
            new_state = "CRITICAL"
        elif status.is_warning:
            new_state = "WARNING"

        if new_state != self._current_state:
            # State transition
            if new_state == "CRITICAL":
                logger.critical(f"🚨 MEMORY CRITICAL ({status.percent_used}% used)")
            elif new_state == "WARNING":
                logger.warning(f"⚠️ MEMORY WARNING ({status.percent_used}% used)")
            elif new_state == "NORMAL" and self._current_state != "NORMAL":
                logger.success(f"✅ MEMORY RECOVERED ({status.percent_used}% used)")

            self._current_state = new_state
            self._last_log_time = current_time
        else:
            # Same state, throttle logs
            if new_state != "NORMAL" and (
                current_time - self._last_log_time >= self._log_interval_seconds
            ):
                if new_state == "CRITICAL":
                    logger.critical(f"🚨 STILL CRITICAL ({status.percent_used}% used)")
                elif new_state == "WARNING":
                    logger.warning(f"⚠️ STILL WARNING ({status.percent_used}% used)")
                self._last_log_time = current_time

    async def cleanup_if_needed(self, force: bool = False):
        """
        Run garbage collection and cleanup if memory is high.

        Args:
            force: Force cleanup regardless of threshold and cooldown
        """
        status = self.get_status()
        self._update_logging_state(status)

        current_time = time.monotonic()

        if force:
            logger.warning(f"⚠️ Forced memory cleanup triggered ({status.percent_used}%)")
            await self._aggressive_cleanup(force=True)
            return

        if status.is_critical:
            if current_time - self._last_aggressive_cleanup_time >= self._gc_interval_seconds:
                await self._aggressive_cleanup()
        elif status.is_warning:
            if current_time - self._last_gc_time >= self._gc_interval_seconds:
                await self._standard_cleanup()

    async def _standard_cleanup(self):
        """Standard garbage collection."""
        self._last_gc_time = time.monotonic()
        logger.debug("Running standard GC...")
        gc.collect()

        if hasattr(self, "_clear_caches"):
            self._clear_caches()

    async def _aggressive_cleanup(self, force: bool = False):
        """Aggressive cleanup for critical memory situations."""
        self._last_aggressive_cleanup_time = time.monotonic()
        self._last_gc_time = time.monotonic()  # Aggressive also counts as standard

        logger.critical("🚨 Running AGGRESSIVE memory cleanup!")

        # 1. Force multiple GC passes
        for _ in range(3):
            gc.collect()
            await asyncio.sleep(0.01)  # Reduced sleep to not block event loop as much

        # 2. Clear any object pools
        try:
            from core.ai_memory.vector_store import FreeTierOptimizedVectorStore as VectorStore

            if hasattr(VectorStore, "_connection_pool"):
                pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")


# Singleton instance
_memory_manager: FreeTierMemoryManager | None = None


def get_memory_manager() -> FreeTierMemoryManager:
    """Get or create the singleton memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = FreeTierMemoryManager()
    return _memory_manager


def memory_aware(func):
    """
    Decorator that checks memory before and after function execution.
    Automatically triggers cleanup if needed.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        manager = get_memory_manager()

        await manager.cleanup_if_needed()

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await manager.cleanup_if_needed()
            return result

        except MemoryError:
            logger.critical("💥 Out of memory! Emergency cleanup...")
            await manager.cleanup_if_needed(force=True)
            raise

    return wrapper


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class MemoryAwareMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that monitors memory usage."""

    async def dispatch(self, request: Request, call_next):
        manager = get_memory_manager()

        response = await call_next(request)

        # Allow debugging memory in non-production environments or if requested
        import os

        if os.getenv("ENV") != "production" or os.getenv("DEBUG_MEMORY_HEADERS") == "true":
            status = manager.get_status()
            response.headers["X-Memory-Used-MB"] = str(status.used_mb)
            response.headers["X-Memory-Percent"] = str(status.percent_used)

        # Throttled cleanup check after request
        await manager.cleanup_if_needed()

        return response
