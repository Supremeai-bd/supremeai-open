"""
SupremeAI — Layer 5: Data & Analytics — DataTrendAnomalyAgent
=========================================================

Auto-generates natural language reports, trends, and anomaly detection
from Firestore data. Zero-cost design: uses on-device aggregation,
caching, and free-tier LLM routing.

Key Components:
- `InsightMage`: Core analytics engine with trend/anomaly/report generation.
- `TrendDetector`: Statistical trend analysis using pure Python (no pandas).
- `AnomalyDetector`: Z-score / IQR based outlier detection.
- `ReportFormatter`: Natural language report generation via LLM.

Dependencies:
- `core.config`: For settings, API keys, and environment config.
- `database.tenant_db`: For tenant-aware Firestore access.
- `core.cache`: For caching computed analytics.
- `core.llm_router`: For zero-cost LLM routing (Kimi Primary → DeepSeek Fallback).
"""

# বাংলা মন্তব্য: ইনসাইট-মেজ — মেমোরি ক্যাশ এবং Z-স্কোর অ্যালগরিদম ব্যবহার করে অসঙ্গতি ও ট্রেন্ড ডিটেকশন রিপোর্ট তৈরি করে।

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.logging_config import logger
from database.tenant_db import TenantAwareFirestore

T = TypeVar("T", bound="DataTrendAnomalyAgent")


# ── Constants ───────────────────────────────────────────────────────────────
DEFAULT_WINDOW_DAYS = 30
MAX_CACHE_TTL_SECONDS = 300  # 5 minutes for analytics cache
ANOMALY_Z_THRESHOLD = 2.5
TREND_MIN_POINTS = 7


@dataclass(frozen=True)
class TrendResult:
    """Immutable trend analysis result."""

    direction: str  # "up", "down", "flat", "volatile"
    slope: float
    confidence: float  # 0.0 - 1.0
    change_percent: float
    data_points: int


@dataclass(frozen=True)
class AnomalyResult:
    """Immutable anomaly detection result."""

    is_anomaly: bool
    severity: str  # "low", "medium", "high", "critical"
    z_score: float
    expected_value: float
    deviation_percent: float


@dataclass(frozen=True)
class ReportResult:
    """Immutable report generation result."""

    title: str
    summary: str
    sections: list[dict[str, Any]]
    generated_at: datetime
    cache_hit: bool


class TrendDetector:
    """
    Pure-Python statistical trend detection.

    Uses simple linear regression (least squares) — no external dependencies.
    """

    def __init__(self, min_points: int = TREND_MIN_POINTS) -> None:
        self.min_points = min_points

    def analyze(self, values: list[float], timestamps: list[datetime] | None = None) -> TrendResult:
        """
        Detect trend direction and confidence from a time series.

        Args:
            values: Numeric values to analyze.
            timestamps: Optional datetime sequence. If None, uses index-based x.

        Returns:
            TrendResult with direction, slope, confidence, and change percent.
        """
        n = len(values)
        if n < self.min_points:
            return TrendResult(
                direction="insufficient_data",
                slope=0.0,
                confidence=0.0,
                change_percent=0.0,
                data_points=n,
            )

        # Use index-based x if no timestamps provided
        x: list[float]
        if timestamps is None:
            x = [float(i) for i in range(n)]
        else:
            # Convert to hours since first point for slope interpretability
            base = timestamps[0]
            x = [(t - base).total_seconds() / 3600 for t in timestamps]

        # Simple linear regression: y = mx + b
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        # R-squared for confidence
        ss_res = sum(
            (values[i] - (slope * x[i] + (y_mean - slope * x_mean))) ** 2 for i in range(n)
        )
        ss_tot = sum((v - y_mean) ** 2 for v in values)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Direction classification
        if abs(slope) < 0.001 * y_mean if y_mean != 0 else 0.001:
            direction = "flat"
        elif slope > 0:
            direction = "up"
        else:
            direction = "down"

        # Volatility check: high variance relative to mean
        if n > 10 and r_squared < 0.3:
            direction = "volatile"

        # Change percent from first to last
        if values[0] != 0:
            change_percent = ((values[-1] - values[0]) / abs(values[0])) * 100
        else:
            change_percent = (
                0.0 if values[-1] == 0 else float("inf") if values[-1] > 0 else float("-inf")
            )

        return TrendResult(
            direction=direction,
            slope=slope,
            confidence=min(r_squared, 1.0),
            change_percent=change_percent,
            data_points=n,
        )


