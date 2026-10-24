from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .models import ManualTask


class ManualTaskRegistry:
    """Creates non-secret handoffs for actions that code must not perform."""

    def __init__(self) -> None:
        self._tasks: dict[str, ManualTask] = {}

    def create(
        self,
        category: str,
        title: str,
        steps: list[str],
        evidence_required: list[str],
        owner: str = "authorized operator",
    ) -> ManualTask:
        task = ManualTask(
            id=str(uuid.uuid4()),
            category=category,
            title=title,
            owner=owner,
            steps=steps,
            evidence_required=evidence_required,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._tasks[task.id] = task
        return task

    def list_open(self) -> list[ManualTask]:
        return [task for task in self._tasks.values() if task.status == "open"]

    def complete(self, task_id: str) -> ManualTask:
        task = self._tasks[task_id]
        self._tasks[task_id] = task.model_copy(update={"status": "completed"})
        return self._tasks[task_id]

    def report(self) -> list[dict[str, object]]:
        return [task.model_dump(exclude={"secret_free"}) for task in self._tasks.values()]


manual_tasks = ManualTaskRegistry()

__all__ = ["ManualTaskRegistry", "manual_tasks"]
