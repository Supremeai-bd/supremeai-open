#!/usr/bin/env python
"""
DEPRECATED: This bot is being replaced by the new Admin God Control Center.
auto_alert_bot.py
=================
Automatically sends alerts to Discord and Slack channels for system events.

Monitors various system health indicators and sends notifications when
thresholds are exceeded or important events occur.

Environment Variables:
- DISCORD_WEBHOOK_URL: Discord webhook URL for alerts
- SLACK_WEBHOOK_URL: Slack webhook URL for alerts
- ALERTICALERTS_ENABLED: Whether to enable alerts (default: true)
- CHECK_INTERVAL: How often to check for alerts in seconds (default: 300)
- BUDGET_ALERT_THRESHOLD: Percentage for budget alerts (default: 0.8)
- SYSTEM_HEALTH_CHECK_URL: URL to check system health (optional)
- SERVICE_NAME: Name of this service instance (default: "SupremeAI-Bot")
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
ALERTS_ENABLED = os.getenv("ALERTS_ENABLED", "true").lower() == "true"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 minutes
BUDGET_ALERT_THRESHOLD = float(os.getenv("BUDGET_ALERT_THRESHOLD", "0.8"))  # 80%
SYSTEM_HEALTH_CHECK_URL = os.getenv("SYSTEM_HEALTH_CHECK_URL")
SERVICE_NAME = os.getenv("SERVICE_NAME", "SupremeAI-Bot")

def record_event_to_db(message: str, title: str, alert_type: str) -> bool:
    """Records an event to the database for the new Admin Dashboard."""
    logger.info(f"Recording event: [{alert_type.upper()}] {title} - {message}")
    try:
        # In a real implementation, this would use a proper DB client.
        # For now, we'll just log it to a file as a placeholder.
        log_path = "/app/data/dashboard_events.jsonl"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": alert_type,
                "title": title,
                "message": message,
                "source": SERVICE_NAME
            }) + "\n")
        return True
    except Exception as e:
        logger.error(f"Failed to record event to DB: {e}")
        return False

def send_alert(message: str, title: str | None = None, alert_type: str = "info") -> bool:
    """Records an alert to the internal system for the dashboard."""
    if not ALERTS_ENABLED:
        logger.debug("Alerts are disabled")
        return False
    return record_event_to_db(message, title, alert_type)

def check_budget_alerts() -> bool:
    """Check for budget-related alerts."""
    try:
        # Import the budget guardian to check status
        import sys
        sys.path.append('/app/scripts/orchestrator')
        from auto_budget_guardian import get_tracker

        tracker = get_tracker()
        status = tracker.get_status()

        alerts_sent = False

        for provider_name, provider_status in status["providers"].items():
            # Check each metric against threshold
            rpm_usage = provider_status["rpm_used"] / provider_status["rpm_limit"] if provider_status["rpm_limit"] > 0 else 0
            tpm_usage = provider_status["tpm_used"] / provider_status["tpm_limit"] if provider_status["tpm_limit"] > 0 else 0
            rpd_usage = provider_status["rpd_used"] / provider_status["rpd_limit"] if provider_status["rpd_limit"] > 0 else 0

            max_usage = max(rpm_usage, tpm_usage, rpd_usage)

            if max_usage >= BUDGET_ALERT_THRESHOLD:
                alert_msg = (
                    f"🚨 **Budget Alert** for {provider_name.upper()}\n"
                    f"Usage has exceeded {BUDGET_ALERT_THRESHOLD*100}% threshold\n"
                    f"• RPM: {provider_status['rpm_used']}/{provider_status['rpm_limit']} "
                    f"({rpm_usage*100:.1f}%)\n"
                    f"• TPM: {provider_status['tpm_used']:,}/{provider_status['tpm_limit']:,} "
                    f"({tpm_usage*100:.1f}%)\n"
                    f"• RPD: {provider_status['rpd_used']}/{provider_status['rpd_limit']} "
                    f"({rpd_usage*100:.1f}%)"
                )

                if send_alert(alert_msg, f"Budget Alert: {provider_name}", "error"):
                    alerts_sent = True

        return alerts_sent
    except Exception as e:
        logger.error(f"Error checking budget alerts: {e}")
        return False

def check_system_health() -> bool:
    """Check system health via HTTP endpoint."""
    if not SYSTEM_HEALTH_CHECK_URL:
        return False

    try:
        response = requests.get(SYSTEM_HEALTH_CHECK_URL, timeout=10)
        if response.status_code == 200:
            # System is healthy
            return False
        else:
            alert_msg = (
                f"🏥 **System Health Alert**\n"
                f"Health check endpoint returned status {response.status_code}\n"
                f"URL: {SYSTEM_HEALTH_CHECK_URL}\n"
                f"Response: {response.text[:200]}..."
            )
            return send_alert(alert_msg, "System Health Issue", "warning")
    except requests.exceptions.RequestException as e:
        alert_msg = (
            f"🏥 **System Health Alert**\n"
            f"Failed to reach health check endpoint: {e!s}\n"
            f"URL: {SYSTEM_HEALTH_CHECK_URL}"
        )
        return send_alert(alert_msg, "System Health Issue", "error")
    except Exception as e:
        logger.error(f"Error checking system health: {e}")
        return False

def check_log_errors() -> bool:
    """Check for recent errors in application logs."""
    # This would typically involve querying a logging service like Cloud Logging, ELK, etc.
    # For simplicity, we'll simulate this with a placeholder
    # In a real implementation, you would:
    # 1. Query your logging backend for recent ERROR-level logs
    # 2. If any found, send a summary alert

    # Placeholder implementation
    return False

def send_startup_notification() -> bool:
    """Send a notification that the bot has started."""
    message = (
        f"🤖 **{SERVICE_NAME} Started**\n"
        f"Monitoring system health and budget thresholds\n"
        f"Check interval: {CHECK_INTERVAL} seconds\n"
        f"Budget alert threshold: {BUDGET_ALERT_THRESHOLD*100}%\n"
        f"Discord alerts: {'✅ Enabled' if DISCORD_WEBHOOK_URL else '❌ Disabled'}\n"
        f"Slack alerts: {'✅ Enabled' if SLACK_WEBHOOK_URL else '❌ Disabled'}"
    )

    return send_alert(message, "Alert Bot Started", "info")

def send_shutdown_notification() -> bool:
    """Send a notification that the bot is stopping."""
    message = f"🛑 **{SERVICE_NAME} Stopped**\nMonitoring has ceased."
    return send_alert(message, "Alert Bot Stopped", "info")

def main() -> int:
    """Main monitoring loop."""
    print("🚨 Starting SupremeAI Alert Bot...")
    print("🔧 Configuration:")
    print(f"   • Check interval: {CHECK_INTERVAL} seconds")
    print(f"   • Budget alert threshold: {BUDGET_ALERT_THRESHOLD*100}%")
    print(f"   • Discord alerts: {'✅ Enabled' if DISCORD_WEBHOOK_URL else '❌ Disabled'}")
    print(f"   • Slack alerts: {'✅ Enabled' if SLACK_WEBHOOK_URL else '❌ Disabled'}")
    print(f"   • System health check: {'✅ Enabled' if SYSTEM_HEALTH_CHECK_URL else '❌ Disabled'}")

    # Send startup notification
    if ALERTS_ENABLED:
        send_startup_notification()

    try:
        while True:
            print(f"🔍 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for alerts...")

            alerts_triggered = False

            # Check budget alerts
            if check_budget_alerts():
                alerts_triggered = True
                print("   💰 Budget alerts processed")

            # Check system health
            if check_system_health():
                alerts_triggered = True
                print("   🏥 System health alerts processed")

            # Check for log errors (if implemented)
            # if check_log_errors():
            #     alerts_triggered = True
            #     print("   📝 Log error alerts processed")

            if not alerts_triggered:
                print("   ✅ No alerts triggered")

            # Wait for next check
            print(f"😴 Sleeping for {CHECK_INTERVAL} seconds...")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n⚠️  Received interrupt signal")
    except Exception as e:
        logger.error(f"Unexpected error in alert bot: {e}")
        if ALERTS_ENABLED:
            send_alert(f"💥 **{SERVICE_NAME} Crashed**\n```{e!s}```", "Alert Bot Error", "error")
        return 1
    finally:
        # Send shutdown notification
        if ALERTS_ENABLED:
            send_shutdown_notification()

    print("👋 Alert bot stopped")
    return 0

if __name__ == "__main__":
    sys.exit(main())
