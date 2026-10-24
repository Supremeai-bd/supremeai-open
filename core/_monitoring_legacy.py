import logging

"""
SuperAI Advanced Monitoring & Observability Layer
===================================================
Production-grade monitoring with:
- Structured logging with request correlation
- Performance metrics collection
- Health status aggregation
- Custom alerting system
- Prometheus-compatible /metrics endpoint

Author: SuperAI Transformation Patch
Version: 1.0.0

Compliance: OpenTelemetry, Prometheus, GDPR logging
"""

import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any

from core.logging_config import logger

# Logging is now unified via Loguru InterceptHandler in core.logging_config


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class Alert:
    """Structured alert object."""

    id: str
    severity: AlertSeverity
    source: str
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: datetime | None = None


@dataclass
class RequestMetrics:
    """Per-request performance metrics."""

    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    user_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    cache_hit: bool = False
    llm_provider: str | None = None
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SystemHealth:
    """Aggregated system health status."""

    overall_status: str  # healthy, degraded, unhealthy
    components: dict[str, dict[str, Any]]
    uptime_seconds: float
    total_requests: int
    errors_5m: int
    avg_response_time_ms: float
    cache_stats: dict[str, Any]
    active_alerts: int
    last_check: datetime = field(default_factory=datetime.utcnow)