class AnomalyDetector:
    """
    Z-score and IQR-based anomaly detection — zero external dependencies.
    """

    def __init__(self, z_threshold: float = ANOMALY_Z_THRESHOLD) -> None:
        self.z_threshold = z_threshold

    def detect(self, value: float, historical: list[float]) -> AnomalyResult:
        """
        Detect if a value is anomalous against historical data.

        Args:
            value: The value to check.
            historical: Past values for baseline statistics.

        Returns:
            AnomalyResult with severity and statistics.
        """
        if len(historical) < 3:
            return AnomalyResult(
                is_anomaly=False,
                severity="low",
                z_score=0.0,
                expected_value=value,
                deviation_percent=0.0,
            )

        mean = sum(historical) / len(historical)
        variance = sum((h - mean) ** 2 for h in historical) / len(historical)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0

        if std_dev == 0:
            z_score = 0.0 if value == mean else float("inf")
        else:
            z_score = (value - mean) / std_dev

        # IQR-based secondary check
        sorted_hist = sorted(historical)
        q1_idx = len(sorted_hist) // 4
        q3_idx = (3 * len(sorted_hist)) // 4
        q1 = sorted_hist[q1_idx]
        q3 = sorted_hist[q3_idx]
        iqr = q3 - q1
        iqr_lower = q1 - 1.5 * iqr
        iqr_upper = q3 + 1.5 * iqr

        is_anomaly = abs(z_score) > self.z_threshold or value < iqr_lower or value > iqr_upper

        # Severity classification
        if abs(z_score) > 4.0 or (iqr > 0 and (value < q1 - 3 * iqr or value > q3 + 3 * iqr)):
            severity = "critical"
        elif abs(z_score) > 3.0:
            severity = "high"
        elif abs(z_score) > 2.0:
            severity = "medium"
        else:
            severity = "low"

        if mean != 0:
            deviation_percent = ((value - mean) / abs(mean)) * 100
        else:
            deviation_percent = 0.0 if value == 0 else float("inf")

        return AnomalyResult(
            is_anomaly=is_anomaly,
            severity=severity,
            z_score=z_score,
            expected_value=mean,
            deviation_percent=deviation_percent,
        )


class ReportFormatter:
    """
    Natural language report formatter using zero-cost LLM routing.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm_router = llm_router or ModelRouter()
        self._prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Load the report generation prompt template."""
        return """\
You are InsightMage, the Analytics AI of SupremeAI. Generate a clear, actionable business report in Bengali-English mixed tone (Banglish).

DATA CONTEXT:
{data_context}

TRENDS:
{trends}

ANOMALIES:
{anomalies}

INSTRUCTIONS:
1. Write a compelling executive summary (2-3 sentences).
2. List 3-5 key insights with bullet points.
3. Provide 2-3 actionable recommendations.
4. Include a "Risk Alert" section if anomalies detected.
5. Format as clean Markdown. No code blocks.

Keep it concise, business-friendly, and data-driven.
"""

    async def generate(
        self,
        data_context: dict[str, Any],
        trends: list[TrendResult],
        anomalies: list[AnomalyResult],
        title: str = "Analytics Report",
    ) -> str:
        """
        Generate a natural language report via LLM.

        Args:
            data_context: Raw data context dictionary.
            trends: List of trend results.
            anomalies: List of anomaly results.
            title: Report title.

        Returns:
            Markdown-formatted report string.
        """
        trends_text = (
            "\n".join(
                f"- {t.direction.upper()}: {t.change_percent:.1f}% change "
                f"(confidence: {t.confidence:.0%}, n={t.data_points})"
                for t in trends
            )
            if trends
            else "No significant trends detected."
        )

        anomalies_text = (
            "\n".join(
                f"- 🚨 {a.severity.upper()}: z={a.z_score:.2f}, "
                f"deviation={a.deviation_percent:.1f}% from expected"
                for a in anomalies
                if a.is_anomaly
            )
            if any(a.is_anomaly for a in anomalies)
            else "No anomalies detected."
        )

        prompt = self._prompt_template.format(
            data_context=json.dumps(data_context, indent=2, default=str),
            trends=trends_text,
            anomalies=anomalies_text,
        )

        # Zero-cost routing: Kimi Primary → DeepSeek Fallback → Local
        response = await self.llm_router.async_route_and_generate(
            prompt=prompt,
            task_type="analytics_report",
            max_tokens=config_cache.get("insight_mage_max_tokens", 2000),
            temperature=config_cache.get("insight_mage_temperature", 0.3),
        )

        return response.get("text", "Report generation failed. Please retry.")


