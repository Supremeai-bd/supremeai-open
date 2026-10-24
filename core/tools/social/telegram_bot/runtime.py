"""Delivery runtime for :class:`TelegramBotHandler`
(verbatim split artifact of the former single-module telegram_bot.py).

Long-polling loop (dev/local) and webhook registration helper.
"""

from __future__ import annotations

import asyncio

import httpx

from core.logging_config import logger


class RuntimeMixin:
    """Polling/webhook-runtime mixin for :class:`TelegramBotHandler`."""

    # ── Polling mode (dev/local) ─────────────────────────────────

    async def run_polling(self) -> None:
        """Long-polling loop — receives updates and callback queries in real time."""
        if not self.configured:
            logger.warning("Telegram bot not configured — skipping polling.")
            return

        # Delete any conflicting webhook so getUpdates works cleanly
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(f"{self.api_base}/deleteWebhook")
                logger.info("Cleared Telegram Webhook for polling mode.")
        except Exception as e:
            logger.warning(f"deleteWebhook notice: {e}")

        logger.info("🤖 SupremeAI Telegram long-polling loop active...")
        offset = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=35) as client:
                    resp = await client.get(
                        f"{self.api_base}/getUpdates",
                        params={
                            "offset": offset,
                            "timeout": 25,
                            "allowed_updates": ["message", "callback_query"],
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        for update in updates:
                            offset = update["update_id"] + 1
                            asyncio.create_task(self.handle_update(update))
            except Exception as exc:
                logger.error(f"Telegram polling error: {exc}")
                await asyncio.sleep(2)

    async def start_webhook(self, webhook_url: str):
        """Register Telegram Webhook to point to live backend endpoint."""
        if not self.bot_token:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url, json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]}
                )
                if resp.status_code == 200:
                    logger.info(f"Successfully registered Telegram Webhook to {webhook_url}")
                else:
                    logger.error(f"Failed to register webhook: {resp.text}")
        except Exception as e:
            logger.error(f"Webhook setup exception: {e}")
