#!/usr/bin/env python3
"""
scripts/monitoring/capacity_planner.py
======================================
SupremeAI 2.0 — Auto-Scaling Capacity Planner
🟢 Low Priority | Production-Grade Resource Optimization

এই স্ক্রিপ্টটি সার্ভার রিসোর্স ব্যবহার, API ল্যাটেন্সি, এবং ট্রাফিক প্যাটার্ন
এনালাইজ করে অটো-স্কেলিং সুপারিশ তৈরি করে। Render/Netlify/Vercel এর
ফ্রি-টায়ার লিমিটের ভেতর থাকতে সাহায্য করে (Zero-Cost HA Strategy)।

কী কী করে:
  1. CPU/Memory/ডিস্ক ব্যবহার মনিটর করে (psutil)
  2. API endpoint ল্যাটেন্সি মেপে capacity threshold চেক করে
  3. Redis/DB connection pool usage ট্র্যাক করে
  4. Render free-tier sleep/wake cycle অপটিমাইজেশন সুপারিশ দেয়
  5. Historical capacity data JSONL এ সেভ করে trend analysis করে
  6. Telegram এ alert পাঠায় যদি threshold cross হয়
  7. GitHub Step Summary তে markdown report লেখে

Exit code: 0 = healthy capacity, 1 = scaling recommended, 2 = critical

ব্যবহার:
    python scripts/monitoring/capacity_planner.py
    python scripts/monitoring/capacity_planner.py --check-interval 60 --alert-threshold 80
    python scripts/monitoring/capacity_planner.py --dry-run --verbose
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
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

# ── পাথ সেটআপ ─────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("capacity_planner")

# ── কনফিগারেশন কনস্ট্যান্টস ───────────────────────────────────────────
DEFAULT_API_URL = settings.backend_url
DEFAULT_CHECK_INTERVAL = int(os.getenv("CAPACITY_CHECK_INTERVAL", "300"))  # 5 min
DEFAULT_ALERT_THRESHOLD = float(os.getenv("CAPACITY_ALERT_THRESHOLD", "75.0"))  # %
DEFAULT_CRITICAL_THRESHOLD = float(os.getenv("CAPACITY_CRITICAL_THRESHOLD", "90.0"))
DEFAULT_HISTORY_LIMIT = int(os.getenv("CAPACITY_HISTORY_LIMIT", "288"))  # 24h @ 5min
DATA_DIR = PROJECT_ROOT / "backend" / "data"
CAPACITY_HISTORY_FILE = DATA_DIR / "capacity_history.jsonl"
CAPACITY_REPORT_FILE = DATA_DIR / "capacity_report.json"


# ── ডেটা ক্লাসেস ──────────────────────────────────────────────────────
@dataclass
class ResourceSnapshot:
    """একটি সময়ে রিসোর্স ব্যবহারের স্ন্যাপশট"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    api_latency_ms: float
    api_status: str
    redis_connections: int | None = None
    db_connections: int | None = None
    request_queue_depth: int = 0
    render_free_minutes_used: int | None = None


@dataclass
class CapacityRecommendation:
    """স্কেলিং সুপারিশ"""
    action: str  # "scale_up", "scale_down", "maintain", "alert"
    reason: str
    confidence: float  # 0.0 - 1.0
    estimated_cost_impact: str
    suggested_replicas: int | None = None
    suggested_instance_type: str | None = None


@dataclass
class CapacityReport:
    """সম্পূর্ণ ক্যাপাসিটি রিপোর্ট"""
    generated_at: str
    overall_status: str  # "healthy", "warning", "critical"
    current_snapshot: ResourceSnapshot
    trends: dict[str, Any]
    recommendations: list[CapacityRecommendation]
    render_optimization: dict[str, Any]
    next_check_due: str


