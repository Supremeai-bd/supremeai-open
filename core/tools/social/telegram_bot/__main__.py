"""Standalone polling entrypoint — ``python -m tools.social.telegram_bot``
(verbatim split artifact of the former single-module telegram_bot.py)."""

from __future__ import annotations

import asyncio

from .handler import TelegramBotHandler

# ── Standalone entrypoint ─────────────────────────────────────────

if __name__ == "__main__":
    handler = TelegramBotHandler()
    asyncio.run(handler.run_polling())
