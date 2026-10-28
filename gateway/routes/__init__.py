"""Safe re-exports of API routers from core.api.routes (SSOT #751)."""

from __future__ import annotations

from core.api.routes import *  # noqa: F401, F403
from core.api.routes import _safe_imports, _ROUTER_DEFINITIONS  # noqa: F401