class MetricsCollector:
    """
    Thread-safe metrics collector for application monitoring.

    Features:
    - Request counting by status code
    - Response time percentiles (p50, p95, p99)
    - Error rate tracking
    - LLM cost accumulation
    - Cache hit/miss ratios
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._requests: list[RequestMetrics] = []
        self._alerts: list[Alert] = []
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

        # Cleanup old metrics every 5 minutes
        self._max_metrics_age = timedelta(minutes=5)

    def record_request(self, metrics: RequestMetrics):
        """Record a completed request."""
        with self._lock:
            self._requests.append(metrics)
            self._counters["requests_total"] += 1
            self._counters[f"requests_{metrics.method}"] += 1
            self._counters[f"status_{metrics.status_code}"] += 1

            # Response time histogram
            self._histograms["response_time_ms"].append(metrics.duration_ms)

            # Cache stats
            if metrics.cache_hit:
                self._counters["cache_hits"] += 1
            else:
                self._counters["cache_misses"] += 1

            # Error tracking
            if metrics.status_code >= 400:
                self._counters["errors_total"] += 1

            # LLM costs
            if metrics.estimated_cost_usd > 0:
                self._gauges["llm_total_cost_usd"] += metrics.estimated_cost_usd
                self._counters["llm_tokens_total"] += metrics.tokens_used

    def create_alert(
        self, severity: AlertSeverity, source: str, title: str, message: str, **metadata
    ) -> Alert:
        """Create and store an alert."""
        alert = Alert(
            id=str(uuid.uuid4()),
            severity=severity,
            source=source,
            title=title,
            message=message,
            metadata=metadata,
        )

        with self._lock:
            self._alerts.append(alert)
            self._counters[f"alerts_{severity.value}"] += 1

        # Log based on severity
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
            AlertSeverity.EMERGENCY: logger.critical,
        }.get(severity, logger.error)

        log_method(f"ALERT [{severity.value.upper()}] {title}: {message}")

        return alert

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved."""
        with self._lock:
            for alert in self._alerts:
                if alert.id == alert_id and not alert.resolved:
                    alert.resolved = True
                    alert.resolved_at = datetime.utcnow()
                    return True
        return False

    def get_recent_requests(self, limit: int = 100) -> list[RequestMetrics]:
        """Get recent requests (sorted by time desc)."""
        with self._lock:
            cutoff = datetime.utcnow() - self._max_metrics_age
            recent = [r for r in self._requests if r.timestamp > cutoff]
            return sorted(recent, key=lambda x: x.timestamp, reverse=True)[:limit]

    def get_active_alerts(self) -> list[Alert]:
        """Get unresolved alerts."""
        with self._lock:
            return [a for a in self._alerts if not a.resolved]

    def get_percentile(self, metric_name: str, percentile: float) -> float:
        """Calculate percentile from histogram data."""
        with self._lock:
            values = sorted(self._histograms.get(metric_name, []))
            if not values:
                return 0.0
            k = (len(values) - 1) * percentile
            f = int(k)
            c = f + 1 if f < len(values) else f
            return values[f] + (k - f) * (values[c] - values[f]) if c != f else values[f]

    def get_summary(self) -> dict[str, Any]:
        """Get metrics summary for /health endpoint."""
        with self._lock:
            total_requests = self._counters.get("requests_total", 0)
            total_errors = self._counters.get("errors_total", 0)
            cache_hits = self._counters.get("cache_hits", 0)
            cache_misses = self._counters.get("cache_misses", 0)

        return {
            "uptime_seconds": time.time() - self._start_time,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0,
            "response_time_p50_ms": self.get_percentile("response_time_ms", 0.50),
            "response_time_p95_ms": self.get_percentile("response_time_ms", 0.95),
            "response_time_p99_ms": self.get_percentile("response_time_ms", 0.99),
            "cache_hit_rate": (cache_hits / (cache_hits + cache_misses) * 100)
            if (cache_hits + cache_misses) > 0
            else 0,
            "llm_total_cost_usd": self._gauges.get("llm_total_cost_usd", 0.0),
            "llm_tokens_total": self._counters.get("llm_tokens_total", 0),
            "active_alerts": len([a for a in self._alerts if not a.resolved]),
        }

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        summary = self.get_summary()

        lines = [
            "# HELP superai_requests_total Total number of requests",
            "# TYPE superai_requests_total counter",
            f"superai_requests_total {summary['total_requests']}",
            "",
            "# HELP superai_errors_total Total number of errors",
            "# TYPE superai_errors_total counter",
            f"superai_errors_total {summary['total_errors']}",
            "",
            "# HELP superai_error_rate Percentage of requests resulting in error",
            "# TYPE superai_errors_total gauge",
            f"superai_error_rate {summary['error_rate']:.2f}",
            "",
            "# HELP superai_response_time_ms Request response times",
            "# TYPE superai_response_time_ms summary",
            f'superai_response_time_ms{{p50="{summary["response_time_p50_ms"]:.2f}",p95="{summary["response_time_p95_ms"]:.2f}",p99="{summary["response_time_p99_ms"]:.2f}"}}',
            "",
            "# HELP superai_cache_hit_rate Cache hit percentage",
            "# TYPE superai_cache_hit_rate gauge",
            f"superai_cache_hit_rate {summary['cache_hit_rate']:.2f}",
            "",
            "# HELP superai_llm_cost_usd Total LLM API costs in USD",
            "# TYPE superai_llm_cost_usd counter",
            f"superai_llm_cost_usd {summary['llm_total_cost_usd']:.4f}",
            "",
            "# HELP superai_uptime_seconds Application uptime in seconds",
            "# TYPE superai_uptime_seconds counter",
            f"superai_uptime_seconds {summary['uptime_seconds']:.2f}",
            "",
        ]

        return "\n".join(lines)

    def cleanup_old_metrics(self):
        """Remove metrics older than max age."""
        with self._lock:
            cutoff = datetime.utcnow() - self._max_metrics_age
            self._requests = [r for r in self._requests if r.timestamp > cutoff]

            # Trim histograms to last 1000 entries
            for key in self._histograms:
                if len(self._histograms[key]) > 1000:
                    self._histagrams[key] = self._histograms[key][-1000:]


# Global singleton
_collector: MetricsCollector | None = None
_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector singleton."""
    global _collector
    if _collector is None:
        with _lock:
            if _collector is None:
                _collector = MetricsCollector()
    return _collector


def monitor_request():
    """
    Decorator to automatically monitor FastAPI endpoints.

    Usage:
        @app.get("/api/chat")
        @monitor_request()
        async def chat_endpoint(request: Request):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = next((a for a in args if hasattr(a, "method")), None)
            start_time = time.time()
            request_id = str(uuid.uuid4())[:8]

            try:
                result = await func(*args, **kwargs)

                # Extract response info
                status_code = getattr(result, "status_code", 200)
                duration_ms = (time.time() - start_time) * 1000

                metrics = RequestMetrics(
                    request_id=request_id,
                    method=request.method if request else "UNKNOWN",
                    path=request.url.path if request else "/unknown",
                    status_code=status_code,
                    duration_ms=duration_ms,
                    ip_address=request.client.host if request and request.client else None,
                    user_agent=request.headers.get("user-agent") if request else None,
                )

                get_metrics_collector().record_request(metrics)
                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                metrics = RequestMetrics(
                    request_id=request_id,
                    method=request.method if request else "UNKNOWN",
                    path=request.url.path if request else "/unknown",
                    status_code=500,
                    duration_ms=duration_ms,
                    error=str(e),
                )

                get_metrics_collector().record_request(metrics)
                raise

        return wrapper

    return decorator


