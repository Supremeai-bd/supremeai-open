from __future__ import annotations

import asyncio
import logging

"""
SupremeAI - LLM Cost Optimizer Agent
================================
Purpose: Track API usage (Gemini, OpenAI, Render) and suggest cost optimizations.
Author: SupremeAI Architecture Team
Date: July 18, 2026
"""


import datetime
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.logging_config import logger

# বাংলা মন্তব্য: উইন্ডোজ টার্মিনালে ইউনিকোড/ইমোজি আউটপুট সাপোর্ট করার জন্য এনকোডিং কনফিগার করা হলো।
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")

# --- Path Setup (consistent with existing codebase) ---
# বাংলা মন্তব্য: পাথ সেটআপ ও কোর কনফিগ ইম্পোর্ট
try:
    from core.config import settings  # noqa: F401 -- শুধু importability যাচাই, path-setup probe
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# Try importing litellm cost tracking
try:
    import litellm  # noqa: F401 -- শুধু availability probe, LITELLM_AVAILABLE flag-এর জন্য

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.warning("⚠️ litellm not available. Token cost tracking will be limited.")

try:
    import httpx as requests
except ImportError:
    requests = None

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

COST_DB_FILE = Path(__file__).parent / ".costsage_db.json"
BUDGET_CONFIG_FILE = Path(__file__).parent / ".costsage_budget.json"
REQUEST_TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS") or "15")

DEFAULT_COST_RATES = {
    "gemini": {
        "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
        "gemini-2.0-flash": {"input": 0.000075, "output": 0.0003},
        "gemini-1.0-pro": {"input": 0.0005, "output": 0.0015},
    },
    "openai": {
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    },
    "groq": {
        "llama-3.1-70b": {"input": 0.00059, "output": 0.00079},
        "llama-3.1-8b": {"input": 0.00005, "output": 0.00008},
    },
    "deepseek": {
        "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    },
    "render": {
        "web_service": {"monthly": 7.0},
        "background_worker": {"monthly": 7.0},
    },
    "vercel": {
        "pro_plan": {"monthly": 20.0},
        "bandwidth_per_gb": 0.4,
    },
    "gcp": {
        "cloud_run_per_million_requests": 0.40,
        "firestore_per_million_reads": 0.06,
        "firestore_per_million_writes": 0.18,
    },
}


@dataclass
class UsageRecord:
    """একটি API call-এর usage record।"""

    timestamp: str
    provider: str
    model_or_service: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetConfig:
    """Monthly budget configuration per provider."""

    provider: str
    monthly_limit_usd: float
    alert_threshold_pct: float = 80.0
    alert_sent: bool = False


@dataclass
class CostReport:
    """Generated cost report with optimization suggestions."""

    period_start: str
    period_end: str
    total_cost_usd: float
    breakdown_by_provider: dict[str, float]
    top_models: list[dict[str, Any]]
    budget_status: list[dict[str, Any]]
    optimization_suggestions: list[str]
    trend_analysis: str


class UsageTracker:
    """Tracks and stores all API usage records."""

    def __init__(self, db_file: Path = COST_DB_FILE):
        self.db_file = db_file
        self.records: list[UsageRecord] = []
        self._load_db()

    def _load_db(self):
        # বাংলা মন্তব্য: কস্ট ডেটাবেস ক্যাশ ফাইল থেকে লোড করা।
        if self.db_file.exists():
            try:
                data = json.loads(self.db_file.read_text(encoding="utf-8"))
                self.records = [UsageRecord(**r) for r in data.get("records", [])]
                logger.info(f"📚 Loaded {len(self.records)} usage records")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load cost DB: {e}")

    def _save_db(self):
        # বাংলা মন্তব্য: মেমোরি থেকে কস্ট ডেটাবেস ক্যাশ ফাইলে রাইট করা।
        try:
            data = {
                "last_updated": datetime.datetime.now(datetime.UTC).isoformat(),
                "records": [asdict(r) for r in self.records],
            }
            self.db_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save cost DB: {e}")

    def record_usage(
        self,
        provider: str,
        model_or_service: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float | None = None,
        metadata: dict | None = None,
    ):
        # বাংলা মন্তব্য: এপিআই ইউসেজ রেকর্ড সিস্টেমে সেভ করা।
        if cost_usd is None:
            cost_usd = self._calculate_cost(provider, model_or_service, input_tokens, output_tokens)

        record = UsageRecord(
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            provider=provider,
            model_or_service=model_or_service,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            metadata=metadata or {},
        )
        self.records.append(record)
        self._save_db()
        logger.info(f"💰 Recorded: {provider}/{model_or_service} — ${cost_usd:.4f}")

    def _calculate_cost(
        self, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        rates = DEFAULT_COST_RATES.get(provider, {})
        model_rates = rates.get(model, {})
        if not model_rates:
            return (input_tokens + output_tokens) * 0.000001

        input_cost = (input_tokens / 1000) * model_rates.get("input", 0)
        output_cost = (output_tokens / 1000) * model_rates.get("output", 0)
        return input_cost + output_cost

    def get_cost_summary(self, days: int = 30) -> dict[str, Any]:
        cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)).isoformat()
        recent = [r for r in self.records if r.timestamp >= cutoff]

        total_cost = sum(r.cost_usd for r in recent)
        by_provider = defaultdict(float)
        by_model = defaultdict(
            lambda: {"cost": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}
        )

        for r in recent:
            by_provider[r.provider] += r.cost_usd
            by_model[r.model_or_service]["cost"] += r.cost_usd
            by_model[r.model_or_service]["calls"] += 1
            by_model[r.model_or_service]["input_tokens"] += r.input_tokens
            by_model[r.model_or_service]["output_tokens"] += r.output_tokens

        top_models = sorted(
            [{"model": k, **v} for k, v in by_model.items()],
            key=lambda x: x["cost"],
            reverse=True,
        )[:10]

        return {
            "total_cost_usd": total_cost,
            "by_provider": dict(by_provider),
            "top_models": top_models,
            "total_calls": len(recent),
            "period_days": days,
        }


