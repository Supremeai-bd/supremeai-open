"""Shared client primitives for external APIs (DRY)."""

from core.clients.render_api import RENDER_API_BASE, render_get_json

__all__ = ["RENDER_API_BASE", "render_get_json"]
