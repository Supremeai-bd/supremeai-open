"""core.monitoring package.

Re-exports metrics collector and budget monitor from core._monitoring_legacy
for backward compatibility with `from core.monitoring import get_metrics_collector`.
"""
from __future__ import annotations

from typing import Any

from core import _monitoring_legacy as _ml
from core._monitoring_legacy import *  # noqa: F401, F403


def __getattr__(name: str) -> Any:
    return getattr(_ml, name)
