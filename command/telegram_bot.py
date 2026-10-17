"""src/telegram_bot.py — async Telegram command handler with strict RBAC.

Design notes (honesty + portability):
- The COMMAND LAYER (RBAC, routing, payload shaping) is pure logic over
  Telegram update dicts and is fully unit-testable offline.
- The TRANSPORT layer (long-polling + send_message) is a thin stdlib adapter
  used at runtime; tests inject fakes and never touch the network.
- Every outbound HTTP call carries an explicit timeout (cross-platform guard
  doctrine: no subprocess/IO call without a timeout).
- RBAC is fail-closed: an update whose chat id is not the configured
  superadmin receives a denial and triggers nothing.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .config import CommandConfig

HELP_TEXT = (
    "SupremeAI Omnichannel Admin Control\n"
    "Commands:\n"
    "  /status              - Control Tower runway + active agent claims\n"
    "  /runway              - runway summary (alias of /status)\n"
    "  /dispatch <issue-url> - dispatch an agent loop intake for an issue\n"
    "  /stop                - arm the persistent emergency kill-switch\n"
    "  /help                - this text"
)

DENY_TEXT = "⛔ Unauthorized: this control channel accepts the Superadmin chat only."

ISSUE_URL_PREFIX = "https://github.com/"
VALID_COMMANDS = ("/status", "/runway", "/dispatch", "/stop", "/help", "/start")


class TelegramUpdate:
    """Minimal projection of a Telegram message update."""

    def __init__(self, chat_id: str, text: str) -> None:
        self.chat_id = str(chat_id or "").strip()
        self.text = (text or "").strip()

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TelegramUpdate":
        message = (payload or {}).get("message") or {}
        chat = message.get("chat") or {}
        return cls(chat_id=str(chat.get("id", "")), text=str(message.get("text", "")))


class BotReply:
    def __init__(self, text: str, allowed: bool = True, action: str = "reply") -> None:
        self.text = text
        self.allowed = allowed
        self.action = action


def _validate_issue_url(url: str) -> Optional[str]:
    url = (url or "").strip()
    if not url.startswith(ISSUE_URL_PREFIX) or "/issues/" not in url:
        return None
    tail = url.rsplit("/issues/", 1)[1]
    number = tail.split("?")[0].split("#")[0].strip("/")
    if not number.isdigit():
        return None
    return url


class CommandRouter:
    """Pure RBAC + routing layer. Dependencies are injected callables so every
    branch is testable offline."""

    def __init__(
        self,
        config: CommandConfig,
        fetch_status: Callable[[], str],
        dispatch_issue: Callable[[str], str],
        arm_kill_switch: Callable[[], str],
    ) -> None:
        self.config = config
        self._fetch_status = fetch_status
        self._dispatch_issue = dispatch_issue
        self._arm_kill_switch = arm_kill_switch

    def route(self, update: TelegramUpdate) -> BotReply:
        if not self.config.is_superadmin(update.chat_id):
            return BotReply(DENY_TEXT, allowed=False, action="deny")
        text = update.text.strip()
        if not text.startswith("/"):
            return BotReply(HELP_TEXT)
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        if command in ("/status", "/runway"):
            return BotReply(self._fetch_status())
        if command == "/dispatch":
            issue_url = _validate_issue_url(argument)
            if issue_url is None:
                return BotReply(
                    "⚠️ /dispatch requires a GitHub issue URL, e.g.\n"
                    "/dispatch https://github.com/Supremeai-bd/supremeai-open/issues/505"
                )
            return BotReply(self._dispatch_issue(issue_url), action="dispatch")
        if command == "/stop":
            return BotReply(self._arm_kill_switch(), action="kill_switch")
        if command in ("/help", "/start"):
            return BotReply(HELP_TEXT)
        return BotReply(HELP_TEXT)


class StdlibTelegramTransport:
    """Runtime transport: sendMessage + getUpdates long-polling (stdlib only)."""

    def __init__(self, config: CommandConfig) -> None:
        self.config = config

    def send_message(self, chat_id: str, text: str) -> None:
        payload = json.dumps(
            {"chat_id": chat_id, "text": text}
        ).encode("utf-8")
        req = urllib.request.Request(
            self.config.telegram_api_base + "/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.request_timeout_s) as resp:
            if resp.status != 200:
                raise RuntimeError("telegram sendMessage HTTP %d" % resp.status)

    def poll_updates(self, router: CommandRouter, timeout_s: int = 25) -> None:  # pragma: no cover - runtime loop
        offset = 0
        url = self.config.telegram_api_base + "/getUpdates?timeout=%d" % max(1, timeout_s)
        while True:
            req = urllib.request.Request(
                url + ("&offset=%d" % offset if offset else ""),
                method="GET",
            )
            try:
                with urllib.request.urlopen(
                    req, timeout=timeout_s + self.config.request_timeout_s
                ) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.URLError:
                time.sleep(3)
                continue
            for item in data.get("result", []):
                offset = max(offset, int(item.get("update_id", 0)) + 1)
                reply = router.route(TelegramUpdate.from_payload(item))
                message = (item.get("message") or {}).get("chat", {}).get("id")
                if message and reply.allowed:
                    self.send_message(str(message), reply.text)
                    if reply.action == "kill_switch":
                        break  # emergency stop also ends the poll loop


def default_router(config: CommandConfig, dispatcher: Any, kill_switch: Any) -> CommandRouter:
    """Wire the router to the real dispatcher + kill-switch implementations."""
    return CommandRouter(
        config=config,
        fetch_status=lambda: dispatcher.fetch_status(),
        dispatch_issue=lambda issue_url: dispatcher.dispatch_issue(issue_url),
        arm_kill_switch=lambda: kill_switch.arm(),
    )
