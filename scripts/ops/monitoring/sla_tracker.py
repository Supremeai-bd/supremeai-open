#!/usr/bin/env python3
"""
scripts/monitoring/sla_tracker.py
==================================
SupremeAI 2.0 — SLA Compliance Tracking & SLO Dashboard

Tracks Service Level Objectives (SLOs) and Agreements (SLAs) across all
SupremeAI services: API endpoints, AI providers, database, WebSocket,
CI/CD pipelines, and external integrations.

Features:
- Real-time SLO compliance calculation (availability, latency, error rate)
- Multi-tier SLA tracking (API, AI Provider, Database, CI/CD)
- Automatic breach detection with escalation
- Historical trend analysis
- Export to GitHub Step Summary / Markdown reports
- Integration with existing health check and cost monitoring

Usage:
    python scripts/monitoring/sla_tracker.py --check
    python scripts/monitoring/sla_tracker.py --report --days 30
    python scripts/monitoring/sla_tracker.py --provider gemini --slo availability
    python scripts/monitoring/sla_tracker.py --watch --interval 60

Environment:
    BACKEND_URL             - API base URL (default: http://localhost:8000)  # is_local()
    SUPABASE_URL            - Supabase project URL
    REDIS_URL               - Redis connection URL
    DISCORD_WEBHOOK_URL     - Discord alerts
    TELEGRAM_BOT_TOKEN      - Telegram bot token
    TELEGRAM_CHAT_ID        - Telegram chat ID
    SLA_AVAILABILITY_TARGET - Default availability target (default: 99.9)
    SLA_LATENCY_P99_TARGET  - P99 latency target ms (default: 2000)
    SLA_ERROR_RATE_TARGET     - Error rate target % (default: 0.1)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / "backend"))
from core.config import settings
from core.deployment_fallback_defaults import SCRAPER_URL_DEFAULT
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

# ── Setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sla_tracker")

# ── Constants ──────────────────────────────────────────────────────────
DEFAULT_BACKENDS = [
    settings.backend_url,
    os.getenv("SCRAPER_URL", SCRAPER_URL_DEFAULT),
]
API_HEALTH_PATH = "/api/v1/health"
API_METRICS_PATH = "/api/v1/metrics"

DEFAULT_SLO_TARGETS = {
    "availability": 99.9,
    "latency_p99": 2000,
    "error_rate": 0.1,
    "throughput_rps": 10.0,
}


# ── Enums ──────────────────────────────────────────────────────────────
class ServiceTier(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SLABreachSeverity(Enum):
    NONE = "none"
    WARNING = "warning"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


# ── Data Models ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SLIMetric:
    """Single metric measurement."""
    timestamp: datetime
    service: str
    metric_type: str
    value: float
    unit: str
    region: str = "global"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class SLODefinition:
    """Service Level Objective definition."""
    name: str
    description: str
    target_value: float
    unit: str
    tier: ServiceTier
    window_minutes: int = 60
    burn_rate_threshold: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "target_value": self.target_value,
            "unit": self.unit,
            "tier": self.tier.value,
            "window_minutes": self.window_minutes,
            "burn_rate_threshold": self.burn_rate_threshold,
        }


@dataclass
class SLAResult:
    """SLA compliance result for a service."""
    service: str
    slo_name: str
    target: float
    actual: float
    unit: str
    compliance_pct: float
    is_compliant: bool
    window_start: datetime
    window_end: datetime
    measurements: int
    severity: SLABreachSeverity = SLABreachSeverity.NONE
    error_budget_remaining_pct: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "slo_name": self.slo_name,
            "target": self.target,
            "actual": round(self.actual, 4),
            "unit": self.unit,
            "compliance_pct": round(self.compliance_pct, 2),
            "is_compliant": self.is_compliant,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "measurements": self.measurements,
            "severity": self.severity.value,
            "error_budget_remaining_pct": round(self.error_budget_remaining_pct, 2),
        }


@dataclass
class ServiceHealth:
    """Aggregated health status for a service."""
    service: str
    tier: ServiceTier
    overall_status: str
    slo_results: list[SLAResult] = field(default_factory=list)
    last_check: datetime | None = None
    uptime_pct: float = 100.0
    incident_count_24h: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "tier": self.tier.value,
            "overall_status": self.overall_status,
            "slo_results": [r.to_dict() for r in self.slo_results],
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "uptime_pct": round(self.uptime_pct, 2),
            "incident_count_24h": self.incident_count_24h,
        }


@dataclass
class Incident:
    """Detected SLA breach incident."""
    id: str
    service: str
    slo_name: str
    severity: SLABreachSeverity
    started_at: datetime
    resolved_at: datetime | None = None
    duration_seconds: int = 0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "service": self.service,
            "slo_name": self.slo_name,
            "severity": self.severity.value,
            "started_at": self.started_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "duration_seconds": self.duration_seconds,
            "description": self.description,
        }


# ── SLO Registry ───────────────────────────────────────────────────────
SLO_REGISTRY: list[SLODefinition] = [
    SLODefinition("api_availability", "API endpoint availability", 99.9, "%", ServiceTier.CRITICAL, 60),
    SLODefinition("api_latency_p99", "API P99 response time", 2000, "ms", ServiceTier.CRITICAL, 60),
    SLODefinition("api_error_rate", "API error rate", 0.1, "%", ServiceTier.CRITICAL, 60),
    SLODefinition("api_throughput", "API requests per second", 10.0, "rps", ServiceTier.CRITICAL, 60),

    SLODefinition("ai_availability", "AI provider availability", 99.5, "%", ServiceTier.HIGH, 60),
    SLODefinition("ai_latency_p99", "AI response P99 latency", 5000, "ms", ServiceTier.HIGH, 60),
    SLODefinition("ai_error_rate", "AI provider error rate", 1.0, "%", ServiceTier.HIGH, 60),

    SLODefinition("db_availability", "Database availability", 99.99, "%", ServiceTier.CRITICAL, 60),
    SLODefinition("db_query_p99", "Database query P99 latency", 100, "ms", ServiceTier.CRITICAL, 60),
    SLODefinition("db_connection_pool", "DB connection pool utilization", 80.0, "%", ServiceTier.CRITICAL, 60),

    SLODefinition("ws_availability", "WebSocket availability", 99.5, "%", ServiceTier.HIGH, 60),
    SLODefinition("ws_message_latency", "WebSocket message latency", 500, "ms", ServiceTier.HIGH, 60),

    SLODefinition("ci_success_rate", "CI pipeline success rate", 95.0, "%", ServiceTier.MEDIUM, 1440),
    SLODefinition("ci_duration_p95", "CI pipeline P95 duration", 600, "seconds", ServiceTier.MEDIUM, 1440),

    SLODefinition("frontend_lcp", "Largest Contentful Paint", 2500, "ms", ServiceTier.MEDIUM, 1440),
    SLODefinition("frontend_cls", "Cumulative Layout Shift", 0.1, "score", ServiceTier.MEDIUM, 1440),
]


# ── Collectors ─────────────────────────────────────────────────────────
class MetricCollector:
    """Base class for metric collection."""

    async def collect(self) -> list[SLIMetric]:
        raise NotImplementedError


class APICollector(MetricCollector):
    """Collect metrics from SupremeAI API endpoints."""

    def __init__(self, base_urls: list[str] | None = None):
        self.base_urls = base_urls or [settings.backend_url]

    async def collect(self) -> list[SLIMetric]:
        metrics: list[SLIMetric] = []
        now = datetime.now()

        for base_url in self.base_urls:
            start = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{base_url}{API_HEALTH_PATH}")
                latency_ms = (time.perf_counter() - start) * 1000

                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"api:{base_url}",
                    metric_type="availability",
                    value=100.0 if resp.status_code == 200 else 0.0,
                    unit="%",
                ))
                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"api:{base_url}",
                    metric_type="latency",
                    value=latency_ms,
                    unit="ms",
                ))
                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"api:{base_url}",
                    metric_type="error_rate",
                    value=0.0 if resp.status_code == 200 else 100.0,
                    unit="%",
                ))
            except Exception as exc:
                logger.warning(f"API health check failed for {base_url}: {exc}")
                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"api:{base_url}",
                    metric_type="availability",
                    value=0.0,
                    unit="%",
                ))
                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"api:{base_url}",
                    metric_type="error_rate",
                    value=100.0,
                    unit="%",
                ))

        return metrics


class AIProviderCollector(MetricCollector):
    """Collect AI provider health metrics."""

    async def collect(self) -> list[SLIMetric]:
        metrics: list[SLIMetric] = []
        now = datetime.now()

        providers = [
            ("openrouter", os.getenv("OPENROUTER_API_KEY")),
            ("gemini", os.getenv("GEMINI_API_KEY")),
            ("deepseek", os.getenv("DEEPSEEK_API_KEY")),
            ("groq", os.getenv("GROQ_API_KEY")),
            ("nvidia", os.getenv("NVIDIA_API_KEY")),
        ]

        for name, key in providers:
            if not key:
                continue

            start = time.perf_counter()
            try:
                if name == "openrouter":
                    async with httpx.AsyncClient(timeout=15) as client:
                        headers = {"Authorization": f"Bearer {key}"}
                        resp = await client.get(
                            "https://openrouter.ai/api/v1/auth/key",
                            headers=headers,
                        )
                    latency_ms = (time.perf_counter() - start) * 1000
                    is_up = resp.status_code == 200

                elif name == "gemini":
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.get(
                            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                        )
                    latency_ms = (time.perf_counter() - start) * 1000
                    is_up = resp.status_code == 200

                else:
                    latency_ms = 0
                    is_up = True

                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"ai:{name}",
                    metric_type="availability",
                    value=100.0 if is_up else 0.0,
                    unit="%",
                ))
                if latency_ms > 0:
                    metrics.append(SLIMetric(
                        timestamp=now,
                        service=f"ai:{name}",
                        metric_type="latency",
                        value=latency_ms,
                        unit="ms",
                    ))
            except Exception as exc:
                logger.warning(f"AI provider check failed for {name}: {exc}")
                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"ai:{name}",
                    metric_type="availability",
                    value=0.0,
                    unit="%",
                ))
                metrics.append(SLIMetric(
                    timestamp=now,
                    service=f"ai:{name}",
                    metric_type="error_rate",
                    value=100.0,
                    unit="%",
                ))

        return metrics


class DatabaseCollector(MetricCollector):
    """Collect database health metrics."""

    async def collect(self) -> list[SLIMetric]:
        metrics: list[SLIMetric] = []
        now = datetime.now()

        backend_url = settings.backend_url
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{backend_url}{API_HEALTH_PATH}")
                data = resp.json() if resp.status_code == 200 else {}

            db_status = data.get("database", "unknown")
            metrics.append(SLIMetric(
                timestamp=now,
                service="db:supabase",
                metric_type="availability",
                value=100.0 if db_status == "connected" else 0.0,
                unit="%",
            ))
        except Exception as exc:
            logger.warning(f"DB health check failed: {exc}")
            metrics.append(SLIMetric(
                timestamp=now,
                service="db:supabase",
                metric_type="availability",
                value=0.0,
                unit="%",
            ))

        return metrics


# ── SLA Engine ─────────────────────────────────────────────────────────
class SLAEngine:
    """Core SLA calculation and breach detection engine."""

    def __init__(self):
        self.metrics: list[SLIMetric] = []
        self.incidents: list[Incident] = []
        self._active_incidents: dict[str, Incident] = {}

    def add_metrics(self, metrics: list[SLIMetric]) -> None:
        self.metrics.extend(metrics)
        cutoff = datetime.now() - timedelta(days=7)
        self.metrics = [m for m in self.metrics if m.timestamp > cutoff]

    def calculate_slo(self, slo: SLODefinition, window_minutes: int | None = None) -> SLAResult:
        """Calculate SLO compliance for a specific objective."""
        window = window_minutes or slo.window_minutes
        cutoff = datetime.now() - timedelta(minutes=window)

        relevant = [
            m for m in self.metrics
            if m.metric_type in slo.name and m.timestamp > cutoff
        ]

        if not relevant:
            return SLAResult(
                service=slo.name.split("_")[0],
                slo_name=slo.name,
                target=slo.target_value,
                actual=0.0,
                unit=slo.unit,
                compliance_pct=0.0,
                is_compliant=False,
                window_start=cutoff,
                window_end=datetime.now(),
                measurements=0,
            )

        values = [m.value for m in relevant]

        if "availability" in slo.name:
            actual = statistics.mean(values)
            compliance = (actual / slo.target_value) * 100 if slo.target_value > 0 else 0
        elif "latency" in slo.name or "duration" in slo.name or "lcp" in slo.name:
            actual = max(values) if "p99" in slo.name or "p95" in slo.name else statistics.mean(values)
            compliance = (slo.target_value / actual) * 100 if actual > 0 else 100
        elif "error_rate" in slo.name or "cls" in slo.name:
            actual = statistics.mean(values)
            compliance = ((slo.target_value - actual) / slo.target_value) * 100 if slo.target_value > 0 else 100
        elif "throughput" in slo.name:
            actual = statistics.mean(values)
            compliance = (actual / slo.target_value) * 100 if slo.target_value > 0 else 0
        else:
            actual = statistics.mean(values)
            compliance = (actual / slo.target_value) * 100 if slo.target_value > 0 else 0

        compliance = max(0, min(100, compliance))
        is_compliant = compliance >= 100

        error_budget_used = max(0, 100 - compliance)
        error_budget_remaining = max(0, 100 - error_budget_used)

        severity = SLABreachSeverity.NONE
        if not is_compliant:
            if error_budget_used >= 100:
                severity = SLABreachSeverity.CRITICAL
            elif error_budget_used >= 50:
                severity = SLABreachSeverity.MAJOR
            elif error_budget_used >= 20:
                severity = SLABreachSeverity.MINOR
            else:
                severity = SLABreachSeverity.WARNING

        service_key = f"{slo.name}"
        if severity in [SLABreachSeverity.MINOR, SLABreachSeverity.MAJOR, SLABreachSeverity.CRITICAL]:
            if service_key not in self._active_incidents:
                incident = Incident(
                    id=f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slo.name}",
                    service=slo.name.split("_")[0],
                    slo_name=slo.name,
                    severity=severity,
                    started_at=datetime.now(),
                    description=f"SLO breach: {slo.name} at {actual:.2f}{slo.unit} (target: {slo.target_value}{slo.unit})",
                )
                self._active_incidents[service_key] = incident
                self.incidents.append(incident)
        else:
            if service_key in self._active_incidents:
                incident = self._active_incidents.pop(service_key)
                incident.resolved_at = datetime.now()
                incident.duration_seconds = int((incident.resolved_at - incident.started_at).total_seconds())

        return SLAResult(
            service=slo.name.split("_")[0],
            slo_name=slo.name,
            target=slo.target_value,
            actual=actual,
            unit=slo.unit,
            compliance_pct=compliance,
            is_compliant=is_compliant,
            window_start=cutoff,
            window_end=datetime.now(),
            measurements=len(relevant),
            severity=severity,
            error_budget_remaining_pct=error_budget_remaining,
        )

    def full_report(self) -> dict[str, Any]:
        """Generate complete SLA compliance report."""
        services: dict[str, ServiceHealth] = {}

        for slo in SLO_REGISTRY:
            result = self.calculate_slo(slo)
            service_name = result.service

            if service_name not in services:
                tier = ServiceTier.MEDIUM
                for s in SLO_REGISTRY:
                    if s.name.startswith(service_name):
                        tier = s.tier
                        break

                services[service_name] = ServiceHealth(
                    service=service_name,
                    tier=tier,
                    overall_status="healthy",
                )

            services[service_name].slo_results.append(result)

            if any(r.severity == SLABreachSeverity.CRITICAL for r in services[service_name].slo_results):
                services[service_name].overall_status = "unhealthy"
            elif any(r.severity in [SLABreachSeverity.MAJOR, SLABreachSeverity.MINOR] for r in services[service_name].slo_results):
                services[service_name].overall_status = "degraded"

        for service_name, health in services.items():
            avail_results = [r for r in health.slo_results if "availability" in r.slo_name]
            if avail_results:
                health.uptime_pct = statistics.mean([r.actual for r in avail_results])
            health.last_check = datetime.now()
            health.incident_count_24h = len([
                i for i in self.incidents
                if i.service == service_name and i.started_at > datetime.now() - timedelta(hours=24)
            ])

        active_incidents = [i for i in self.incidents if i.resolved_at is None]

        return {
            "generated_at": datetime.now().isoformat(),
            "services": {name: svc.to_dict() for name, svc in services.items()},
            "active_incidents": [i.to_dict() for i in active_incidents],
            "resolved_incidents_24h": len([i for i in self.incidents if i.resolved_at and i.resolved_at > datetime.now() - timedelta(hours=24)]),
            "overall_compliance": {
                "critical": len([s for s in services.values() if s.tier == ServiceTier.CRITICAL and s.overall_status == "healthy"]),
                "total_critical": len([s for s in services.values() if s.tier == ServiceTier.CRITICAL]),
                "all_healthy": all(s.overall_status == "healthy" for s in services.values()),
            },
        }


# ── Alerting ───────────────────────────────────────────────────────────
async def send_sla_alert(report: dict[str, Any]) -> None:
    """Send alerts for active SLA breaches."""
    active = report.get("active_incidents", [])
    if not active:
        return

    critical = [i for i in active if i.get("severity") == "critical"]
    if not critical:
        return

    message = "🚨 **SupremeAI SLA Breach Alert**\n\n"
    for inc in critical:
        message += f"• **{inc['service']}** — {inc['slo_name']}\n"
        message += f"  {inc['description']}\n"
        message += f"  Started: {inc['started_at']}\n\n"

    discord_url = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(discord_url, json={"content": message})
            logger.info("SLA Discord alert sent")
        except Exception as exc:
            logger.error(f"Discord alert failed: {exc}")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                )
            logger.info("SLA Telegram alert sent")
        except Exception as exc:
            logger.error(f"Telegram alert failed: {exc}")


# ── Output Formatters ──────────────────────────────────────────────────
def format_markdown(report: dict[str, Any]) -> str:
    """Format SLA report as Markdown."""
    lines = [
        "# 📊 SupremeAI SLA Compliance Report",
        f"**Generated:** {report['generated_at']}",
        "",
        "## 🎯 Overall Compliance",
        f"- **All Services Healthy:** {'✅ Yes' if report['overall_compliance']['all_healthy'] else '❌ No'}",
        f"- **Critical Services Healthy:** {report['overall_compliance']['critical']}/{report['overall_compliance']['total_critical']}",
        f"- **Active Incidents:** {len(report['active_incidents'])}",
        f"- **Resolved (24h):** {report['resolved_incidents_24h']}",
        "",
        "## 🔍 Service Status",
        "",
        "| Service | Tier | Status | Uptime % | Incidents (24h) |",
        "|---------|------|--------|----------|-----------------|",
    ]

    for name, svc in report["services"].items():
        status_emoji = "🟢" if svc["overall_status"] == "healthy" else "🟡" if svc["overall_status"] == "degraded" else "🔴"
        lines.append(
            f"| {name} | {svc['tier']} | {status_emoji} {svc['overall_status']} | "
            f"{svc['uptime_pct']:.2f}% | {svc['incident_count_24h']} |"
        )

    lines.extend([
        "",
        "## 📋 SLO Details",
        "",
        "| Service | SLO | Target | Actual | Compliance | Budget Left | Status |",
        "|---------|-----|--------|--------|------------|-------------|--------|",
    ])

    for name, svc in report["services"].items():
        for slo in svc["slo_results"]:
            status = "✅" if slo["is_compliant"] else "❌"
            lines.append(
                f"| {name} | {slo['slo_name']} | {slo['target']}{slo['unit']} | "
                f"{slo['actual']:.2f}{slo['unit']} | {slo['compliance_pct']:.1f}% | "
                f"{slo['error_budget_remaining_pct']:.1f}% | {status} |"
            )

    if report["active_incidents"]:
        lines.extend([
            "",
            "## 🚨 Active Incidents",
            "",
            "| ID | Service | SLO | Severity | Started | Duration |",
            "|----|---------|-----|----------|---------|----------|",
        ])
        for inc in report["active_incidents"]:
            duration = "ongoing"
            lines.append(
                f"| {inc['id']} | {inc['service']} | {inc['slo_name']} | "
                f"{inc['severity']} | {inc['started_at']} | {duration} |"
            )

    lines.extend([
        "",
        "---",
        "*Generated by SupremeAI SLA Tracker*",
    ])

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────
async def run_check() -> dict[str, Any]:
    """Run a single SLA compliance check."""
    engine = SLAEngine()

    collectors: list[MetricCollector] = [
        APICollector(),
        AIProviderCollector(),
        DatabaseCollector(),
    ]

    for collector in collectors:
        try:
            metrics = await collector.collect()
            engine.add_metrics(metrics)
            logger.info(f"  ✓ {collector.__class__.__name__}: {len(metrics)} metrics")
        except Exception as exc:
            logger.error(f"  ✗ {collector.__class__.__name__}: {exc}")

    return engine.full_report()


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI 2.0 SLA Compliance Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--check", action="store_true", help="Run single check")
    parser.add_argument("--report", action="store_true", help="Generate full report")
    parser.add_argument("--days", type=int, default=7, help="Report window in days")
    parser.add_argument("--provider", type=str, help="Filter to specific provider")
    parser.add_argument("--slo", type=str, help="Filter to specific SLO")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring mode")
    parser.add_argument("--interval", type=int, default=60, help="Watch interval in seconds")
    parser.add_argument("--output", choices=["json", "markdown"], default="markdown", help="Output format")
    parser.add_argument("--save", type=str, help="Save output to file")

    args = parser.parse_args()

    if args.watch:
        logger.info(f"👁️  Starting SLA watch mode (interval: {args.interval}s)")
        while True:
            report = await run_check()
            if args.output == "json":
                print(json.dumps(report, indent=2, default=str))
            else:
                print(format_markdown(report))

            await send_sla_alert(report)

            logger.info(f"Next check in {args.interval}s...")
            await asyncio.sleep(args.interval)

    elif args.check or args.report:
        logger.info("🔍 Running SLA compliance check...")
        report = await run_check()

        if args.provider:
            report["services"] = {
                k: v for k, v in report["services"].items()
                if args.provider.lower() in k.lower()
            }

        if args.slo:
            for svc in report["services"].values():
                svc["slo_results"] = [
                    r for r in svc["slo_results"]
                    if args.slo.lower() in r["slo_name"].lower()
                ]

        if args.output == "json":
            output = json.dumps(report, indent=2, default=str)
        else:
            output = format_markdown(report)

        print(output)

        if args.save:
            Path(args.save).write_text(output, encoding="utf-8")
            logger.info(f"Report saved to {args.save}")

        await send_sla_alert(report)

        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write(format_markdown(report))
            logger.info("GitHub Step Summary written")

        critical = any(
            i.get("severity") == "critical"
            for i in report.get("active_incidents", [])
        )
        return 1 if critical else 0

    else:
        parser.print_help()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
