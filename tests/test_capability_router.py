"""tests/test_capability_router.py — unit tests for gateway capability router."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.capability_router import Account, CapabilityRouter


def test_register_and_select_healthy():
    clock = [1000.0]
    router = CapabilityRouter(clock=lambda: clock[0])
    router.register(
        "chat",
        [
            Account("a1", "groq", "m1", latency_ms=50),
            Account("a2", "gemini", "m2", latency_ms=10),
        ],
    )
    sel = router.select("chat")
    assert sel.account is not None
    assert sel.account.alias == "a2"  # lower latency
    assert sel.reason == "ok"


def test_select_skips_cooldown_and_unhealthy():
    clock = [1000.0]
    router = CapabilityRouter(clock=lambda: clock[0])
    a1 = Account("a1", "groq", "m1", healthy=False)
    a2 = Account("a2", "gemini", "m2", cooldown_until=2000.0)
    a3 = Account("a3", "openai", "m3")
    router.register("chat", [a1, a2, a3])
    sel = router.select("chat")
    assert sel.account is not None
    assert sel.account.alias == "a3"


def test_select_quota_exhausted():
    clock = [1000.0]
    router = CapabilityRouter(clock=lambda: clock[0])
    a1 = Account("a1", "groq", "m1", quota_remaining=0)
    router.register("chat", [a1])
    sel = router.select("chat")
    assert sel.account is None
    assert "no eligible" in sel.reason


def test_unknown_capability():
    router = CapabilityRouter()
    sel = router.select("nope")
    assert sel.account is None
    assert "unknown" in sel.reason


def test_record_failure_marks_unhealthy_after_three():
    clock = [1000.0]
    router = CapabilityRouter(clock=lambda: clock[0])
    router.register("chat", [Account("a1", "groq", "m1")])
    for _ in range(3):
        router.record_failure("chat", "a1", cooldown_s=10.0)
    acc = router.accounts("chat")[0]
    assert acc.healthy is False
    assert acc.consecutive_failures == 3


def test_record_success_restores_and_decrements_quota():
    clock = [1000.0]
    router = CapabilityRouter(clock=lambda: clock[0])
    a = Account(
        "a1", "groq", "m1", quota_remaining=5, healthy=False, consecutive_failures=2
    )
    router.register("chat", [a])
    router.record_success("chat", "a1", latency_ms=42.0, quota_used=2)
    acc = router.accounts("chat")[0]
    assert acc.healthy is True
    assert acc.consecutive_failures == 0
    assert acc.quota_remaining == 3
    assert acc.latency_ms == 42.0


def test_register_validation():
    router = CapabilityRouter()
    try:
        router.register("", [Account("a", "p", "m")])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        router.register("c", [])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_reset_health():
    clock = [1000.0]
    router = CapabilityRouter(clock=lambda: clock[0])
    a = Account(
        "a1", "groq", "m1", healthy=False, consecutive_failures=3, cooldown_until=9999.0
    )
    router.register("chat", [a])
    router.reset_health("chat", "a1")
    acc = router.accounts("chat")[0]
    assert acc.healthy is True
    assert acc.consecutive_failures == 0
    assert acc.cooldown_until == 0.0
