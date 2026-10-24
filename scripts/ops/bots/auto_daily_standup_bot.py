#!/usr/bin/env python
"""
DEPRECATED: This bot is being replaced by the new Admin God Control Center's reporting module.
auto_daily_standup_bot.py
=========================
Automatically posts daily standup summaries to Discord and Slack channels.

Provides a summary of system activity, performance metrics, and key events
from the previous day to keep teams informed.

Environment Variables:
- DISCORD_WEBHOOK_URL: Discord webhook URL for standup posts
- SLACK_WEBHOOK_URL: Slack webhook URL for standup posts
- STANDUP_HOUR: Hour of day to post (0-23, default: 9 for 9 AM)
- STANDUP_MINUTE: Minute of hour to post (default: 0)
- TIMEZONE: Timezone for scheduling (default: UTC)
- INCLUDE_METRICS: Whether to include detailed metrics (default: true)
- INCLUDE_ERRORS: Whether to include error summaries (default: true)
- SERVICE_NAME: Name of this service instance (default: "SupremeAI-Standup")
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import schedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
STANDUP_HOUR = int(os.getenv("STANDUP_HOUR", "9"))  # 9 AM default
STANDUP_MINUTE = int(os.getenv("STANDUP_MINUTE", "0"))
TIMEZONE = os.getenv("TIMEZONE", "UTC")
INCLUDE_METRICS = os.getenv("INCLUDE_METRICS", "true").lower() == "true"
INCLUDE_ERRORS = os.getenv("INCLUDE_ERRORS", "true").lower() == "true"
SERVICE_NAME = os.getenv("SERVICE_NAME", "SupremeAI-Standup")

def save_standup_report(report_content: str) -> bool:
    """Saves the generated standup report to a shared location for the dashboard."""
    logger.info("Saving daily standup report for the admin dashboard.")
    try:
        # In a real implementation, this would save to a database or a file store like S3/GCS.
        # For now, we'll save it to a local file.
        report_dir = "/app/data/reports"
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"standup_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        logger.info(f"Standup report saved to {report_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save standup report: {e}")
        return False

def send_standup(message: str) -> bool:
    """Generate and save the standup report for the dashboard."""
    logger.info("Processing daily standup...")
    if save_standup_report(message):
        logger.info("Standup report successfully generated and stored.")
        return True
    else:
        logger.error("Failed to store standup report.")
        return False

def get_yesterday_stats() -> dict[str, Any]:
    """Get statistics for yesterday."""
    # In a real implementation, this would query your databases, logging systems, etc.
    # For this example, we'll return mock data

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    # Mock data - replace with actual queries to your systems
    stats = {
        "date": yesterday_str,
        "total_requests": 12450,
        "successful_requests": 12100,
        "failed_requests": 350,
        "avg_response_time_ms": 145,
        "peak_rpm": 850,
        "total_tokens": 2500000,
        "estimated_cost_usd": 12.50,
        "active_users": 45,
        "new_users": 8,
        "top_endpoints": [
            {"endpoint": "/api/v1/chat", "count": 5200, "avg_time": 120},
            {"endpoint": "/api/v1/embed", "count": 3100, "avg_time": 85},
            {"endpoint": "/api/v1/analyze", "count": 1800, "avg_time": 220},
            {"endpoint": "/api/v1/generate", "count": 1200, "avg_time": 350},
            {"endpoint": "/api/v1/translate", "count": 1150, "avg_time": 95}
        ],
        "error_summary": [
            {"type": "RateLimitError", "count": 120, "message": "Too many requests"},
            {"type": "ValidationError", "count": 95, "message": "Invalid input parameters"},
            {"type": "InternalError", "count": 75, "message": "Internal server error"},
            {"type": "TimeoutError", "count": 40, "message": "Request timeout"},
            {"type": "AuthError", "count": 20, "message": "Authentication failed"}
        ],
        "system_events": [
            {"time": "02:15", "event": "Deployed version 2.1.0 to production"},
            {"time": "14:30", "event": "Scaled up frontend due to traffic spike"},
            {"time": "22:45", "event": "Completed daily backup successfully"}
        ]
    }

    return stats

def format_feedback_card(title: str, items: list[dict[str, Any]], item_format_func) -> str:
    """Format a section of the report with a title and list of items."""
    if not items:
        return ""

    section = f"\n## {title}\n"
    for item in items:
        section += f"- {item_format_func(item)}\n"
    return section

def format_endpoint_stat(item: dict[str, Any]) -> str:
    """Format an endpoint statistics item."""
    return f"`{item['endpoint']}`: {item['count']:,} requests (avg {item['avg_time']}ms)"

def format_error_item(item: dict[str, Any]) -> str:
    """Format an error summary item."""
    return f"**{item['type']}**: {item['count']} occurrences - {item['message']}"

def format_event_item(item: dict[str, Any]) -> str:
    """Format a system event item."""
    return f"**{item['time']}**: {item['event']}"

def generate_standup_message() -> str:
    """Generate the daily standup message."""
    stats = get_yesterday_stats()

    # Header
    message = f"""# 📊 Daily Standup Report - {stats['date']}

