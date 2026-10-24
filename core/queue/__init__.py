"""Backward-compatibility shim for core.queue -> core.task_queue."""
from __future__ import annotations

from core.task_queue import *  # noqa: F401, F403
from core.task_queue.task_contract import TaskEnvelope, TaskState  # noqa: F401
from core.task_queue.task_queue import RedisTaskQueue, redis_configured, task_queue  # noqa: F401
from core.task_queue.task_queue_enhanced import EnhancedTaskQueue, celery_app, get_task_queue  # noqa: F401
