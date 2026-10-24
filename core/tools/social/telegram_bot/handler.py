"""TelegramBotHandler core — ``COMMANDS`` map, token bootstrap, Telegram
Bot API helpers and the synchronous message entrypoint.

Split artifact of the former single-module ``tools/social/telegram_bot.py``:
the original class head, copied verbatim, is composed with the feature
mixins below into the public ``TelegramBotHandler`` class.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac

# বাংলা মন্তব্য: ওএস মডিউল ইম্পোর্ট করা হলো যাতে os.environ ঠিকমত কাজ করে
import os
from typing import Any, ClassVar

import httpx

from core.config import settings
from core.logging_config import logger

from .admin_handlers import AdminHandlersMixin
from .ai_assignment_handler import AIAssignmentHandlerMixin
from .ai_engine import AIEngineMixin
from .conversations import ConversationsMixin
from .keyboards import KeyboardsMixin
from .runtime import RuntimeMixin
from .updates import UpdatesMixin
from .user_handlers import UserHandlersMixin


class TelegramBotCore:
    """Core of :class:`TelegramBotHandler` (split artifact — the original
    head of the single TelegramBotHandler class: ``COMMANDS`` texts,
    token bootstrap, Telegram Bot API helpers and the sync entrypoint)."""

    COMMANDS: ClassVar[dict[str, str]] = {
        "/start": (
            "👋 Welcome to <b>SupremeAI 2.0</b>!\n"
            "Your self-evolving autonomous AI co-engineer & cloud powerhouse.\n\n"
            "✨ <b>Key Features:</b>\n"
            "• 🌐 <b>Mini App:</b> /app — Launch full Studio directly in Telegram\n"
            "• ⚡ <b>Quick Actions:</b> /quick — Autonomous 1-click controls\n"
            "• 📊 <b>Live Telemetry:</b> /telemetry — Swarm latency & KPIs\n"
            "• 📚 <b>Knowledge Base:</b> /kb &lt;query&gt; — 52 Crown Jewel cards\n"
            "• 💬 <b>Sessions:</b> /session — Multi-session chat switcher\n\n"
            "Type /help for all commands or send any message to chat with AI!"
        ),
        "/app": (
            "✨ <b>SupremeAI Studio (Telegram Mini App)</b>\n\n"
            "টেলিগ্রামের ভেতরেই ১-ট্যাপে সরাসরি সম্পূর্ণ React 19 ড্যাশবোর্ড ওপেন করতে নিচের বাটনে ক্লিক করুন:"
        ),
        "/studio": (
            "✨ <b>SupremeAI Studio (Telegram Mini App)</b>\n\n"
            "টেলিগ্রামের ভেতরেই ১-ট্যাপে সরাসরি সম্পূর্ণ React 19 ড্যাশবোর্ড ওপেন করতে নিচের বাটনে ক্লিক করুন:"
        ),
        "/quick": (
            "⚡ <b>SupremeAI 2.0 | Quick Actions Panel</b>\n\n"
            "ড্যাশবোর্ডের মতো ১-ক্লিকে যেকোনো উচ্চ ক্ষমতাসম্পন্ন অপারেশন পরিচালনা করুন:"
        ),
        "/telemetry": (
            "📊 <b>SupremeAI 2.0 | Live Telemetry</b>\n\n"
            "এই কমান্ড প্রতিবার সিস্টেম থেকে বাস্তব ডেটা পড়ে দেখায় "
            "(supervised agent health + সচল রান সংখ্যা)।\n"
            "<i>যে ডেটা পাওয়া যায় না, সেটি সৎভাবে 'unavailable' দেখানো হয় — "
            "বানানো সংখ্যা কখনো নয়।</i>"
        ),
        "/help": (
            "📖 <b>SupremeAI Commands:</b>\n\n"
            "✨ /app — Launch SupremeAI Studio Mini App in Telegram\n"
            "⚡ /quick — Dashboard Quick Actions keyboard\n"
            "📊 /telemetry — Live system health & run telemetry (real reads)\n"
            "🛑 /abort &lt;run_id&gt; — Admin: cancel a running run instantly\n"
            "📚 /kb &lt;query&gt; — Search 52 Crown Jewel cards & 8 Master Docs\n"
            "💬 /session — Multi-session chat switcher\n"
            "⚡ /sys_status — Real-time infrastructure & health monitor\n"
            "💾 /backup_now — Trigger immediate encrypted DB & memory backup\n"
            "🚀 /latest_build — Fetch latest Desktop, VSIX & build artifacts\n"
            "📜 /rules — Constitutional rules & architecture matrix\n"
            "🔐 /admin — Admin operations & vault controls\n\n"
            "<i>Or just ask any question to chat with SupremeAI!</i>"
        ),
        "/admin": "🔐 <b>Admin Operations:</b>\n/backup_now — Run immediate encrypted backup\n/sys_status — Cluster telemetry\n/abort &lt;run_id&gt; — Cancel a running run\n/rules — AI Directives\n/telemetry — Live metrics\n/mcp_clients — Approve MCP clients and change roles",
        "/rules": "📜 <b>Constitutional Rules:</b> 5 directions (North, South, East, West, Center) enforce Zero Infrastructure Cost & Brand Exclusivity.",
    }

    def __init__(self, task_processor_interface=None) -> None:
        self.bot_token: str = str(
            os.environ.get("TELEGRAM_BOT_TOKEN")
            or getattr(settings, "telegram_bot_token", "")
            or ""
        ).strip()
        self.api_base: str = f"https://api.telegram.org/bot{self.bot_token}"
        self.processor = task_processor_interface

        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled.")

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.bot_token != "mock_token")

    async def get_me(self) -> dict[str, Any] | None:
        """Get Telegram Bot user profile information."""
        if not self.configured:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.api_base}/getMe")
                data = resp.json() if hasattr(resp, "json") else {}
                if isinstance(data, dict) and data.get("ok"):
                    return data.get("result")
                return None
        except Exception as exc:
            logger.error(f"Telegram get_me failed: {exc}")
            return None

    # ── Telegram API helpers ──────────────────────────────────────

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        if not self.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                body: dict[str, Any] = {"chat_id": str(chat_id), "text": text}
                if parse_mode:
                    body["parse_mode"] = parse_mode
                if reply_markup:
                    body["reply_markup"] = reply_markup

                resp = await client.post(f"{self.api_base}/sendMessage", json=body)
                if resp.is_error and parse_mode:
                    # Fallback without parse_mode if formatting caused a 400
                    body.pop("parse_mode", None)
                    resp = await client.post(f"{self.api_base}/sendMessage", json=body)
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.error(f"Telegram sendMessage failed: {exc}")
            return False

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        if not self.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                payload: dict[str, Any] = {"callback_query_id": callback_query_id}
                if text:
                    payload["text"] = text
                resp = await client.post(f"{self.api_base}/answerCallbackQuery", json=payload)
                return bool(resp.status_code == 200)
        except Exception as e:
            logger.error(f"answerCallbackQuery error: {e}")
            return False

    async def send_document(
        self,
        chat_id: int | str,
        document: bytes | str,
        filename: str | None = None,
        caption: str | None = None,
        parse_mode: str | None = "HTML",
    ) -> dict[str, Any] | None:
        """Upload and send a document/file to Telegram."""
        if not self.configured:
            return None
        try:
            url = f"{self.api_base}/sendDocument"
            data: dict[str, Any] = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption
            if parse_mode:
                data["parse_mode"] = parse_mode

            files: dict[str, Any] = {}
            if isinstance(document, bytes):
                fname = filename or "backup.enc.gz"
                files = {"document": (fname, document)}
            elif isinstance(document, str) and os.path.isfile(document):
                fname = filename or os.path.basename(document)
                with open(document, "rb") as f:
                    file_content = f.read()
                files = {"document": (fname, file_content)}
            else:
                logger.error(f"Invalid document payload: {document}")
                return None

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, data=data, files=files)
                if resp.is_error and parse_mode:
                    data.pop("parse_mode", None)
                    resp = await client.post(url, data=data, files=files)
                resp.raise_for_status()
                res_data = resp.json()
                return res_data.get("result") if res_data.get("ok") else None
        except Exception as exc:
            logger.error(f"Telegram send_document failed: {exc}")
            return None

    async def send_typing(self, chat_id: int | str) -> None:
        if not self.configured:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.api_base}/sendChatAction",
                    json={"chat_id": str(chat_id), "action": "typing"},
                )
        except Exception as e:
            logger.error(f"Telegram sendTyping failed for chat_id {chat_id}: {e}")

    async def set_webhook(self, webhook_url: str) -> bool:
        """Register webhook URL with Telegram."""
        if not self.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.api_base}/setWebhook",
                    json={
                        "url": webhook_url,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
                data = resp.json()
                if data.get("ok"):
                    logger.info(f"✅ Telegram webhook set: {webhook_url}")
                    return True
                logger.error(f"Webhook error: {data}")
                return False
        except Exception as exc:
            logger.error(f"set_webhook failed: {exc}")
            return False

    async def sync_bot_profile(
        self,
        name: str = "SupremeAI 2.0 | Autonomous Intelligence",
        description: str | None = None,
        short_description: str | None = None,
    ) -> bool:
        """Sets official Name, Description, Short Description, and Commands Menu on Telegram."""
        if not self.configured:
            return False
        default_desc = (
            "🔱 SupremeAI 2.0 — Living Self-Evolving Superintelligence\n\n"
            "Built with 100% Zero-Cost Infrastructure & Continuous Learning Matrix.\n\n"
            "⚡ Core Capabilities:\n"
            "• Autonomous AI Pair Programmer & Metaprogramming\n"
            "• TelDrive Encrypted DB & Memory Vault (/backup_now)\n"
            "• Real-time Cluster Telemetry & Health (/sys_status)\n"
            "• Instant Desktop (.exe) & VSIX Build Delivery (/latest_build)\n\n"
            "Created by Saiful Haq Niloy | Powered by SupremeAI"
        )
        default_short = "🔱 SupremeAI 2.0: Self-evolving autonomous intelligence, $0-cost cloud vault & AI developer powerhouse."

        commands = [
            {"command": "start", "description": "Initialize SupremeAI assistant"},
            {"command": "sys_status", "description": "Real-time telemetry & health check"},
            {"command": "backup_now", "description": "Trigger encrypted DB & memory backup"},
            {"command": "latest_build", "description": "Download latest Desktop & VSIX builds"},
            {"command": "help", "description": "Command list & help documentation"},
            {"command": "rules", "description": "Constitutional rules & architecture"},
            {"command": "admin", "description": "Admin security & cluster controls"},
        ]

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(f"{self.api_base}/setMyName", json={"name": name})
                await client.post(
                    f"{self.api_base}/setMyDescription",
                    json={"description": description or default_desc},
                )
                await client.post(
                    f"{self.api_base}/setMyShortDescription",
                    json={"short_description": short_description or default_short},
                )
                await client.post(f"{self.api_base}/setMyCommands", json={"commands": commands})
                logger.info("✅ Telegram bot profile and commands synchronized successfully.")
                return True
        except Exception as exc:
            logger.error(f"sync_bot_profile failed: {exc}")
            return False

    # ── Message handling ──────────────────────────────────────────

    def handle_message(self, text: str, user_id: str = "user") -> str:
        """Synchronous message handler used by tests and scripts."""
        command = text.strip().split()[0].lower() if text.strip().startswith("/") else None
        if command and command in self.COMMANDS:
            return self.COMMANDS[command]
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._ai_response(text, user_id))
        finally:
            with contextlib.suppress(Exception):
                loop.close()

    # ── Admin identity (fail-closed, env/vault only — zero hardcode) ──

    _admin_gate_warned: ClassVar[bool] = False

    def _configured_admin_ids(self) -> set[str]:
        """Return configured admin identities from settings/vault + env only.

        বাংলা মন্তব্য (P-B admin-identity truth): আগে এই ফাইলে একটি হার্ডকোড করা
        ব্যক্তিগত admin chat-ID ফলব্যাক ছিল — ফলে env দিয়ে তা প্রত্যাহার করা
        অসম্ভব ছিল এবং কিছু কনফিগার না থাকলেও সেই এক ব্যক্তি স্বয়ংক্রিয়ভাবে
        admin হয়ে যেত (fail-open)। এখন কোনো হার্ডকোড নেই: কিছু কনফিগার না
        থাকলে কেউ admin নয়। একাধিক আইডি কমা/সেমিকোলন দিয়ে দেওয়া যায়।
        """
        raw_candidates: list[str] = []
        try:
            raw_candidates.append(str(getattr(settings, "admin_telegram_chat_id", "") or ""))
        except Exception as exc:
            # বাংলা মন্তব্য: settings lookup ব্যর্থ হলেও fail-closed — env চেক চলবে।
            logger.warning(f"Admin identity: settings lookup failed (env fallback): {exc}")
        raw_candidates.append(os.environ.get("ADMIN_TELEGRAM_CHAT_ID", ""))
        # Legacy fallback: TELEGRAM_CHAT_ID ইতিহাসগতভাবে alert-gateway হিসেবে ব্যবহৃত।
        raw_candidates.append(os.environ.get("TELEGRAM_CHAT_ID", ""))

        admin_ids: set[str] = set()
        for raw in raw_candidates:
            for part in str(raw).replace(";", ",").split(","):
                candidate = part.strip()
                if candidate:
                    admin_ids.add(candidate)
        return admin_ids

    def is_admin(self, chat_id: int | str, user_id: int | str | None = None) -> bool:
        """Check whether the *sender* of this update is the configured administrator.

        ``user_id`` (Telegram ``from.id``) is authoritative when supplied, because
        in group chats ``chat_id`` identifies the group — not the human — so a
        chat_id-only check would let any group member pass the admin gate.
        Fails closed (deny) when no admin identity is configured.
        """
        admin_ids = self._configured_admin_ids()
        if not admin_ids:
            if not TelegramBotCore._admin_gate_warned:
                TelegramBotCore._admin_gate_warned = True
                logger.warning(
                    "Telegram admin gate is FAIL-CLOSED: ADMIN_TELEGRAM_CHAT_ID is not "
                    "configured — every admin operation will be denied until it is set."
                )
            return False

        sender = str(user_id).strip() if user_id is not None else str(chat_id).strip()
        if not sender:
            return False
        return any(
            hmac.compare_digest(sender.encode("utf-8"), admin_id.encode("utf-8"))
            for admin_id in admin_ids
        )


class TelegramBotHandler(
    AIAssignmentHandlerMixin,
    TelegramBotCore,
    KeyboardsMixin,
    UpdatesMixin,
    ConversationsMixin,
    AdminHandlersMixin,
    UserHandlersMixin,
    AIEngineMixin,
    RuntimeMixin,
):
    """
    Production Telegram Bot — handles messages via webhook payload.
    Integrates with SupremeOrchestrator for AI responses.
    """
