"""Event-driven automation pipeline: normalize, dedup, policy, task, dispatch.

Implements proposal section 8 on top of the existing command layer. The
pipeline is dependency-injected (dedup store, permission check, handler,
notifier, clock) so it stays unit-testable without sockets or Redis.
Bounded retries and a durable task record prevent stuck/duplicate jobs.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class DedupStore(Protocol):
    def contains(self, key: str) -> bool: ...
    def add(self, key: str) -> None: ...


class InMemoryDedupStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def contains(self, key: str) -> bool:
        return key in self._keys

    def add(self, key: str) -> None:
        self._keys.add(key)


@dataclass
class Event:
    event_id: str
    kind: str
    payload: dict[str, Any]
    received_at: float


@dataclass
class DurableTask:
    task_id: str
    event_id: str
    kind: str
    state: str = "queued"  # queued | running | completed | failed | blocked
    attempts: int = 0
    last_error: str = ""


TASK_STATES = {"queued", "running", "completed", "failed", "blocked"}


class EventPipeline:
    def __init__(
        self,
        dedup: DedupStore | None = None,
        permission_ok: Callable[[Event], bool] | None = None,
        handler: Callable[[Event, DurableTask], bool] | None = None,
        notifier: Callable[[DurableTask], None] | None = None,
        clock: Callable[[], float] = time.time,
        max_retries: int = 3,
    ) -> None:
        self._dedup = dedup if dedup is not None else InMemoryDedupStore()
        self._permission_ok = permission_ok if permission_ok is not None else (lambda e: True)
        self._handler = handler if handler is not None else (lambda e, t: True)
        self._notifier = notifier
        self._clock = clock
        self._max_retries = max_retries
        self._tasks: dict[str, DurableTask] = {}
        self._task_counter = 0

    def normalize(self, raw: Any) -> Event:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {"payload": raw}
        if not isinstance(raw, dict):
            raw = {"payload": raw}
        event_id = str(raw.get("id") or raw.get("event_id") or self._hash(raw))
        kind = str(raw.get("kind") or raw.get("type") or raw.get("event") or "unknown")
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
        return Event(event_id=event_id, kind=kind, payload=payload, received_at=self._clock())

    def _hash(self, raw: Any) -> str:
        return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def submit(self, raw: Any) -> DurableTask | None:
        event = self.normalize(raw)
        if self._dedup.contains(event.event_id):
            return None
        self._dedup.add(event.event_id)
        if not self._permission_ok(event):
            task = self._new_task(event, state="blocked")
            self._notify(task)
            return task
        task = self._new_task(event, state="queued")
        self._run(task, event)
        return task

    def _new_task(self, event: Event, state: str = "queued") -> DurableTask:
        self._task_counter += 1
        task = DurableTask(
            task_id=f"task-{self._task_counter}",
            event_id=event.event_id,
            kind=event.kind,
            state=state,
        )
        self._tasks[task.task_id] = task
        return task

    def _run(self, task: DurableTask, event: Event) -> None:
        while task.attempts < self._max_retries:
            task.attempts += 1
            task.state = "running"
            try:
                ok = bool(self._handler(event, task))
            except Exception as exc:  # noqa: BLE001 - record and retry
                ok = False
                task.last_error = str(exc)
            if ok:
                task.state = "completed"
                self._notify(task)
                return
            task.last_error = task.last_error or "handler returned false"
            task.state = "queued"
        task.state = "failed"
        self._notify(task)

    def _notify(self, task: DurableTask) -> None:
        if self._notifier is not None:
            self._notifier(task)

    def tasks(self) -> list[DurableTask]:
        return list(self._tasks.values())

    def get(self, task_id: str) -> DurableTask | None:
        return self._tasks.get(task_id)
