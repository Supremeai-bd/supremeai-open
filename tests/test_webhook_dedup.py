"""tests/test_webhook_dedup.py — dedup + task lease for webhook ingress."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command.webhook_ingress import (
    InMemoryDedupStore,
    WebhookIngress,
    compute_signature,
)


def _ingress(on_valid, dedup=None, task_factory=None):
    return WebhookIngress(
        "h" * 32, on_valid=on_valid, dedup=dedup, task_factory=task_factory
    )


def test_dedup_drops_duplicate():
    calls = []
    store = InMemoryDedupStore()
    ing = _ingress(calls.append, dedup=store)
    body = json.dumps({"issue_url": "https://github.com/o/r/issues/1"}).encode()
    sig = compute_signature("h" * 32, body)
    assert ing.handle("POST", "/dispatch", body, sig)[0] == 202
    assert calls == ["https://github.com/o/r/issues/1"]
    # duplicate delivery
    assert ing.handle("POST", "/dispatch", body, sig)[0] == 202
    assert calls == ["https://github.com/o/r/issues/1"]  # not re-dispatched


def test_task_factory_invoked_once():
    calls = []
    tasks = []
    store = InMemoryDedupStore()
    ing = _ingress(calls.append, dedup=store, task_factory=tasks.append)
    body = json.dumps({"issue_url": "https://github.com/o/r/issues/2"}).encode()
    sig = compute_signature("h" * 32, body)
    ing.handle("POST", "/dispatch", body, sig)
    assert tasks == ["https://github.com/o/r/issues/2"]
    ing.handle("POST", "/dispatch", body, sig)  # duplicate
    assert tasks == ["https://github.com/o/r/issues/2"]  # factory not re-run


def test_no_dedup_preserves_original_behavior():
    calls = []
    ing = _ingress(calls.append)  # no dedup
    body = json.dumps({"issue_url": "https://github.com/o/r/issues/3"}).encode()
    sig = compute_signature("h" * 32, body)
    assert ing.handle("POST", "/dispatch", body, sig)[0] == 202
    assert ing.handle("POST", "/dispatch", body, sig)[0] == 202
    assert len(calls) == 2