Good morning! Here's what happened in the SupremeAI system yesterday:

## 📈 Overall Metrics
- **Total Requests:** {stats['total_requests']:,}
- **Successful Requests:** {stats['successful_requests']:,} ({100*stats['successful_requests']/max(stats['total_requests'],1):.1f}%)
- **Failed Requests:** {stats['failed_requests']:,} ({100*stats['failed_requests']/max(stats['total_requests'],1):.1f}%)
- **Average Response Time:** {stats['avg_response_time_ms']}ms
- **Peak RPM:** {stats['peak_rpm']:,}
- **Total Tokens Processed:** {stats['total_tokens']:,}
- **Estimated Cost:** ${stats['estimated_cost_usd']:.2f}
- **Active Users:** {stats['active_users']}
- **New Users:** {stats['new_users']}
"""

    # Add metrics section if enabled
    if INCLUDE_METRICS:
        message += format_feedback_card(
            "🔥 Top Endpoints by Usage",
            stats["top_endpoints"],
            format_endpoint_stat
        )

    # Add errors section if enabled
    if INCLUDE_ERRORS and stats.get("error_summary"):
        message += format_feedback_card(
            "❌ Error Summary",
            stats["error_summary"],
            format_error_item
        )

    # Add system events
    if stats.get("system_events"):
        message += format_feedback_card(
            "⚙️ System Events",
            stats["system_events"],
            format_event_item
        )

    # Footer
    message += f"""
---
*Report generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*
*Next report scheduled for {(datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=STANDUP_HOUR, minute=STANDUP_MINUTE, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""

    return message

def run_scheduler() -> None:
    """Run the scheduler loop."""
    # Schedule the daily standup
    schedule.every().day.at(f"{STANDUP_HOUR:02d}:{STANDUP_MINUTE:02d}").do(
        lambda: send_standup(generate_standup_message())
    ).timezone = timezone(timedelta(hours=int(TIMEZONE))) if TIMEZONE != "UTC" else timezone.utc

    print(f"⏰ Scheduled daily standup for {STANDUP_HOUR:02d}:{STANDUP_MINUTE:02d} {TIMEZONE}")

    # Send an immediate test run if requested
    if os.getenv("RUN_NOW", "false").lower() == "true":
        print("🚀 Running immediate test...")
        message = generate_standup_message()
        print("\n" + "="*50)
        print("TEST MESSAGE:")
        print("="*50)
        print(message)
        print("="*50)

        # Actually send it if not just testing
        if os.getenv("SEND_NOW", "false").lower() == "true":
            send_standup(message)
            print("✅ Test message sent!")
        return

    # Main loop
    print("🔄 Starting scheduler...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("\n⚠️  Received interrupt signal")
    except Exception as e:
        logger.error(f"Error in scheduler: {e}")

def main() -> int:
    """Main function."""
    print("📅 Starting Daily Standup Bot...")
    print("🔧 Configuration:")
    print(f"   • Scheduled time: {STANDUP_HOUR:02d}:{STANDUP_MINUTE:02d} {TIMEZONE}")
    print(f"   • Discord webhook: {'✅ Configured' if DISCORD_WEBHOOK_URL else '❌ Not configured'}")
    print(f"   • Slack webhook: {'✅ Configured' if SLACK_WEBHOOK_URL else '❌ Not configured'}")
    print(f"   • Include metrics: {'✅ Yes' if INCLUDE_METRICS else '❌ No'}")
    print(f"   • Include errors: {'✅ Yes' if INCLUDE_ERRORS else '❌ No'}")

    # Validate configuration
    if not DISCORD_WEBHOOK_URL and not SLACK_WEBHOOK_URL:
        print("⚠️  Warning: No webhook URLs configured - will only output to console")

    try:
        run_scheduler()
    except KeyboardInterrupt:
        print("\n⚠️  Received interrupt signal")
    except Exception as e:
        logger.error(f"Unexpected error in standup bot: {e}")
        return 1

    print("👋 Standup bot stopped")
    return 0

if __name__ == "__main__":
    sys.exit(main())
