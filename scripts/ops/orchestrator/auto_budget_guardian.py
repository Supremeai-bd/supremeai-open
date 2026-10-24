#!/usr/bin/env python
"""
auto_budget_guardian.py
=======================
Autonomous budget guardian for SupremeAI 2.0 free-tier providers.

Monitors free-tier usage across all AI providers and automatically pauses
any provider that exceeds 80% of its allocated quota (RPM, TPM, or RPD)
to prevent hard rate limits and service disruption.

Features:
- Periodic checks (every 5 minutes by default)
- Automatic pausing of providers at 80% threshold
- Automatic resumption after cooldown period (1 hour)
- Discord webhook notifications for alerts and recoveries
- Integration with existing FreeTierTracker singleton

Usage:
    python -m scripts.orchestrator.auto_budget_guardian
    # Or run as a background service
"""

"""
auto_budget_guardian.py
SupremeAI 2.0 Budget Guardian — Serverless-Ready Version.

ব্যবহার:
  1. Cloud Scheduler / Cron Job হিসেবে: প্রতি ৫ মিনিটে `run_budget_guardian_check()` কল করুন
  2. Persistent process হিসেবে: `main()` দিয়ে infinite loop চালান (শুধুমাত্র VM/Bare-metal এ)

Serverless (Cloud Run, Cloud Functions) পরিবেশে শুধুমাত্র `run_budget_guardian_check()`
ব্যবহার করতে হবে — প্রতিটি কল একটি স্বতন্ত্র stateless invocation, যা timeout খাবে না।
"""

import os

# Add the backend directory to the path so we can import from core
import sys
import time
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '../../backend'))

from core.llm.free_tier_tracker import get_tracker
from loguru import logger

# Configuration — ENV vars থেকে কনফিগারেশন নেওয়া হয়
CHECK_INTERVAL_SECONDS = int(os.getenv("BUDGET_GUARDIAN_INTERVAL", "300"))  # 5 minutes
THRESHOLD_PERCENT = float(os.getenv("BUDGET_GUARDIAN_THRESHOLD", "0.8"))   # 80%
PAUSE_DURATION_SECONDS = int(os.getenv("BUDGET_GUARDIAN_PAUSE_DURATION", "3600"))  # 1 hour
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Setup logging
logger.configure(
    handlers=[{"sink": sys.stderr, "level": "INFO"}]
)

