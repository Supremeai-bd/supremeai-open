"""
Backward compatibility bridge: re-export all from data_trend_anomaly_agent.
Preserves legacy imports for 'agents.insight_mage' and 'backend.agents.insight_mage'.
"""

from agents.data_trend_anomaly_agent import (  # noqa: F401
    ANOMALY_Z_THRESHOLD,
    DEFAULT_WINDOW_DAYS,
    MAX_CACHE_TTL_SECONDS,
    TREND_MIN_POINTS,
    AnomalyDetector,
    AnomalyResult,
    DataTrendAnomalyAgent,
    InsightMage,
    ReportFormatter,
    ReportResult,
    TrendDetector,
    TrendResult,
    get_data_trend_anomaly_agent,
    get_insight_mage,
)

__all__ = [
    "ANOMALY_Z_THRESHOLD",
    "DEFAULT_WINDOW_DAYS",
    "MAX_CACHE_TTL_SECONDS",
    "TREND_MIN_POINTS",
    "AnomalyDetector",
    "AnomalyResult",
    "DataTrendAnomalyAgent",
    "InsightMage",
    "ReportFormatter",
    "ReportResult",
    "TrendDetector",
    "TrendResult",
    "get_data_trend_anomaly_agent",
    "get_insight_mage",
]
