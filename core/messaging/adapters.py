"""
SupremeAI Messaging Adapters
=============================
বাংলা: Plan Section 14 — existing Telegram ও Email implementations-কে
MessagingProvider protocol-এ wrap করে। এতে সব messaging একটি central
dispatcher দিয়ে যাবে, vendor-specific code domain layer-এ leak করবে না।

নীতি (Plan Section 14): "The existing Telegram implementation should be
wrapped before building an entirely new Telegram subsystem."

Adapters:
  - TelegramMessagingAdapter: wraps tools/social/telegram_bot.py::TelegramBotHandler
  - EmailMessagingAdapter: wraps services/email/email_service.py::EmailService
  - MockMessagingAdapter: already exists (fallback for local dev)

Dispatcher auto-selects adapter based on settings (Telegram first, then Email,
then Mock fallback)।
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from core.logging_config import logger

from .interfaces import MessagingProvider
from .models import MessageEvent, MessageResult


class TelegramMessagingAdapter(MessagingProvider):
    """
    Plan Section 14: wraps existing TelegramBotHandler-কে MessagingProvider হিসেবে।
    recipient = chat_id (int বা str), body = message text।
    """

    def __init__(self):
        try:
            from tools.social.telegram_bot import TelegramBotHandler

            self._handler = TelegramBotHandler()
            logger.info("TelegramMessagingAdapter initialized (wraps TelegramBotHandler)")
        except Exception as e:
            logger.error(f"Failed to init TelegramMessagingAdapter: {e}")
            self._handler = None

    async def send(self, event: MessageEvent) -> MessageResult:
        if self._handler is None:
            return MessageResult(
                success=False, provider="telegram", error="TelegramBotHandler not initialized"
            )
        try:
            # recipient কে chat_id হিসেবে interpret করি
            chat_id = event.recipient
            # subject থাকলে text-এ prepend করি
            text = f"*{event.subject}*\n\n{event.body}" if event.subject else event.body
            sent = await self._handler.send_message(chat_id=chat_id, text=text)
            return MessageResult(
                success=bool(sent),
                message_id=str(uuid4()) if sent else None,
                provider="telegram",
                error=None if sent else "Telegram send_message returned False",
            )
        except Exception as e:
            logger.error(f"TelegramMessagingAdapter send failed: {e!r}")
            return MessageResult(success=False, provider="telegram", error=str(e))


class EmailMessagingAdapter(MessagingProvider):
    """
    Plan Section 14: wraps existing EmailService-কে MessagingProvider হিসেবে।
    recipient = email address, subject = email subject, body = HTML body।
    """

    def __init__(self):
        try:
            from services.email.email_service import email_service

            self._service = email_service
            logger.info("EmailMessagingAdapter initialized (wraps EmailService)")
        except Exception as e:
            logger.error(f"Failed to init EmailMessagingAdapter: {e}")
            self._service = None

    async def send(self, event: MessageEvent) -> MessageResult:
        if self._service is None:
            return MessageResult(
                success=False, provider="email", error="EmailService not initialized"
            )
        try:
            # EmailService._send_email(to_email, subject, html_body) call করি
            # body কে HTML হিসেবে treat করি
            html_body = event.body
            subject = event.subject or "(no subject)"
            sent = await self._service._send_email(event.recipient, subject, html_body)
            return MessageResult(
                success=bool(sent),
                message_id=str(uuid4()) if sent else None,
                provider="email",
                error=None if sent else "EmailService._send_email returned False",
            )
        except Exception as e:
            logger.error(f"EmailMessagingAdapter send failed: {e!r}")
            return MessageResult(success=False, provider="email", error=str(e))
