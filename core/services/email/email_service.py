"""This module provides a robust and asynchronous email service for the SupremeAI project, centralizing the functionality for sending various transactional emails such as welcome messages, password reset links, and billing notifications. It integrates with an external email API (e.g., Resend) for delivery, leverages application settings for configuration, and reports errors via the internal event bus, ensuring reliable communication with users within the highly scalable AI ecosystem.

Key Components:
- `EmailService`: Manages the configuration and dispatch of different types of emails through an external API, handling API key retrieval, settings, and error reporting.
- `email_service`: A module-level instance of `EmailService` for convenient, singleton access throughout the application.
- `_get_settings()`: Lazily loads application settings from `core.config`, providing a simple fallback for environments where settings might not be available (e.g., certain test setups).
- `api_key`: Property to retrieve the Resend API key from environment variables, essential for authenticating with the email service.
- `from_email`: Property to retrieve the sender's email address from environment variables, with a default fallback.
- `_send_email()`: An internal asynchronous method responsible for making the actual HTTP POST request to the configured email API, handling success/failure logging and error event emission.
- `send_welcome_email()`: Sends a personalized welcome email to new users, including a link to the SupremeAI studio.
- `send_password_reset()`: Dispatches a password reset email containing a unique, time-limited reset link.
- `send_billing_notification()`: Sends a notification regarding upcoming invoices, usage details, and suggestions for cost optimization.

Dependencies:
- `os`: For accessing environment variables (e.g., `RESEND_API_KEY`, `RESEND_FROM_EMAIL`).
- `httpx`: For making asynchronous HTTP requests to the external email API.
- `loguru`: For structured logging of email sending operations, warnings, and errors.
- `core.messaging.event_bus`: For emitting `ErrorEvent`s when email sending encounters API or network failures.
- `core.config`: For accessing application-wide settings such as the Resend API URL and the SupremeAI frontend URL."""

import os
from typing import Any

import httpx

from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus
from utils.http_client import create_async_client