# ── হেল্পার ফাংশনস ────────────────────────────────────────────────────
def _mask(value: str, visible: int = 3) -> str:
    """সেনসিটিভ ভ্যালু মাস্ক করে"""
    if not value:
        return ""
    return value[:visible] + "*" * max(len(value) - visible, 0)


def _ensure_data_dir() -> None:
    """ডেটা ডিরেক্টরি নিশ্চিত করে"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_history(limit: int = DEFAULT_HISTORY_LIMIT) -> deque[dict[str, Any]]:
    """ইতিহাস লোড করে"""
    history: deque[dict[str, Any]] = deque(maxlen=limit)
    if not CAPACITY_HISTORY_FILE.exists():
        return history

    try:
        with open(CAPACITY_HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        history.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError as exc:
        logger.warning(f"History file read failed: {exc}")

    return history


def _append_history(snapshot: ResourceSnapshot) -> None:
    """ইতিহাসে নতুন এন্ট্রি যোগ করে"""
    _ensure_data_dir()
    try:
        with open(CAPACITY_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(snapshot), default=str) + "\n")
    except OSError as exc:
        logger.error(f"Failed to write history: {exc}")


def _calculate_trends(history: deque[dict[str, Any]]) -> dict[str, Any]:
    """ট্রেন্ড ক্যালকুলেট করে"""
    if len(history) < 2:
        return {
            "cpu_trend": "insufficient_data",
            "memory_trend": "insufficient_data",
            "latency_trend": "insufficient_data",
            "data_points": len(history),
        }

    recent = list(history)[-12:]  # Last hour (12 * 5min)
    older = list(history)[:-12] if len(history) > 12 else list(history)[: len(history) // 2]

    def _avg(key: str, data: list[dict]) -> float:
        vals = [d.get(key, 0) for d in data if isinstance(d.get(key), (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    cpu_recent = _avg("cpu_percent", recent)
    cpu_older = _avg("cpu_percent", older)
    mem_recent = _avg("memory_percent", recent)
    mem_older = _avg("memory_percent", older)
    lat_recent = _avg("api_latency_ms", recent)
    lat_older = _avg("api_latency_ms", older)

    return {
        "cpu_trend": "increasing" if cpu_recent > cpu_older * 1.1 else "decreasing" if cpu_recent < cpu_older * 0.9 else "stable",
        "memory_trend": "increasing" if mem_recent > mem_older * 1.1 else "decreasing" if mem_recent < mem_older * 0.9 else "stable",
        "latency_trend": "increasing" if lat_recent > lat_older * 1.2 else "decreasing" if lat_recent < lat_older * 0.8 else "stable",
        "cpu_change_percent": round((cpu_recent - cpu_older) / max(cpu_older, 0.01) * 100, 1),
        "memory_change_percent": round((mem_recent - mem_older) / max(mem_older, 0.01) * 100, 1),
        "latency_change_percent": round((lat_recent - lat_older) / max(lat_older, 0.01) * 100, 1),
        "data_points": len(history),
        "analysis_window_hours": len(recent) * 5 / 60,
    }


# ── রিসোর্স কালেক্টরস ─────────────────────────────────────────────────
def _collect_system_resources() -> dict[str, Any]:
    """সিস্টেম রিসোর্স কালেক্ট করে"""
    resources: dict[str, Any] = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "memory_used_mb": 0.0,
        "memory_total_mb": 0.0,
        "disk_percent": 0.0,
        "disk_used_gb": 0.0,
        "disk_total_gb": 0.0,
    }

    try:
        import psutil

        resources["cpu_percent"] = psutil.cpu_percent(interval=1.0)
        mem = psutil.virtual_memory()
        resources["memory_percent"] = mem.percent
        resources["memory_used_mb"] = round(mem.used / (1024 * 1024), 1)
        resources["memory_total_mb"] = round(mem.total / (1024 * 1024), 1)

        disk = psutil.disk_usage("/")
        resources["disk_percent"] = round(disk.percent, 1)
        resources["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
        resources["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
    except ImportError:
        logger.warning("psutil not installed — using fallback values")
        # Fallback: try reading from /proc (Linux only)
        try:
            with open("/proc/loadavg", "r") as f:
                load = f.read().split()
                resources["cpu_percent"] = float(load[0]) * 10  # rough estimate
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")
    except Exception as exc:
        logger.warning(f"Resource collection failed: {exc}")

    return resources


async def _check_api_latency(base_url: str, timeout: float = 5.0) -> tuple[float, str]:
    """API ল্যাটেন্সি চেক করে"""
    health_url = f"{base_url}/api/v1/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            start = time.perf_counter()
            response = await client.get(health_url)
            elapsed_ms = (time.perf_counter() - start) * 1000
            status = "healthy" if response.status_code == 200 else f"degraded_{response.status_code}"
            return round(elapsed_ms, 2), status
    except httpx.ConnectError:
        return -1.0, "unreachable"
    except httpx.TimeoutException:
        return -1.0, "timeout"
    except Exception as exc:
        logger.warning(f"API check failed: {exc}")
        return -1.0, "error"


async def _check_redis_connections() -> int | None:
    """Redis কানেকশন সংখ্যা চেক করে"""
    redis_url = os.getenv("REDIS_URL", os.getenv("UPSTASH_REDIS_REST_URL", ""))
    if not redis_url:
        return None

    try:
        # Try redis-py first
        import redis.asyncio as redis_lib
        r = redis_lib.from_url(redis_url, decode_responses=True)
        info = await r.info("clients")
        connected = info.get("connected_clients", 0)
        await r.aclose()
        return int(connected)
    except ImportError:
        # Fallback: REST API for Upstash
        try:
            token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
            if not token:
                return None
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{redis_url}/info/clients",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return int(resp.text) if resp.text.isdigit() else None
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")
    except Exception as exc:
        logger.debug(f"Redis check failed: {exc}")

    return None


async def _check_db_connections() -> int | None:
    """DB কানেকশন সংখ্যা চেক করে (PostgreSQL/Supabase)"""
    db_url = os.getenv("SUPABASE_DATABASE_URL_POOLER", settings.database_url)
    if not db_url:
        return None

    try:
        # Try asyncpg for direct PostgreSQL
        import asyncpg
        conn = await asyncpg.connect(dsn=db_url, timeout=5.0)
        row = await conn.fetchrow(
            "SELECT count(*) as connections FROM pg_stat_activity WHERE datname = current_database()"
        )
        count = row["connections"] if row else None
        await conn.close()
        return int(count) if count else None
    except Exception as exc:
        logger.debug(f"DB connection check failed: {exc}")

    return None


def _estimate_render_usage() -> int | None:
    """Render free tier usage estimate (minutes used this month)"""
    # Render free tier: 750 hours/month = 45,000 minutes
    render_service = os.getenv("RENDER_SERVICE_NAME", "")
    if not render_service:
        return None

    # Check if we can read from a tracked file
    tracker_file = DATA_DIR / "render_uptime_minutes.json"
    if tracker_file.exists():
        try:
            with open(tracker_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("minutes_used_this_month")
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")

    return None


# ── সুপারিশ ইঞ্জিন ─────────────────────────────────────────────────────
def _generate_recommendations(
    snapshot: ResourceSnapshot,
    trends: dict[str, Any],
    alert_threshold: float,
    critical_threshold: float,
) -> list[CapacityRecommendation]:
    """স্কেলিং সুপারিশ তৈরি করে"""
    recommendations: list[CapacityRecommendation] = []

    cpu = snapshot.cpu_percent
    mem = snapshot.memory_percent
    disk = snapshot.disk_percent
    latency = snapshot.api_latency_ms
    status = snapshot.api_status

    # Critical conditions
    if cpu >= critical_threshold or mem >= critical_threshold:
        recommendations.append(CapacityRecommendation(
            action="scale_up",
            reason=f"Critical resource usage: CPU {cpu:.1f}%, Memory {mem:.1f}%",
            confidence=0.95,
            estimated_cost_impact="HIGH — may exceed free tier, consider upgrading to Starter ($7/mo)",
            suggested_replicas=2,
            suggested_instance_type="starter",
        ))

    elif disk >= critical_threshold:
        recommendations.append(CapacityRecommendation(
            action="alert",
            reason=f"Disk usage critical: {disk:.1f}% — log rotation needed",
            confidence=0.90,
            estimated_cost_impact="LOW — cleanup logs and temp files",
        ))

    # Warning conditions
    elif cpu >= alert_threshold or mem >= alert_threshold:
        recommendations.append(CapacityRecommendation(
            action="scale_up",
            reason=f"High resource usage: CPU {cpu:.1f}%, Memory {mem:.1f}%",
            confidence=0.80,
            estimated_cost_impact="MEDIUM — monitor closely, enable caching",
            suggested_replicas=1,
            suggested_instance_type="free_with_caching",
        ))

    # Latency-based recommendations
    if latency > 1000 and status == "healthy":
        recommendations.append(CapacityRecommendation(
            action="scale_up",
            reason=f"High API latency: {latency:.0f}ms — consider async workers",
            confidence=0.75,
            estimated_cost_impact="MEDIUM — add background job queue",
        ))
    elif latency > 500:
        recommendations.append(CapacityRecommendation(
            action="maintain",
            reason=f"Elevated latency: {latency:.0f}ms — monitor trends",
            confidence=0.60,
            estimated_cost_impact="NONE — optimize queries first",
        ))

    # Trend-based proactive recommendations
    if trends.get("cpu_trend") == "increasing" and trends.get("cpu_change_percent", 0) > 20:
        recommendations.append(CapacityRecommendation(
            action="scale_up",
            reason=f"CPU trending up {trends['cpu_change_percent']:.1f}% — proactive scaling advised",
            confidence=0.70,
            estimated_cost_impact="LOW — preemptive scaling avoids downtime",
        ))

    if trends.get("memory_trend") == "increasing" and trends.get("memory_change_percent", 0) > 15:
        recommendations.append(CapacityRecommendation(
            action="alert",
            reason=f"Memory leak suspected: {trends['memory_change_percent']:.1f}% increase",
            confidence=0.65,
            estimated_cost_impact="LOW — investigate memory leaks",
        ))

    # Render-specific: if free tier nearly exhausted
    render_minutes = snapshot.render_free_minutes_used
    if render_minutes and render_minutes > 40000:  # ~89% of 45,000
        recommendations.append(CapacityRecommendation(
            action="alert",
            reason=f"Render free tier {render_minutes}/45000 minutes used ({render_minutes/45000*100:.1f}%)",
            confidence=0.85,
            estimated_cost_impact="HIGH — upgrade to Starter or add secondary instance",
        ))

    # Scale-down opportunity
    if cpu < 20 and mem < 30 and latency < 200 and status == "healthy":
        if trends.get("cpu_trend") == "stable" and trends.get("memory_trend") == "stable":
            recommendations.append(CapacityRecommendation(
                action="scale_down",
                reason="Resources underutilized — cost optimization possible",
                confidence=0.50,
                estimated_cost_impact="SAVINGS — reduce to minimum instance",
                suggested_replicas=1,
                suggested_instance_type="free",
            ))

    if not recommendations:
        recommendations.append(CapacityRecommendation(
            action="maintain",
            reason="All metrics within normal parameters",
            confidence=0.99,
            estimated_cost_impact="NONE",
        ))

    return recommendations


def _render_optimization_tips(snapshot: ResourceSnapshot) -> dict[str, Any]:
    """Render-specific অপটিমাইজেশন টিপস"""
    tips = {
        "keepalive_strategy": "ping every 14 minutes to prevent free-tier sleep",
        "secondary_instance": "Use supremeai-backend-secondary for zero-cost HA",
        "cron_schedule": "*/14 * * * * curl -s $BACKEND_URL/api/v1/health > /dev/null",
        "database": "Use Supabase connection pooler to reduce Render CPU load",
        "caching": "Enable Redis caching for repeated AI queries (semantic cache)",
        "static_assets": "Serve via Netlify CDN, not Render backend",
    }

    # Dynamic tips based on current state
    if snapshot.api_latency_ms > 500:
        tips["immediate_action"] = "Enable response caching or add async workers"
    if snapshot.memory_percent > 70:
        tips["immediate_action"] = "Restart instance or reduce worker processes"

    return tips


# ── অ্যালার্টিং ──────────────────────────────────────────────────────
async def _send_telegram_alert(message: str) -> None:
    """টেলিগ্রাম এলার্ট পাঠায়"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.debug("Telegram credentials missing — alert skipped")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"📊 *SupremeAI Capacity Alert* 📊\n\n{message}",
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info("✅ Telegram capacity alert sent")
            else:
                logger.warning(f"Telegram alert failed: {response.status_code}")
    except Exception as exc:
        logger.warning(f"Telegram send failed: {exc}")


