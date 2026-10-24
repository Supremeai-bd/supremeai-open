"""Background task tracking helper.

বাংলা: `asyncio.create_task()` দিয়ে তৈরি টাস্কের রেফারেন্স কোথাও না রাখলে
Python-এর garbage collector মাঝপথে সেটা silently তুলে নিতে (ও বাতিল করতে) পারে —
এটা asyncio ডকুমেন্টেশনে উল্লেখিত একটা পরিচিত ফাঁদ। এই মডিউলটা একটা module-level
strong-reference সেট বজায় রাখে যাতে টাস্ক শেষ না হওয়া পর্যন্ত GC হয়ে না যায়।

Usage:
    from core.utils.background_tasks import track_task
    task = track_task(asyncio.create_task(some_coro()))
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import TypeVar

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Module-level strong-reference registry — একবার তৈরি হওয়া টাস্ক এখানে যোগ হয়,
# শেষ হলে নিজে থেকেই সরে যায় (done-callback দিয়ে)।
_BACKGROUND_TASKS: set[asyncio.Task] = set()

# Per-task metadata (creation time) so the admin security dashboard can show
# REAL telemetry instead of fabricated numbers (Wave 2.5, issue #1242).
_TASK_META: dict[asyncio.Task, dict] = {}

# Count of tracked tasks that completed with an unhandled exception since
# process start — real "failuresBlocked"-style signal for the dashboard.
_TRACKED_TASK_FAILURES: int = 0


def _task_done_callback(task: asyncio.Task) -> None:
    """Safely remove task from tracker and log any unhandled exception."""
    global _TRACKED_TASK_FAILURES
    _BACKGROUND_TASKS.discard(task)
    _TASK_META.pop(task, None)
    try:
        if not task.cancelled():
            exc = task.exception()
            if exc:
                _TRACKED_TASK_FAILURES += 1
                task_name = task.get_name() if hasattr(task, "get_name") else "unnamed_task"
                logger.error(
                    f"Background task '{task_name}' failed with unhandled exception: {exc}",
                    exc_info=exc,
                )
    except Exception as err:
        logger.error(f"Error inspecting completed background task: {err}")


def track_task(task: asyncio.Task[_T]) -> asyncio.Task[_T]:
    """Keep a strong reference to *task* until it completes, and log any error.

    Prevents the classic asyncio "fire-and-forget task gets garbage
    collected mid-flight" bug and ensures errors are never silent. Pass
    the task through this function right where you create it:
    ``track_task(asyncio.create_task(coro()))``.
    """
    _BACKGROUND_TASKS.add(task)
    _TASK_META[task] = {"created_at": datetime.now(UTC).isoformat()}
    task.add_done_callback(_task_done_callback)
    return task


def snapshot_tasks() -> list[dict]:
    """REAL telemetry for the admin security dashboard (issue #1242).

    বাংলা: রেজিস্ট্রিতে এখন যত লাইভ টাস্ক আছে — নাম, স্টেটাস, শুরুর সময়।
    কোনো বানানো সংখ্যা নয়; খালি রেজিস্ট্রি মানে সত্যিই কোনো ট্র্যাকড টাস্ক চলছে না।
    """
    tasks: list[dict] = []
    for task in list(_BACKGROUND_TASKS):
        meta = _TASK_META.get(task, {})
        try:
            status = (
                "running"
                if not task.done()
                else (
                    "cancelled" if task.cancelled() else ("failed" if task.exception() else "done")
                )
            )
        except Exception:
            status = "unknown"
        tasks.append(
            {
                "id": f"{id(task):x}",
                "name": task.get_name() if hasattr(task, "get_name") else "unnamed_task",
                "strongRef": True,
                "status": status,
                "startedAt": meta.get("created_at"),
            }
        )
    return tasks


def security_memory_snapshot() -> dict:
    """REAL memory/task telemetry or explicit unavailable markers (issue #1242).

    Returns honest fields — every value is measured, never fabricated:
      trackedTasks / untrackedTasks: live asyncio task registry diff
      failuresBlocked: tracked tasks that completed with unhandled exceptions
      heapUsed/heapTotal: tracemalloc when tracing is active, else None
    """
    try:
        all_tasks = {t for t in asyncio.all_tasks() if not t.done()}
    except Exception:
        all_tasks = set()
    tracked_live = {t for t in _BACKGROUND_TASKS if not t.done()}
    untracked = len(all_tasks - tracked_live)

    heap_used = heap_total = None
    try:
        import tracemalloc

        if tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            heap_used = f"{current / 1024 / 1024:.1f} MB"
            heap_total = f"{peak / 1024 / 1024:.1f} MB (peak)"
    except Exception:
        # #1409: stats are best-effort, but failures must be visible — a silent
        # pass here hid runtime diagnostics from production logs.
        logger.exception("Failed to collect tracemalloc heap stats")

    return {
        "trackedTasks": len(tracked_live),
        "untrackedTasks": untracked,
        "zombieTasksDetected": untracked,
        "failuresBlocked": _TRACKED_TASK_FAILURES,
        "heapUsed": heap_used,
        "heapTotal": heap_total,
        "heapSource": "tracemalloc" if heap_used is not None else "unavailable",
    }


def safe_create_task(
    coro: Coroutine[None, None, _T],
    name: str | None = None,
) -> asyncio.Task[_T]:
    """Safely spawn a tracked background task with GC-protection and error logging."""
    task = asyncio.create_task(coro, name=name)
    return track_task(task)
