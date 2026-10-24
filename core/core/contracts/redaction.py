"""Secret-safe evidence serialization."""

from __future__ import annotations

import re
from typing import Any

_SECRET_KEY = re.compile(
    r"(token|secret|password|api[_-]?key|authorization|private[_-]?key|credential)", re.I
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


__all__ = ["redact"]
