"""Ecosystem shared storage — delegates to canonical adaptive_engine._store.

Maintains backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine._store import (
    ensure_columns,
    get_conn,
    get_db_path,
    jdump,
    jload,
)

__all__ = ["get_db_path", "get_conn", "ensure_columns", "jdump", "jload"]