class BudgetManager:
    """Manages monthly budgets and sends alerts."""

    def __init__(self, config_file: Path = BUDGET_CONFIG_FILE, tracker: UsageTracker = None):
        self.config_file = config_file
        self.tracker = tracker or UsageTracker()
        self.budgets: dict[str, BudgetConfig] = {}
        self._load_config()

    def _load_config(self):
        # বাংলা মন্তব্য: বাজেট কনফিগারেশন ফাইল থেকে লোড করা।
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self.budgets[k] = BudgetConfig(**v)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load budget config: {e}")
        else:
            self.budgets = {
                "gemini": BudgetConfig("gemini", 50.0),
                "openai": BudgetConfig("openai", 30.0),
                "groq": BudgetConfig("groq", 20.0),
                "render": BudgetConfig("render", 50.0),
                "vercel": BudgetConfig("vercel", 30.0),
                "gcp": BudgetConfig("gcp", 100.0),
            }
            self._save_config()

    def _save_config(self):
        # বাংলা মন্তব্য: বাজেট কনফিগারেশন ফাইলে রাইট করা।
        try:
            data = {k: asdict(v) for k, v in self.budgets.items()}
            self.config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save budget config: {e}")

    def check_budgets(self) -> list[dict[str, Any]]:
        summary = self.tracker.get_cost_summary(days=30)
        by_provider = summary["by_provider"]
        alerts = []

        for provider, budget in self.budgets.items():
            spent = by_provider.get(provider, 0.0)
            pct = (spent / budget.monthly_limit_usd) * 100 if budget.monthly_limit_usd > 0 else 0

            status = {
                "provider": provider,
                "spent_usd": spent,
                "limit_usd": budget.monthly_limit_usd,
                "pct_used": pct,
                "alert_triggered": False,
                "severity": "normal",
            }

            if pct >= 100:
                status["severity"] = "critical"
                status["alert_triggered"] = True
                if not budget.alert_sent:
                    logger.error(f"🚨 BUDGET EXCEEDED: {provider} — ${spent:.2f} used")
                    budget.alert_sent = True
            elif pct >= budget.alert_threshold_pct:
                status["severity"] = "warning"
                status["alert_triggered"] = True
                if not budget.alert_sent:
                    logger.warning(f"⚠️ BUDGET WARNING: {provider} — {pct:.1f}% reached")
                    budget.alert_sent = True
            else:
                budget.alert_sent = False

            alerts.append(status)

        return alerts

    def set_budget(self, provider: str, limit_usd: float, alert_pct: float = 80.0):
        self.budgets[provider] = BudgetConfig(provider, limit_usd, alert_pct)
        self._save_config()


