"""core.monitoring package.

Re-exports metrics collector and budget monitor from core._monitoring_legacy
for backward compatibility with `from core.monitoring import get_metrics_collector`.
"""
from __future__ import annotations

from typing import Any

_ml: Any = None


def _load_ml() -> Any:
    global _ml
    if _ml is None:
        try:
            import _monitoring_legacy as _ml
        except ImportError:
            try:
                from core import _monitoring_legacy as _ml
            except ImportError:
                try:
                    import importlib

                    _ml = importlib.import_module("core._monitoring_legacy")
                except ImportError:
                    _ml = None
    return _ml


def __getattr__(name: str) -> Any:
    mod = _load_ml()
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    mod = _load_ml()
    return list(mod.__dict__.keys()) if mod is not None else []

