"""
service/telegram_webhook.py — SupremeAI Telegram Inbound Webhook Listener.

Routes strategic Telegram queries (#gemini, /spark, !gemini, /idea) directly to
the SupremeAI Gemini Engine / Dynamic Squad, formats executive briefs,
and delivers responses with auto-chunking back to Telegram.
"""
from __future__ import annotations

import logging
import os
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Request, Response, status
import httpx

try:
    from service.pool import squad
    from service.providers.adapters import forward_chat_completion, forward_stealth_webhook
except ImportError:
    squad = None  # type: ignore[assignment]
    forward_chat_completion = None  # type: ignore[assignment]
    forward_stealth_webhook = None  # type: ignore[assignment]

logger = logging.getLogger("supremeai.telegram_webhook")

telegram_router = APIRouter(tags=["telegram"])

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

TRIGGER_TAGS = ["#gemini", "!gemini", "/spark", "/idea"]

SYSTEM_PROMPT = """You are the SupremeAI Strategy Agent powered by Gemini.
When the user sends a project idea or architecture question, provide a structured,
high-impact executive brief in Bengali and English. Keep it concise, clear, and actionable.
Structure:
1. Concept & Global Origin
2. Direct Benefit for SupremeAI
3. Optimal Implementation Roadmap
"""


