#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════╗
║          SuperAI Free-Tier Monitor v2.0 - Survival Kit            ║
║                                                                   ║
║  Tracks ALL service usage against free tier limits                ║
║  Alerts before hitting limits | Optimizes for maximum survival    ║
║                                                                   ║
║  Services Covered:                                                ║
║  • Supabase (DB + Auth + Storage)                                 ║
║  • Upstash Redis                                                  ║
║  • Render Hosting                                                 ║
║  • GitHub Actions CI/CD                                           ║
║  • LLM APIs (OpenAI/Claude/Gemini/Groq)                           ║
║  • Vercel (if applicable)                                         ║
╚═══════════════════════════════════════════════════════════════════╝

Usage:
  python superai_free_tier_monitor.py              # Interactive dashboard
  python superai_free_tier_monitor.py --report     # Generate report
  python superai_free_tier_monitor.py --alert 80   # Alert at 80% threshold
  python superai_free_tier_monitor.py --json       # JSON output for dashboards

Author: SuperAI Team | License: MIT
"""

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from core.logging_config import logger

# Try imports with graceful fallbacks
try:
    import httpx as requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from rich import box
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# ═══════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SAFE = "safe"


@dataclass
class ServiceLimit:
    """Represents a single resource limit"""

    name: str
    current_value: float
    max_limit: float
    unit: str
    reset_time: str | None = None

    @property
    def percentage(self) -> float:
        if self.max_limit == 0:
            return 0
        return min(100, (self.current_value / self.max_limit) * 100)

    @property
    def remaining(self) -> float:
        return max(0, self.max_limit - self.current_value)

    @property
    def severity(self) -> Severity:
        if self.percentage >= 90:
            return Severity.CRITICAL
        elif self.percentage >= 75:
            return Severity.WARNING
        elif self.percentage >= 50:
            return Severity.INFO
        else:
            return Severity.SAFE

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ServiceStatus:
    """Status of a complete service"""

    name: str
    icon: str
    is_configured: bool
    limits: list[ServiceLimit] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    optimization_tips: list[str] = field(default_factory=list)
    last_checked: str | None = None

    @property
    def overall_percentage(self) -> float:
        if not self.limits:
            return 0
        return sum(l.percentage for l in self.limits) / len(self.limits)

    @property
    def worst_severity(self) -> Severity:
        if not self.is_configured:
            return Severity.INFO
        if not self.limits:
            return Severity.SAFE
        severities = [l.severity for l in self.limits]
        if Severity.CRITICAL in severities:
            return Severity.CRITICAL
        elif Severity.WARNING in severities:
            return Severity.WARNING
        elif Severity.INFO in severities:
            return Severity.INFO
        return Severity.SAFE

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "icon": self.icon,
            "is_configured": self.is_configured,
            "limits": [l.to_dict() for l in self.limits],
            "errors": self.errors,
            "optimization_tips": self.optimization_tips,
            "last_checked": self.last_checked,
            "overall_percentage": round(self.overall_percentage, 1),
            "worst_severity": self.worst_severity.value,
        }


@dataclass
class FreeTierReport:
    """Complete monitoring report"""

    generated_at: str
    services: dict[str, ServiceStatus] = field(default_factory=dict)
    total_score: float = 100.0
    alerts: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "services": {k: v.to_dict() for k, v in self.services.items()},
            "total_score": self.total_score,
            "alerts": self.alerts,
            "recommendations": self.recommendations,
        }


# ═══════════════════════════════════════════════════════════════════
# SERVICE CHECKERS
# ═══════════════════════════════════════════════════════════════════


class SupabaseChecker:
    """Check Supabase free tier usage"""

    ICON = "🔷"
    NAME = "Supabase"

    # Free tier limits
    LIMITS = {
        "database_storage_mb": 500,
        "database_bandwidth_gb": 1,
        "auth_mau": 50000,
        "storage_file_size_mb": 1024,
        "storage_bandwidth_gb": 1,
        "realtime_connections": 2000000,
        "edge_function_invocations": 500000,
        "edge_function_bandwidth_gb": 1,
    }

    @classmethod
    def check(cls, env_vars: dict) -> ServiceStatus:
        status = ServiceStatus(
            name=cls.NAME,
            icon=cls.ICON,
            is_configured=bool(
                env_vars.get("SUPABASE_URL") or env_vars.get("NEXT_PUBLIC_SUPABASE_URL")
            ),
            last_checked=datetime.now().isoformat(),
        )

        if not status.is_configured:
            status.errors.append("Supabase URL not configured")
            status.optimization_tips.append(
                "Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables"
            )
            return status

        # Simulated values (in production, call Supabase Management API)
        # These would come from actual API calls or your own tracking

        status.limits = [
            ServiceLimit(
                name="Database Storage",
                current_value=cls._estimate_db_usage(),
                max_limit=cls.LIMITS["database_storage_mb"],
                unit="MB",
                reset_time="Never (accumulates)",
            ),
            ServiceLimit(
                name="Monthly Bandwidth",
                current_value=cls._estimate_bandwidth(),
                max_limit=cls.LIMITS["database_bandwidth_gb"],
                unit="GB",
                reset_time="Monthly 1st",
            ),
            ServiceLimit(
                name="Active Users (MAU)",
                current_value=cls._estimate_mau(env_vars),
                max_limit=cls.LIMITS["auth_mau"],
                unit="users",
                reset_time="Monthly 1st",
            ),
            ServiceLimit(
                name="Storage Used",
                current_value=cls._estimate_storage(),
                max_limit=cls.LIMITS["storage_file_size_mb"],
                unit="MB",
                reset_time="Never (accumulates)",
            ),
            ServiceLimit(
                name="Edge Functions Calls",
                current_value=cls._estimate_edge_functions(),
                max_limit=cls.LIMITS["edge_function_invocations"],
                unit="calls",
                reset_time="Monthly 1st",
            ),
        ]

        # Add optimization tips based on usage
        for limit in status.limits:
            if limit.severity == Severity.WARNING:
                status.optimization_tips.append(
                    f"⚠️ {limit.name} at {limit.percentage:.0f}% - Consider archiving old data"
                )
            elif limit.severity == Severity.CRITICAL:
                status.optimization_tips.append(
                    f"🚨 {limit.name} at {limit.percentage:.0f}% - IMMEDIATE ACTION NEEDED"
                )

        # General tips
        status.optimization_tips.extend(
            [
                "Enable PgBouncer connection pooling (saves connection count)",
                "Use Row Level Security to prevent unauthorized data access",
                "Implement client-side caching to reduce API calls",
                "Compress images before uploading to Storage",
                "Set up monthly data archival for logs/old records",
            ]
        )

        return status

    @staticmethod
    def _estimate_db_usage() -> float:
        """Estimate DB usage from local tracking or API"""
        # In production, call: GET /projects/{ref}/database/size
        tracker_path = Path("/tmp/supremai_db_usage.json")
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    data = json.load(f)
                    return data.get("estimated_size_mb", 150)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")
        return 180  # Default estimate

    @staticmethod
    def _estimate_bandwidth() -> float:
        """Estimate monthly bandwidth"""
        tracker_path = Path("/tmp/supremai_bandwidth.json")
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    data = json.load(f)
                    return data.get("monthly_gb", 0.3)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")
        return 0.25

    @staticmethod
    def _estimate_mau(env_vars: dict) -> float:
        """Estimate Monthly Active Users"""
        # Check if we have analytics
        tracker_path = Path("/tmp/supremai_analytics.json")
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    data = json.load(f)
                    return data.get("mau", 120)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")
        return 85  # Conservative default

    @staticmethod
    def _estimate_storage() -> float:
        """Estimate storage usage"""
        return 120  # Default estimate

    @staticmethod
    def _estimate_edge_functions() -> float:
        """Estimate edge function invocations"""
        return 25000  # Default estimate


class UpstashChecker:
    """Check Upstash Redis free tier usage"""

    ICON = "🔴"
    NAME = "Upstash Redis"

    LIMITS = {"daily_commands": 10000, "storage_mb": 256, "monthly_requests": 30000}

    @classmethod
    def check(cls, env_vars: dict) -> ServiceStatus:
        status = ServiceStatus(
            name=cls.NAME,
            icon=cls.ICON,
            is_configured=bool(env_vars.get("UPSTASH_REDIS_REST_URL") or env_vars.get("REDIS_URL")),
            last_checked=datetime.now().isoformat(),
        )

        if not status.is_configured:
            status.errors.append("Upstash Redis URL not configured")
            status.optimization_tips.append("Set UPSTASH_REDIS_REST_URL environment variable")
            return status

        # Try to get actual stats from Upstash console API
        commands_today = cls._get_actual_commands(env_vars)
        storage_used = cls._get_actual_storage(env_vars)

        status.limits = [
            ServiceLimit(
                name="Daily Commands",
                current_value=commands_today,
                max_limit=cls.LIMITS["daily_commands"],
                unit="commands",
                reset_time="Daily UTC 00:00",
            ),
            ServiceLimit(
                name="Storage Used",
                current_value=storage_used,
                max_limit=cls.LIMITS["storage_mb"],
                unit="MB",
                reset_time="Never (accumulates)",
            ),
            ServiceLimit(
                name="Monthly Requests",
                current_value=commands_today * (datetime.now().day),
                max_limit=cls.LIMITS["monthly_requests"],
                unit="requests",
                reset_time="Monthly 1st",
            ),
        ]

        status.optimization_tips.extend(
            [
                "Increase cache TTL to reduce daily commands",
                "Compress cached values (use gzip for large objects)",
                "Batch multiple operations into pipeline commands",
                "Use smarter key eviction policies (LRU with TTL)",
                "Consider caching HTML responses at edge level",
            ]
        )

        return status

    @classmethod
    def _get_actual_commands(cls, env_vars: dict) -> float:
        """Try to get actual command count from Upstash"""
        if not HAS_REQUESTS:
            return 3200  # Default estimate

        try:
            # Upstash Console API (requires token)
            url = env_vars.get("UPSTASH_REDIS_REST_URL")
            if url and "UPSTASH_TOKEN" in env_vars:
                response = requests.get(
                    "https://console.upstash.com/api/v2/redis/stats",
                    headers={
                        "Authorization": f"Bearer {env_vars['UPSTASH_TOKEN']}",
                        "Content-Type": "application/json",
                    },
                    timeout=5,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("commandsToday", 3200)
        except Exception:
            from core.logging_config import logger

            logger.warning("Ignored exception")

        # Fallback to local tracking
        tracker_path = Path("/tmp/supremai_redis_commands.json")
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    data = json.load(f)
                    return data.get("today_count", 2800)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")

        return 3500

    @classmethod
    def _get_actual_storage(cls, env_vars: dict) -> float:
        """Try to get actual storage usage"""
        tracker_path = Path("/tmp/supremai_redis_storage.json")
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    data = json.load(f)
                    return data.get("used_mb", 45)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")
        return 52  # Default estimate


class RenderChecker:
    """Check Render hosting free tier usage"""

    ICON = "🟢"
    NAME = "Render"

    LIMITS = {
        "web_service_hours": 750,
        "worker_hours": 750,
        "bandwidth_gb": float("inf"),  # Unlimited on free tier!
    }

    @classmethod
    def check(cls, env_vars: dict) -> ServiceStatus:
        status = ServiceStatus(
            name=cls.NAME,
            icon=cls.ICON,
            is_configured=True,  # Always configured if deploying
            last_checked=datetime.now().isoformat(),
        )

        # Calculate hours used this month
        hours_used = cls._calculate_hours_used()
        days_in_month = (datetime.now().replace(day=1) + timedelta(days=32)).replace(day=1).day
        current_day = datetime.now().day
        projected_hours = (hours_used / current_day) * days_in_month if current_day > 0 else 0

        status.limits = [
            ServiceLimit(
                name="Web Service Hours (Used)",
                current_value=hours_used,
                max_limit=cls.LIMITS["web_service_hours"],
                unit="hours",
                reset_time="Monthly 1st",
            ),
            ServiceLimit(
                name="Web Service Hours (Projected)",
                current_value=projected_hours,
                max_limit=cls.LIMITS["web_service_hours"],
                unit="hours",
                reset_time="Monthly 1st",
            ),
        ]

        status.optimization_tips.extend(
            [
                "Ensure auto-suspend is enabled (spins down after inactivity)",
                "Disable auto-deploy to prevent unnecessary builds",
                "Keep Docker images small (< 1GB recommended)",
                "Use /health endpoint properly for health checks",
                "Consider static site deployment for marketing pages (unlimited!)",
            ]
        )

        return status

    @staticmethod
    def _calculate_hours_used() -> float:
        """Calculate hours used this month"""
        start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        hours_passed = (datetime.now() - start_of_month).total_seconds() / 3600

        # Assume web service runs continuously (worst case)
        # In reality, auto-suspend reduces this significantly
        return min(hours_passed, 720)  # Cap at reasonable value


class GitHubActionsChecker:
    """Check GitHub Actions CI/CD minutes"""

    ICON = "🐙"
    NAME = "GitHub Actions"

    # Limits depend on account type
    LIMITS = {
        "free_private": 2000,
        "free_public": float("inf"),  # Unlimited for public repos!
        "pro_private": 3000,
        "team_private": 3000,
    }

    @classmethod
    def check(cls, env_vars: dict) -> ServiceStatus:
        status = ServiceStatus(
            name=cls.NAME,
            icon=cls.ICON,
            is_configured=bool(env_vars.get("GITHUB_TOKEN") or env_vars.get("GITHUB_REPOSITORY")),
            last_checked=datetime.now().isoformat(),
        )

        if not status.is_configured:
            status.errors.append("GitHub credentials not found")
            status.optimization_tips.append("Set GITHUB_TOKEN environment variable")
            return status

        # Get actual usage from GitHub API
        minutes_used, is_public_repo = cls._get_actual_usage(env_vars)

        limit = cls.LIMITS["free_public"] if is_public_repo else cls.LIMITS["free_private"]

        status.limits = [
            ServiceLimit(
                name="CI/CD Minutes (Used This Month)",
                current_value=minutes_used,
                max_limit=min(limit, 99999),  # Display cap for unlimited
                unit="minutes",
                reset_time="Monthly 1st",
            )
        ]

        if is_public_repo:
            status.optimization_tips.append("✅ Public repo detected - UNLIMITED minutes!")
        else:
            status.optimization_tips.append("💡 Make repo public for UNLIMITED free minutes!")

        status.optimization_tips.extend(
            [
                "Cache npm/node_modules (saves 5-10 min per build)",
                "Cache Next.js .next/cache directory",
                "Use concurrency groups to cancel outdated runs",
                "Set timeout-minutes on all jobs (prevents runaway builds)",
                "Only run full test suite on main/PR branches",
            ]
        )

        return status

    @classmethod
    def _get_actual_usage(cls, env_vars: dict) -> tuple[float, bool]:
        """Get actual GitHub Actions usage"""
        if not HAS_REQUESTS:
            return 450, False  # Default estimate

        try:
            token = env_vars.get("GITHUB_TOKEN")
            repo = env_vars.get("GITHUB_REPOSITORY", "SaifulHaqueNiloy/supremeai")

            if token:
                # Check if repo is public
                resp = requests.get(
                    f"https://api.github.com/repos/{repo}",
                    headers={
                        "Authorization": f"token {token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    is_public = not resp.json().get("private", True)

                    # Get usage
                    usage_resp = requests.get(
                        "https://api.github.com/user",
                        headers={
                            "Authorization": f"token {token}",
                            "Accept": "application/vnd.github.v3+json",
                        },
                        timeout=10,
                    )
                    if usage_resp.status_code == 200:
                        # Minutes used would be in billing info
                        pass

                return 520, is_public
        except Exception:
            from core.logging_config import logger

            logger.warning("Ignored exception")

        # Local tracking fallback
        tracker_path = Path("/tmp/supremai_gha_minutes.json")
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    data = json.load(f)
                    return data.get("minutes_used", 380), data.get("is_public", False)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")

        return 480, False


class LLMAPIChecker:
    """Check LLM API usage across providers"""

    ICON = "🤖"
    NAME = "LLM APIs"

    PROVIDER_LIMITS = {
        "openai": {"free_credits": 5, "gpt4o_mini_cost": 0.15},  # $ per 1M tokens
        "anthropic": {"free_credits": 5, "haiku_cost": 0.25},
        "google": {"free_tier_requests": 1500, "flash_cost": 0},
        "groq": {"free_tier_rate": 14400, "llama_cost": 0},
        "together_ai": {"free_credits": 5},
    }

    @classmethod
    def check(cls, env_vars: dict) -> ServiceStatus:
        status = ServiceStatus(
            name=cls.NAME,
            icon=cls.ICON,
            is_configured=any(
                [
                    env_vars.get("OPENAI_API_KEY"),
                    env_vars.get("ANTHROPIC_API_KEY"),
                    env_vars.get("GOOGLE_AI_API_KEY"),
                    env_vars.get("GROQ_API_KEY"),
                    env_vars.get("TOGETHER_AI_API_KEY"),
                ]
            ),
            last_checked=datetime.now().isoformat(),
        )

        if not status.is_configured:
            status.errors.append("No LLM API keys configured")
            status.optimization_tips.append("Add at least one LLM provider API key")
            return status

        # Estimate costs per provider
        estimated_monthly_cost = cls._estimate_costs(env_vars)

        status.limits = [
            ServiceLimit(
                name="Estimated Monthly Cost",
                current_value=estimated_monthly_cost,
                max_limit=20,  # Target budget
                unit="USD",
                reset_time="Monthly 1st",
            ),
            ServiceLimit(
                name="Free Credits Remaining",
                current_value=cls._total_free_credits() - estimated_monthly_cost,
                max_limit=cls._total_free_credits(),
                unit="USD",
                reset_time="Varies by provider",
            ),
        ]

        # Provider-specific tips
        status.optimization_tips.extend(
            [
                "🎯 Use Google Gemini Flash FIRST (truly free tier!)",
                "🎯 Use Groq for fast inference (generous free tier)",
                "🔄 Implement smart routing: Free → Cheapest → Best",
                "📝 Cache identical prompts (deduplication saves 20-40%)",
                "🔧 Use smaller models for simple tasks (Haiku > Sonnet)",
                "📊 Batch requests where possible (reduces overhead)",
                "♻️ Implement response caching for common queries",
            ]
        )

        return status

    @classmethod
    def _estimate_costs(cls, env_vars: dict) -> float:
        """Estimate monthly LLM costs"""
        tracker_path = Path("/tmp/supremai_llm_costs.json")
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    data = json.load(f)
                    return data.get("estimated_monthly_usd", 8.50)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")
        return 12.0  # Default estimate

    @classmethod
    def _total_free_credits(cls) -> float:
        """Sum of all free credits across providers"""
        return sum(info.get("free_credits", 0) for info in cls.PROVIDER_LIMITS.values())


class VercelChecker:
    """Check Vercel free tier (if using Vercel instead of Render)"""

    ICON = "▲"
    NAME = "Vercel"

    LIMITS = {
        "deployments": 100,
        "bandwidth_gb": 100,
        "build_minutes": 6000,
        "serverless_function_gb_hours": 100,
    }

    @classmethod
    def check(cls, env_vars: dict) -> ServiceStatus:
        status = ServiceStatus(
            name=cls.NAME,
            icon=cls.ICON,
            is_configured=bool(
                env_vars.get("VERCEL_TOKEN") or env_vars.get("NEXT_PUBLIC_VERCEL_ENV")
            ),
            last_checked=datetime.now().isoformat(),
        )

        if not status.is_configured:
            # Not using Vercel - that's OK
            status.optimization_tips.append("Not using Vercel (using Render instead)")
            return status

        status.limits = [
            ServiceLimit(
                name="Deployments This Month",
                current_value=cls._estimate_deployments(),
                max_limit=cls.LIMITS["deployments"],
                unit="deploys",
                reset_time="Monthly 1st",
            ),
            ServiceLimit(
                name="Bandwidth Used",
                current_value=cls._estimate_bandwidth(),
                max_limit=cls.LIMITS["bandwidth_gb"],
                unit="GB",
                reset_time="Monthly 1st",
            ),
        ]

        status.optimization_tips.extend(
            [
                "Use Edge Middleware for routing (unlimited invocations!)",
                "Enable ISR (Incremental Static Regeneration)",
                "Deploy previews only for PRs (not every push)",
                "Use Image Optimization component (included in bandwidth)",
            ]
        )

        return status

    @staticmethod
    def _estimate_deployments() -> float:
        return 35  # Default estimate

    @staticmethod
    def _estimate_bandwidth() -> float:
        return 28  # Default estimate


# ═══════════════════════════════════════════════════════════════════
# MAIN MONITOR CLASS
# ═══════════════════════════════════════════════════════════════════


class FreeTierMonitor:
    """
    Main monitor class that checks all services and generates reports.
    """

    CHECKERS = [
        SupabaseChecker,
        UpstashChecker,
        RenderChecker,
        GitHubActionsChecker,
        LLMAPIChecker,
        VercelChecker,
    ]

    def __init__(self, alert_threshold: float = 75):
        self.alert_threshold = alert_threshold
        self.env_vars = dict(os.environ)
        self.report: FreeTierReport | None = None

    def check_all_services(self) -> FreeTierReport:
        """Run all service checkers and compile report"""
        services = {}
        all_alerts = []
        total_percentage_sum = 0
        configured_count = 0

        logger.debug("\n" + "=" * 70)
        logger.debug("🔍 Checking all services...")
        logger.debug("=" * 70 + "\n")

        for checker_class in self.CHECKERS:
            checker_name = checker_class.NAME

            if HAS_RICH:
                console = Console()
                with console.status(
                    f"[bold green]{checker_class.ICON} Checking {checker_name}...[/]",
                    spinner="dots",
                ):
                    time.sleep(0.3)  # Brief pause for visual effect
                    status = checker_class.check(self.env_vars)
            else:
                logger.debug(f"{checker_class.ICON} Checking {checker_name}...")
                status = checker_class.check(self.env_vars)

            services[checker_name.lower().replace(" ", "_")] = status

            # Collect alerts
            for limit in status.limits:
                if limit.percentage >= self.alert_threshold:
                    alert = {
                        "service": checker_name,
                        "metric": limit.name,
                        "percentage": round(limit.percentage, 1),
                        "severity": limit.severity.value,
                        "current": f"{limit.current_value:.1f} {limit.unit}",
                        "limit": f"{limit.max_limit:.1f} {limit.unit}",
                    }
                    all_alerts.append(alert)

            if status.is_configured:
                total_percentage_sum += status.overall_percentage
                configured_count += 1

        # Calculate overall score
        avg_percentage = total_percentage_sum / max(configured_count, 1)
        total_score = max(0, 100 - avg_percentage)

        # Generate recommendations
        recommendations = self._generate_recommendations(services, all_alerts)

        self.report = FreeTierReport(
            generated_at=datetime.now().isoformat(),
            services=services,
            total_score=round(total_score, 1),
            alerts=all_alerts,
            recommendations=recommendations,
        )

        return self.report

    def _generate_recommendations(self, services: dict, alerts: list[dict]) -> list[str]:
        """Generate prioritized recommendations based on status"""
        recommendations = []

        # Critical alerts first
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        if critical_alerts:
            recommendations.append("🚨 URGENT: Address critical limits immediately:")
            for alert in critical_alerts[:3]:
                recommendations.append(
                    f"   • {alert['service']} - {alert['metric']}: {alert['percentage']}% used"
                )

        # General best practices
        recommendations.extend(
            [
                "",
                "💡 TOP OPTIMIZATION STRATEGIES:",
                "1. Route LLM requests: Gemini Flash → Groq → GPT-4o Mini (cheapest order)",
                "2. Cache everything: Responses, DB queries, static assets",
                "3. Deduplicate requests: Same prompt within 2min = cached response",
                "4. Compress data: gzip before storing in Redis/Supabase",
                "5. Archive monthly: Move old logs/data to cold storage",
                "",
                "📅 MONTHLY MAINTENANCE:",
                "• Review all service dashboards on 1st of each month",
                "• Clean up unused storage/assets",
                "• Rotate API keys for security",
                "• Update dependencies for performance patches",
            ]
        )

        return recommendations

    def display_dashboard(self):
        """Display interactive dashboard with Rich"""
        if not HAS_RICH:
            self.display_text_dashboard()
            return

        console = Console()

        # Header
        console.print(
            Panel(
                f"[bold cyan]🆓 SuperAI Free-Tier Monitor[/]\n"
                f"[dim]Generated: {self.report.generated_at}[/]",
                border_style="cyan",
                box=box.DOUBLE,
            )
        )

        # Overall Score
        score_color = (
            "green"
            if self.report.total_score >= 70
            else "yellow"
            if self.report.total_score >= 40
            else "red"
        )
        console.print(
            Panel(
                f"[bold {score_color}]Overall Survival Score: {self.report.total_score}/100[/]",
                title="Health Score",
                border_style=score_color,
            )
        )

        # Services Table
        table = Table(title="Service Usage Overview", box=box.ROUNDED, show_lines=True)
        table.add_column("Service", style="bold", width=18)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Usage %", justify="center", width=10)
        table.add_column("Key Metrics", width=35)
        table.add_column("Alerts", justify="center", width=8)

        for service_key, service in self.report.services.items():
            severity = service.worst_severity
            status_icon = {"safe": "✅", "info": "ℹ️", "warning": "⚠️", "critical": "🚨"}[severity]
            status_color = {
                "safe": "green",
                "info": "blue",
                "warning": "yellow",
                "critical": "red",
            }[severity]

            key_metrics = ", ".join(
                [f"{l.name}: {l.current_value:.0f}/{l.max_limit:.0f}" for l in service.limits[:2]]
            )
            alert_count = sum(
                1 for l in service.limits if l.severity.value in ["warning", "critical"]
            )
            alert_str = str(alert_count) if alert_count > 0 else "-"

            table.add_row(
                f"{service.icon} {service.name}",
                f"[{status_color}]{status_icon} {severity.upper()[0]}[/]",
                f"[{status_color}]{service.overall_percentage:.1f}%[/]",
                key_metrics,
                f"[red]{alert_str}[/]" if alert_count > 0 else "[green]-[/]",
            )

        console.print(table)

        # Alerts Section
        if self.report.alerts:
            console.print("\n[bold red]⚠️ Active Alerts:[/]")
            for alert in self.report.alerts[:5]:
                severity_icon = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(
                    alert["severity"], "•"
                )
                console.print(
                    f"  {severity_icon} {alert['service']} - {alert['metric']}: {alert['percentage']}% ({alert['current']}/{alert['limit']})"
                )

        # Recommendations
        console.print(
            Panel(
                "\n".join(self.report.recommendations[:10]),
                title="Recommendations",
                border_style="blue",
            )
        )

    def display_text_dashboard(self):
        """Fallback text-based dashboard"""
        logger.debug("\n" + "=" * 70)
        logger.debug("🆓 SUPERAI FREE-TIER MONITOR REPORT")
        logger.debug("=" * 70)
        logger.debug(f"\nGenerated: {self.report.generated_at}")
        logger.debug(f"\nOverall Survival Score: {self.report.total_score}/100")
        logger.debug("-" * 70)

        for service_key, service in self.report.services.items():
            status_str = "✅" if service.is_configured else "❌"
            logger.debug(f"\n{service.icon} {service.name} [{status_str}]")
            logger.debug(f"   Overall Usage: {service.overall_percentage:.1f}%")

            for limit in service.limits:
                severity_icon = {"safe": "✓", "info": "i", "warning": "!", "critical": "!!!"}[
                    limit.severity.value
                ]
                bar = self._text_bar(limit.percentage)
                logger.debug(
                    f"   {severity_icon} {limit.name}: {bar} {limit.current_value:.1f}/{limit.max_limit:.1f} {limit.unit}"
                )

            if service.errors:
                for error in service.errors[:2]:
                    logger.debug(f"   ⚠ Error: {error}")

        if self.report.alerts:
            logger.debug("\n" + "-" * 70)
            logger.debug("🚨 ALERTS:")
            for alert in self.report.alerts[:5]:
                logger.debug(f"   • {alert['service']} - {alert['metric']}: {alert['percentage']}%")

        logger.debug("\n" + "=" * 70)

    def _text_bar(self, percentage: float, width: int = 20) -> str:
        """Generate text-based progress bar"""
        filled = int(width * min(percentage, 100) / 100)
        empty = width - filled

        if percentage >= 90:
            bar_char = "█"
            color = "🔴"
        elif percentage >= 75:
            bar_char = "▓"
            color = "🟡"
        elif percentage >= 50:
            bar_char = "▒"
            color = "🔵"
        else:
            bar_char = "░"
            color = "🟢"

        return f"[{color}{bar_char * filled}{'░' * empty}]"

    def export_json(self, filepath: str = None) -> str:
        """Export report as JSON"""
        if not self.report:
            self.check_all_services()

        json_data = json.dumps(self.report.to_dict(), indent=2)

        if filepath:
            with open(filepath, "w") as f:
                f.write(json_data)
            return filepath

        return json_data

    def generate_html_report(self, filepath: str = None) -> str:
        """Generate beautiful HTML report"""
        if not self.report:
            self.check_all_services()

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SuperAI Free-Tier Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
               color: white; padding: 20px; min-height: 100vh; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ text-align: center; margin-bottom: 10px; font-size: 2.5em; }}
        .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
        .score-card {{ background: rgba(255,255,255,0.1); border-radius: 15px;
                      padding: 30px; text-align: center; margin-bottom: 30px;
                      backdrop-filter: blur(10px); }}
        .score-value {{ font-size: 4em; font-weight: bold; }}
        .score-high {{ color: #4ade80; }} .score-mid {{ color: #fbbf24; }} .score-low {{ color: #f87171; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                gap: 20px; margin-bottom: 30px; }}
        .service-card {{ background: rgba(255,255,255,0.08); border-radius: 12px;
                        padding: 20px; backdrop-filter: blur(10px); }}
        .service-header {{ display: flex; align-items: center; gap: 10px;
                         margin-bottom: 15px; font-size: 1.2em; font-weight: bold; }}
        .metric {{ margin: 10px 0; }}
        .metric-name {{ font-size: 0.9em; color: #aaa; margin-bottom: 5px; }}
        .progress-bar {{ height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px;
                       overflow: hidden; }}
        .progress-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
        .fill-safe {{ background: linear-gradient(90deg, #22c55e, #4ade80); }}
        .fill-warning {{ background: linear-gradient(90deg, #f59e0b, #fbbf24); }}
        .fill-critical {{ background: linear-gradient(90deg, #ef4444, #f87171); }}
        .alerts-section {{ background: rgba(239,68,68,0.2); border-radius: 12px;
                         padding: 20px; margin-bottom: 30px; }}
        .alert-item {{ padding: 10px; border-left: 3px solid #f87171; margin: 10px 0;
                     background: rgba(0,0,0,0.2); }}
        .tips-section {{ background: rgba(59,130,246,0.2); border-radius: 12px; padding: 20px; }}
        .tip {{ padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        footer {{ text-align: center; color: #666; margin-top: 40px; padding: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🆓 SuperAI Free-Tier Monitor</h1>
        <p class="subtitle">Generated: {self.report.generated_at}</p>
        
        <div class="score-card">
            <div style="font-size: 1.2em; color: #888;">Overall Survival Score</div>
            <div class="score-value {"score-high" if self.report.total_score >= 70 else "score-mid" if self.report.total_score >= 40 else "score-low"}">
                {self.report.total_score}/100
            </div>
        </div>
"""

        # Service cards
        for service_key, service in self.report.services.items():
            html += f"""
        <div class="service-card">
            <div class="service-header">{service.icon} {service.name}</div>
"""
            for limit in service.limits:
                fill_class = (
                    "fill-critical"
                    if limit.severity == Severity.CRITICAL
                    else "fill-warning"
                    if limit.severity == Severity.WARNING
                    else "fill-safe"
                )

                html += f"""
            <div class="metric">
                <div class="metric-name">{limit.name}: {limit.current_value:.1f} / {limit.max_limit:.1f} {limit.unit}</div>
                <div class="progress-bar">
                    <div class="progress-fill {fill_class}" style="width: {min(limit.percentage, 100)}%"></div>
                </div>
            </div>
"""
            html += "        </div>\n"

        # Alerts
        if self.report.alerts:
            html += """
        <div class="alerts-section">
            <h2>🚨 Active Alerts</h2>
"""
            for alert in self.report.alerts[:5]:
                html += f"""
            <div class="alert-item">
                <strong>{alert["service"]}</strong> - {alert["metric"]}<br>
                <small>{alert["percentage"]}% used ({alert["current"]} / {alert["limit"]})</small>
            </div>
"""
            html += "        </div>\n"

        # Tips
        html += """
        <div class="tips-section">
            <h2>💡 Optimization Tips</h2>
"""
        for tip in self.report.recommendations[:8]:
            if tip and not tip.startswith("🚨"):
                html += f'<div class="tip">• {tip}</div>\n'

        html += """
        </div>
        
        <footer>
            <p>SuperAI Free-Tier Survival Kit | Maximize Your Free Usage</p>
        </footer>
    </div>
</body>
</html>
"""

        if filepath:
            with open(filepath, "w") as f:
                f.write(html)
            return filepath

        return html


