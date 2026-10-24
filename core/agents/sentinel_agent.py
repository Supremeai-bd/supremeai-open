"""
SupremeAI — Sentinel Agent
===========================

Monitoring and alerting agent for production systems.
- Heartbeat monitoring
- Anomaly detection
- Alert routing (Discord, email, webhook)
- Health score calculation
- Zero-cost: uses Upstash Redis + Discord webhooks
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.cache import get_cache
from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
HEARTBEAT_TTL = 60  # 1 minute
ALERT_CACHE_TTL = 3600


class AlertSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class HealthCheck:
    """Health check result."""

    service: str
    status: str
    latency_ms: float
    error_rate: float
    checked_at: datetime


@dataclass(frozen=True)
class Alert:
    """Alert notification."""

    service: str
    severity: AlertSeverity
    message: str
    details: dict[str, Any]
    triggered_at: datetime


class HeartbeatMonitor:
    """
    Monitors service heartbeats via Redis.
    """

    def __init__(self, cache: Any | None = None) -> None:
        self.cache = cache or get_cache()

    def _heartbeat_key(self, service: str) -> str:
        return f"heartbeat:{service}"

    async def register_heartbeat(self, service: str) -> None:
        """Register service heartbeat."""
        await self.cache.set(
            self._heartbeat_key(service),
            datetime.now(UTC).isoformat(),
            ttl=HEARTBEAT_TTL * 2,  # Must refresh before this expires
        )

    async def check_heartbeat(self, service: str) -> bool:
        """Check if service heartbeat is recent."""
        last_beat = await self.cache.get(self._heartbeat_key(service))
        if not last_beat:
            return False

        try:
            last_time = datetime.fromisoformat(last_beat.replace("Z", "+00:00"))
            elapsed = (datetime.now(UTC) - last_time).total_seconds()
            return elapsed < HEARTBEAT_TTL
        except (ValueError, TypeError):
            return False


class AnomalyDetector:
    """
    Detects anomalies in metrics using statistical methods.
    """

    @staticmethod
    def detect(
        metric_name: str,
        current_value: float,
        baseline_values: list[float],
    ) -> tuple[bool, float]:
        """
        Detect anomaly using z-score.

        Returns:
            Tuple of (is_anomaly, z_score).
        """
        if len(baseline_values) < 5:
            return False, 0.0

        mean = sum(baseline_values) / len(baseline_values)
        variance = sum((v - mean) ** 2 for v in baseline_values) / len(baseline_values)
        std_dev = variance**0.5

        if std_dev == 0:
            return False, 0.0

        z_score = abs(current_value - mean) / std_dev
        return z_score > 2.0, z_score


class AlertRouter:
    """
    Routes alerts to configured channels.
    Supports Discord, Resend (email), webhooks.
    """

    @staticmethod
    async def send_discord(webhook_url: str, alert: Alert) -> bool:
        """Send alert to Discord webhook."""
        import aiohttp

        color_map = {
            AlertSeverity.CRITICAL: 16711680,  # Red
            AlertSeverity.HIGH: 16776960,  # Yellow
            AlertSeverity.MEDIUM: 16711680,  # Orange
            AlertSeverity.LOW: 65280,  # Green
        }

        payload = {
            "embeds": [
                {
                    "title": f"Alert: {alert.service}",
                    "description": alert.message,
                    "color": color_map.get(alert.severity, 0),
                    "fields": [
                        {"name": "Severity", "value": alert.severity.value},
                        {"name": "Time", "value": alert.triggered_at.isoformat()},
                    ],
                }
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    return resp.status == 204
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return False


class SentinelAgent:
    """
    Main sentinel monitoring agent.
    """

    def __init__(
        self,
        monitor: HeartbeatMonitor | None = None,
        detector: AnomalyDetector | None = None,
    ) -> None:
        self.monitor = monitor or HeartbeatMonitor()
        self.detector = detector or AnomalyDetector()
        self.cache = get_cache()
        self.discord_webhook = os.environ.get("DISCORD_ALERT_WEBHOOK", "")
        logger.info("SentinelAgent initialized")

    async def check_service_health(self, service: str, metrics: dict[str, float]) -> HealthCheck:
        """
        Check service health and trigger alerts.

        Args:
            service: Service name.
            metrics: Current metrics.

        Returns:
            HealthCheck result.
        """
        # Check heartbeat
        heartbeat_ok = await self.monitor.check_heartbeat(service)

        # Get baseline metrics
        baseline_key = f"baseline:{service}"
        baseline = await self.cache.get(baseline_key) or []

        # Check for anomalies
        anomalies = []
        for name, value in metrics.items():
            is_anomaly, z_score = self.detector.detect(name, value, baseline)
            if is_anomaly:
                anomalies.append({"metric": name, "value": value, "z_score": z_score})

        # Calculate health score
        health_score = 1.0
        if not heartbeat_ok:
            health_score -= 0.4
        health_score -= len(anomalies) * 0.1
        health_score = max(0.0, health_score)

        status = (
            "healthy" if health_score > 0.8 else "degraded" if health_score > 0.5 else "unhealthy"
        )

        # Trigger alerts
        if status != "healthy":
            alert = Alert(
                service=service,
                severity=(AlertSeverity.HIGH if status == "unhealthy" else AlertSeverity.MEDIUM),
                message=f"Service {service} is {status}",
                details={"anomalies": anomalies, "health_score": health_score},
                triggered_at=datetime.now(UTC),
            )
            await self._send_alert(alert)

        return HealthCheck(
            service=service,
            status=status,
            latency_ms=metrics.get("latency", 0),
            error_rate=metrics.get("error_rate", 0),
            checked_at=datetime.now(UTC),
        )

    async def _send_alert(self, alert: Alert) -> None:
        """Send alert to configured channels."""
        if self.discord_webhook:
            await AlertRouter.send_discord(self.discord_webhook, alert)

        # Cache alert
        alert_key = f"alert:{alert.service}:{alert.triggered_at.isoformat()}"
        await self.cache.set(
            alert_key,
            alert.__dict__,
            ttl=ALERT_CACHE_TTL,
        )

    def check_behavioral_anomaly(self, agent_id: str, action: str, prompt: str) -> dict[str, Any]:
        """Check agent action against BehavioralGuard."""
        from monitoring.behavioral_guard import BehavioralGuard

        if not hasattr(self, "_behavioral_guard"):
            self._behavioral_guard = BehavioralGuard()
        return self._behavioral_guard.record_action(agent_id, action, prompt)


# Singleton
_sentinel_instance: SentinelAgent | None = None


def get_sentinel() -> SentinelAgent:
    """Get or create the singleton SentinelAgent instance."""
    global _sentinel_instance
    if _sentinel_instance is None:
        _sentinel_instance = SentinelAgent()
    return _sentinel_instance
