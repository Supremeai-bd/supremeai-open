# backend/api/routes/webhooks_ai.py
"""
SupremeAI Interactive Telegram/Slack AI Webhook Router
Handles outgoing alerts with inline approval buttons and incoming callbacks.

Wave-1 security fix: আগে /callback ও /send-alert — দুটোই সম্পূর্ণ unauthenticated ছিল
(কেউ যেকোনো PR approve/reject করতে পারত) এবং /send-alert বাস্তবে কিছু না পাঠিয়েও
"status: sent" ফেরত দিত (False-Assurance)। এখন n8n_webhooks.py / cdc_webhooks.py-র
মতোই fail-closed secret verification ব্যবহার করা হয়েছে এবং পাঠানো সত্যিই হয়।
"""

import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from core.config import settings
from core.logging_config import logger

router = APIRouter(prefix="/api/v1/webhooks/telegram", tags=["Webhooks AI"])

# Telegram স্ট্যান্ডার্ড হেডার নাম (setWebhook secret_token স্কিম)
_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class AlertPayload(BaseModel):
    title: str
    description: str
    patch_code: str | None = None
    pr_id: str | None = None
    severity: str = "WARNING"


class CallbackQuery(BaseModel):
    callback_id: str
    user_id: str
    action: str  # "approve_pr" or "reject_pr"
    pr_id: str


async def _verify_telegram_secret(request: Request) -> bool:
    # বাংলা মন্তব্য: secret কনফিগার না থাকলে আগের মতো সব রিকোয়েস্ট গ্রহণ করা হবে না —
    # n8n/cdc-র মতো কঠোর fail-closed নীতি; অপারেটরকে জোরালোভাবে জানানো হচ্ছে।
    secret = settings.telegram_webhook_secret
    if not secret:
        logger.error(
            "TELEGRAM_WEBHOOK_SECRET is not configured! "
            "Rejecting all telegram AI hook requests under fail-closed policy."
        )
        return False

    provided = request.headers.get(_SECRET_HEADER, "")
    if not provided:
        logger.warning(f"Telegram AI hook rejected: missing {_SECRET_HEADER} header")
        return False

    # বাংলা মন্তব্য: timing attack এড়াতে constant-time comparison বাধ্যতামূলক।
    return hmac.compare_digest(provided.encode("utf-8"), secret.encode("utf-8"))


@router.post("/send-alert")
async def send_telegram_alert(payload: AlertPayload, request: Request) -> dict[str, Any]:
    """
    Send formatted alert message with inline buttons to Telegram chat.

    বাংলা মন্তব্য (honesty fix): আগে এই এন্ডপয়েন্ট কিছুই না পাঠিয়েও ভুয়া
    "status: sent" দিত। এখন বাস্তবে TelegramBotHandler.sendMessage ব্যবহার করে
    পাঠানো হয়; বট টোকেন/চ্যাট আইডি না থাকলে সৎ 503, পাঠানো ব্যর্থ হলে সৎ 502।
    """
    if not await _verify_telegram_secret(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing secret token",
        )

    inline_keyboard = [
        [
            {
                "text": "✅ Approve PR & Merge",
                "callback_data": f"approve_pr:{payload.pr_id or 'PR-001'}",
            },
            {"text": "❌ Reject", "callback_data": f"reject_pr:{payload.pr_id or 'PR-001'}"},
        ]
    ]

    message_text = f"⚠️ <b>{payload.severity}: {payload.title}</b>\n\n{payload.description}\n\n"
    if payload.patch_code:
        message_text += f"<b>Suggested Fix:</b>\n<code>{payload.patch_code[:500]}</code>\n"

    chat_id = str(settings.admin_telegram_chat_id or "").strip()

    # বাংলা মন্তব্য: বট টোকেন বা গন্তব্য চ্যাট কনফিগার না থাকলে ভুয়া সাফল্য নয় —
    # সৎ "not configured" ব্যর্থতা; লগে পরিষ্কারভাবে জানানো হচ্ছে কী সেট করতে হবে।
    try:
        from tools.social.telegram_bot.handler import TelegramBotHandler

        bot = TelegramBotHandler()
    except Exception as exc:
        logger.error(f"Telegram handler init failed while sending alert: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram alerting unavailable: handler init failed",
        ) from exc

    if not bot.configured or not chat_id:
        logger.error(
            "Telegram alert not sent: TELEGRAM_BOT_TOKEN or ADMIN_TELEGRAM_CHAT_ID "
            f"is not configured (bot_configured={bot.configured}, chat_id_set={bool(chat_id)})"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram alerting not configured: set TELEGRAM_BOT_TOKEN and "
            "ADMIN_TELEGRAM_CHAT_ID",
        )

    logger.info(f"📢 [Telegram AI] Sending alert: {payload.title} (PR: {payload.pr_id})")

    try:
        sent = await bot.send_message(
            chat_id,
            message_text,
            parse_mode="HTML",
            reply_markup={"inline_keyboard": inline_keyboard},
        )
    except Exception as exc:
        # বাংলা মন্তব্য: পাঠানোর সময় অপ্রত্যাশিত ব্যতিক্রমেও ভুয়া সাফল্য নিষিদ্ধ —
        # উঁচু লগ + সৎ 502; handler.send_message নিজেই ত্রুটি লগ করে False দেয়।
        logger.error(f"Telegram alert send raised unexpectedly: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Telegram alert send failed",
        ) from exc

    if not sent:
        logger.error(
            f"Telegram alert send failed for chat {chat_id} (PR: {payload.pr_id}) — "
            "reporting honest failure, not fake success"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Telegram alert send failed",
        )

    return {
        "status": "sent",
        "chat_id": chat_id,
        "message": message_text,
        "inline_keyboard": inline_keyboard,
    }


@router.post("/callback")
async def handle_telegram_callback(query: CallbackQuery, request: Request) -> dict[str, Any]:
    """
    Handle user interaction on Telegram inline keyboard buttons.

    বাংলা মন্তব্য (security fix): আগে এই এন্ডপয়েন্টে কোনো প্রমাণীকরণ ছিল না —
    যেকোনো ইন্টারনেট কলার PR approve/reject করতে পারত। এখন secret-token হেডার
    যাচাই বাধ্যতামূলক (fail-closed, constant-time)।
    """
    if not await _verify_telegram_secret(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing secret token",
        )

    logger.info(
        f"📥 [Telegram Callback] Action '{query.action}' by User '{query.user_id}' on PR '{query.pr_id}'"
    )

    if query.action == "approve_pr":
        # Trigger PR Pipeline / Auto-merge logic
        result = {
            "status": "approved",
            "pr_id": query.pr_id,
            "message": f"✅ PR {query.pr_id} approved by user {query.user_id}. Auto-merge initiated.",
        }
    elif query.action == "reject_pr":
        result = {
            "status": "rejected",
            "pr_id": query.pr_id,
            "message": f"❌ PR {query.pr_id} rejected by user {query.user_id}.",
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown action: {query.action}"
        )

    return result