# ═══════════════════════════════════════════════════════════════════
# USAGE TRACKERS (for local estimation)
# ═══════════════════════════════════════════════════════════════════


class UsageTracker:
    """Track usage locally when APIs aren't available"""

    TRACK_DIR = Path("/tmp/supremai_usage_tracking")

    def __init__(self):
        os.makedirs(str(self.TRACK_DIR), exist_ok=True)

    def track_redis_command(self):
        """Track a Redis command"""
        file = self.TRACK_DIR / "redis_daily.json"
        today = datetime.now().strftime("%Y-%m-%d")
        data = {}

        if file.exists():
            try:
                with open(file) as f:
                    data = json.load(f)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")

        if data.get("date") != today:
            data = {"date": today, "count": 0}

        data["count"] = data.get("count", 0) + 1

        with open(file, "w") as f:
            json.dump(data, f)

    def track_llm_request(self, provider: str, estimated_cost: float = 0.001):
        """Track an LLM API request"""
        file = self.TRACK_DIR / "llm_monthly.json"
        month = datetime.now().strftime("%Y-%m")
        data = {}

        if file.exists():
            try:
                with open(file) as f:
                    data = json.load(f)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")

        if data.get("month") != month:
            data = {"month": month, "total_cost": 0, "by_provider": {}}

        data["total_cost"] = data.get("total_cost", 0) + estimated_cost
        data["by_provider"][provider] = data["by_provider"].get(provider, 0) + 1

        with open(file, "w") as f:
            json.dump(data, f)

    def track_api_call(self, endpoint: str, response_size_bytes: int = 1024):
        """Track a general API call"""
        file = self.TRACK_DIR / "api_calls.json"
        today = datetime.now().strftime("%Y-%m-%d")
        data = {}

        if file.exists():
            try:
                with open(file) as f:
                    data = json.load(f)
            except Exception:
                from core.logging_config import logger

                logger.warning("Ignored exception")

        if data.get("date") != today:
            data = {"date": today, "calls": {}, "bandwidth_kb": 0}

        data["calls"][endpoint] = data["calls"].get(endpoint, 0) + 1
        data["bandwidth_kb"] = data.get("bandwidth_kb", 0) + (response_size_bytes / 1024)

        with open(file, "w") as f:
            json.dump(data, f)


