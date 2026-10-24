"""
SupremeAI — Performance Guardian Agent
======================================

Monitors and optimizes system performance.
- Real-time metric collection
- Anomaly detection
- Auto-scaling recommendations
- Resource usage analysis
- Zero-cost: heuristic-based without external metrics systems
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
METRIC_CACHE_TTL = 300  # 5 minutes
ANOMALY_THRESHOLD = 2.0  # Standard deviations


class MetricSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class PerformanceAlert:
    """Performance alert/notification."""

    metric_name: str
    current_value: float
    threshold: float
    severity: MetricSeverity
    recommendation: str
    detected_at: datetime


class MetricCollector:
    """
    Collects system and application metrics.
    Zero-cost: uses psutil when available, else basic estimation.
    """

    def __init__(self) -> None:
        self.cache = get_cache()
        self._metrics: dict[str, list[float]] = defaultdict(list)

    def collect_system_metrics(self) -> dict[str, float]:
        """Collect system resource metrics."""
        metrics = {
            "timestamp": time.time(),
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "disk_percent": 0.0,
            "network_io": 0.0,
        }

        try:
            import psutil

            metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            metrics["memory_percent"] = psutil.virtual_memory().percent
            metrics["disk_percent"] = psutil.disk_usage("/").percent
            net = psutil.net_io_counters()
            metrics["network_io"] = (net.bytes_sent + net.bytes_recv) / 1024 / 1024
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")

        return metrics

    def record_metric(self, name: str, value: float) -> None:
        """Record a custom metric."""
        self._metrics[name].append(value)
        if len(self._metrics[name]) > 100:
            self._metrics[name] = self._metrics[name][-100:]


class AnomalyDetector:
    """
    Detects performance anomalies using statistical methods.
    """

    def __init__(self, cache: Any | None = None) -> None:
        self.cache = cache or get_cache()

    def detect(
        self,
        metric_name: str,
        values: list[float],
        threshold: float = ANOMALY_THRESHOLD,
    ) -> tuple[bool, float]:
        """
        Detect if current value is anomalous.

        Returns:
            Tuple of (is_anomaly, z_score).
        """
        if len(values) < 5:
            return False, 0.0

        mean = sum(values) / len(values)
        # Sample variance (n-1) makes the detector more sensitive for small windows
        variance = sum((v - mean) ** 2 for v in values) / max(1, (len(values) - 1))
        std_dev = variance**0.5

        if std_dev == 0:
            return False, 0.0

        current = values[-1]
        z_score = abs(current - mean) / std_dev

        return z_score >= threshold, z_score


class PerformanceGuardian:
    """
    Main performance monitoring and optimization agent.
    """

    def __init__(
        self,
        collector: MetricCollector | None = None,
        detector: AnomalyDetector | None = None,
        llm_router: ModelRouter | None = None,
    ) -> None:
        self.collector = collector or MetricCollector()
        self.detector = detector or AnomalyDetector()
        self.llm = llm_router or ModelRouter()
        self.cache = get_cache()
        self.alerts: list[PerformanceAlert] = []
        logger.info("PerformanceGuardian initialized")

    async def check_health(self) -> dict[str, Any]:
        """
        Check overall system health.

        Returns:
            Health report with metrics and alerts.
        """
        metrics = self.collector.collect_system_metrics()

        alerts = []

        # Check CPU
        cpu = metrics.get("cpu_percent", 0)
        # বাংলা মন্তব্য: NOTE — AnomalyDetector.detect() পরিসংখ্যানগতভাবে অর্থপূর্ণ ফলাফল
        # দিতে ন্যূনতম ৫টা historical value দরকার (len(values) < 5 হলে সবসময়
        # (False, 0.0) রিটার্ন করে)। এখানে শুধু বর্তমান মুহূর্তের একটা মান
        # ([cpu]) পাঠানো হচ্ছে, তাই এই কলটা কখনোই anomaly detect করতে পারবে না —
        # আপাতত শুধু নিচের হার্ডকোডেড থ্রেশহোল্ড (cpu > 80) দিয়েই alert হচ্ছে।
        # প্রকৃত anomaly detection চালু করতে PerformanceGuardian-এ প্রতিটা metric-এর
        # rolling history buffer রাখা দরকার — এটা একটা আলাদা ফিচার-স্কোপ কাজ।
        _is_anomaly, _ = self.detector.detect("cpu_percent", [cpu])
        if cpu > 80:
            alerts.append(
                PerformanceAlert(
                    metric_name="cpu_percent",
                    current_value=cpu,
                    threshold=80,
                    severity=MetricSeverity.WARNING,
                    recommendation="Consider optimizing CPU-intensive operations or scaling horizontally.",
                    detected_at=datetime.now(UTC),
                )
            )

        # Check Memory
        memory = metrics.get("memory_percent", 0)
        if memory > 85:
            alerts.append(
                PerformanceAlert(
                    metric_name="memory_percent",
                    current_value=memory,
                    threshold=85,
                    severity=MetricSeverity.CRITICAL,
                    recommendation="High memory usage detected. Consider memory profiling and cleanup.",
                    detected_at=datetime.now(UTC),
                )
            )

        self.alerts.extend(alerts)

        return {
            "status": (
                "healthy"
                if not any(a.severity == MetricSeverity.CRITICAL for a in alerts)
                else "degraded"
            ),
            "metrics": metrics,
            "alerts": [
                {
                    "metric": a.metric_name,
                    "value": a.current_value,
                    "severity": a.severity.value,
                    "recommendation": a.recommendation,
                }
                for a in alerts
            ],
            "checked_at": datetime.now(UTC).isoformat(),
        }

    async def analyze_bottleneck(self, operation_name: str, duration_ms: float) -> dict[str, Any]:
        """
        Analyze performance bottleneck.

        Args:
            operation_name: Name of slow operation.
            duration_ms: Duration in milliseconds.

        Returns:
            Analysis and recommendations.
        """
        cache_key = f"bottleneck:{operation_name}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # Get context for analysis
        metrics = self.collector.collect_system_metrics()

        # Analyze with LLM
        prompt = (
            f"Analyze this performance bottleneck in {operation_name}. "
            f"Duration: {duration_ms}ms. "
            f"Current CPU: {metrics.get('cpu_percent', 0)}%, "
            f"Memory: {metrics.get('memory_percent', 0)}%. "
            "Suggest optimizations and explain why this might be happening."
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("performance_guardian_max_tokens", 500),
            )

            analysis = {
                "operation": operation_name,
                "duration_ms": duration_ms,
                "analysis": result.get("text", ""),
                "system_context": metrics,
            }

            await self.cache.set(cache_key, analysis, ttl=METRIC_CACHE_TTL)
            return analysis

        except Exception as e:
            return {
                "operation": operation_name,
                "error": str(e),
            }

    async def get_scaling_recommendation(
        self, current_load: float, predicted_load: float
    ) -> dict[str, Any]:
        """
        Recommend scaling actions.

        Args:
            current_load: Current system load (0-1 scale).
            predicted_load: Predicted future load.

        Returns:
            Scaling recommendation.
        """
        if predicted_load > 0.8 and current_load < predicted_load * 1.5:
            return {
                "action": "scale_up",
                "instances_to_add": max(1, int(predicted_load - current_load) * 3),
                "urgency": "high" if predicted_load > 0.9 else "medium",
            }

        if current_load < 0.3:
            return {
                "action": "scale_down",
                "instances_to_remove": 1,
                "urgency": "low",
            }

        return {
            "action": "maintain",
            "instances_to_add": 0,
            "instances_to_remove": 0,
            "urgency": "none",
        }


# Singleton
_guardian_instance: PerformanceGuardian | None = None


def get_performance_guardian() -> PerformanceGuardian:
    """Get or create the singleton PerformanceGuardian instance."""
    global _guardian_instance
    if _guardian_instance is None:
        _guardian_instance = PerformanceGuardian()
    return _guardian_instance
