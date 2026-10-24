"""SupremeAI 2.0 — Telegram Security Guard & TOTP 2FA Verification Engine.

Provides:
  1. Anti-Hacking & Prompt Injection Detection (Jailbreak / Leak Prevention).
  2. Critical Action Interceptor (Database modification, Secrets, Core Rules).
  3. TOTP 2FA Challenge & Verification Engine (Google Authenticator / RFC 6238).
  4. Brute-Force Rate Limiting & Audit Logging.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import struct
import time
from typing import Any

from core.logging_config import logger


def _get_base32_totp_secret() -> str:
    """Retrieve or derive the Base32 TOTP secret for the administrator."""
    secret = os.environ.get("SUPREMEAI_ADMIN_TOTP_SECRET", "").strip()
    return secret


def check_totp_code(user_otp: str, base32_secret: str | None = None) -> bool:
    """RFC 6238 compliant TOTP verification with constant-time comparison and drift tolerance."""
    if not user_otp or len(user_otp.strip()) != 6 or not user_otp.strip().isdigit():
        return False

    secret = (base32_secret or _get_base32_totp_secret()).upper()
    if not secret:
        logger.error("TOTP validation unavailable: SUPREMEAI_ADMIN_TOTP_SECRET is not configured")
        return False
    try:
        missing_padding = len(secret) % 8
        if missing_padding:
            secret += "=" * (8 - missing_padding)
        key = base64.b32decode(secret)
        current_time = int(time.time() // 30)

        # Tolerance window: [-1 (prev 30s), 0 (current), +1 (next 30s)]
        for drift in [-1, 0, 1]:
            msg = struct.pack(">Q", current_time + drift)
            h = hmac.new(key, msg, hashlib.sha1).digest()
            o = h[19] & 15
            h_num = struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF
            code = f"{h_num % 1000000:06d}"
            if hmac.compare_digest(code, user_otp.strip()):
                return True
        return False
    except Exception as exc:
        logger.error(f"TOTP validation exception: {exc}")
        return False


class TelegramSecurityGuard:
    """Security Guard for Telegram Chat & Multi-Agent Operations."""

    def __init__(self) -> None:
        self._pending_challenges: dict[str, dict[str, Any]] = {}
        self._failed_attempts: dict[str, int] = {}
        self._lockouts: dict[str, float] = {}

        # Anti-Hacking & Prompt Injection signatures
        self.injection_patterns = [
            re.compile(
                r"ignore\s+(all\s+)?(previous|prior)\s+(instructions|directives|rules)", re.I
            ),
            re.compile(
                r"(reveal|print|show|dump|leak|exfiltrate)\s+(all\s+)?(api[_\s]?keys?|secrets?|\.env|passwords?|tokens?)",
                re.I,
            ),
            re.compile(
                r"you\s+are\s+now\s+(in\s+)?(dan\s+mode|unrestricted|god\s+mode|jailbreak)", re.I
            ),
            re.compile(r"bypass\s+(safety|security|guardrails|auth|totp|verification)", re.I),
            re.compile(
                r"override\s+(all\s+)?(constitutional\s+rules|core\s+directives|agents\.md)", re.I
            ),
        ]

        # Critical / Destructive Action keywords
        self.critical_actions = [
            (
                re.compile(
                    r"\b(drop|truncate|delete\s+from|wipe|destroy)\s+(table|database|db|postgres|schema|ai_memory)\b",
                    re.I,
                ),
                "DATABASE_DESTRUCTION",
                "Destructive Database Modification / Wipe",
            ),
            (
                re.compile(
                    r"\b(rotate|change|update|delete)\s+(api[_\s]?keys?|secrets?|admin\s+password|jwt_secret)\b",
                    re.I,
                ),
                "SECRET_MUTATION",
                "Critical Secret / API Key Rotation",
            ),
            (
                re.compile(
                    r"\b(disable|turn\s+off|remove)\s+(auth|security|guardrails|firewall|rate_limit)\b",
                    re.I,
                ),
                "SECURITY_DEGRADATION",
                "Security Guardrail Degradation",
            ),
            (
                re.compile(
                    r"\b(force\s+push|hard\s+reset|delete\s+branch)\s+(main|master|prod|production)\b",
                    re.I,
                ),
                "GIT_DESTRUCTIVE",
                "Destructive Git Operation on Production Branch",
            ),
            (
                re.compile(
                    r"\b(shutdown|reboot|terminate|destroy)\s+(cluster|backend|container|server|render)\b",
                    re.I,
                ),
                "INFRA_TEARDOWN",
                "Cloud Infrastructure Teardown / Reboot",
            ),
        ]

    def detect_prompt_injection(self, text: str) -> tuple[bool, str]:
        """Detect prompt injection and adversarial attacks."""
        for pattern in self.injection_patterns:
            if pattern.search(text):
                return True, "Potential prompt injection / security evasion pattern detected."
        return False, ""

    def detect_critical_action(self, text: str) -> tuple[bool, str, str]:
        """Detect whether the message commands a major destructive or privileged action."""
        for pattern, action_type, description in self.critical_actions:
            if pattern.search(text):
                return True, action_type, description
        return False, "", ""

    def is_locked_out(self, chat_id: int | str) -> tuple[bool, int]:
        """Check if chat_id is temporarily locked out due to excessive failed 2FA attempts."""
        cid = str(chat_id)
        if cid in self._lockouts:
            remaining = int(self._lockouts[cid] - time.time())
            if remaining > 0:
                return True, remaining
            else:
                self._lockouts.pop(cid, None)
                self._failed_attempts[cid] = 0
        return False, 0

    def create_challenge(
        self,
        chat_id: int | str,
        action_type: str,
        action_desc: str,
        original_command: str,
        ttl_seconds: int = 300,
    ) -> str:
        """Create a pending 2FA challenge for a critical action."""
        cid = str(chat_id)
        challenge_id = f"CHAL_{int(time.time())}_{cid[-4:]}"
        self._pending_challenges[cid] = {
            "challenge_id": challenge_id,
            "action_type": action_type,
            "action_desc": action_desc,
            "original_command": original_command,
            "expires_at": time.time() + ttl_seconds,
        }
        return challenge_id

    def has_pending_challenge(self, chat_id: int | str) -> bool:
        """Check if chat_id has an active pending challenge."""
        cid = str(chat_id)
        challenge = self._pending_challenges.get(cid)
        if not challenge:
            return False
        if time.time() > challenge["expires_at"]:
            self._pending_challenges.pop(cid, None)
            return False
        return True

    def get_pending_challenge(self, chat_id: int | str) -> dict[str, Any] | None:
        """Retrieve active challenge if valid."""
        if self.has_pending_challenge(chat_id):
            return self._pending_challenges.get(str(chat_id))
        return None

    def verify_challenge(
        self, chat_id: int | str, otp_code: str
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Verify the 6-digit TOTP code against the pending challenge."""
        cid = str(chat_id)
        locked, rem = self.is_locked_out(cid)
        if locked:
            return (
                False,
                f"🔒 2FA verification is locked due to multiple failed attempts. Try again in {rem} seconds.",
                None,
            )

        challenge = self.get_pending_challenge(cid)
        if not challenge:
            return False, "⚠️ No pending authorization challenge found or challenge expired.", None

        if check_totp_code(otp_code):
            # Success: reset attempts and consume challenge
            self._failed_attempts[cid] = 0
            self._pending_challenges.pop(cid, None)
            logger.info(
                f"✅ TOTP 2FA authorization verified for action '{challenge['action_type']}' by chat_id={cid}"
            )
            return (
                True,
                f"✅ Authorization verified for: <b>{challenge['action_desc']}</b>",
                challenge,
            )
        else:
            attempts = self._failed_attempts.get(cid, 0) + 1
            self._failed_attempts[cid] = attempts
            if attempts >= 3:
                self._lockouts[cid] = time.time() + 600  # 10 minutes lockout
                self._pending_challenges.pop(cid, None)
                logger.warning(
                    f"🚨 Multiple failed TOTP attempts on chat_id={cid}. Locked for 10 minutes."
                )
                return (
                    False,
                    "🚨 <b>Authentication Failed:</b> 3 incorrect OTP attempts. Security lock applied for 10 minutes.",
                    None,
                )
            return (
                False,
                f"❌ <b>Invalid OTP code.</b> ({3 - attempts} attempts remaining before temporary lockout).",
                None,
            )

    def validate_webapp_init_data(
        self, init_data: str, bot_token: str
    ) -> tuple[bool, dict[str, str]]:
        """Validate Telegram WebApp initData string using bot token HMAC-SHA256."""
        if not init_data or not bot_token:
            return False, {}
        try:
            from urllib.parse import parse_qsl

            parsed = dict(parse_qsl(init_data, keep_blank_values=True))
            if "hash" not in parsed:
                return False, {}
            received_hash = parsed.pop("hash")
            data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
            secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
            computed_hash = hmac.new(
                secret_key, data_check_string.encode(), hashlib.sha256
            ).hexdigest()
            if hmac.compare_digest(computed_hash, received_hash):
                return True, parsed
            return False, {}
        except Exception as e:
            logger.error(f"Telegram WebApp initData validation failed: {e}")
            return False, {}


# Global singleton instance
security_guard = TelegramSecurityGuard()