class EmailService:
    """বাংলা মন্তব্য: ইমেইল সার্ভিস যা Pydantic Settings থেকে URL এবং API Key রিড করে।"""

    def __init__(self):
        self._settings = None

    def _get_settings(self):
        if self._settings is not None:
            return self._settings
        return settings

    @property
    def api_key(self) -> str:
        """বাংলা মন্তব্য: Resend API key from env var."""
        return os.getenv("RESEND_API_KEY", "")

    @property
    def from_email(self) -> str:
        """বাংলা মন্তব্য: From email address."""
        env_val = os.getenv("RESEND_FROM_EMAIL")
        if env_val:
            return env_val
        from core.config import settings

        return settings.resend_from_email

    @with_error_bus("_send_email")
    async def _send_email(
        self, to_email: str = "", subject: str = "", html_body: str = "", **kwargs
    ) -> bool:
        to_email = to_email or kwargs.get("to", "") or kwargs.get("to_email", "")
        html_body = html_body or kwargs.get("body", "") or kwargs.get("html_body", "")
        s = self._get_settings()
        api_key = self.api_key or "mock-key-for-testing"
        from_email = self.from_email
        api_url = getattr(s, "resend_api_url", "https://api.resend.com/emails")

        if not api_key:
            logger.warning(f"[Mock Email] To: {to_email} | Subject: {subject}")
            logger.debug(f"Body: {html_body[:100]}...")
            return False

        try:
            async with create_async_client(timeout=15.0) as client:
                response = await client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": from_email,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_body,
                    },
                )
                if getattr(response, "is_success", False) or getattr(
                    response, "status_code", 0
                ) in (200, 201):
                    logger.info(f"Email sent successfully to {to_email}")
                    return True
                else:
                    err_msg = str(getattr(response, "text", "API Error"))[:200]
                    logger.error(f"Failed to send email to {to_email}: {err_msg}")
                    error_event_bus.emit(
                        ErrorEvent(
                            module="email_service",
                            error_type="RESEND_API_ERROR",
                            message=err_msg,
                            severity="ERROR",
                            structured_context=ErrorContext(module="auto_fixed"),
                            context={
                                "status_code": getattr(response, "status_code", 500),
                                "to_email": to_email,
                            },
                        )
                    )
                    return False
        except Exception as e:
            logger.error(f"Exception while sending email: {e}")
            error_event_bus.emit(
                ErrorEvent(
                    module="email_service",
                    error_type="HTTP_REQUEST_FAILED",
                    message=str(e)[:200],
                    severity="ERROR",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"to_email": to_email},
                )
            )
            return False

    async def send_welcome_email(
        self, user_email: str = "", user_name: str = "Developer", **kwargs
    ) -> Any:
        to_email = user_email or kwargs.get("to_email", "")
        user_name = user_name or kwargs.get("user_name", "Developer")
        subject = "Welcome to SupremeAI 2.0 🚀"
        frontend_url = getattr(self._get_settings(), "frontend_url", "https://supremeai.dev")
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>Welcome, {user_name}!</h2>
                <p>We're thrilled to have you onboard SupremeAI 2.0.</p>
                <p>You can now orchestrate multiple cloud providers, run local agents, and build faster than ever.</p>
                <a href="{frontend_url}/studio" style="padding: 10px 20px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 5px;">Go to Studio</a>
            </body>
        </html>
        """
        return await self._send_email(to_email, subject, html)

    async def send_password_reset(
        self, user_email: str = "", reset_link: str = "", **kwargs
    ) -> Any:
        to_email = user_email or kwargs.get("to_email", "")
        reset_link = reset_link or kwargs.get("reset_link", "")
        subject = "Reset Your SupremeAI Password"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>Password Reset Request</h2>
                <p>Click the link below to reset your password. This link expires in 1 hour.</p>
                <a href="{reset_link}">{reset_link}</a>
            </body>
        </html>
        """
        return await self._send_email(to_email, subject, html)

    async def send_billing_notification(
        self, user_email: str = "", amount: float = 0.0, usage: str = "", **kwargs
    ) -> Any:
        to_email = user_email or kwargs.get("to_email", "")
        amount = amount or kwargs.get("invoice_amount", 0.0)
        usage = usage or kwargs.get("due_date", "")
        subject = "SupremeAI - Upcoming Invoice Notification"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>Billing Update</h2>
                <p>Your upcoming invoice for this month is <strong>${amount:.2f}</strong>.</p>
                <p>Top usage category: {usage}</p>
                <p>To keep zero-cost operations, consider connecting your own API keys in the Studio.</p>
            </body>
        </html>
        """
        return await self._send_email(to_email, subject, html)

    async def draft(self, intent: str, context: dict[str, Any] | None = None) -> dict[str, str]:
        """ADVANCED: Generate smart AI-drafted email content using ModelRouter."""
        context = context or {}
        prompt = (
            f"You are SupremeAI's automated communication agent.\n"
            f"Draft a professional, concise email for intent: '{intent}'.\n"
            f"Context: {context}\n"
            f"Return ONLY a JSON with keys: 'subject' and 'html_body'."
        )
        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()
            res = router.route_and_generate(prompt=prompt, task_type="general", max_cost=0.01)
            raw = res.get("text", "{}").strip()
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            import json

            data = json.loads(raw)
            return {
                "subject": data.get("subject", f"SupremeAI Notification: {intent}"),
                "html_body": data.get("html_body", f"<p>{intent}</p>"),
            }
        except Exception as e:
            logger.warning(f"[EmailService] AI drafting fallback: {e}")
            return {
                "subject": f"SupremeAI: {intent.capitalize()}",
                "html_body": f"<p>Hello,<br/>This is an automated notification regarding {intent}.</p>",
            }

    async def optimal_send_hour(self, user_email: str) -> int:
        """ADVANCED: Compute the optimal send hour for user engagement (default 10 AM)."""
        try:
            from core.cache.semantic_cache import semantic_cache

            cached = await semantic_cache.get(f"email_optimal_hour::{user_email}")
            if cached and isinstance(cached, int | str):
                return int(cached)
        except Exception as e:
            logger.debug(f"[EmailService] Optimal send hour cache error: {e}")
        return 10


email_service = EmailService()