def _write_github_summary(report: CapacityReport) -> None:
    """GitHub Step Summary তে রিপোর্ট লেখে"""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    status_emoji = {"healthy": "🟢", "warning": "🟡", "critical": "🔴"}.get(report.overall_status, "⚪")

    lines = [
        f"## {status_emoji} Capacity Planner Report",
        "",
        f"**Status:** `{report.overall_status.upper()}`",
        f"**Generated:** {report.generated_at}",
        "",
        "### Current Snapshot",
        "| Metric | Value |",
        "|--------|-------|",
        f"| CPU | {report.current_snapshot.cpu_percent:.1f}% |",
        f"| Memory | {report.current_snapshot.memory_percent:.1f}% ({report.current_snapshot.memory_used_mb:.0f}/{report.current_snapshot.memory_total_mb:.0f} MB) |",
        f"| Disk | {report.current_snapshot.disk_percent:.1f}% |",
        f"| API Latency | {report.current_snapshot.api_latency_ms:.1f} ms |",
        f"| API Status | {report.current_snapshot.api_status} |",
        "",
        "### Recommendations",
    ]

    for rec in report.recommendations:
        emoji = {"scale_up": "⬆️", "scale_down": "⬇️", "maintain": "✅", "alert": "⚠️"}.get(rec.action, "❓")
        lines.append(f"- {emoji} **{rec.action.upper()}**: {rec.reason}")
        lines.append(f"  - Confidence: {rec.confidence:.0%} | Cost Impact: {rec.estimated_cost_impact}")

    lines.extend([
        "",
        "### Render Optimization",
        "```",
        json.dumps(report.render_optimization, indent=2),
        "```",
        "",
        f"**Next Check:** {report.next_check_due}",
    ])

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        logger.warning(f"GitHub summary write failed: {exc}")


