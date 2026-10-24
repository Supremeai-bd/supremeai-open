"""Token Estimation Calibration — Sprint 5 (bounded, measurable, reversible).

Implements the plan's §6.2 learning process:

    estimated_tokens + actual provider-reported usage
        -> provider/model-specific error
        -> EMA / bounded calibration
        -> better future estimate

Safety properties (plan: "Do not allow calibration to become unbounded or
unstable"):
  * the ratio is clamped to ``[MIN_RATIO, MAX_RATIO]`` at every update
  * the per-update step is clamped to ``MAX_STEP`` (change-rate limit)
  * fewer than ``MIN_SAMPLES`` observations → ratio stays 1.0 (no evidence,
    no learning — plan Principle 1)
  * pure in-process state; zero network; never raises
"""

from __future__ import annotations

import threading

__all__ = [
    "MAX_RATIO",
    "MAX_STEP",
    "MIN_RATIO",
    "MIN_SAMPLES",
    "get_calibration_stats",
    "get_ratio",
    "reset_calibration",
    "update_ratio",
]

MIN_RATIO = 0.5
MAX_RATIO = 2.0
MAX_STEP = 0.1  # change-rate limit per single observation
MIN_SAMPLES = 5
_EMA_ALPHA = 0.2  # standard EMA smoothing

_lock = threading.Lock()
# (provider, model) -> {"ratio": float, "samples": int}
_ratios: dict[tuple[str, str], dict[str, float]] = {}


def _normalize(provider: str | None, model: str | None) -> tuple[str, str]:
    return (str(provider or "unknown"), str(model or "unknown"))


def update_ratio(
    provider: str | None, model: str | None, *, estimated: int, actual: int
) -> float | None:
    """Fold one (estimated, actual) observation into the EMA. Returns new ratio.

    Bounded in every dimension; invalid inputs (<= 0) are ignored.
    """
    try:
        estimated_i = int(estimated)
        actual_i = int(actual)
    except (TypeError, ValueError):
        return None
    if estimated_i <= 0 or actual_i <= 0:
        return None

    key = _normalize(provider, model)
    raw = actual_i / float(estimated_i)
    with _lock:
        entry = _ratios.setdefault(key, {"ratio": 1.0, "samples": 0})
        entry["samples"] = int(entry["samples"]) + 1
        if int(entry["samples"]) < MIN_SAMPLES:
            # Insufficient evidence — no behavioral change yet (plan Principle 1).
            return float(entry["ratio"])
        target = min(MAX_RATIO, max(MIN_RATIO, raw))
        proposed = float(entry["ratio"]) + _EMA_ALPHA * (target - float(entry["ratio"]))
        # change-rate limit: never jump more than MAX_STEP in one update
        proposed = min(
            float(entry["ratio"]) + MAX_STEP, max(float(entry["ratio"]) - MAX_STEP, proposed)
        )
        entry["ratio"] = min(MAX_RATIO, max(MIN_RATIO, proposed))
        return float(entry["ratio"])


def get_ratio(provider: str | None, model: str | None) -> float:
    """Current calibrated ratio (1.0 until MIN_SAMPLES observations exist)."""
    key = _normalize(provider, model)
    with _lock:
        entry = _ratios.get(key)
        if not entry:
            return 1.0
        return float(entry["ratio"])


def get_calibration_stats() -> dict[str, dict[str, float]]:
    """Snapshot of all calibrated ratios (for observability endpoints)."""
    with _lock:
        return {
            f"{provider}/{model}": {
                "ratio": round(float(entry["ratio"]), 4),
                "samples": int(entry["samples"]),
            }
            for (provider, model), entry in sorted(_ratios.items())
        }


def reset_calibration() -> None:
    """Testing helper — clears all calibration state."""
    with _lock:
        _ratios.clear()
