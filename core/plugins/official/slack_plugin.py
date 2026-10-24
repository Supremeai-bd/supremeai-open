# Deprecated: moved to backend/core/plugins/experimental/slack_plugin.py
from typing import Any

from ..experimental.slack_plugin import SlackPlugin as _SlackPlugin
from .base import BasePlugin


class SlackPlugin(_SlackPlugin):
    """Shim — delegates to experimental implementation."""

    pass
