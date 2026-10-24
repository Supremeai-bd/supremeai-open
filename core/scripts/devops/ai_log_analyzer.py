import logging
import os

import httpx

from core.logging_config import logger

# Configure standard logging
logging.basicConfig(level=logging.INFO)

# Configuration
RENDER_API_KEY = os.getenv("RENDER_API_KEY")
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID")  # e.g. srv-cxxx
SUPREMEAI_API_KEY = os.getenv("SUPREMEAI_API_KEY")  # Optional: Used for the AI analysis
INTERNAL_API_URL = os.getenv("INTERNAL_API_URL", "http://localhost:8000")  # is_local()


def fetch_render_logs():
    """Fetch recent logs from Render API"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        logger.warning("RENDER_API_KEY or RENDER_SERVICE_ID missing. Skipping log fetch.")
        return []

    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/logs"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}

    try:
        response = httpx.get(url, headers=headers, params={"limit": 100})
        response.raise_for_status()
        logs = response.json()

        # Filter for error logs
        error_logs = [
            log["log"]
            for log in logs
            if "error" in log.get("log", "").lower() or "exception" in log.get("log", "").lower()
        ]
        return error_logs
    except Exception as e:
        logger.error(f"Failed to fetch Render logs: {e}")
        return []


def analyze_with_ai(logs):
    """Placeholder for SupremeAI LLM analysis."""
    if not logs:
        return "No errors found."

    # In a full implementation, this would call the SupremeAI LLM endpoint
    # to provide a Root Cause Analysis.
    # For now, we perform a naive analysis.
    log_text = "\n".join(logs[-10:])  # Take last 10 errors

    if "Connection refused" in log_text:
        return "Root Cause Analysis: Database connection refused. Check Supabase pooler."
    if "Timeout" in log_text:
        return "Root Cause Analysis: Endpoint timeout. Possible infinite loop or slow query."

    return f"Root Cause Analysis: Anomalies detected. Requires manual inspection.\nPreview:\n{log_text[:200]}"


def alert_webhook(analysis):
    """Send analysis to Internal Admin Dashboard Alerts API"""
    if not SUPREMEAI_API_KEY:
        logger.warning("SUPREMEAI_API_KEY not configured. Cannot save internal alert.")
        return

    try:
        payload = {"level": "error", "message": f"🚨 **Auto-Healing Report**\n\n{analysis}"}
        headers = {"x-api-key": SUPREMEAI_API_KEY, "Content-Type": "application/json"}

        url = f"{INTERNAL_API_URL.rstrip('/')}/api/v1/admin/alerts"
        response = httpx.post(url, json=payload, headers=headers)
        response.raise_for_status()
        logger.info("Sent AI analysis to Internal Admin Dashboard.")
    except Exception as e:
        logger.error(f"Failed to send internal alert: {e}")


def main():
    logger.info("Starting AI Observability Log Analyzer...")
    error_logs = fetch_render_logs()

    if error_logs:
        logger.info(f"Found {len(error_logs)} error log entries. Running AI analysis...")
        analysis = analyze_with_ai(error_logs)
        alert_webhook(analysis)
    else:
        logger.info("System is healthy. No errors found.")


if __name__ == "__main__":
    main()