def _save_report(report: CapacityReport) -> None:
    """রিপোর্ট JSON এ সেভ করে"""
    _ensure_data_dir()
    try:
        with open(CAPACITY_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, default=str)
        logger.info(f"Report saved to {CAPACITY_REPORT_FILE}")
    except OSError as exc:
        logger.error(f"Report save failed: {exc}")


# ── মেইন লজিক ─────────────────────────────────────────────────────────
async def run_capacity_plan(
    base_url: str,
    alert_threshold: float,
    critical_threshold: float,
    dry_run: bool = False,
    verbose: bool = False,
) -> CapacityReport:
    """মেইন ক্যাপাসিটি প্ল্যানিং লজিক"""
    logger.info("🔍 Starting capacity planning analysis...")

    # Collect metrics
    sys_resources = _collect_system_resources()
    api_latency, api_status = await _check_api_latency(base_url)
    redis_conns = await _check_redis_connections()
    db_conns = await _check_db_connections()
    render_usage = _estimate_render_usage()

    snapshot = ResourceSnapshot(
        timestamp=datetime.now(UTC).isoformat(),
        cpu_percent=sys_resources["cpu_percent"],
        memory_percent=sys_resources["memory_percent"],
        memory_used_mb=sys_resources["memory_used_mb"],
        memory_total_mb=sys_resources["memory_total_mb"],
        disk_percent=sys_resources["disk_percent"],
        disk_used_gb=sys_resources["disk_used_gb"],
        disk_total_gb=sys_resources["disk_total_gb"],
        api_latency_ms=api_latency,
        api_status=api_status,
        redis_connections=redis_conns,
        db_connections=db_conns,
        render_free_minutes_used=render_usage,
    )

    if verbose:
        logger.info(f"Snapshot: CPU={snapshot.cpu_percent:.1f}%, MEM={snapshot.memory_percent:.1f}%, "
                   f"LAT={snapshot.api_latency_ms:.1f}ms, STATUS={snapshot.api_status}")

    # Load history and calculate trends
    history = _load_history()
    trends = _calculate_trends(history)

    if verbose:
        logger.info(f"Trends: CPU={trends.get('cpu_trend')}, MEM={trends.get('memory_trend')}, "
                   f"LAT={trends.get('latency_trend')}")

    # Generate recommendations
    recommendations = _generate_recommendations(
        snapshot, trends, alert_threshold, critical_threshold
    )

    # Determine overall status
    if snapshot.cpu_percent >= critical_threshold or snapshot.memory_percent >= critical_threshold or api_status in ("unreachable", "timeout"):
        overall_status = "critical"
    elif snapshot.cpu_percent >= alert_threshold or snapshot.memory_percent >= alert_threshold or snapshot.api_latency_ms > 1000:
        overall_status = "warning"
    else:
        overall_status = "healthy"

    # Render optimization
    render_tips = _render_optimization_tips(snapshot)

    # Build report
    report = CapacityReport(
        generated_at=datetime.now(UTC).isoformat(),
        overall_status=overall_status,
        current_snapshot=snapshot,
        trends=trends,
        recommendations=recommendations,
        render_optimization=render_tips,
        next_check_due=(datetime.now(UTC) + timedelta(seconds=DEFAULT_CHECK_INTERVAL)).isoformat(),
    )

    # Save history and report
    if not dry_run:
        _append_history(snapshot)
        _save_report(report)

    # Alerts for critical/warning
    if overall_status in ("critical", "warning"):
        alert_msg = (
            f"Status: {overall_status.upper()}\n"
            f"CPU: {snapshot.cpu_percent:.1f}%\n"
            f"Memory: {snapshot.memory_percent:.1f}%\n"
            f"API: {snapshot.api_status} ({snapshot.api_latency_ms:.1f}ms)\n"
            f"Primary Action: {recommendations[0].action}"
        )
        if not dry_run:
            await _send_telegram_alert(alert_msg)

    # GitHub summary
    _write_github_summary(report)

    return report


