# Deprecated: moved to backend/core/plugins/experimental/notion_plugin.py
from typing import Any

from ..experimental.notion_plugin import NotionPlugin as _NotionPlugin
from .base import BasePlugin


class NotionPlugin(_NotionPlugin):
    """Shim — delegates to experimental implementation."""

    pass
