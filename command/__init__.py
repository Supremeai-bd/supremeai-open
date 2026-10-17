"""supremeai-command — Omnichannel Admin Remote Control (foundation seed).

Modules:
    config          - env-only configuration (fail-closed, vault doctrine)
    telegram_bot    - RBAC command router + stdlib Telegram transport
    webhook_ingress - HMAC-SHA256 authenticated webhook server
    dispatcher      - MCP Control Tower relay + minimal Redis kill-switch
"""

from .config import CommandConfig, CommandConfigError  # noqa: F401
from .dispatcher import (  # noqa: F401
    DispatcherError,
    KillSwitch,
    KillSwitchUnavailable,
    MiniRedis,
    TowerDispatcher,
)
from .telegram_bot import CommandRouter, TelegramUpdate  # noqa: F401
from .webhook_ingress import WebhookIngress, verify_hmac  # noqa: F401

__all__ = [
    "CommandConfig",
    "CommandConfigError",
    "CommandRouter",
    "DispatcherError",
    "KillSwitch",
    "KillSwitchUnavailable",
    "MiniRedis",
    "TelegramUpdate",
    "TowerDispatcher",
    "WebhookIngress",
    "verify_hmac",
]
