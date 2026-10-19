"""
cookie_sync_scheduler.py — Auto-sync AI fleet cookies to Infisical every N hours.

Runs sync_cookies_to_infisical.export_and_sync() on a fixed interval
(default 6h, override via SYNC_INTERVAL_HOURS). Sends a Telegram alert to the
superadmin on failure (session expired, sync error, missing config).

Env:
  SYNC_INTERVAL_HOURS   (default 6)
  TELEGRAM_BOT_TOKEN     (optional; alerts skipped if unset)
  TELEGRAM_SUPERADMIN_CHAT_ID (optional)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sync_cookies_to_infisical import export_and_sync
except ImportError:  # pragma: no cover - package context
    from .sync_cookies_to_infisical import export_and_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cookie_sync_scheduler")

INTERVAL_HOURS = float(os.getenv("SYNC_INTERVAL_HOURS", "6"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_SUPERADMIN_CHAT_ID", "").strip()


def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured; skipping alert: %s", text)
        return
    url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Telegram alert sent (HTTP %s)", resp.status)
    except Exception as exc:  # noqa: BLE001
        logger.error("Telegram alert failed: %s", exc)


async def run_once() -> bool:
    try:
        result = await export_and_sync()
        logger.info("Sync OK: %s", result)
        if result.get("expired"):
            send_telegram("⚠️ SupremeAI cookie sync: AI fleet session appears EXPIRED (%d AI cookies). Re-login required." % result.get("ai_cookies", 0))
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Sync FAILED: %s", exc)
        send_telegram("🚨 SupremeAI cookie sync FAILED: %s" % str(exc)[:300])
        return False


async def main() -> None:
    logger.info("Cookie sync scheduler started (interval=%sh)", INTERVAL_HOURS)
    while True:
        await run_once()
        sleep_s = INTERVAL_HOURS * 3600
        logger.info("Sleeping %s seconds until next sync...", sleep_s)
        await asyncio.sleep(sleep_s)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")
