# -*- coding: utf-8 -*-
"""Backward-compatible proxy pointing to canonical browser.runtime.infinite_scanner."""

from browser.runtime.infinite_scanner import (  # noqa: F401
    InfiniteScanner,
    ScanResult,
)

__all__ = ["InfiniteScanner", "ScanResult"]