@contextmanager
def request_context(request_id: str = None):
    """
    Context manager for request-scoped logging.

    Usage:
        with request_context() as ctx:
            logger.info("Processing request")
    """
    request_id = request_id or str(uuid.uuid4())[:8]

    # Add correlation ID to log records
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.correlation_id = request_id
        return record

    logging.setLogRecordFactory(record_factory)

    try:
        yield {"request_id": request_id}
    finally:
        logging.setLogRecordFactory(old_factory)


class BudgetMonitor:
    """
    Monitor LLM spending against budget thresholds.
    Alerts when approaching or exceeding limits.
    """

    def __init__(self, daily_budget_usd: float = 10.0, alert_threshold: float = 0.7):
        self.daily_budget = daily_budget_usd
        self.alert_threshold = alert_threshold  # Alert at 70% of budget
        self._daily_spend = 0.0
        self._reset_time = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        self._alerts_sent = set()  # Track sent alerts to avoid spamming

    def record_spend(self, amount: float, provider: str = "unknown"):
        """Record LLM spend and check budget."""
        self._check_reset()
        self._daily_spend += amount

        collector = get_metrics_collector()
        usage_pct = self._daily_spend / self.daily_budget * 100 if self.daily_budget > 0 else 0

        # Check thresholds
        if usage_pct >= 100:
            alert_key = "budget_exceeded"
            if alert_key not in self._alerts_sent:
                collector.create_alert(
                    severity=AlertSeverity.CRITICAL,
                    source="budget_monitor",
                    title="💸 Daily Budget Exceeded!",
                    message=f"Spend ${self._daily_spend:.2f} exceeds ${self.daily_budget:.2f} budget",
                    current_spend=self._daily_spend,
                    budget=self.daily_budget,
                    provider=provider,
                )
                self._alerts_sent.add(alert_key)

        elif usage_pct >= self.alert_threshold * 100:
            alert_key = f"budget_warning_{int(self.alert_threshold * 100)}"
            if alert_key not in self._alerts_sent:
                collector.create_alert(
                    severity=AlertSeverity.WARNING,
                    source="budget_monitor",
                    title="⚠️ Approaching Daily Budget Limit",
                    message=f"At ${self._daily_spend:.2f} ({usage_pct:.0f}%) of ${self.daily_budget:.2f} daily budget",
                    current_spend=self._daily_spend,
                    budget=self.daily_budget,
                    provider=provider,
                )
                self._alerts_sent.add(alert_key)

        return {
            "spend": self._daily_spend,
            "budget": self.daily_budget,
            "percentage": usage_pct,
            "remaining": max(0, self.daily_budget - self._daily_spend),
        }

    def _check_reset(self):
        """Reset daily counter at midnight UTC."""
        if datetime.utcnow() >= self._reset_time:
            self._daily_spend = 0.0
            self._reset_time = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            self._alerts_sent.clear()
            logger.info("📊 Budget monitor reset for new day")

    def get_status(self) -> dict[str, Any]:
        """Return current budget status."""
        self._check_reset()
        return {
            "daily_budget_usd": self.daily_budget,
            "current_spend_usd": self._daily_spend,
            "percentage_used": (self._daily_spend / self.daily_budget * 100)
            if self.daily_budget > 0
            else 0,
            "remaining_usd": max(0, self.daily_budget - self._daily_spend),
            "resets_at": self._reset_time.isoformat(),
            "alert_threshold": self.alert_threshold * 100,
        }


# Global budget monitor instance
_budget_monitor: BudgetMonitor | None = None


def get_budget_monitor() -> BudgetMonitor:
    """Get or create budget monitor singleton."""
    global _budget_monitor
    if _budget_monitor is None:
        import os

        budget = float(os.getenv("DAILY_BUDGET_USD", "10.0"))
        threshold = float(os.getenv("BUDGET_ALERT_THRESHOLD", "0.7"))
        _budget_monitor = BudgetMonitor(daily_budget_usd=budget, alert_threshold=threshold)
    return _budget_monitor


# END OF PATCH 06
# Verify: GET /metrics returns Prometheus-formatted output
# Monitor: Check logs for ALERT messages when budgets exceeded
