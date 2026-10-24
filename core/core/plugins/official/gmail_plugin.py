# Deprecated: moved to backend/core/plugins/experimental/gmail_plugin.py
# Keep this file as a shim that re-exports from experimental for backward compatibility.
from typing import Any

from ..experimental.gmail_plugin import GmailPlugin as _GmailPlugin
from .base import BasePlugin


class GmailPlugin(_GmailPlugin):
    """Shim — delegates to experimental implementation."""

    pass
