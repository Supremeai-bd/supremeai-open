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


_http_client: Optional[httpx.AsyncClient] = None


def get_telegram_client() -> httpx.AsyncClient:
    """Returns a shared, pooled AsyncClient with connection reuse for low-latency delivery."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=4.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _http_client


async def send_chat_action(chat_id: int | str, action: str = "typing") -> None:
    """Delivers instant typing status indicator to Telegram so users see immediate responsiveness."""
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction"
    try:
        client = get_telegram_client()
        await client.post(url, json={"chat_id": chat_id, "action": action})
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Failed to send typing chat action: {exc}")


async def send_telegram_message(
    chat_id: int | str,
    text: str,
    reply_to_message_id: Optional[int] = None
) -> bool:
    """Delivers formatted message chunks to Telegram via shared keep-alive pool."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured; cannot deliver message.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Auto-chunking for Telegram's 4096 character limit (safe margin at 3800)
    chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)] if len(text) > 3800 else [text]

    client = get_telegram_client()
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
    1. Priority-1 (Chat Mandate): Queries $0 Stealth Webhook Relay.
    2. Priority-2 (Ultra-fast API Keys): Direct Gemini -> Groq -> Perplexity.
    3. Priority-3: Federation Squad pool failover.
    """
    # 0. Priority-1 (Chat Mandate): Stealth Webhook Relay
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
            logger.warning(f"Stealth Priority-1 bypassed ({exc}), falling back to API keys...")

    # 1. Priority-2 (Top-Speed API Keys): Gemini -> Groq -> Perplexity
    client = get_telegram_client()

    # A) Gemini API Key
    gemini_pool = squad.pools.get("gemini") if squad else None
    healthy_gemini_slots = gemini_pool.healthy_slots if gemini_pool else []
    gemini_key = healthy_gemini_slots[0].key if healthy_gemini_slots else (
        os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1") or os.getenv("GOOGLE_API_KEY")
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
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"]
            logger.warning(f"Direct Gemini call returned {res.status_code}, falling back to Groq...")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Direct Gemini attempt failed ({exc}), falling back to Groq...")

    # B) Groq API Key (Ultra-low latency, ~200ms)
    groq_pool = squad.pools.get("groq") if squad else None
    healthy_groq_slots = groq_pool.healthy_slots if groq_pool else []
    groq_key = healthy_groq_slots[0].key if healthy_groq_slots else os.getenv("GROQ_API_KEY")

    if groq_key and forward_chat_completion:
        chat_payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        }
        try:
            status_code, resp_data = await forward_chat_completion("groq", groq_key, chat_payload, timeout=12.0)
            if 200 <= status_code < 300 and isinstance(resp_data, dict):
                choices = resp_data.get("choices", [])
                if choices and isinstance(choices[0], dict) and "message" in choices[0]:
                    return choices[0]["message"].get("content", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Direct Groq attempt failed ({exc}), falling back to Perplexity...")

    # C) Perplexity API Key
    pplx_key = os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY")
    if pplx_key and forward_chat_completion:
        chat_payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        }
        try:
            status_code, resp_data = await forward_chat_completion("perplexity", pplx_key, chat_payload, timeout=15.0)
            if 200 <= status_code < 300 and isinstance(resp_data, dict):
                choices = resp_data.get("choices", [])
                if choices and isinstance(choices[0], dict) and "message" in choices[0]:
                    return choices[0]["message"].get("content", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Direct Perplexity attempt failed ({exc}), falling back to squad...")

    # 2. Dynamic Squad Failover (OpenRouter, Mistral, OpenAI, etc.)
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
                status_code, response_data = await forward_chat_completion(provider, slot.key, chat_payload, timeout=15.0)
                if 200 <= status_code < 300 and isinstance(response_data, dict):
                    choices = response_data.get("choices", [])
                    if choices and isinstance(choices[0], dict) and "message" in choices[0]:
                        return choices[0]["message"].get("content", "")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Squad slot {slot.name} failed during telegram query: {exc}")

    return "⚠️ দুঃখিত, এই মুহূর্তে কোনো এআই প্রোভাইডার উপলব্ধ নেই। অনুগ্রহ করে কিছুক্ষণ পর চেষ্টা করুন।"


async def _process_and_reply(chat_id: int | str, text: str, msg_id: Optional[int] = None):
    """Background task to generate and reply with instant typing status indicator."""
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

    # Send immediate typing action so Telegram shows "typing..." without lag
    await send_chat_action(chat_id, "typing")

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
