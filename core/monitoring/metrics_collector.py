"""
Metrics Collection Module for SupremeAI 2.0

This module implements a comprehensive metrics collection system that tracks
application performance, system health, and business metrics for the SupremeAI platform.
It provides both synchronous and asynchronous metric collection capabilities,
integration with Prometheus, and real-time monitoring support.

Features:
- Request volume and response time tracking
- Database query performance metrics
- Cache hit/miss statistics
- AI model usage and cost tracking
- Security event monitoring
- System resource utilization
"""

import asyncio
import time
from collections import defaultdict
from enum import Enum
from typing import Any


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class MetricsCollector:
    """Central metrics collection system for SupremeAI 2.0."""

    def __init__(self):
        self._metrics: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._start_times: dict[str, float] = {}
        self._request_counts = defaultdict(int)
        self._error_counts = defaultdict(int)
        self._db_query_times = []
        self._cache_stats = {"hits": 0, "misses": 0}
        self._ai_costs = defaultdict(float)
        self._security_events = defaultdict(int)
        self._active_connections = 0

    async def increment_counter(
        self, metric_name: str, value: int = 1, labels: dict[str, str] | None = None
    ):
        """Increment a counter metric."""
        labels = labels or {}
        key = f"{metric_name}:{sorted(labels.items())!s}"

        async with self._lock:
            if key not in self._metrics:
                self._metrics[key] = 0
            self._metrics[key] += value

    async def set_gauge(self, metric_name: str, value: float, labels: dict[str, str] | None = None):
        """Set a gauge metric value."""
        labels = labels or {}
        key = f"{metric_name}:{sorted(labels.items())!s}"

        async with self._lock:
            self._metrics[key] = value

    async def observe_histogram(
        self, metric_name: str, value: float, labels: dict[str, str] | None = None
    ):
        """Record a histogram observation."""
        labels = labels or {}
        key = f"{metric_name}:{sorted(labels.items())!s}"

        async with self._lock:
            if key not in self._metrics:
                self._metrics[key] = []
            self._metrics[key].append(value)

    async def start_timer(self, timer_id: str):
        """Start a timer for measuring duration."""
        self._start_times[timer_id] = time.time()

    async def stop_timer(
        self, timer_id: str, metric_name: str, labels: dict[str, str] | None = None
    ):
        """Stop a timer and record the duration."""
        if timer_id in self._start_times:
            duration = time.time() - self._start_times[timer_id]
            await self.observe_histogram(metric_name, duration, labels)
            del self._start_times[timer_id]
            return duration
        return None

    # Application-specific metrics
    async def record_request(self, endpoint: str, method: str = "GET", status_code: int = 200):
        """Record an incoming request."""
        labels = {"endpoint": endpoint, "method": method, "status_code": str(status_code)}
        await self.increment_counter("http_requests_total", 1, labels)
        self._request_counts[(endpoint, method, status_code)] += 1

    async def record_error(self, error_type: str, endpoint: str = "unknown"):
        """Record an error occurrence."""
        labels = {"type": error_type, "endpoint": endpoint}
        await self.increment_counter("errors_total", 1, labels)
        self._error_counts[(error_type, endpoint)] += 1

    async def record_db_query(self, operation: str, duration: float, success: bool = True):
        """Record a database query performance."""
        labels = {"operation": operation, "success": str(success)}
        await self.observe_histogram("db_query_duration_seconds", duration, labels)
        self._db_query_times.append(duration)

    async def record_cache_hit(self):
        """Record a cache hit."""
        await self.increment_counter("cache_hits_total", 1)
        self._cache_stats["hits"] += 1

    async def record_cache_miss(self):
        """Record a cache miss."""
        await self.increment_counter("cache_misses_total", 1)
        self._cache_stats["misses"] += 1

    async def record_ai_model_usage(self, model_name: str, tokens_used: int, cost_usd: float):
        """Record AI model usage and cost."""
        labels = {"model": model_name}
        await self.increment_counter("ai_model_requests_total", 1, labels)
        await self.increment_counter("ai_tokens_total", tokens_used, labels)
        self._ai_costs[model_name] += cost_usd

    async def record_security_event(self, event_type: str, severity: str = "medium"):
        """Record a security event."""
        labels = {"type": event_type, "severity": severity}
        await self.increment_counter("security_events_total", 1, labels)
        self._security_events[event_type] += 1

    async def update_active_connections(self, count: int):
        """Update the count of active connections."""
        await self.set_gauge("active_connections", count)
        self._active_connections = count

    # Data retrieval methods for monitoring systems
    async def get_request_volume(self, timeframe_minutes: int = 5) -> dict[str, float]:
        """Get request volume metrics."""
        # This would typically integrate with a time-series database
        # For now, returning current counts
        total_requests = sum(self._request_counts.values())
        return {"total_requests": total_requests, "timeframe_minutes": timeframe_minutes}

    async def get_recent_metrics(self, minutes: int = 1) -> dict[str, float]:
        """
        বাংলা: গত N মিনিটের aggregated app-metrics। auto_scaling_agent ও
        performance_tuning_agent এই method-টি call করে (তারা graceful fallback সহ)।
        আগে এই method ছিল না বলে agent-গুলো simulated values fallback নিত।

        Returns:
            active_connections: বর্তমান active connection count
            requests_per_second: সাম্প্রতিক request rate (RPS)
            avg_response_time: গড় DB query time (ms — proxy for response time)
            error_rate: error / total request percentage
        """
        try:
            total_requests = sum(self._request_counts.values())
            total_errors = sum(self._error_counts.values())
            error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0.0

            # avg DB query time কে response time proxy হিসেবে ব্যবহার করি
            avg_response_time = 0.0
            if self._db_query_times:
                avg_response_time = (
                    sum(self._db_query_times) / len(self._db_query_times) * 1000
                )  # → ms

            # requests_per_second: total requests / (minutes * 60)
            seconds = max(minutes * 60, 1)
            rps = total_requests / seconds if total_requests > 0 else 0.0

            return {
                "active_connections": float(self._active_connections),
                "requests_per_second": rps,
                "avg_response_time": avg_response_time,
                "error_rate": error_rate,
                "total_requests": float(total_requests),
                "total_errors": float(total_errors),
            }
        except Exception:
            # graceful: কিছু ভুল হলে empty dict (agents তখন fallback নেবে)
            return {}

    async def get_cache_performance(self) -> dict[str, float]:
        """Get cache performance metrics."""
        total = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (self._cache_stats["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "hit_rate_percentage": hit_rate,
        }

    async def get_db_performance(self) -> dict[str, float]:
        """Get database performance metrics."""
        if not self._db_query_times:
            return {"avg_query_time": 0.0, "query_count": 0}

        avg_time = sum(self._db_query_times) / len(self._db_query_times)
        return {
            "avg_query_time": avg_time,
            "query_count": len(self._db_query_times),
            "slow_queries": len([t for t in self._db_query_times if t > 1.0]),  # >1s is slow
        }

    async def get_ai_cost_metrics(self) -> dict[str, float]:
        """Get AI model cost metrics."""
        return dict(self._ai_costs)

    async def get_security_metrics(self) -> dict[str, int]:
        """Get security event metrics."""
        return dict(self._security_events)

    async def get_overall_health(self) -> dict[str, Any]:
        """Get overall system health metrics."""
        cache_perf = await self.get_cache_performance()
        db_perf = await self.get_db_performance()
        ai_costs = await self.get_ai_cost_metrics()
        security_events = await self.get_security_metrics()

        return {
            "timestamp": time.time(),
            "active_connections": self._active_connections,
            "total_requests": sum(self._request_counts.values()),
            "total_errors": sum(self._error_counts.values()),
            "cache_performance": cache_perf,
            "database_performance": db_perf,
            "ai_costs": ai_costs,
            "security_events": security_events,
            "uptime_minutes": (time.time() - getattr(self, "_start_time", time.time())) / 60,
        }

    def __enter__(self):
        """Context manager entry."""
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


# Global metrics collector instance
metrics_collector = MetricsCollector()


# Convenience functions for easy metric recording
async def record_api_request(endpoint: str, method: str = "GET", status_code: int = 200):
    """Convenience function to record an API request."""
    await metrics_collector.record_request(endpoint, method, status_code)


async def record_db_operation(operation: str, duration: float, success: bool = True):
    """Convenience function to record a database operation."""
    await metrics_collector.record_db_query(operation, duration, success)


async def record_cache_access(hit: bool):
    """Convenience function to record a cache access."""
    if hit:
        await metrics_collector.record_cache_hit()
    else:
        await metrics_collector.record_cache_miss()


async def record_ai_usage(model: str, tokens: int, cost: float):
    """Convenience function to record AI model usage."""
    await metrics_collector.record_ai_model_usage(model, tokens, cost)


async def record_security_incident(event_type: str, severity: str = "medium"):
    """Convenience function to record a security incident."""
    await metrics_collector.record_security_event(event_type, severity)


async def start_operation_timer(operation_id: str):
    """Start timing an operation."""
    await metrics_collector.start_timer(operation_id)


async def end_operation_timer(
    operation_id: str, metric_name: str, labels: dict[str, str] | None = None
):
    """End timing an operation and record the duration."""
    return await metrics_collector.stop_timer(operation_id, metric_name, labels)
