"""tests/test_event_pipeline.py — unit tests for command event pipeline."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from command.event_pipeline import (
        EventPipeline,
        InMemoryDedupStore,
    )
except ImportError:
    from src.event_pipeline import (
        EventPipeline,
        InMemoryDedupStore,
    )


def test_normalize_extracts_id_and_kind():
    p = EventPipeline()
    ev = p.normalize({"id": "e1", "kind": "ci_failure", "payload": {"x": 1}})
    assert ev.event_id == "e1"
    assert ev.kind == "ci_failure"
    assert ev.payload == {"x": 1}


def test_normalize_from_string_and_hash_id():
    p = EventPipeline()
    ev = p.normalize('{"type": "push", "foo": "bar"}')
    assert ev.kind == "push"
    assert ev.event_id  # hashed fallback or provided


def test_dedup_drops_duplicate():
    p = EventPipeline()
    t1 = p.submit({"id": "e1", "kind": "k"})
    t2 = p.submit({"id": "e1", "kind": "k"})
    assert t1 is not None
    assert t2 is None
    assert len(p.tasks()) == 1


def test_permission_blocked():
    notified = []
    p = EventPipeline(permission_ok=lambda e: False, notifier=notified.append)
    t = p.submit({"id": "e2", "kind": "k"})
    assert t is not None
    assert t.state == "blocked"
    assert len(notified) == 1


def test_handler_success():
    p = EventPipeline(handler=lambda e, t: True)
    t = p.submit({"id": "e3", "kind": "k"})
    assert t.state == "completed"
    assert t.attempts == 1


def test_handler_retry_then_fail():
    calls = {"n": 0}

    def h(e, t):
        calls["n"] += 1
        return False

    p = EventPipeline(handler=h, max_retries=2)
    t = p.submit({"id": "e4", "kind": "k"})
    assert t.state == "failed"
    assert t.attempts == 2


def test_handler_exception_retries():
    calls = {"n": 0}

    def h(e, t):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return True

    p = EventPipeline(handler=h, max_retries=3)
    t = p.submit({"id": "e5", "kind": "k"})
    assert t.state == "completed"
    assert t.attempts == 2
    assert t.last_error == "" or t.last_error is not None


def test_notify_on_completion():
    notified = []
    p = EventPipeline(handler=lambda e, t: True, notifier=notified.append)
    t = p.submit({"id": "e6", "kind": "k"})
    assert len(notified) == 1
    assert notified[0].task_id == t.task_id


def test_get_and_tasks():
    p = EventPipeline(handler=lambda e, t: True)
    t = p.submit({"id": "e7", "kind": "k"})
    assert p.get(t.task_id) is t
    assert t.task_id in [x.task_id for x in p.tasks()]


def test_custom_dedup_store():
    store = InMemoryDedupStore()
    store.add("pre")
    p = EventPipeline(dedup=store)
    t = p.submit({"id": "pre", "kind": "k"})
    assert t is None