def _print_report(report: CapacityReport) -> None:
    """কনসোলে রিপোর্ট প্রিন্ট করে"""
    status_colors = {
        "healthy": "\033[92m",  # Green
        "warning": "\033[93m",  # Yellow
        "critical": "\033[91m",  # Red
    }
    reset = "\033[0m"
    color = status_colors.get(report.overall_status, "")
    status_str = f"{color}{report.overall_status.upper()}{reset}"

    print(f"\n{'='*60}")
    print("  📊 SUPREMEAI CAPACITY PLANNER REPORT")
    print(f"{'='*60}")
    print(f"  Status:        {status_str}")
    print(f"  Generated:     {report.generated_at}")
    print(f"  Next Check:      {report.next_check_due}")
    print(f"{'-'*60}")
    print(f"  CPU:             {report.current_snapshot.cpu_percent:.1f}%")
    print(f"  Memory:          {report.current_snapshot.memory_percent:.1f}% "
          f"({report.current_snapshot.memory_used_mb:.0f}/{report.current_snapshot.memory_total_mb:.0f} MB)")
    print(f"  Disk:            {report.current_snapshot.disk_percent:.1f}% "
          f"({report.current_snapshot.disk_used_gb:.1f}/{report.current_snapshot.disk_total_gb:.1f} GB)")
    print(f"  API Latency:     {report.current_snapshot.api_latency_ms:.1f} ms")
    print(f"  API Status:      {report.current_snapshot.api_status}")
    if report.current_snapshot.redis_connections is not None:
        print(f"  Redis Conns:     {report.current_snapshot.redis_connections}")
    if report.current_snapshot.db_connections is not None:
        print(f"  DB Conns:        {report.current_snapshot.db_connections}")
    print(f"{'-'*60}")
    print("  TRENDS:")
    for key, val in report.trends.items():
        print(f"    {key}: {val}")
    print(f"{'-'*60}")
    print("  RECOMMENDATIONS:")
    for i, rec in enumerate(report.recommendations, 1):
        action_color = {"scale_up": "\033[91m", "scale_down": "\033[94m", "maintain": "\033[92m", "alert": "\033[93m"}.get(rec.action, "")
        print(f"    {i}. {action_color}{rec.action.upper()}{reset}: {rec.reason}")
        print(f"       Confidence: {rec.confidence:.0%} | Cost: {rec.estimated_cost_impact}")
        if rec.suggested_replicas:
            print(f"       Suggested Replicas: {rec.suggested_replicas}")
    print(f"{'-'*60}")
    print("  RENDER OPTIMIZATION:")
    for key, val in report.render_optimization.items():
        print(f"    {key}: {val}")
    print(f"{'='*60}\n")


