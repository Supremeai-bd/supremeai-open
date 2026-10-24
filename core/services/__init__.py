"""core.services package.

Provides backward-compatible attribute access to singletons in core.service_container
(e.g. `services.parallel_router`, `services.redis_queue`, `services.global_http_client`).
"""
from __future__ import annotations

import sys
from typing import Any

from core import service_container as _sc
from core.service_container import *  # noqa: F401, F403


def __getattr__(name: str) -> Any:
    return getattr(_sc, name)


def __setattr__(name: str, value: Any) -> None:
    setattr(_sc, name, value)
