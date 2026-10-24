# Deprecated: moved to backend/core/plugins/experimental/telegram_plugin.py
from typing import Any

from ..experimental.telegram_plugin import TelegramPlugin as _TelegramPlugin
from .base import BasePlugin


class TelegramPlugin(_TelegramPlugin):
    """Shim — delegates to experimental implementation."""

    pass
