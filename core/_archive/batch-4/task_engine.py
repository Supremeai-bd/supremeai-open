"""Task Engine — delegates to canonical adaptive_engine.task_engine.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.task_engine import (
    TaskEngine,
    TaskNotFoundError,
    TaskOwner,
    TaskRecord,
    TaskRetryExceeded,
    TaskState,
    TaskStateError,
    TaskTimeoutError,
    get_task_engine,
)

__all__ = [
    "TaskState",
    "TaskOwner",
    "TaskRecord",
    "TaskEngine",
    "get_task_engine",
    "TaskStateError",
    "TaskNotFoundError",
    "TaskRetryExceeded",
    "TaskTimeoutError",
]
