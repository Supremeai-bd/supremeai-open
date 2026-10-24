"""InsightMage compatibility wrapper pointing to agents/insight_mage.py."""

# বাংলা মন্তব্য: ইনসাইট-মেজ — কোড ডুপ্লিকেশন এড়াতে agents/insight_mage.py এর মূল ইম্প্লিমেন্টেশন ইম্পোর্ট করা হলো।

from __future__ import annotations

from agents.insight_mage import (
    AnomalyDetector,
    AnomalyResult,
    InsightMage,
    ReportFormatter,
    ReportResult,
    TrendDetector,
    TrendResult,
)

__all__ = [
    "AnomalyDetector",
    "AnomalyResult",
    "InsightMage",
    "ReportFormatter",
    "ReportResult",
    "TrendDetector",
    "TrendResult",
]
