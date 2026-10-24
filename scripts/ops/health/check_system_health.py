#!/usr/bin/env python
"""
scripts/health/check_system_health.py
======================================
SupremeAI 2.0 — একক, ক্যানোনিকাল (canonical) হেলথ-চেক স্ক্রিপ্ট।

এই স্ক্রিপ্টটি নিচের তিনটা পুরনো, ডুপ্লিকেট স্ক্রিপ্টকে replace করে:
  - scripts/health/auto_health_check.py       (এতিম/orphan, কোনো CI তে ছিল না)
  - scripts/health_check/auto_health_check.py (এতিম/orphan, mypy থেকে exclude করা ছিল)
  - backend/tools/health_checker.py           (এটার HealthChecker ক্লাস reuse করা হয়েছে,
                                                শুধু dependency/anomaly অংশটুকুর জন্য)

কী কী চেক করে:
  1. ডিপেন্ডেন্সি ও .env / DB ফাইল উপস্থিতি   (backend/tools/health_checker.HealthChecker)
  2. লাইভ API endpoint (/api/v1/health)
  3. লাইভ Database কানেকশন (async, database.session.AsyncSessionLocal)
  4. লাইভ Redis কানেকশন (core.config.settings.redis_url)
  5. ব্যর্থ হলে Telegram এ masked/সংক্ষিপ্ত এলার্ট পাঠায় (কোনো secret plaintext এ যায় না)

Exit code: 0 = সব ঠিক আছে, 1 = কোনো একটা সার্ভিস ডাউন (CI/cron এ ব্যবহারযোগ্য)

ব্যবহার:
    python scripts/health/check_system_health.py
    python scripts/health/check_system_health.py --skip-db --skip-redis   # লোকাল ডেভে দ্রুত চেক
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

# backend ডিরেক্টরিকে sys.path এ যোগ করা হচ্ছে, যাতে core.*, database.*, backend.tools.* ইম্পোর্ট করা যায়
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("health_check")

TIMEOUT = float(os.getenv("HEALTH_CHECK_TIMEOUT", "5"))
def _resolve_health_api_url() -> str:
    env_url = os.getenv("API_URL")
    if env_url:
        return env_url.rstrip("/") + ("/api/v1/health" if not env_url.endswith("/health") else "")
    try:
        from core.config import settings
        if getattr(settings, "backend_url", None):
            return settings.backend_url.rstrip("/") + "/api/v1/health"
        if getattr(settings, "auto_backend_url", None):
            return settings.auto_backend_url.rstrip("/") + "/api/v1/health"
        if hasattr(settings, "is_local") and settings.is_local():
            return "http://localhost:8000/api/v1/health"
    except Exception as _cfg_err:
        logger.debug(f"Config load error: {_cfg_err}")
    if os.getenv("ENV") in ("local", "dev", "development") or os.getenv("CI"):
        return "http://localhost:8000/api/v1/health"
    raise ValueError("Backend URL must be configured via settings or API_URL environment variable.")

API_URL = _resolve_health_api_url()


def _mask(value: str, visible: int = 3) -> str:
    """সেনসিটিভ ভ্যালুর শুধু প্রথম কয়েকটা ক্যারেক্টার দেখায়, বাকিটা মাস্ক করে দেয়।"""
    if not value:
        return ""
    return value[:visible] + "*" * max(len(value) - visible, 0)


async def send_telegram_alert(message: str) -> None:
    """টেলিগ্রাম বটের মাধ্যমে এলার্ট পাঠায়। টোকেন/চ্যাট আইডি না থাকলে চুপচাপ স্কিপ করে।"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram credentials সেট করা নেই (bot_token=%s) — alert স্কিপ করা হলো।", _mask(bot_token))
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🚨 *SupremeAI Health Alert* 🚨\n\n{message}",
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info("✅ Telegram alert সফলভাবে পাঠানো হয়েছে।")
            else:
                logger.error("❌ Telegram alert পাঠাতে ব্যর্থ: status=%s", response.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ Telegram alert পাঠাতে এরর: %s", exc)


import random


async def check_api(max_retries: int = 2) -> tuple[bool, str]:
    """API health endpoint লাইভ কিনা চেক করে (exponential backoff + jitter সহ)।"""
    last_error = "Unknown error"
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(API_URL)
                if response.status_code == 200:
                    return True, "OK"
                last_error = f"Status Code: {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

        if attempt < max_retries:
            # বাংলা: ব্যাকঅফ ও জিটার দিয়ে ক্ষণস্থায়ী নেটওয়ার্ক ফ্লিকার হ্যান্ডেল করা
            backoff = (0.5 * (2 ** attempt)) + random.uniform(0.1, 0.3)
            await asyncio.sleep(backoff)

    return False, last_error


async def check_database() -> tuple[bool, str]:
    """AsyncSessionLocal (database.session) ব্যবহার করে DB কানেকশন যাচাই করে।"""
    try:
        from database.session import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True, "Database connection successful."
    except ImportError as exc:
        return False, f"Missing database module: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Database query failed: {exc}"


async def check_redis() -> tuple[bool, str]:
    """core.config.settings.redis_url থেকে Redis কানেকশন যাচাই করে।"""
    try:
        from core.config import settings
        from redis.asyncio import Redis

        redis_url = getattr(settings, "redis_url", None) or os.getenv("REDIS_URL", "redis://dummy-redis-server:6379")
        client: Redis = Redis.from_url(redis_url, socket_timeout=TIMEOUT)
        try:
            await client.ping()
            return True, "Redis connection successful."
        finally:
            await client.aclose()
    except ImportError as exc:
        return False, f"Missing redis module: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Redis check failed: {exc}"


def check_dependencies_and_env() -> tuple[bool, str]:
    """backend/tools/health_checker.py এর HealthChecker রি-ইউজ করে dependency/.env/db-file চেক করে।"""
    try:
        from tools.health_checker import HealthChecker

        report = HealthChecker().run_health_check()
        ok = report.get("overall_status") == "HEALTHY"
        detail = f"status={report.get('overall_status')} deps={report.get('dependencies')}"
        return ok, detail
    except ImportError as exc:
        return False, f"HealthChecker ইম্পোর্ট করা যায়নি: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Dependency/env check error: {exc}"


async def run_health_check(skip_db: bool, skip_redis: bool, skip_deps: bool) -> int:
    logger.info("🚀 SupremeAI 2.0 — সিস্টেম হেলথ চেক শুরু হচ্ছে (Parallel Mode)...")

    alert_messages: list[str] = []
    checks_total = 0
    checks_passed = 0

    # ── ১. সমান্তরালে (Parallel) সব Async প্রোব এক্সিকিউট করা ──────────────
    async_tasks = []
    task_keys = []

    # API Check
    async_tasks.append(check_api())
    task_keys.append("api")

    # DB Check
    run_db = not skip_db and os.getenv("CI") != "true"
    if run_db:
        async_tasks.append(check_database())
        task_keys.append("db")
    else:
        logger.info("⏭️  Database চেক স্কিপ করা হলো (CI/--skip-db)।")

    # Redis Check
    if not skip_redis:
        async_tasks.append(check_redis())
        task_keys.append("redis")
    else:
        logger.info("⏭️  Redis চেক স্কিপ করা হলো (--skip-redis)।")

    # সমান্তরাল রান
    results = await asyncio.gather(*async_tasks, return_exceptions=True)

    for key, res in zip(task_keys, results):
        checks_total += 1
        if isinstance(res, Exception):
            ok, msg = False, str(res)
        else:
            ok, msg = res

        if key == "api":
            if ok:
                checks_passed += 1
                logger.info("✅ API Gateway সুস্থ (healthy)।")
            else:
                alert_messages.append(f"API Gateway ডাউন! Error: {msg}")
                logger.error("❌ API Gateway ডাউন: %s", msg)
        elif key == "db":
            if ok:
                checks_passed += 1
                logger.info("✅ Database কানেকশন সুস্থ।")
            else:
                alert_messages.append(f"Database ডাউন! Error: {msg}")
                logger.error("❌ Database সমস্যা: %s", msg)
        elif key == "redis":
            if ok:
                checks_passed += 1
                logger.info("✅ Redis কানেকশন সুস্থ।")
            else:
                alert_messages.append(f"Redis ডাউন! Error: {msg}")
                logger.error("❌ Redis সমস্যা: %s", msg)

    # ── ২. Dependencies / Env চেক ──────────────────────────────────────────
    if not skip_deps:
        checks_total += 1
        deps_ok, deps_msg = check_dependencies_and_env()
        if deps_ok:
            checks_passed += 1
            logger.info("✅ Dependencies ও .env ঠিক আছে।")
        else:
            alert_messages.append(f"Dependency/Env সমস্যা: {deps_msg}")
            logger.warning("⚠️  Dependency/Env warning: %s", deps_msg)

    # ── ৩. কমপোজিট হেলথ স্কোর ক্যালকুলেশন ─────────────────────────────────
    health_score = round((checks_passed / max(checks_total, 1)) * 100, 1)
    logger.info(f"📊 Composite Health Score: {health_score}% ({checks_passed}/{checks_total} checks passed)")

    # ── ৪. সমস্যা থাকলে Telegram এলার্ট ──────────────────────────────────
    if alert_messages:
        alert_payload = (
            f"Composite Score: {health_score}%\n\n" + "\n".join(alert_messages)
        )
        await send_telegram_alert(alert_payload)
        logger.error("🔥 এক বা একাধিক হেলথ চেক ফেইল করেছে।")
        return 1

    logger.info("🎉 সব সিস্টেম হেলথ চেক সফলভাবে পাস করেছে!")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="SupremeAI 2.0 unified system health check")
    parser.add_argument("--skip-db", action="store_true", help="Database চেক স্কিপ করুন")
    parser.add_argument("--skip-redis", action="store_true", help="Redis চেক স্কিপ করুন")
    parser.add_argument("--skip-deps", action="store_true", help="Dependency/.env চেক স্কিপ করুন")
    args = parser.parse_args()

    exit_code = asyncio.run(
        run_health_check(skip_db=args.skip_db, skip_redis=args.skip_redis, skip_deps=args.skip_deps)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
