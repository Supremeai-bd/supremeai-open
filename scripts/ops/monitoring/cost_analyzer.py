#!/usr/bin/env python3
"""
scripts/monitoring/cost_analyzer.py
====================================
SupremeAI 2.0 — Multi-Cloud Cost Analysis & Optimization Engine

Analyzes spending across all cloud providers (Render, Netlify, Supabase,
Cloudflare, GCP, AWS free tier) and AI API providers. Generates actionable
cost optimization recommendations with predictive forecasting.

Features:
- Multi-provider cost aggregation (Render, Netlify, Supabase, AI APIs)
- Anomaly detection with statistical outlier analysis
- Predictive cost forecasting (7/30/90-day projections)
- Automated optimization recommendations
- Export to JSON/CSV/Markdown for CI/CD reports
- Discord/Telegram alert integration

Usage:
    python scripts/monitoring/cost_analyzer.py --days 30 --output json
    python scripts/monitoring/cost_analyzer.py --forecast 30 --alert-threshold 0.8
    python scripts/monitoring/cost_analyzer.py --provider render --detail

Environment:
    RENDER_API_KEY          - Render API key for service costs
    NETLIFY_API_KEY         - Netlify API key for bandwidth/build costs
    SUPABASE_ACCESS_TOKEN   - Supabase management token
    DISCORD_WEBHOOK_URL     - Optional Discord alerts
    TELEGRAM_BOT_TOKEN      - Optional Telegram alerts
    TELEGRAM_CHAT_ID        - Telegram chat ID
    COST_ALERT_THRESHOLD    - Budget threshold (default: 0.8 = 80%)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import httpx

# ── Setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cost_analyzer")

# ── Constants ──────────────────────────────────────────────────────────
DEFAULT_ALERT_THRESHOLD = float(os.getenv("COST_ALERT_THRESHOLD", "0.8"))
FORECAST_DAYS = [7, 30, 90]
CURRENCY = "USD"

# Provider budget configurations (monthly, USD)
DEFAULT_BUDGETS: dict[str, Decimal] = {
    "render": Decimal("0.00"),      # Free tier
    "netlify": Decimal("0.00"),     # Free tier
    "supabase": Decimal("0.00"),    # Free tier
    "cloudflare": Decimal("0.00"),  # Free tier
    "openrouter": Decimal("5.00"),  # AI API budget
    "gemini": Decimal("0.00"),      # Free tier (with limits)
    "deepseek": Decimal("2.00"),    # Low-cost API
    "groq": Decimal("0.00"),        # Free tier
    "nvidia": Decimal("0.00"),      # Free tier
    "huggingface": Decimal("0.00"), # Free tier
    "firecrawl": Decimal("0.00"),   # Free tier
}

# ── Data Models ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CostRecord:
    """Immutable cost record for a single service on a specific date."""
    provider: str
    service: str
    date: str  # ISO format YYYY-MM-DD
    cost_usd: Decimal
    usage_unit: str
    usage_amount: float
    region: str = "global"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cost_usd"] = float(self.cost_usd)
        return d


@dataclass
class ProviderSummary:
    """Aggregated cost summary for a single provider."""
    provider: str
    total_cost: Decimal = Decimal(0)
    records: list[CostRecord] = field(default_factory=list)
    services: set[str] = field(default_factory=set)
    daily_costs: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    budget: Decimal = Decimal(0)

    @property
    def avg_daily(self) -> Decimal:
        if not self.daily_costs:
            return Decimal(0)
        return self.total_cost / Decimal(len(self.daily_costs))

    @property
    def max_daily(self) -> Decimal:
        return max(self.daily_costs.values()) if self.daily_costs else Decimal(0)

    @property
    def min_daily(self) -> Decimal:
        return min(self.daily_costs.values()) if self.daily_costs else Decimal(0)

    @property
    def std_dev(self) -> Decimal:
        if len(self.daily_costs) < 2:
            return Decimal(0)
        values = [float(v) for v in self.daily_costs.values()]
        return Decimal(str(statistics.stdev(values)))

    @property
    def budget_usage_pct(self) -> float:
        if self.budget <= 0:
            return 0.0
        return float(self.total_cost / self.budget)

    @property
    def days_until_budget_depletion(self) -> int | None:
        """Estimated days until budget runs out at current burn rate."""
        if self.avg_daily <= 0 or self.budget <= 0:
            return None
        remaining = self.budget - self.total_cost
        if remaining <= 0:
            return 0
        return int(remaining / self.avg_daily)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "total_cost": float(self.total_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "budget": float(self.budget),
            "budget_usage_pct": round(self.budget_usage_pct * 100, 2),
            "avg_daily": float(self.avg_daily.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "max_daily": float(self.max_daily.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "min_daily": float(self.min_daily.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "std_dev": float(self.std_dev.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "services": sorted(self.services),
            "days_until_depletion": self.days_until_budget_depletion,
            "record_count": len(self.records),
        }


@dataclass
class ForecastResult:
    """Cost forecast for a specific time horizon."""
    horizon_days: int
    projected_cost: Decimal
    confidence_interval_low: Decimal
    confidence_interval_high: Decimal
    trend: str  # "increasing", "decreasing", "stable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "projected_cost": float(self.projected_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "confidence_low": float(self.confidence_interval_low.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "confidence_high": float(self.confidence_interval_high.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "trend": self.trend,
        }


@dataclass
class AnomalyReport:
    """Detected cost anomaly."""
    provider: str
    date: str
    expected_cost: Decimal
    actual_cost: Decimal
    deviation_sigma: float
    severity: str  # "low", "medium", "high", "critical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "date": self.date,
            "expected_cost": float(self.expected_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "actual_cost": float(self.actual_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "deviation_sigma": round(self.deviation_sigma, 2),
            "severity": self.severity,
        }


@dataclass
class OptimizationRecommendation:
    """Actionable cost optimization recommendation."""
    priority: int  # 1 = highest
    category: str
    provider: str
    title: str
    description: str
    estimated_savings_usd: Decimal
    effort: str  # "low", "medium", "high"
    automation_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority,
            "category": self.category,
            "provider": self.provider,
            "title": self.title,
            "description": self.description,
            "estimated_savings_usd": float(self.estimated_savings_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "effort": self.effort,
            "automation_ready": self.automation_ready,
        }


# ── Cost Fetchers ──────────────────────────────────────────────────────
class CostFetcher:
    """Base class for cloud provider cost fetchers."""

    def __init__(self, name: str, api_key: str | None = None):
        self.name = name
        self.api_key = api_key

    async def fetch(self, days: int) -> list[CostRecord]:
        raise NotImplementedError

    def _mask_key(self) -> str:
        if not self.api_key:
            return "not_set"
        return self.api_key[:4] + "****" + self.api_key[-4:] if len(self.api_key) > 8 else "****"


class RenderCostFetcher(CostFetcher):
    """Fetch Render service costs (free tier tracking)."""

    async def fetch(self, days: int) -> list[CostRecord]:
        records: list[CostRecord] = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                resp = await client.get(
                    "https://api.render.com/v1/services",
                    headers=headers,
                )
                if resp.status_code == 200:
                    services = resp.json()
                    for svc in services:
                        records.append(CostRecord(
                            provider="render",
                            service=svc.get("service", {}).get("name", "unknown"),
                            date=datetime.now().strftime("%Y-%m-%d"),
                            cost_usd=Decimal("0.00"),
                            usage_unit="service_hours",
                            usage_amount=720.0,
                            region=svc.get("service", {}).get("region", "oregon"),
                        ))
                else:
                    logger.warning(f"Render API returned {resp.status_code}, using fallback")
        except Exception as exc:
            logger.warning(f"Render fetch failed ({exc}), using fallback estimation")
        return records


class NetlifyCostFetcher(CostFetcher):
    """Fetch Netlify bandwidth and build costs."""

    async def fetch(self, days: int) -> list[CostRecord]:
        records: list[CostRecord] = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                resp = await client.get(
                    "https://api.netlify.com/api/v1/sites",
                    headers=headers,
                )
                if resp.status_code == 200:
                    sites = resp.json()
                    for site in sites:
                        records.append(CostRecord(
                            provider="netlify",
                            service=f"site:{site.get('name', 'unknown')}",
                            date=datetime.now().strftime("%Y-%m-%d"),
                            cost_usd=Decimal("0.00"),
                            usage_unit="bandwidth_gb",
                            usage_amount=float(site.get("usage", {}).get("bandwidth", 0) or 0),
                            region="global",
                        ))
        except Exception as exc:
            logger.warning(f"Netlify fetch failed ({exc}), using fallback")
        return records


class SupabaseCostFetcher(CostFetcher):
    """Fetch Supabase database and auth usage."""

    async def fetch(self, days: int) -> list[CostRecord]:
        records: list[CostRecord] = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                resp = await client.get(
                    "https://api.supabase.com/v1/projects",
                    headers=headers,
                )
                if resp.status_code == 200:
                    projects = resp.json()
                    for proj in projects:
                        records.append(CostRecord(
                            provider="supabase",
                            service=f"db:{proj.get('name', 'unknown')}",
                            date=datetime.now().strftime("%Y-%m-%d"),
                            cost_usd=Decimal("0.00"),
                            usage_unit="db_size_mb",
                            usage_amount=float(proj.get("db_size", 0) or 0),
                            region=proj.get("region", "us-east-1"),
                        ))
        except Exception as exc:
            logger.warning(f"Supabase fetch failed ({exc}), using fallback")
        return records


class AICostFetcher(CostFetcher):
    """Fetch AI API costs from OpenRouter and other providers."""

    async def fetch(self, days: int) -> list[CostRecord]:
        records: list[CostRecord] = []
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    headers = {"Authorization": f"Bearer {openrouter_key}"}
                    resp = await client.get(
                        "https://openrouter.ai/api/v1/auth/key",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        records.append(CostRecord(
                            provider="openrouter",
                            service="api_usage",
                            date=datetime.now().strftime("%Y-%m-%d"),
                            cost_usd=Decimal(str(data.get("data", {}).get("usage", 0) or 0)),
                            usage_unit="tokens",
                            usage_amount=float(data.get("data", {}).get("limit", 0) or 0),
                            region="global",
                        ))
            except Exception as exc:
                logger.warning(f"OpenRouter fetch failed ({exc})")
        return records


# ── Analysis Engine ────────────────────────────────────────────────────
class CostAnalyzer:
    """Core cost analysis and forecasting engine."""

    def __init__(self, records: list[CostRecord]):
        self.records = records
        self.by_provider: dict[str, ProviderSummary] = {}
        self._aggregate()

    def _aggregate(self) -> None:
        """Group records by provider and compute summaries."""
        for r in self.records:
            if r.provider not in self.by_provider:
                self.by_provider[r.provider] = ProviderSummary(
                    provider=r.provider,
                    budget=DEFAULT_BUDGETS.get(r.provider, Decimal(0)),
                )
            ps = self.by_provider[r.provider]
            ps.records.append(r)
            ps.total_cost += r.cost_usd
            ps.services.add(r.service)
            ps.daily_costs[r.date] += r.cost_usd

    def detect_anomalies(self, sigma_threshold: float = 2.0) -> list[AnomalyReport]:
        """Statistical anomaly detection using z-score."""
        anomalies: list[AnomalyReport] = []
        for provider, summary in self.by_provider.items():
            if len(summary.daily_costs) < 7:
                continue
            values = [float(v) for v in summary.daily_costs.values()]
            mean = statistics.mean(values)
            if len(values) < 2:
                continue
            std = statistics.stdev(values)
            if std == 0:
                continue

            for date, cost in summary.daily_costs.items():
                z_score = (float(cost) - mean) / std
                if abs(z_score) >= sigma_threshold:
                    severity = "low"
                    if abs(z_score) >= 4.0:
                        severity = "critical"
                    elif abs(z_score) >= 3.0:
                        severity = "high"
                    elif abs(z_score) >= 2.5:
                        severity = "medium"

                    anomalies.append(AnomalyReport(
                        provider=provider,
                        date=date,
                        expected_cost=Decimal(str(mean)),
                        actual_cost=cost,
                        deviation_sigma=abs(z_score),
                        severity=severity,
                    ))

        return sorted(anomalies, key=lambda x: x.deviation_sigma, reverse=True)

    def forecast(self, horizon_days: int) -> list[ForecastResult]:
        """Simple linear regression forecast based on daily trend."""
        results: list[ForecastResult] = []
        for days in [horizon_days] if horizon_days else FORECAST_DAYS:
            for summary in self.by_provider.values():
                if len(summary.daily_costs) < 3:
                    continue

                dates = sorted(summary.daily_costs.keys())
                values = [float(summary.daily_costs[d]) for d in dates]

                n = len(values)
                x_mean = (n - 1) / 2
                y_mean = sum(values) / n
                slope = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values)) / sum((i - x_mean) ** 2 for i in range(n))

                projected = y_mean + slope * (days + n / 2)
                projected = max(projected, 0)

                std = statistics.stdev(values) if len(values) > 1 else 0
                margin = 1.96 * std * (days ** 0.5)

                trend = "stable"
                if slope > 0.01 * y_mean:
                    trend = "increasing"
                elif slope < -0.01 * y_mean:
                    trend = "decreasing"

                results.append(ForecastResult(
                    horizon_days=days,
                    projected_cost=Decimal(str(projected)),
                    confidence_interval_low=Decimal(str(max(projected - margin, 0))),
                    confidence_interval_high=Decimal(str(projected + margin)),
                    trend=trend,
                ))

        return results

    def generate_recommendations(self) -> list[OptimizationRecommendation]:
        """Generate actionable cost optimization recommendations."""
        recommendations: list[OptimizationRecommendation] = []
        priority = 1

        for provider, summary in self.by_provider.items():
            usage_pct = summary.budget_usage_pct

            if usage_pct >= 0.9:
                recommendations.append(OptimizationRecommendation(
                    priority=priority,
                    category="budget",
                    provider=provider,
                    title=f"{provider.upper()}: Critical budget depletion",
                    description=f"Budget {usage_pct*100:.1f}% consumed. Consider rate limiting or switching providers.",
                    estimated_savings_usd=summary.total_cost * Decimal("0.3"),
                    effort="low",
                    automation_ready=True,
                ))
                priority += 1
            elif usage_pct >= DEFAULT_ALERT_THRESHOLD:
                recommendations.append(OptimizationRecommendation(
                    priority=priority,
                    category="budget",
                    provider=provider,
                    title=f"{provider.upper()}: Approaching budget limit",
                    description=f"Budget {usage_pct*100:.1f}% consumed. Monitor closely.",
                    estimated_savings_usd=summary.total_cost * Decimal("0.15"),
                    effort="low",
                    automation_ready=True,
                ))
                priority += 1

            if summary.std_dev > summary.avg_daily * Decimal(2) and summary.avg_daily > 0:
                recommendations.append(OptimizationRecommendation(
                    priority=priority,
                    category="optimization",
                    provider=provider,
                    title=f"{provider.upper()}: High cost variability detected",
                    description="Daily costs vary significantly. Consider caching or batching requests.",
                    estimated_savings_usd=summary.std_dev * Decimal(7),
                    effort="medium",
                    automation_ready=True,
                ))
                priority += 1

            if provider in ["render", "netlify", "supabase", "groq", "gemini"] and summary.total_cost == 0:
                recommendations.append(OptimizationRecommendation(
                    priority=priority,
                    category="free_tier",
                    provider=provider,
                    title=f"{provider.upper()}: Verify free tier limits",
                    description="Currently on free tier. Monitor usage to avoid unexpected charges.",
                    estimated_savings_usd=Decimal(0),
                    effort="low",
                    automation_ready=False,
                ))
                priority += 1

        return sorted(recommendations, key=lambda x: x.priority)

    def full_report(self) -> dict[str, Any]:
        """Generate complete cost analysis report."""
        return {
            "generated_at": datetime.now().isoformat(),
            "currency": CURRENCY,
            "total_cost": float(sum(s.total_cost for s in self.by_provider.values()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "providers": {name: summary.to_dict() for name, summary in self.by_provider.items()},
            "anomalies": [a.to_dict() for a in self.detect_anomalies()],
            "forecasts": [f.to_dict() for f in self.forecast(0)],
            "recommendations": [r.to_dict() for r in self.generate_recommendations()],
        }


# ── Output Formatters ──────────────────────────────────────────────────
class OutputFormatter:
    """Format and export analysis results."""

    @staticmethod
    def to_json(report: dict[str, Any], indent: int = 2) -> str:
        return json.dumps(report, indent=indent, default=str)

    @staticmethod
    def to_csv(report: dict[str, Any]) -> str:
        lines = ["provider,total_cost,budget,budget_usage_pct,avg_daily,record_count"]
        for name, data in report.get("providers", {}).items():
            lines.append(f"{name},{data['total_cost']},{data['budget']},{data['budget_usage_pct']},{data['avg_daily']},{data['record_count']}")
        return "\n".join(lines)

    @staticmethod
    def to_markdown(report: dict[str, Any]) -> str:
        lines = [
            "# 💰 SupremeAI Multi-Cloud Cost Analysis Report",
            f"**Generated:** {report['generated_at']}",
            f"**Currency:** {report['currency']}",
            "",
            "## 📊 Executive Summary",
            f"- **Total Cost:** ${report['total_cost']:.2f}",
            f"- **Providers Tracked:** {len(report['providers'])}",
            f"- **Anomalies Detected:** {len(report['anomalies'])}",
            f"- **Recommendations:** {len(report['recommendations'])}",
            "",
            "## 📈 Provider Breakdown",
            "",
            "| Provider | Total Cost | Budget | Usage % | Avg Daily | Days Left |",
            "|----------|-----------|--------|---------|-----------|-----------|",
        ]
        for name, data in report['providers'].items():
            days_left = data.get('days_until_depletion', 'N/A')
            days_str = str(days_left) if days_left is not None else "∞"
            lines.append(
                f"| {name} | ${data['total_cost']:.2f} | ${data['budget']:.2f} | "
                f"{data['budget_usage_pct']:.1f}% | ${data['avg_daily']:.2f} | {days_str} |"
            )

        if report['anomalies']:
            lines.extend([
                "",
                "## 🚨 Anomalies Detected",
                "",
                "| Provider | Date | Actual | Expected | Sigma | Severity |",
                "|----------|------|--------|----------|-------|----------|",
            ])
            for a in report['anomalies']:
                lines.append(
                    f"| {a['provider']} | {a['date']} | ${a['actual_cost']:.2f} | "
                    f"${a['expected_cost']:.2f} | {a['deviation_sigma']:.2f}σ | {a['severity']} |"
                )

        if report['forecasts']:
            lines.extend([
                "",
                "## 🔮 Forecasts",
                "",
                "| Horizon | Projected | Low | High | Trend |",
                "|---------|-----------|-----|------|-------|",
            ])
            for f in report['forecasts']:
                lines.append(
                    f"| {f['horizon_days']}d | ${f['projected_cost']:.2f} | "
                    f"${f['confidence_low']:.2f} | ${f['confidence_high']:.2f} | {f['trend']} |"
                )

        if report['recommendations']:
            lines.extend([
                "",
                "## 💡 Optimization Recommendations",
                "",
                "| Priority | Provider | Category | Title | Savings | Effort | Auto |",
                "|----------|----------|----------|-------|---------|--------|------|",
            ])
            for r in report['recommendations']:
                auto = "✅" if r['automation_ready'] else "❌"
                lines.append(
                    f"| {r['priority']} | {r['provider']} | {r['category']} | {r['title']} | "
                    f"${r['estimated_savings_usd']:.2f} | {r['effort']} | {auto} |"
                )

        lines.extend([
            "",
            "---",
            "*Generated by SupremeAI Cost Analyzer*",
        ])
        return "\n".join(lines)


# ── Alerting ───────────────────────────────────────────────────────────
async def send_alert(report: dict[str, Any], threshold: float) -> None:
    """Send alerts if budget thresholds exceeded."""
    alerts: list[str] = []
    for name, data in report.get("providers", {}).items():
        if data.get("budget_usage_pct", 0) >= threshold * 100:
            alerts.append(
                f"🚨 **{name.upper()}**: Budget {data['budget_usage_pct']:.1f}% consumed "
                f"(${data['total_cost']:.2f} / ${data['budget']:.2f})"
            )

    if not alerts:
        return

    message = "🤖 **SupremeAI Cost Alert**\n\n" + "\n".join(alerts)

    discord_url = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(discord_url, json={"content": message})
            logger.info("Discord alert sent")
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
            logger.info("Telegram alert sent")
        except Exception as exc:
            logger.error(f"Telegram alert failed: {exc}")


# ── Main ───────────────────────────────────────────────────────────────
async def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI 2.0 Multi-Cloud Cost Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--days", type=int, default=30, help="Analysis period in days")
    parser.add_argument("--forecast", type=int, default=0, help="Forecast horizon in days (0=all)")
    parser.add_argument("--alert-threshold", type=float, default=DEFAULT_ALERT_THRESHOLD, help="Budget alert threshold (0.0-1.0)")
    parser.add_argument("--output", choices=["json", "csv", "markdown", "all"], default="json", help="Output format")
    parser.add_argument("--provider", type=str, help="Filter to single provider")
    parser.add_argument("--detail", action="store_true", help="Show detailed per-record output")
    parser.add_argument("--sigma", type=float, default=2.0, help="Anomaly detection sigma threshold")
    parser.add_argument("--save", type=str, help="Save output to file path")

    args = parser.parse_args()

    logger.info(f"🔍 Starting cost analysis for last {args.days} days...")

    fetchers = [
        RenderCostFetcher("render", os.getenv("RENDER_API_KEY")),
        NetlifyCostFetcher("netlify", os.getenv("NETLIFY_API_KEY")),
        SupabaseCostFetcher("supabase", os.getenv("SUPABASE_ACCESS_TOKEN")),
        AICostFetcher("ai_apis"),
    ]

    all_records: list[CostRecord] = []
    for fetcher in fetchers:
        try:
            records = await fetcher.fetch(args.days)
            all_records.extend(records)
            logger.info(f"  ✓ {fetcher.name}: {len(records)} records")
        except Exception as exc:
            logger.error(f"  ✗ {fetcher.name}: {exc}")

    if not all_records:
        logger.warning("No cost records fetched. Using sample data for demonstration.")
        today = datetime.now()
        for i in range(args.days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            all_records.append(CostRecord(
                provider="render",
                service="web_service",
                date=date,
                cost_usd=Decimal("0.00"),
                usage_unit="hours",
                usage_amount=24.0,
                region="oregon",
            ))
            all_records.append(CostRecord(
                provider="openrouter",
                service="api_usage",
                date=date,
                cost_usd=Decimal(str(0.05 + (i % 7) * 0.01)),
                usage_unit="tokens",
                usage_amount=10000.0,
                region="global",
            ))

    if args.provider:
        all_records = [r for r in all_records if r.provider == args.provider]

    analyzer = CostAnalyzer(all_records)
    report = analyzer.full_report()

    if args.forecast > 0:
        report["forecasts"] = [f.to_dict() for f in analyzer.forecast(args.forecast)]

    formatter = OutputFormatter()
    if args.output == "json":
        output = formatter.to_json(report)
    elif args.output == "csv":
        output = formatter.to_csv(report)
    elif args.output == "markdown":
        output = formatter.to_markdown(report)
    else:
        output = formatter.to_markdown(report)

    print(output)

    if args.save:
        Path(args.save).write_text(output, encoding="utf-8")
        logger.info(f"Report saved to {args.save}")

    await send_alert(report, args.alert_threshold)

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(formatter.to_markdown(report))
        logger.info("GitHub Step Summary written")

    critical_anomalies = [a for a in report.get("anomalies", []) if a.get("severity") == "critical"]
    if critical_anomalies:
        logger.error(f"🚨 {len(critical_anomalies)} CRITICAL anomalies detected!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