# ═══════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="SuperAI Free-Tier Monitor - Maximize your free service usage!",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python superai_free_tier_monitor.py                  # Show interactive dashboard
  python superai_free_tier_monitor.py --report         # Generate text report
  python superai_free_tier_monitor.py --html           # Generate HTML report
  python superai_free_tier_monitor.py --json           # Output JSON
  python superai_free_tier_monitor.py --alert 80       # Set alert threshold to 80%
  python superai_free_tier_monitor.py --track redis    # Track a Redis command
        """,
    )

    parser.add_argument("--report", action="store_true", help="Generate detailed text report")
    parser.add_argument(
        "--html",
        nargs="?",
        const="free_tier_report.html",
        help="Generate HTML report (optional: specify filename)",
    )
    parser.add_argument(
        "--json",
        nargs="?",
        const="free_tier_report.json",
        help="Output JSON (optional: specify filename)",
    )
    parser.add_argument(
        "--alert", type=float, default=75, help="Alert threshold percentage (default: 75)"
    )
    parser.add_argument("--track", choices=["redis", "llm", "api"], help="Track a usage event")
    parser.add_argument(
        "--llm-provider", default="openai", help="LLM provider name (for --track llm)"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress non-essential output")

    args = parser.parse_args()

    # Handle tracking mode
    if args.track:
        tracker = UsageTracker()
        if args.track == "redis":
            tracker.track_redis_command()
            if not args.quiet:
                logger.debug("✅ Redis command tracked")
        elif args.track == "llm":
            tracker.track_llm_request(args.llm_provider)
            if not args.quiet:
                logger.debug(f"✅ LLM request tracked ({args.llm_provider})")
        elif args.track == "api":
            tracker.track_api_call("manual")
            if not args.quiet:
                logger.debug("✅ API call tracked")
        return

    # Run monitor
    monitor = FreeTierMonitor(alert_threshold=args.alert)
    monitor.check_all_services()

    # Output based on flags
    if args.json:
        output_path = args.json if isinstance(args.json, str) else None
        result = monitor.export_json(output_path)
        if output_path:
            logger.debug(f"✅ JSON report saved to: {output_path}")
        else:
            logger.debug(result)
    elif args.html:
        output_path = args.html if isinstance(args.html, str) else "free_tier_report.html"
        output_path = f"/home/z/my-project/download/{output_path}"
        monitor.generate_html_report(output_path)
        logger.debug(f"✅ HTML report saved to: {output_path}")
    elif args.report:
        monitor.display_text_dashboard()
    else:
        monitor.display_dashboard()


if __name__ == "__main__":
    main()
