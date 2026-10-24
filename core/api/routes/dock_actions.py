"""Compatibility bridge: re-export router from dock_integrations.py."""

from api.routes.dock_integrations import router  # noqa: F401

__all__ = ["router"]