class OptimizationEngine:
    def __init__(self, tracker: UsageTracker):
        self.tracker = tracker

    def generate_suggestions(self) -> list[str]:
        # বাংলা মন্তব্য: খরচ কমানোর জন্য এআই/রুল-বেজড অপ্টিমাইজেশন সাজেশন জেনারেট করা।
        summary = self.tracker.get_cost_summary(days=30)
        suggestions = []
        top_models = summary["top_models"]

        expensive_models = [m for m in top_models if m["cost"] > 5.0]
        for model in expensive_models[:3]:
            cheaper = self._find_cheaper_alternative(model["model"])
            if cheaper:
                potential_savings = model["cost"] * 0.7
                suggestions.append(
                    f"🔄 **Model Downgrade**: `{model['model']}` → `{cheaper}` could save ~${potential_savings:.2f}/month"
                )

        high_repeat = [m for m in top_models if m["calls"] > 100]
        for model in high_repeat[:2]:
            suggestions.append(
                f"💾 **Enable Caching**: `{model['model']}` has {model['calls']} calls. Save ~${model['cost'] * 0.3:.2f}/month."
            )

        by_provider = summary["by_provider"]
        if by_provider.get("render", 0) > 20:
            suggestions.append(
                "☁️ **Render Optimization**: Consider auto-suspend for dev/staging services."
            )

        if not suggestions:
            suggestions.append(
                "✅ Cost usage is optimized. No major savings opportunities detected."
            )
        return suggestions

    def _find_cheaper_alternative(self, model: str) -> str | None:
        alternatives = {
            "gemini-1.5-pro": "gemini-2.0-flash",
            "gpt-4o": "gpt-4o-mini",
            "gpt-4": "gpt-4o-mini",
            "claude-3-opus": "claude-3-haiku",
        }
        return alternatives.get(model)


class CostReporter:
    def __init__(self, tracker: UsageTracker, budget_manager: BudgetManager):
        self.tracker = tracker
        self.budget_manager = budget_manager

    def generate_report(self, days: int = 30) -> CostReport:
        summary = self.tracker.get_cost_summary(days=days)
        budget_status = self.budget_manager.check_budgets()
        engine = OptimizationEngine(self.tracker)
        suggestions = engine.generate_suggestions()

        prev_period = self.tracker.get_cost_summary(days=days * 2)
        prev_cost = prev_period["total_cost_usd"] - summary["total_cost_usd"]
        if prev_cost > 0:
            change_pct = ((summary["total_cost_usd"] - prev_cost) / prev_cost) * 100
            trend = f"📈 Cost changed by {change_pct:.1f}% vs previous baseline."
        else:
            trend = "📊 First period — establishing baseline."

        return CostReport(
            period_start=(
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
            ).isoformat(),
            period_end=datetime.datetime.now(datetime.UTC).isoformat(),
            total_cost_usd=summary["total_cost_usd"],
            breakdown_by_provider=summary["by_provider"],
            top_models=summary["top_models"],
            budget_status=budget_status,
            optimization_suggestions=suggestions,
            trend_analysis=trend,
        )

    def format_report_bilingual(self, report: CostReport) -> str:
        lines = [
            "=" * 60,
            "💰 SUPREMEAI COST REPORT — CostSage",
            "=" * 60,
            f"📅 Period: {report.period_start[:10]} → {report.period_end[:10]}",
            f"💵 Total Cost: ${report.total_cost_usd:.2f}\n",
            "📊 Provider Breakdown:",
        ]
        for provider, cost in sorted(report.breakdown_by_provider.items(), key=lambda x: -x[1]):
            lines.append(f"   • {provider}: ${cost:.2f}")

        lines.append("\n💡 Optimization Suggestions:")
        for i, s in enumerate(report.optimization_suggestions, 1):
            lines.append(f"   {i}. {s}")

        lines.append(
            f"\n📈 Trend: {report.trend_analysis}\n\n"
            + "=" * 60
            + "\n💰 সুপ্রিমএআই খরচ রিপোর্ট — কস্টসেজ\n"
            + "=" * 60
        )
        lines.append(f"📅 সময়কাল: {report.period_start[:10]} → {report.period_end[:10]}")
        lines.append(f"💵 মোট খরচ: ${report.total_cost_usd:.2f}\n\n📊 প্রভাইডার ভিত্তিক খরচ:")
        for provider, cost in sorted(report.breakdown_by_provider.items(), key=lambda x: -x[1]):
            lines.append(f"   • {provider}: ${cost:.2f}")

        return "\n".join(lines)


class LlmCostOptimizer:
    def __init__(self):
        self.tracker = UsageTracker()
        self.budget_manager = BudgetManager(tracker=self.tracker)
        self.reporter = CostReporter(self.tracker, self.budget_manager)

    def record_api_call(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        metadata: dict | None = None,
    ):
        self.tracker.record_usage(provider, model, input_tokens, output_tokens, metadata=metadata)

    def record_infrastructure_cost(
        self, provider: str, service: str, cost_usd: float, metadata: dict | None = None
    ):
        self.tracker.record_usage(provider, service, cost_usd=cost_usd, metadata=metadata)

    def get_report(self, days: int = 30) -> str:
        report = self.reporter.generate_report(days=days)
        return self.reporter.format_report_bilingual(report)


# Canonical aliases for backward compatibility
CostSage = LlmCostOptimizer
LLMCostOptimizer = LlmCostOptimizer  # noqa: E741 (uppercase alias)


if __name__ == "__main__":
    sage = CostSage()
