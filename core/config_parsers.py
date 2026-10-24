"""Leaf-level config value parsers — zero heavy dependencies (json/typing only).

বাংলা নোট: এই মডিউলটি dependency-লিফ রাখা হয়েছে ইচ্ছাকৃতভাবে — pydantic/fastapi
কিছুই import করে না, তাই `middleware/cors_policy.py`-এর মতো dependency-free
মডিউলও নির্দ্বিধায় এখান থেকে import করতে পারে (roadmap item 1.4, issue #1173)।
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["parse_origin_list"]


def parse_origin_list(value: Any) -> Any:
    """Single shared parser for CORS-origin-style list settings (issue #684 DRY).

    Accepts a JSON array string, a comma-separated string, or an existing
    list/tuple and returns the stripped, empty-entry-free ``list[str]``.
    Values of any other type are returned untouched so pydantic's own field
    validation keeps failing loudly on genuinely invalid config instead of
    the parser silently swallowing it.

    বাংলা নোট (roadmap 1.4 / issue #1173): এটি origin/list parsing-এর একমাত্র
    কপি — আগে এই লজিক `config_fields.py`, `middleware/cors_policy.py`,
    `core/security/origin_validator.py`, `api/server.py`,
    `api/routes/browser/_render_proxy.py`, `core/config_validation.py`,
    `core/config_secrets.py` — ৭ জায়গায় হাতে লেখা ছিল, edge behavior-ও
    আলাদা ছিল (কিছু কপি JSON-array বোঝে না, কিছু strip করে না)। সবাই এখন
    এই leaf module থেকে import করে।

    This is THE one copy of the origin/list parsing routine — previously the
    JSON-then-comma-split logic was duplicated across config/middleware/api
    modules with drifted edge behaviour.
    """
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return value
