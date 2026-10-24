"""Atomic single-op rate limiting for billable serverless Redis providers.

Issue #460 (Upstash quota burn): Upstash bills EVERY command inside a
pipeline as an individual request against the monthly free-tier quota. The
pre-fix production stack spent up to 12 billable ops per HTTP request
(3 middleware layers × 4-command ZSET / two-phase pipelines), which let
~3,000 background bot requests/day burn the 500k monthly quota in ~14 days.

একটি EVAL (Lua script) কল = ১টি billable op — script-এর ভেতরের redis.call()
গুলো আলাদাভাবে বিল হয় না। তাই ৪-কমান্ড pipeline → ১টি atomic EVAL (75%+ সাশ্রয়)।
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Fixed-window counter, single billable op:
#   INCR key                      → attempt count (rejected attempts counted
#                                   too, so retry storms cannot pass through
#                                   by flooding)
#   EXPIRE key window (on first)  → the window can never be extended by
#                                   retries — preserves the P2
#                                   no-self-amplification fix from
#                                   core/rate_limit.py (2026-09-12)
#   TTL<0 safety net              → keys that lost their TTL (crash between
#                                   INCR/EXPIRE in exotic providers) get one
#                                   re-applied instead of living forever
ATOMIC_WINDOW_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
else
    if redis.call('TTL', KEYS[1]) < 0 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
end
return current
"""


async def atomic_window_incr(
    client: Any,
    key: str,
    window: int | None = None,
    *,
    window_seconds: int | None = None,
    raise_on_failure: bool = False,
) -> int:
    """INCR ``key`` and enforce a ``window``-second TTL in ONE billable Redis op.

    বাংলা: ১টি মাত্র EVAL-এ counter বাড়ায় ও TTL সেট করে — Upstash-এ এটি
    ১টি মাত্র op হিসেবে বিল হয়। Returns the current window count (1-based).

    Issue #895: টেস্ট কন্ট্রাক্ট অনুযায়ী `window_seconds` কিওয়ার্ড আর্গুমেন্ট সাপোর্ট
    করা হয় (legacy positional `window`-এর পাশাপাশি alias হিসেবে)। Redis failure-এ
    exception না তুলে 0 রিটার্ন করা হয় — "fail-open" semantic (rate-limiter কখনো
    user-কে block করবে না শুধু Redis ডাউন থাকার কারণে)। WRONGTYPE recovery path
    সংরক্ষিত: legacy ZSET key থাকলে একবার delete করে retry করা হয়।

    Issue #936: `raise_on_failure=True` opt-in প্যারামিটার যোগ করা হয়েছে। ডিফল্ট False
    — Issue #895 contract সংরক্ষিত (test_redis_error_returns_zero টেস্ট যা
    `atomic_window_incr(redis, key, window_seconds=60)` দিয়ে কল করে ও 0 expect করে,
    সে ক্ষেত্রেও কাজ করে)। callers যাদের নিজেদের fail-mode policy আছে (যেমন
    middleware/tenant_rate_limiter.py::enforce_tenant_rate_limit — closed/fallback/open
    mode), তারা `raise_on_failure=True` পাস করে exception propagate করিয়ে নিজেদের
    except branch-এ fail_mode apply করতে পারবে। Issue #895-এর "fail-open return 0"
    contract-এর সাথে Issue #936-এর "Redis বিভ্রাটে tenant fail_mode apply করো"
    contract-কে reconcile করে।
    """
    # Issue #895: টেস্ট `window_seconds=60` কিওয়ার্ড দেয়; legacy callers `window`
    # positional দেয়। যেকোনো একটা থাকলেই হবে।
    effective_window = window_seconds if window_seconds is not None else window
    if effective_window is None:
        raise TypeError(
            "atomic_window_incr() missing required argument: "
            "pass `window` (positional) or `window_seconds=` (keyword)"
        )

    try:
        return int(await client.eval(ATOMIC_WINDOW_LUA, 1, key, int(effective_window)))
    except Exception as exc:
        # WRONGTYPE guard: a legacy ZSET (or other-typed) key under the same
        # name from the pre-#460 algorithm would make INCR fail forever.
        # Replace it once with a clean counter, then retry.
        if "WRONGTYPE" in str(exc):
            try:
                await client.delete(key)
                return int(await client.eval(ATOMIC_WINDOW_LUA, 1, key, int(effective_window)))
            except Exception as recovery_exc:
                # WRONGTYPE recovery-ও ব্যর্থ হলে: ডিফল্ট fail-open (Issue #895
                # contract — test_redis_error_returns_zero expects 0), কিন্তু
                # raise_on_failure=True হলে re-raise (Issue #936 — caller
                # নিজেদের fail_mode policy apply করতে পারে)।
                logger.warning(f"atomic_window_incr WRONGTYPE recovery failed for key={key}: {exc}")
                if raise_on_failure:
                    raise recovery_exc from exc
                return 0
        # Issue #895: Redis failure → return 0 (fail-open, per test contract).
        # আগে এখানে `raise` ছিল — callers নিজেদের except branch-ে fallback
        # trigger করত। নতুন contract: atomic_window_incr নিজেই fail-open করে।
        # Issue #936: `raise_on_failure=True` opt-in হলে re-raise করো — caller
        # (যেমন enforce_tenant_rate_limit) নিজেদের fail_mode policy apply করতে পারে।
        logger.warning(
            f"atomic_window_incr Redis failure for key={key}: {exc}. "
            "Returning 0 (fail-open per Issue #895 test contract)."
        )
        if raise_on_failure:
            raise
        return 0
