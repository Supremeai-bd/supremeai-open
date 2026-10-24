"""FastAPI webhook router for the Telegram bot (verbatim split artifact
of the former single-module telegram_bot.py).

Holds the import-time side effect from the original file —
``router = create_telegram_router(TelegramBotHandler())`` — re-exported
by the package so FastAPI auto-discovery (api/routers.py registry,
``importlib.import_module('tools.social.telegram_bot')`` → ``.router``)
keeps working unchanged.

Wave-1 security fix: /webhook আগে Telegram-এর X-Telegram-Bot-Api-Secret-Token
হেডার কখনোই যাচাই করত না (যেকোনো কলার ভুয়া update ঢুকিয়ে দিতে পারত) এবং
/health বটের আসল identity (get_me) পাবলিকলি ফাঁস করত। এখন secret যাচাই
fail-closed + constant-time, এবং /health শুধু honest configured স্টেট দেয়।
"""

from __future__ import annotations

import asyncio
import hmac

from fastapi import APIRouter, Request, Response  # FIX: must be module-level — see below

from core.config import settings
from core.logging_config import logger

from .handler import TelegramBotHandler

# FIX (final-test ci-fixes): ``from __future__ import annotations`` এর কারণে endpoint-এর
# ``request: Request`` annotation string ("Request") হয়ে যায়। FastAPI সেটা module globals
# থেকে resolve করে — কিন্তু import টা create_telegram_router()-এর LOCAL scope-এ ছিল,
# ফলে ForwardRef('Request') unresolved থেকে OpenAPI build ক্র্যাশ করত
# (PydanticUserError: TypeAdapter ... not fully defined → /openapi.json 500)।
# তাই Request/APIRouter/Response এখন module-level।

# Telegram স্ট্যান্ডার্ড সিক্রেট হেডার (setWebhook secret_token স্কিম)
_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

# ── FastAPI webhook endpoint helper ──────────────────────────────


def create_telegram_router(handler: TelegramBotHandler):
    """Returns a FastAPI router for Telegram webhook endpoint."""
    router = APIRouter(prefix="/telegram", tags=["telegram"])
    _webhook_background_tasks: set[asyncio.Task] = set()

    @router.post("/webhook")
    async def telegram_webhook(request: Request):
        # বাংলা মন্তব্য (Wave-1 security fix): HTTP সীমানায় secret-token যাচাই —
        # internal caller (polling loop সরাসরি handle_update কল করে) অপরিবর্তিত থাকবে।
        # secret কনফিগার না থাকলে n8n/cdc-র মতোই কঠোর fail-closed: কোনো update গ্রহণ নয়।
        secret = settings.telegram_webhook_secret
        if not secret:
            logger.error(
                "TELEGRAM_WEBHOOK_SECRET is not configured! "
                "Rejecting all Telegram updates under fail-closed policy — "
                "set this env var to enable the endpoint."
            )
            return Response(status_code=401)

        provided = request.headers.get(_SECRET_HEADER, "")
        if not provided or not hmac.compare_digest(
            provided.encode("utf-8"), secret.encode("utf-8")
        ):
            logger.warning(f"Telegram update rejected: missing/invalid {_SECRET_HEADER} header")
            return Response(status_code=401)

        update = await request.json()
        task = asyncio.create_task(handler.handle_update(update))
        _webhook_background_tasks.add(task)
        task.add_done_callback(_webhook_background_tasks.discard)
        return Response(status_code=200)

    @router.get("/health")
    async def telegram_health():
        # বাংলা মন্তব্য (Wave-1 security fix): আগে get_me() দিয়ে বটের আসল identity
        # (username, id, name) পাবলিক এন্ডপয়েন্ট থেকে ফাঁস হত। এখন শুধু সৎ
        # configured/not_configured স্টেট — কোনো bot identity leak নেই।
        configured = handler.configured
        return {
            "status": "ok" if configured else "not_configured",
            "configured": configured,
        }

    return router


# Module-level router exported for FastAPI auto-discovery
router = create_telegram_router(TelegramBotHandler())
