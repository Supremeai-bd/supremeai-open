# -*- coding: utf-8 -*-
"""Backward-compatible proxy pointing to canonical browser.runtime.cookie_bridge."""

from browser.runtime.cookie_bridge import (  # noqa: F401
    CookieBridge,
    CookieBridgeError,
    CookieRecord,
)

__all__ = ["CookieBridge", "CookieBridgeError", "CookieRecord"]