def send_discord_notification(message: str) -> None:
    """Send a notification to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL:
        logger.debug("Discord webhook not configured, skipping notification")
        return

    try:
        import requests
        payload = {
            "content": f"🤖 **SupremeAI Budget Guardian Alert**\n{message}"
        }
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Discord notification sent successfully")
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")

def check_and_protect_budgets() -> None:
    """Check all providers and pause those exceeding threshold."""
    tracker = get_tracker()
    status = tracker.get_status()

    providers_to_pause: list[str] = []
    providers_to_resume: list[str] = []

    for provider_name, provider_status in status["providers"].items():
        # Skip if already paused (we don't want to double-pause)
        if provider_status.get("paused_until"):
            continue

        # Check each metric against threshold
        rpm_usage = provider_status["rpm_used"] / provider_status["rpm_limit"] if provider_status["rpm_limit"] > 0 else 0
        tpm_usage = provider_status["tpm_used"] / provider_status["tpm_limit"] if provider_status["tpm_limit"] > 0 else 0
        rpd_usage = provider_status["rpd_used"] / provider_status["rpd_limit"] if provider_status["rpd_limit"] > 0 else 0

        max_usage = max(rpm_usage, tpm_usage, rpd_usage)

        if max_usage >= THRESHOLD_PERCENT:
            providers_to_pause.append(provider_name)
            logger.warning(
                f"Provider {provider_name} exceeded {THRESHOLD_PERCENT*100}% usage: "
                f"RPM={rpm_usage:.2%}, TPM={tpm_usage:.2%}, RPD={rpd_usage:.2%}"
            )

    # Pause providers that are over threshold
    for provider in providers_to_pause:
        tracker._budgets[provider].pause(PAUSE_DURATION_SECONDS)
        provider_status = status["providers"][provider]
        msg = (
            f"🚨 **{provider.upper()} PAUSED** due to high usage\n"
            f"• RPM: {provider_status['rpm_used']}/{provider_status['rpm_limit']} "
            f"({provider_status['rpm_used']/provider_status['rpm_limit']*100:.1f}%)\n"
            f"• TPM: {provider_status['tpm_used']:,}/{provider_status['tpm_limit']:,} "
            f"({provider_status['tpm_used']/provider_status['tpm_limit']*100:.1f}%)\n"
            f"• RPD: {provider_status['rpd_used']}/{provider_status['rpd_limit']} "
            f"({provider_status['rpd_used']/provider_status['rpd_limit']*100:.1f}%)\n"
            f"• Paused for {PAUSE_DURATION_SECONDS//3600} hour(s)"
        )
        send_discord_notification(msg)
        logger.info(f"Paused {provider} for {PAUSE_DURATION_SECONDS} seconds")

    # Check for paused providers that might be ready to resume
    # (The tracker automatically resumes after pause duration, but we can log when they become available)
    for provider_name, provider_status in status["providers"].items():
        if provider_status.get("paused_until"):
            resume_time = datetime.fromtimestamp(provider_status["paused_until"])
            if datetime.now() >= resume_time:
                # It should have been auto-resumed by the tracker, but let's verify
                if tracker.is_available(provider_name):
                    providers_to_resume.append(provider_name)

    # Notify about resumed providers
    for provider in providers_to_resume:
        # We need to get the current status for this provider to report usage
        provider_status = status["providers"].get(provider, {})
        msg = (
            f"✅ **{provider.upper()} RESUMED** - Usage back below threshold\n"
            f"• RPM: {provider_status.get('rpm_used', 0)}/{provider_status.get('rpm_limit', 0)} "
            f"({provider_status.get('rpm_used', 0)/max(provider_status.get('rpm_limit', 1), 1)*100:.1f}%)\n"
            f"• TPM: {provider_status.get('tpm_used', 0):,}/{provider_status.get('tpm_limit', 0):,} "
            f"({provider_status.get('tpm_used', 0)/max(provider_status.get('tpm_limit', 1), 1)*100:.1f}%)\n"
            f"• RPD: {provider_status.get('rpd_used', 0)}/{provider_status.get('rpd_limit', 0)} "
            f"({provider_status.get('rpd_used', 0)/max(provider_status.get('rpd_limit', 1), 1)*100:.1f}%)"
        )
        send_discord_notification(msg)
        logger.info(f"Provider {provider} has resumed service")

def run_budget_guardian_check() -> None:
    """Execute a single budget guard check - designed to be called by external schedulers."""
    import asyncio

    from core.config_cache import config_cache

    now = int(time.time())

    # Idempotency check: skip if ran within the last 60 seconds
    try:
        last_run = config_cache.get("budget_guardian_last_run", 0)
        if last_run and now - int(last_run) < 60:
            logger.info("Budget guardian already ran in the last minute. Skipping duplicate execution.")
            return

        asyncio.run(config_cache.set("budget_guardian_last_run", now))
    except Exception as cache_err:
        logger.warning(f"Failed to check/set idempotency via ConfigCache: {cache_err}")

    try:
        check_and_protect_budgets()
    except Exception as e:
        logger.error(f"Error in budget guardian check: {e}")
        if DISCORD_WEBHOOK_URL:
            try:
                import requests
                payload = {
                    "content": f"🆘 **Budget Guardian Check Failed**\n```{e!s}```"
                }
                requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            except Exception as notify_err:
                logger.error(f"Failed to send Discord error notification (non-blocking): {notify_err}")

if __name__ == "__main__":
    logger.info("Starting SupremeAI Stateless Budget Guardian Check...")
    run_budget_guardian_check()
