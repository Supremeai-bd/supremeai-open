"""tests/test_redis_rate_limit.py — Way 14 evidence (distributed limiter, fail-open)."""

from __future__ import annotations

import sys
from pathlib import Path

_GATEWAY_DIR = next(
    (
        p
        for p in Path(__file__).resolve().parents
        if (p / "main.py").is_file() and (p / "routing_policy.json").is_file()
    ),
    Path(__file__).resolve().parent.parent,
)
for p in (str(_GATEWAY_DIR), str(_GATEWAY_DIR.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

from gateway.service.redis_rate_limit import RedisSlidingWindowLimiter


@pytest.mark.asyncio
async def test_fallback_when_no_redis_url(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    limiter = RedisSlidingWindowLimiter(window_s=60, max_requests=3)
    d1 = await limiter.check("k1")
    d2 = await limiter.check("k1")
    d3 = await limiter.check("k1")
    d4 = await limiter.check("k1")
    assert d1.allowed and d2.allowed and d3.allowed
    assert not d4.allowed and d4.retry_after_s and d4.retry_after_s >= 1
    assert limiter.degraded is True  # served by in-process fallback


@pytest.mark.asyncio
async def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "redis://localhost:1/0")
    monkeypatch.setenv("RATE_LIMIT_DISTRIBUTED", "0")
    limiter = RedisSlidingWindowLimiter(window_s=60, max_requests=2)
    d = await limiter.check("k")
    assert d.allowed
    assert limiter.degraded is True


@pytest.mark.asyncio
async def test_bad_redis_url_fails_open(monkeypatch):
    """Unroutable redis must degrade to the fallback, never raise."""
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "redis://127.0.0.1:9/0")  # discard port
    limiter = RedisSlidingWindowLimiter(window_s=60, max_requests=5)
    d = await limiter.check("k")
    assert isinstance(d.allowed, bool)
    assert limiter.degraded is True


@pytest.mark.asyncio
async def test_decision_shape_matches_canonical():
    """P3: decision must be the exact canonical RateDecision (shape-preserving)."""
    from gateway.rate_limit import RateDecision

    monkeypatch_absent = RedisSlidingWindowLimiter(window_s=60, max_requests=3)
    d = await monkeypatch_absent.check("k")
    assert type(d) is RateDecision
    assert isinstance(d.allowed, bool)
    assert isinstance(d.remaining, int)
    assert isinstance(d.reset_epoch, int)
    assert d.retry_after_s is None or isinstance(d.retry_after_s, int)


@pytest.mark.asyncio
async def test_invalid_config_fails_closed():
    with pytest.raises(ValueError):
        RedisSlidingWindowLimiter(window_s=0, max_requests=3)
    with pytest.raises(ValueError):
        RedisSlidingWindowLimiter(window_s=60, max_requests=0)
