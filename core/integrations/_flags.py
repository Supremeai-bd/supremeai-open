"""Shared feature-flag + optional-import helpers for the integrations layer.

এই হেল্পারগুলো প্রজেক্টের existing প্যাটার্ন (services/memory_service.py-এ
`importlib.util.find_spec` দিয়ে sentence-transformers গ্রেসফুলি লোড করা) অনুসরণ করে।
"""

from __future__ import annotations

import importlib.util
import os


def flag(name: str, default: bool = False) -> bool:
    """Read a boolean feature-flag from environment (truthy: '1','true','yes','on')."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def import_available(module: str) -> bool:
    """Return True only if the given optional dependency can be imported."""
    return importlib.util.find_spec(module) is not None
