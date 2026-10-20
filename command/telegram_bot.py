"""src/telegram_bot.py — async Telegram command handler with strict RBAC.

Design notes (honesty + portability):
- The COMMAND LAYER (RBAC, routing, payload shaping) is pure logic over
  Telegram update dicts and is fully unit-testable offline.
- The TRANSPORT layer (long-polling + send_message/send_voice) is a thin
  stdlib adapter used at runtime; tests inject fakes and never touch the
  network.
- Every outbound HTTP call carries an explicit timeout (cross-platform guard
  doctrine: no subprocess/IO call without a timeout).
- RBAC is fail-closed: an update whose chat id is not the configured
  superadmin receives a denial and triggers nothing.
- VOICE (zero-compute doctrine): /voice + the voice-alert toggle lease
  synthesis to the Bangla VoiceService (services/voice_service.py) via an
  injected SYNC synthesizer (async internals wrapped by the factory).
  Without the optional edge-tts client the service degrades LOUDLY into
  the reply text — the bot never pretends a voice note exists.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import CommandConfig
from .services.voice_service import (
    DEFAULT_VOICE,
    VoiceRequestError,
    VoiceServiceUnavailable,
    VoiceSynthesisError,
)
from .services.voice_service import (
    validate_request as validate_voice_request,
)

HELP_TEXT = (
    "SupremeAI Omnichannel Admin Control\n"
    "Commands:\n"
    "  /status              - Control Tower runway + active agent claims\n"
    "  /runway              - runway summary (alias of /status)\n"
    "  /dispatch <issue-url> - dispatch an agent loop intake for an issue\n"
    "  /voice <text>        - Bangla voice note (zero-compute Edge Neural TTS)\n"
    "  /voiceon             - attach a Bangla voice note to /status summaries\n"
    "  /voiceoff            - stop attaching voice notes to /status\n"
    "  /stop                - arm the persistent emergency kill-switch\n"
    "  /help                - this text"
)

DENY_TEXT = "⛔ Unauthorized: this control channel accepts the Superadmin chat only."

ISSUE_URL_PREFIX = "https://github.com/"
VALID_COMMANDS = (
    "/status",
    "/runway",
    "/dispatch",
    "/voice",
    "/voiceon",
    "/voiceoff",
    "/stop",
    "/help",
    "/start",
)

VOICE_USAGE_TEXT = "⚠️ /voice requires text, e.g.\n/voice সিস্টেম সম্পূর্ণ স্বাভাবিক আছে"

# Canonical status phrase (also the warm-cache demo phrase in the docs).
VOICE_STATUS_PHRASE = "সিস্টেম সম্পূর্ণ স্বাভাবিক আছে"
VOICE_TOWER_UP_BN = "কন্ট্রোল টাওয়ার সংযুক্ত আছে"
VOICE_TOWER_DOWN_BN = "কন্ট্রোল টাওয়ার পৌঁছানো যাচ্ছে না"


def build_voice_status_summary(status_text: str) -> str:
    """Short Bangla voice summary derived from a /status report.

    Deterministic by design: the same healthy status always maps to the
    same phrase, so the ephemeral audio cache eliminates the round-trip.
    The liveness probe matches the full "Control Tower: reachable" marker —
    a bare "reachable" substring check would also match "unreachable".
    """
    body = status_text or ""
    tower_part = (
        VOICE_TOWER_UP_BN if "Control Tower: reachable" in body else VOICE_TOWER_DOWN_BN
    )
    return f"{VOICE_STATUS_PHRASE}। {tower_part}।"


@dataclass
class VoiceOutcome:
    """Result of one sync voice synthesis attempt (loud error taxonomy)."""

    audio: bytes | None = None
    error: str | None = None
    voice_used: str = ""
    size_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.audio is not None


def sync_voice_synthesizer(
    service: Any,
    voice: str = DEFAULT_VOICE,
    total_timeout_s: float = 60.0,
) -> Callable[[str], VoiceOutcome]:
    """Wrap the async VoiceService into the sync callable the router needs.

    Never raises: every failure mode becomes a VoiceOutcome(error=...) so
    the Telegram reply degrades loudly instead of crashing the poll loop.
    """

    def _synthesize(text: str) -> VoiceOutcome:
        try:
            request = validate_voice_request(
                text, voice=voice, total_timeout_s=total_timeout_s
            )
        except VoiceRequestError as exc:
            return VoiceOutcome(error=f"invalid request: {exc}")
        try:
            result = asyncio.run(service.synthesize(request))
        except VoiceServiceUnavailable as exc:
            return VoiceOutcome(error=f"service unavailable: {exc}")
        except VoiceSynthesisError as exc:
            return VoiceOutcome(error=f"{exc}")
        except (RuntimeError, OSError, TimeoutError, ConnectionError, ValueError) as exc:
            return VoiceOutcome(error=f"unexpected voice failure: {exc}")
        return VoiceOutcome(
            audio=result.audio,
            voice_used=result.request.voice,
            size_bytes=result.size_bytes,
        )

    return _synthesize


class TelegramUpdate:
    """Minimal projection of a Telegram message update."""

    def __init__(self, chat_id: str, text: str) -> None:
        self.chat_id = str(chat_id or "").strip()
        self.text = (text or "").strip()

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TelegramUpdate:
        message = (payload or {}).get("message") or {}
        chat = message.get("chat") or {}
        return cls(chat_id=str(chat.get("id", "")), text=str(message.get("text", "")))


class BotReply:
    def __init__(
        self,
        text: str,
        allowed: bool = True,
        action: str = "reply",
        voice_audio: bytes | None = None,
    ) -> None:
        self.text = text
        self.allowed = allowed
        self.action = action
        # When present the transport uploads this as a voice note (sendVoice)
        # in addition to the text reply.
        self.voice_audio = voice_audio


def _validate_issue_url(url: str) -> str | None:
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
        synthesize_voice: Callable[[str], VoiceOutcome] | None = None,
    ) -> None:
        self.config = config
        self._fetch_status = fetch_status
        self._dispatch_issue = dispatch_issue
        self._arm_kill_switch = arm_kill_switch
        # Voice extension (zero-compute): optional sync synthesizer; None is
        # answered with a loud "not wired" note, never a silent no-op.
        self.synthesize_voice = synthesize_voice
        self.voice_alerts_enabled = False

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
            status_text = self._fetch_status()
            voice_audio: bytes | None = None
            if self.voice_alerts_enabled:
                if self.synthesize_voice is None:
                    status_text += (
                        "\n🔊 voice alerts enabled but no synthesizer is wired "
                        "into this router"
                    )
                else:
                    outcome = self.synthesize_voice(
                        build_voice_status_summary(status_text)
                    )
                    if outcome.ok:
                        voice_audio = outcome.audio
                    else:
                        status_text += f"\n🔊 voice alert unavailable: {outcome.error}"
            return BotReply(status_text, voice_audio=voice_audio)
        if command == "/voice":
            if not argument:
                return BotReply(VOICE_USAGE_TEXT)
            if self.synthesize_voice is None:
                return BotReply(
                    "🔊 voice service not wired into this router "
                    "(synthesize_voice is None)"
                )
            outcome = self.synthesize_voice(argument)
            if not outcome.ok:
                return BotReply(f"🔊 voice synthesis failed: {outcome.error}")
            return BotReply(
                f"🎙️ voice note ready ({outcome.voice_used}, {outcome.size_bytes} bytes)",
                action="voice",
                voice_audio=outcome.audio,
            )
        if command == "/voiceon":
            self.voice_alerts_enabled = True
            return BotReply(
                "🔊 voice alerts ENABLED — /status now carries a Bangla voice note"
            )
        if command == "/voiceoff":
            self.voice_alerts_enabled = False
            return BotReply("🔇 voice alerts DISABLED")
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
    """Runtime transport: sendMessage + sendVoice + getUpdates long-polling
    (stdlib only)."""

    def __init__(self, config: CommandConfig) -> None:
        self.config = config

    def send_message(self, chat_id: str, text: str) -> None:
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(
            self.config.telegram_api_base + "/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.request_timeout_s) as resp:
            if resp.status != 200:
                raise RuntimeError(f"telegram sendMessage HTTP {resp.status}")

    def send_voice(
        self,
        chat_id: str,
        audio: bytes,
        filename: str = "voice.mp3",
        mime_type: str = "audio/mpeg",
    ) -> None:
        """Upload a voice note via sendVoice (multipart/form-data, stdlib only)."""
        boundary = f"supremeai-voice-{uuid.uuid4().hex}"
        parts = [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
            ).encode(),
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; filename="{filename}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode(),
            audio,
            (f"\r\n--{boundary}--\r\n").encode(),
        ]
        body = b"".join(parts)
        req = urllib.request.Request(
            self.config.telegram_api_base + "/sendVoice",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.request_timeout_s) as resp:
            if resp.status != 200:
                raise RuntimeError(f"telegram sendVoice HTTP {resp.status}")

    def poll_updates(
        self, router: CommandRouter, timeout_s: int = 25
    ) -> None:  # pragma: no cover - runtime loop
        offset = 0
        timeout_val = max(1, timeout_s)
        url = f"{self.config.telegram_api_base}/getUpdates?timeout={timeout_val}"
        while True:
            offset_query = f"&offset={offset}" if offset else ""
            req = urllib.request.Request(
                f"{url}{offset_query}",
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
                    if reply.voice_audio:
                        self.send_voice(str(message), reply.voice_audio)
                    if reply.action == "kill_switch":
                        break  # emergency stop also ends the poll loop


def default_router(
    config: CommandConfig,
    dispatcher: Any,
    kill_switch: Any,
    voice_service: Any = None,
    voice: str = DEFAULT_VOICE,
) -> CommandRouter:
    """Wire the router to the real dispatcher + kill-switch implementations.

    When `voice_service` is provided, /voice and the /voiceon toggle become
    live (sync wrapper over the async zero-compute VoiceService).
    """
    synthesize_voice = None
    if voice_service is not None:
        synthesize_voice = sync_voice_synthesizer(voice_service, voice=voice)
    return CommandRouter(
        config=config,
        fetch_status=lambda: dispatcher.fetch_status(),
        dispatch_issue=lambda issue_url: dispatcher.dispatch_issue(issue_url),
        arm_kill_switch=lambda: kill_switch.arm(),
        synthesize_voice=synthesize_voice,
    )