async def send_telegram_message(
    chat_id: int | str,
    text: str,
    reply_to_message_id: Optional[int] = None
) -> bool:
    """Delivers formatted message chunks to Telegram, with markdown and plain text fallback."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured; cannot deliver message.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Auto-chunking for Telegram's 4096 character limit (safe margin at 3800)
    chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)] if len(text) > 3800 else [text]

    async with httpx.AsyncClient(timeout=15.0) as client:
        success = True
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
            }
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id

            try:
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    # Markdown parsing failed on special chars; retry plain text
                    payload.pop("parse_mode", None)
                    res2 = await client.post(url, json=payload)
                    if res2.status_code != 200:
                        logger.error(f"Failed to deliver Telegram chunk: {res2.text}")
                        success = False
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Telegram network delivery error: {exc}")
                success = False

        return success


async def query_strategy_ai(prompt: str) -> str:
    """
    1. Priority-1: Queries $0 Stealth Engine (Ghost Tower / Web AI / Cloudflare Worker).
    2. Priority-2: Falls back to Gemini 2.5 API Key.
    3. Priority-3: Falls over to the 35-key Dynamic Squad pool.
    """
    # 0. Priority-1: Check $0 Stealth Engine with OpenAI chat messages structure
    stealth_url = os.getenv("STEALTH_WEBHOOK_URL", os.getenv("UPSTREAM_WEBHOOK_URL", "")).strip()
    if stealth_url and forward_stealth_webhook:
        try:
            status_code, resp = await forward_stealth_webhook(
                stealth_url,
                os.getenv("STEALTH_WEBHOOK_SECRET"),
                {
                    "model": "auto",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=float(os.getenv("STEALTH_WEBHOOK_TIMEOUT", "6.0")),
            )
            if 200 <= status_code < 300 and isinstance(resp, dict):
                choices = resp.get("choices", [])
                if choices and isinstance(choices[0], dict) and "message" in choices[0]:
                    content = choices[0]["message"].get("content", "")
                    if content and str(content).strip():
                        return str(content).strip()
                if "reply" in resp and str(resp["reply"]).strip():
                    return str(resp["reply"]).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Stealth Priority-1 bypassed ({exc}), falling back to Gemini API...")

    # 1. Priority-2: Gemini native endpoint with healthy slot key
    gemini_pool = squad.pools.get("gemini") if squad else None
    healthy_gemini_slots = gemini_pool.healthy_slots if gemini_pool else []
    gemini_key = healthy_gemini_slots[0].key if healthy_gemini_slots else (
        os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1")
    )

    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={gemini_key}"
        payload = {
            "contents": [
                {"parts": [{"text": SYSTEM_PROMPT + "\n\nUser Question:\n" + prompt}]}
            ],
            "generationConfig": {"temperature": 0.4},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"]
                logger.warning(f"Direct Gemini call returned {res.status_code}, falling back to squad...")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Direct Gemini attempt failed ({exc}), falling back to squad...")

    # 2. Dynamic Squad Failover (Groq, OpenRouter, Mistral, OpenAI)
    if squad and forward_chat_completion:
        candidates = squad.get_candidate_slots(preferred_provider=None)
        chat_payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        }

        for provider, slot in candidates:
            try:
                status_code, response_data = await forward_chat_completion(provider, slot.key, chat_payload, timeout=20.0)
                if 200 <= status_code < 300 and isinstance(response_data, dict):
                    choices = response_data.get("choices", [])
                    if choices and isinstance(choices[0], dict) and "message" in choices[0]:
                        return choices[0]["message"].get("content", "")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Squad slot {slot.name} failed during telegram query: {exc}")

    return "⚠️ দুঃখিত, এই মুহূর্তে কোনো এআই প্রোভাইডার উপলব্ধ নেই। অনুগ্রহ করে কিছুক্ষণ পর চেষ্টা করুন।"


async def _process_and_reply(chat_id: int | str, text: str, msg_id: Optional[int] = None):
    """Background task to generate and reply without blocking Telegram webhook ACK."""
    # 1. Clean prompt
    clean_prompt = text
    for tag in TRIGGER_TAGS:
        clean_prompt = clean_prompt.replace(tag, "").strip()

    if not clean_prompt:
        help_msg = (
            "⚡ *[SPARK-STRATEGY] | #gemini*\n━━━━━━━━━━━━━━━━━━━\n"
            "অনুগ্রহ করে আপনার আইডিয়া বা বিষয়ের নাম লিখুন।\n\n"
            "💡 *উদাহরণ:*\n"
            "• `/spark latency optimization roadmap`\n"
            "• `#gemini নতুন ফিচারের আইডিয়া`\n"
            "• `/idea hybrid multi-agent consensus`"
        )
        await send_telegram_message(chat_id, help_msg, reply_to_message_id=msg_id)
        return

    logger.info(f"Processing Telegram strategy query for chat {chat_id}: {clean_prompt[:60]}...")
    ai_reply = await query_strategy_ai(clean_prompt)

    header = "⚡ *[SPARK-STRATEGY] | #gemini*\n━━━━━━━━━━━━━━━━━━━\n"
    footer = "\n━━━━━━━━━━━━━━━━━━━\n📌 *Master discussion archived in Gemini.*"
    full_message = header + ai_reply + footer

    await send_telegram_message(chat_id, full_message, reply_to_message_id=msg_id)


@telegram_router.post("/webhook/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Inbound Webhook Listener for @SupremeAitele_bot.
    Returns 200 OK immediately and processes strategy query asynchronously.
    """
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return {"status": "ignored_non_text"}

    chat_id = message["chat"]["id"]
    text = message["text"].strip()
    msg_id = message.get("message_id")

    # Auto-trigger for all 1-on-1 private messages; in groups, require trigger tags (#gemini, /spark, etc.)
    chat_type = message.get("chat", {}).get("type", "private")
    is_triggered = (chat_type == "private") or any(text.startswith(tag) or tag in text.lower() for tag in TRIGGER_TAGS)

    if not is_triggered:
        return {"status": "passthrough"}

    # Process in background so Telegram receives instant 200 OK
    background_tasks.add_task(_process_and_reply, chat_id, text, msg_id)
    return {"status": "accepted"}


@telegram_router.get("/webhook/telegram/status")
async def telegram_webhook_status():
    """Telemetry endpoint for Telegram bot health."""
    return {
        "status": "active",
        "bot_configured": bool(TELEGRAM_BOT_TOKEN),
        "triggers": TRIGGER_TAGS,
        "default_model": GEMINI_MODEL,
    }