# ── CLI ────────────────────────────────────────────────────────────────
def main() -> int:
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="SupremeAI 2.0 — Auto-Scaling Capacity Planner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/monitoring/capacity_planner.py --url https://api.supremeai.com
  python scripts/monitoring/capacity_planner.py --alert-threshold 70 --critical-threshold 85
  python scripts/monitoring/capacity_planner.py --dry-run --verbose
  python scripts/monitoring/capacity_planner.py --daemon --interval 300
        """,
    )
    parser.add_argument("--url", default=DEFAULT_API_URL, help="Base API URL")
    parser.add_argument("--alert-threshold", type=float, default=DEFAULT_ALERT_THRESHOLD, help="Alert threshold %")
    parser.add_argument("--critical-threshold", type=float, default=DEFAULT_CRITICAL_THRESHOLD, help="Critical threshold %")
    parser.add_argument("--dry-run", action="store_true", help="Don't save history or send alerts")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=DEFAULT_CHECK_INTERVAL, help="Check interval in seconds (daemon mode)")

    args = parser.parse_args()

    if args.daemon:
        logger.info(f"🔄 Daemon mode started — checking every {args.interval}s")
        try:
            while True:
                report = asyncio.run(run_capacity_plan(
                    base_url=args.url,
                    alert_threshold=args.alert_threshold,
                    critical_threshold=args.critical_threshold,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                ))
                _print_report(report)
                logger.info(f"Sleeping for {args.interval}s...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user")
            return 0
    else:
        report = asyncio.run(run_capacity_plan(
            base_url=args.url,
            alert_threshold=args.alert_threshold,
            critical_threshold=args.critical_threshold,
            dry_run=args.dry_run,
            verbose=args.verbose,
        ))
        _print_report(report)

    # Exit codes: 0=healthy, 1=warning, 2=critical
    return {"healthy": 0, "warning": 1, "critical": 2}.get(report.overall_status, 1)


if __name__ == "__main__":
    sys.exit(main())
