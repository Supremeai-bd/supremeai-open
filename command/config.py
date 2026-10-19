"""src/config.py — Command configuration (env-only, fail-closed, vault doctrine).

Every credential and endpoint for the supremeai-command satellite arrives via
environment variables. Zero secrets live in source (3-tier verification tier 1).
Missing or malformed configuration raises CommandConfigError listing every
offending variable — the process must never half-start with partial auth.
"""

from __future__ import annotations

import os

DEFAULT_TOWER_MCP_URL = "https://supremeai-mcp-tower.onrender.com/mcp"
DEFAULT_WEBHOOK_BIND_HOST = "127.0.0.1"
DEFAULT_WEBHOOK_PORT = 8787
MIN_HMAC_SECRET_LEN = 16

REQUIRED_VARS = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_SUPERADMIN_CHAT_ID",
    "COMMAND_HMAC_SECRET",
)

REDACTED = "***redacted***"


class CommandConfigError(Exception):
    """Raised when required configuration is missing or malformed."""


class CommandConfig:
    """Immutable-ish runtime configuration for the omnichannel admin control."""

    def __init__(
        self,
        telegram_bot_token: str,
        superadmin_chat_id: str,
        hmac_secret: str,
        redis_url: str | None = None,
        tower_mcp_url: str = DEFAULT_TOWER_MCP_URL,
        webhook_bind_host: str = DEFAULT_WEBHOOK_BIND_HOST,
        webhook_port: int = DEFAULT_WEBHOOK_PORT,
        request_timeout_s: float = 30.0,
    ) -> None:
        errors = []
        if not telegram_bot_token or not telegram_bot_token.strip():
            errors.append("TELEGRAM_BOT_TOKEN must be a non-empty bot token")
        if not superadmin_chat_id or not str(superadmin_chat_id).strip().isdigit():
            errors.append(
                "TELEGRAM_SUPERADMIN_CHAT_ID must be a numeric Telegram chat id"
            )
        if not hmac_secret or len(hmac_secret) < MIN_HMAC_SECRET_LEN:
            errors.append(
                f"COMMAND_HMAC_SECRET must be at least {MIN_HMAC_SECRET_LEN} characters"
            )
        if errors:
            raise CommandConfigError("; ".join(errors))
        self.telegram_bot_token = telegram_bot_token.strip()
        self.superadmin_chat_id = str(superadmin_chat_id).strip()
        self.hmac_secret = hmac_secret
        self.redis_url = redis_url or None
        self.tower_mcp_url = (tower_mcp_url or DEFAULT_TOWER_MCP_URL).strip()
        self.webhook_bind_host = webhook_bind_host or DEFAULT_WEBHOOK_BIND_HOST
        self.webhook_port = int(webhook_port or DEFAULT_WEBHOOK_PORT)
        self.request_timeout_s = float(request_timeout_s)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> CommandConfig:
        source: dict[str, str] = dict(os.environ if env is None else env)
        missing = [v for v in REQUIRED_VARS if not source.get(v)]
        if missing:
            raise CommandConfigError(
                "missing required environment variables: " + ", ".join(missing)
            )
        return cls(
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN", ""),
            superadmin_chat_id=source.get("TELEGRAM_SUPERADMIN_CHAT_ID", ""),
            hmac_secret=source.get("COMMAND_HMAC_SECRET", ""),
            redis_url=source.get("REDIS_URL") or None,
            tower_mcp_url=source.get("TOWER_MCP_URL", DEFAULT_TOWER_MCP_URL),
            webhook_bind_host=source.get(
                "WEBHOOK_BIND_HOST", DEFAULT_WEBHOOK_BIND_HOST
            ),
            webhook_port=source.get("WEBHOOK_PORT", DEFAULT_WEBHOOK_PORT),
            request_timeout_s=float(source.get("COMMAND_REQUEST_TIMEOUT_S", "30")),
        )

    @property
    def telegram_api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.telegram_bot_token}"

    def is_superadmin(self, chat_id: str) -> bool:
        """RBAC: only the configured superadmin chat id may trigger actions."""
        return bool(chat_id) and str(chat_id).strip() == self.superadmin_chat_id

    def __repr__(self) -> str:  # secrets never render — vault doctrine
        return (
            f"CommandConfig(superadmin_chat_id={self.superadmin_chat_id}, redis_url={self.redis_url}, "
            f"tower_mcp_url={self.tower_mcp_url}, webhook={self.webhook_bind_host}:{self.webhook_port}, "
            f"telegram_bot_token={REDACTED}, hmac_secret={REDACTED})"
        )
