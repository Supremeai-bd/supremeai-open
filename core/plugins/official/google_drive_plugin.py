# Deprecated: moved to backend/core/plugins/experimental/google_drive_plugin.py
from typing import Any

from ..experimental.google_drive_plugin import GoogleDrivePlugin as _GoogleDrivePlugin
from .base import BasePlugin


class GoogleDrivePlugin(_GoogleDrivePlugin):
    """Shim — delegates to experimental implementation."""

    pass
