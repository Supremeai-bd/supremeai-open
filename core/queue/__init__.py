"""Backward-compatibility shim for core.queue -> core.task_queue."""
from __future__ import annotations

import importlib.util
import os
import sys

# Re-export Python standard library queue symbols to prevent breaking
# stdlib and third-party libraries (e.g. urllib3, requests, concurrent.futures)
# if core/ is added to sys.path.
for _path in sys.path:
    _candidate = os.path.join(_path, "queue.py")
    if os.path.isfile(_candidate):
        _spec = importlib.util.spec_from_file_location("_stdlib_queue", _candidate)
        if _spec and _spec.loader:
            _stdlib_queue = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_stdlib_queue)
            for _attr in ("Queue", "LifoQueue", "PriorityQueue", "SimpleQueue", "Empty", "Full"):
                if hasattr(_stdlib_queue, _attr):
                    globals()[_attr] = getattr(_stdlib_queue, _attr)
            break

from core.task_queue import *  # noqa: F401, F403
from core.task_queue.task_contract import TaskEnvelope, TaskState  # noqa: F401
from core.task_queue.task_queue import RedisTaskQueue, redis_configured, task_queue  # noqa: F401
from core.task_queue.task_queue_enhanced import (  # noqa: F401
    EnhancedTaskQueue,
    celery_app,
    get_task_queue,
)
