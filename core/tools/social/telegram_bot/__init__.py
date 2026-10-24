"""
SupremeAI 2.0 — Telegram Bot Handler (Production-Ready)

Features:
- Webhook support (recommended for production)
- Polling mode fallback (dev/local)
- /start, /help, /status, /admin commands
- Auto-routes to SupremeOrchestrator

Setup:
  1. Get token from @BotFather → /newbot
  2. Set TELEGRAM_BOT_TOKEN in .env
  3. For webhook: set TELEGRAM_WEBHOOK_URL = https://your-domain.com/telegram/webhook
  4. Register webhook:
     curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WEBHOOK_URL>"
"""

# ─────────────────────────────────────────────────────────────────────────────
# Package layout (split from the former 1,483-line single-module
# telegram_bot.py; every method/comment copied verbatim, no behavior change):
#   handler.py        — TelegramBotHandler core (COMMANDS, token bootstrap, Bot
#                       API helpers, sync entrypoint) + mixin composition
#   keyboards.py      — inline keyboard builders (user / admin / quick actions)
#   updates.py        — handle_update: callback-query & message dispatch incl.
#                       AutonoGuard injection guard + TOTP 2FA flow
#   conversations.py  — MCP clients, quick actions, telemetry, KB search,
#                       session menu, TOTP-authorized critical actions
#   admin_handlers.py — status, TelDrive vault/backup, brain, devops,
#                       security, rules panels
#   user_handlers.py  — user studio/desktop/vsix/skills/guide/build panels
#   ai_engine.py      — _ai_response (Gemini → Groq → orchestrator fallback)
#   runtime.py        — long-polling loop + webhook registration
#   router.py         — create_telegram_router + module-level `router`
#                       (import-time side effect preserved for FastAPI
#                       auto-discovery via api/routers.py)
#   __main__.py       — standalone polling entrypoint
#                       (python -m tools.social.telegram_bot)
# ─────────────────────────────────────────────────────────────────────────────

# Re-exports for exact module-attribute parity with the pre-split module
# (its module-level `from __future__ import annotations`,
# `from fastapi import APIRouter, Request, Response`, stdlib/typing imports
# and core settings/logger were importable attrs).
from __future__ import annotations  # noqa: F401

import asyncio  # noqa: F401
import contextlib  # noqa: F401
import os  # noqa: F401
from typing import Any, ClassVar  # noqa: F401

import httpx  # noqa: F401
from fastapi import APIRouter, Request, Response  # noqa: F401

from core.config import settings  # noqa: F401
from core.logging_config import logger  # noqa: F401

from .handler import TelegramBotHandler
from .router import create_telegram_router, router

__all__ = [
    "Any",
    "APIRouter",
    "ClassVar",
    "annotations",
    "Request",
    "Response",
    "TelegramBotHandler",
    "asyncio",
    "contextlib",
    "create_telegram_router",
    "httpx",
    "logger",
    "os",
    "router",
    "settings",
]
