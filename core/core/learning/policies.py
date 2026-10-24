"""Bounded adaptation policies — Sprint 5 (smart cache TTL + adaptive threshold).

Pure functions implementing the plan's bounded-adaptation rules:

§13.2 Smart TTL:
    frequently reused + stable  -> longer TTL
    rarely reused               -> shorter TTL
    adaptation never exceeds configured bounds (min/max multipliers).

§7.3 Adaptive threshold (only AFTER sufficient history exists):
    baseline threshold + historical distribution -> bounded adaptive
    threshold with minimum bound, maximum bound, change-rate limit and a
    deterministic, reversible result.

All functions are pure, deterministic and unit-testable; every output is
clamped so no adaptation can run away.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "MAX_TTL_MULTIPLIER",
    "MIN_TTL_MULTIPLIER",
    "adaptive_threshold",
    "smart_ttl",
]

MIN_TTL_MULTIPLIER = 0.5  # never shorter than half the base TTL
MAX_TTL_MULTIPLIER = 2.0  # never longer than double the base TTL


def smart_ttl(base_ttl_seconds: float, *, hit_rate: float, reuse_count: int) -> int:
    """Bounded TTL adaptation from measured cache effectiveness.

    hit_rate  — measured cache hit rate in [0, 1]
    reuse_count — how many times entries of this class were reused

    Returns the adapted TTL, always within
    [base*MIN_TTL_MULTIPLIER, base*MAX_TTL_MULTIPLIER].
    """
    try:
        base = max(1.0, float(base_ttl_seconds))
        rate = min(1.0, max(0.0, float(hit_rate)))
        reuse = max(0, int(reuse_count))
    except (TypeError, ValueError):
        return int(base_ttl_seconds)

    # Evidence gates: reuse must exist before TTL ever grows.
    if reuse < 3:
        multiplier = MIN_TTL_MULTIPLIER if rate < 0.2 else 1.0
    else:
        # Linear in hit rate: 0.0 -> 0.5x, 1.0 -> 2.0x (bounded extremes).
        multiplier = MIN_TTL_MULTIPLIER + rate * (MAX_TTL_MULTIPLIER - MIN_TTL_MULTIPLIER)
    adapted = base * multiplier
    adapted = min(base * MAX_TTL_MULTIPLIER, max(base * MIN_TTL_MULTIPLIER, adapted))
    return int(round(adapted))


def adaptive_threshold(
    baseline: float,
    history: Sequence[float],
    *,
    min_bound: float,
    max_bound: float,
    max_change_rate: float = 0.05,
    min_samples: int = 10,
) -> float:
    """Bounded adaptive threshold from historical distribution (plan §7.3).

    Uses a robust center (median) of ``history`` and moves the baseline
    toward it, clamped by:
      * absolute [min_bound, max_bound]
      * per-adjustment change-rate limit (``max_change_rate`` of the baseline)
      * minimum sample requirement (fewer than ``min_samples`` → unchanged)
    """
    try:
        base = float(baseline)
    except (TypeError, ValueError):
        return baseline
    values = [float(v) for v in history if v is not None]
    if len(values) < min_samples:
        return base  # insufficient evidence → no change (plan Principle 1)

    values.sort()
    n = len(values)
    median = values[n // 2] if n % 2 else 0.5 * (values[n // 2 - 1] + values[n // 2])

    step = (median - base) * 0.5  # move halfway toward the observed center
    step = min(max_change_rate, max(-max_change_rate, step))
    adjusted = base + step
    return min(max_bound, max(min_bound, adjusted))
