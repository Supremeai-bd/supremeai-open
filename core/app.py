"""Backwards-compatibility shim — the FastAPI app assembly moved to ``app`` (backend root).

Issue #683 Section 1 (inward layer violations): the old ``core/app.py`` built
the full ASGI app while importing ``api.routers`` /
``api.routes.stream_chat_sse`` from inside ``core/`` — a forbidden core → api
import. Assembling the app is composition-layer work, so the implementation now
lives in ``backend/app.py`` (next to ``main.py``).

This shim re-exports the same singleton so all existing
``from core.app import app`` call sites (tests, commandcenter metrics,
maintenance pipeline, and the uvicorn boot string ``core.app:app`` in
``main.py``) keep working unchanged — while ``core/`` no longer contains or
imports any ``api`` module.
"""

from __future__ import annotations

import os
import sys

# Same sys.path bootstrap the original module performed (core/ sits one level
# below the backend root; tests and scripts may import core.app before the root
# is otherwise on sys.path).
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app import app  # noqa: E402,F401

__all__ = ["app"]
