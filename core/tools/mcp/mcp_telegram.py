"""
SupremeAI 2.0 — Telegram Bot MCP Server
=======================================

Exposes Telegram messaging, alerts, status, and broadcasting capabilities
via FastMCP so that AI agents can communicate directly through Telegram.

Tools:
    - telegram_send_message: Send a notification or formatted message
    - telegram_get_bot_status: Get bot profile & connectivity health
    - telegram_send_document: Send report or log document to chat/admin
    - telegram_broadcast_alert: Send priority operational alert to admin channel
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

mcp = FastMCP("telegram_mcp")


def _get_handler() -> Any:
    """Lazy-load TelegramBotHandler."""
    from tools.social.telegram_bot import TelegramBotHandler

    return TelegramBotHandler()


class SendMessageInput(BaseModel):
    """Input for sending a message via Telegram."""

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(..., description="Message text in HTML or plain text")
    chat_id: str | None = Field(
        None,
        description="Target chat/channel ID. Defaults to TELEGRAM_CHAT_ID from environment if omitted.",
    )
    parse_mode: str = Field("HTML", description="Parse mode ('HTML', 'MarkdownV2', or empty)")


class SendDocumentInput(BaseModel):
    """Input for sending a document/file via Telegram."""

    model_config = ConfigDict(str_strip_whitespace=True)

    file_path: str = Field(..., description="Absolute path of the local file to upload")
    caption: str = Field("", description="Optional caption for the document")
    chat_id: str | None = Field(
        None, description="Target chat/channel ID. Defaults to TELEGRAM_CHAT_ID if omitted."
    )


class BroadcastAlertInput(BaseModel):
    """Input for sending an urgent operational alert."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., description="Alert headline/title")
    details: str = Field(..., description="Full context or error breakdown")
    severity: str = Field("INFO", description="Severity level: INFO, WARNING, ERROR, CRITICAL")


@mcp.tool(
    name="telegram_send_message",
    annotations={
        "title": "Send Telegram Message",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def telegram_send_message(params: SendMessageInput) -> str:
    """Send a formatted message to a Telegram chat or default admin channel."""
    handler = _get_handler()
    target_chat = params.chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not target_chat:
        return json.dumps(
            {
                "success": False,
                "error": "No chat_id provided and TELEGRAM_CHAT_ID is not set in environment.",
            }
        )

    success = await handler.send_message(
        chat_id=target_chat,
        text=params.text,
        parse_mode=params.parse_mode or None,
    )
    return json.dumps(
        {
            "success": success,
            "chat_id": str(target_chat),
            "status": "delivered" if success else "failed",
        }
    )


@mcp.tool(
    name="telegram_get_bot_status",
    annotations={
        "title": "Get Telegram Bot Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def telegram_get_bot_status() -> str:
    """Check Telegram bot configuration and connectivity to Telegram API."""
    handler = _get_handler()
    if not handler.configured:
        return json.dumps(
            {"configured": False, "status": "TELEGRAM_BOT_TOKEN is missing or set to placeholder."}
        )

    bot_info = await handler.get_me()
    if bot_info:
        return json.dumps({"configured": True, "online": True, "bot": bot_info}, ensure_ascii=False)

    return json.dumps(
        {
            "configured": True,
            "online": False,
            "error": "Failed to communicate with Telegram API. Token might be invalid or network blocked.",
        }
    )


@mcp.tool(
    name="telegram_send_document",
    annotations={
        "title": "Send Telegram Document",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def telegram_send_document(params: SendDocumentInput) -> str:
    """Send a file or document directly to a Telegram chat or admin."""
    handler = _get_handler()
    target_chat = params.chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not target_chat:
        return json.dumps(
            {"success": False, "error": "No chat_id provided and TELEGRAM_CHAT_ID is not set."}
        )

    if not os.path.exists(params.file_path):
        return json.dumps({"success": False, "error": f"File does not exist: {params.file_path}"})

    try:
        with open(params.file_path, "rb") as fh:
            file_bytes = fh.read()

        filename = os.path.basename(params.file_path)
        result = await handler.send_document(
            chat_id=target_chat,
            document=file_bytes,
            filename=filename,
            caption=params.caption,
            parse_mode="HTML",
        )
        return json.dumps(
            {"success": bool(result), "filename": filename, "chat_id": str(target_chat)}
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


@mcp.tool(
    name="telegram_broadcast_alert",
    annotations={
        "title": "Broadcast Operational Alert via Telegram",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def telegram_broadcast_alert(params: BroadcastAlertInput) -> str:
    """Send an operational or CI/CD incident alert to the configured Telegram chat."""
    handler = _get_handler()
    target_chat = os.getenv("TELEGRAM_CHAT_ID")
    if not target_chat:
        return json.dumps(
            {"success": False, "error": "TELEGRAM_CHAT_ID is not configured in environment."}
        )

    icons = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "🚨", "CRITICAL": "🔥"}
    icon = icons.get(params.severity.upper(), "📢")

    text = (
        f"{icon} <b>[SupremeAI Alert] {params.severity.upper()}</b>\n\n"
        f"<b>{params.title}</b>\n\n"
        f"{params.details}"
    )

    success = await handler.send_message(chat_id=target_chat, text=text, parse_mode="HTML")
    return json.dumps(
        {"success": success, "chat_id": str(target_chat), "severity": params.severity.upper()}
    )


if __name__ == "__main__":
    mcp.run()