class DataTrendAnomalyAgent:
    """
    Layer 5 Analytics AI — Auto-generates reports, trends, and anomalies
    from Firestore data with zero-cost, scalable architecture.
    """

    def __init__(
        self,
        db: TenantAwareFirestore | None = None,
        cache_ttl: int = MAX_CACHE_TTL_SECONDS,
    ) -> None:
        self.db = db
        self.cache = get_cache()
        self.cache_ttl = cache_ttl
        self.trend_detector = TrendDetector()
        self.anomaly_detector = AnomalyDetector()
        self.report_formatter = ReportFormatter()

    def _cache_key(self, tenant_id: str, collection: str, query_hash: str) -> str:
        """Generate deterministic cache key for analytics queries."""
        raw = f"{tenant_id}:{collection}:{query_hash}:{datetime.now(UTC).strftime('%Y%m%d%H')}"
        return f"insight_mage:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    async def _fetch_time_series(
        self,
        tenant_id: str,
        collection: str,
        value_field: str,
        timestamp_field: str = "created_at",
        days: int = DEFAULT_WINDOW_DAYS,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[float], list[datetime]]:
        """
        Fetch time-series data from Firestore with tenant isolation.

        Args:
            tenant_id: Tenant identifier for data isolation.
            collection: Firestore collection name.
            value_field: Field containing numeric values.
            timestamp_field: Field containing timestamps.
            days: Lookback window in days.
            filters: Additional Firestore query filters.

        Returns:
            Tuple of (values list, timestamps list).
        """
        if self.db is None:
            logger.warning("No database configured; returning empty series.")
            return [], []

        try:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            query = self.db.collection(collection).where(timestamp_field, ">=", cutoff)

            # Apply additional filters
            if filters:
                for field, cond in filters.items():
                    if isinstance(cond, tuple) and len(cond) == 2:
                        op, value = cond
                        query = query.where(field, op, value)
                    else:
                        query = query.where(field, "==", cond)

            # Tenant isolation
            query = query.where("_tenant_id", "==", tenant_id)

            docs = query.stream()
            values: list[float] = []
            timestamps: list[datetime] = []

            async for doc in docs:
                data = doc.to_dict()
                val = data.get(value_field)
                ts = data.get(timestamp_field)

                if val is not None and ts is not None:
                    try:
                        values.append(float(val))
                        if isinstance(ts, datetime):
                            timestamps.append(ts)
                        elif isinstance(ts, str):
                            timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                    except (ValueError, TypeError):
                        continue

            # Sort by timestamp
            paired = sorted(zip(timestamps, values, strict=False), key=lambda x: x[0])
            if paired:
                sorted_ts = [p[0] for p in paired]
                sorted_vals = [p[1] for p in paired]
                return sorted_vals, sorted_ts

            return [], []

        except Exception as e:
            logger.error(f"Failed to fetch time series: {e}")
            return [], []

    async def analyze_trends(
        self,
        tenant_id: str,
        collection: str,
        value_field: str,
        days: int = DEFAULT_WINDOW_DAYS,
        filters: dict[str, Any] | None = None,
    ) -> TrendResult:
        """
        Analyze trends for a specific metric.

        Args:
            tenant_id: Tenant identifier.
            collection: Firestore collection.
            value_field: Numeric field to analyze.
            days: Analysis window.
            filters: Optional query filters.

        Returns:
            TrendResult with direction and confidence.
        """
        cache_key = self._cache_key(
            tenant_id,
            f"{collection}:{value_field}:trend",
            hashlib.sha256(json.dumps(filters or {}, sort_keys=True).encode()).hexdigest()[:8],
        )

        # Check cache
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug("Trend cache hit for %s:%s", tenant_id, collection)
            return TrendResult(**cached)

        values, timestamps = await self._fetch_time_series(
            tenant_id,
            collection,
            value_field,
            days=days,
            filters=filters,
        )

        result = self.trend_detector.analyze(values, timestamps)

        # Cache result
        await self.cache.set(
            cache_key,
            {
                "direction": result.direction,
                "slope": result.slope,
                "confidence": result.confidence,
                "change_percent": result.change_percent,
                "data_points": result.data_points,
            },
            ttl=self.cache_ttl,
        )

        return result

    async def detect_anomalies(
        self,
        tenant_id: str,
        collection: str,
        value_field: str,
        current_value: float | None = None,
        days: int = DEFAULT_WINDOW_DAYS,
        filters: dict[str, Any] | None = None,
    ) -> list[AnomalyResult]:
        """
        Detect anomalies in recent data.

        Args:
            tenant_id: Tenant identifier.
            collection: Firestore collection.
            value_field: Numeric field to analyze.
            current_value: Optional explicit value to check. If None, checks last value.
            days: Historical window.
            filters: Optional query filters.

        Returns:
            List of AnomalyResult objects.
        """
        values, _ = await self._fetch_time_series(
            tenant_id,
            collection,
            value_field,
            days=days,
            filters=filters,
        )

        if not values:
            return []

        results: list[AnomalyResult] = []

        if current_value is not None:
            # Check explicit value against history
            results.append(self.anomaly_detector.detect(current_value, values))
        else:
            # Check last N values against preceding history
            check_window = min(5, len(values) // 5) if len(values) >= 10 else 1
            for i in range(check_window):
                idx = len(values) - check_window + i
                if idx > 0:
                    historical = values[:idx]
                    results.append(self.anomaly_detector.detect(values[idx], historical))

        return results

    async def generate_report(
        self,
        tenant_id: str,
        collection: str,
        value_field: str,
        report_title: str = "Auto-Generated Analytics Report",
        days: int = DEFAULT_WINDOW_DAYS,
        filters: dict[str, Any] | None = None,
        force_refresh: bool = False,
    ) -> ReportResult:
        """
        Generate a complete natural language analytics report.

        Args:
            tenant_id: Tenant identifier.
            collection: Firestore collection.
            value_field: Primary metric field.
            report_title: Custom report title.
            days: Analysis window.
            filters: Optional query filters.
            force_refresh: Bypass cache if True.

        Returns:
            ReportResult with title, summary, sections, and metadata.
        """
        query_hash = hashlib.sha256(
            json.dumps(
                {
                    "collection": collection,
                    "value_field": value_field,
                    "days": days,
                    "filters": filters or {},
                },
                sort_keys=True,
            ).encode(),
        ).hexdigest()[:12]

        cache_key = self._cache_key(tenant_id, "report", query_hash)

        if not force_refresh:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info("Report cache hit for %s", tenant_id)
                return ReportResult(
                    title=cached.get("title", report_title),
                    summary=cached.get("summary", ""),
                    sections=cached.get("sections", []),
                    generated_at=datetime.fromisoformat(cached.get("generated_at", "")),
                    cache_hit=True,
                )

        # Gather data
        values, timestamps = await self._fetch_time_series(
            tenant_id,
            collection,
            value_field,
            days=days,
            filters=filters,
        )

        # Run analysis
        trend = self.trend_detector.analyze(values, timestamps)
        anomalies = []
        if len(values) > 3:
            anomalies = [
                self.anomaly_detector.detect(values[-1], values[:-1]),
            ]

        # Build data context
        data_context = {
            "collection": collection,
            "value_field": value_field,
            "period_days": days,
            "total_records": len(values),
            "latest_value": values[-1] if values else None,
            "avg_value": sum(values) / len(values) if values else 0,
            "max_value": max(values) if values else 0,
            "min_value": min(values) if values else 0,
        }

        # Generate natural language report
        report_md = await self.report_formatter.generate(
            data_context=data_context,
            trends=[trend],
            anomalies=anomalies,
            title=report_title,
        )

        # Parse sections from markdown
        sections = self._parse_markdown_sections(report_md)

        result = ReportResult(
            title=report_title,
            summary=report_md.split("\n")[0] if report_md else "",
            sections=sections,
            generated_at=datetime.now(UTC),
            cache_hit=False,
        )

        # Cache the full report
        await self.cache.set(
            cache_key,
            {
                "title": result.title,
                "summary": result.summary,
                "sections": result.sections,
                "generated_at": result.generated_at.isoformat(),
                "report_md": report_md,
            },
            ttl=self.cache_ttl,
        )

        return result

    def _parse_markdown_sections(self, markdown: str) -> list[dict[str, Any]]:
        """Parse markdown into structured sections."""
        sections: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        for line in markdown.split("\n"):
            line = line.strip()
            if line.startswith("## "):
                if current:
                    sections.append(current)
                current = {"title": line[3:], "content": []}
            elif line.startswith("### "):
                if current:
                    sections.append(current)
                current = {"title": line[4:], "content": []}
            elif current and line:
                current["content"].append(line)

        if current:
            sections.append(current)

        return sections

    async def get_cached_report(
        self,
        tenant_id: str,
        collection: str,
        value_field: str,
        days: int = DEFAULT_WINDOW_DAYS,
    ) -> ReportResult | None:
        """Retrieve a cached report without regeneration."""
        query_hash = hashlib.sha256(
            json.dumps(
                {
                    "collection": collection,
                    "value_field": value_field,
                    "days": days,
                },
                sort_keys=True,
            ).encode(),
        ).hexdigest()[:12]

        cache_key = self._cache_key(tenant_id, "report", query_hash)
        cached = await self.cache.get(cache_key)

        if cached:
            return ReportResult(
                title=cached.get("title", ""),
                summary=cached.get("summary", ""),
                sections=cached.get("sections", []),
                generated_at=datetime.fromisoformat(cached.get("generated_at", "")),
                cache_hit=True,
            )

        return None


# ── Singleton Instance ──────────────────────────────────────────────────────
_insight_mage_instance: InsightMage | None = None


def get_insight_mage(db: TenantAwareFirestore | None = None) -> InsightMage:
    """Get or create the singleton InsightMage instance."""
    global _insight_mage_instance
    if _insight_mage_instance is None:
        _insight_mage_instance = InsightMage(db=db)
    return _insight_mage_instance


# Canonical alias for backward compatibility
InsightMage = DataTrendAnomalyAgent

# ── Singleton Instance ──────────────────────────────────────────────────────
_agent_instance: DataTrendAnomalyAgent | None = None


def get_data_trend_anomaly_agent(db: TenantAwareFirestore | None = None) -> DataTrendAnomalyAgent:
    """Get or create the singleton DataTrendAnomalyAgent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = DataTrendAnomalyAgent(db=db)
    return _agent_instance


get_insight_mage = get_data_trend_anomaly_agent
