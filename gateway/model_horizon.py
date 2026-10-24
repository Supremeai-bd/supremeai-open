"""Temporal horizon calibration (ChronoFact Pillar 1 pattern) for SupremeAI gateway.

Loads ``model_horizon.json`` and provides drift interception + retired-model
flagging. Knowledge cutoff vs training freeze divergence is detected in <5ms
(deterministic, no LLM inference).

Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

_HORIZON_PATH = Path(__file__).resolve().parent / "model_horizon.json"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


@dataclass
class ModelHorizon:
    model_id: str
    provider: str
    official_cutoff: date
    training_freeze: date
    status: str  # "active" | "retired"
    successor: str | None = None
    retired_on: date | None = None

    @property
    def is_retired(self) -> bool:
        return self.status == "retired"

    def drift_days(self, as_of: date | None = None) -> int:
        """Days between training freeze and official cutoff (positive = gap)."""
        ref = as_of or datetime.now(timezone.utc).date()
        # drift = how far 'as_of' is past the training freeze relative to cutoff
        if ref <= self.training_freeze:
            return 0
        return (ref - self.training_freeze).days

    def is_cutoff_stale(self, as_of: date | None = None) -> bool:
        ref = as_of or datetime.now(timezone.utc).date()
        return ref > self.official_cutoff


@dataclass
class DriftEvent:
    model_id: str
    kind: str  # "retired" | "cutoff_stale" | "freeze_drift" | "ok"
    detail: str
    successor: str | None = None


class ModelHorizonRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _HORIZON_PATH
        self._models: dict[str, ModelHorizon] = {}
        self._load()

    def _load(self) -> None:
        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for m in data.get("models", []):
            mh = ModelHorizon(
                model_id=m["id"],
                provider=m["provider"],
                official_cutoff=_parse_date(m["official_cutoff"]),
                training_freeze=_parse_date(m["training_freeze"]),
                status=m.get("status", "active"),
                successor=m.get("successor"),
                retired_on=_parse_date(m["retired_on"]) if m.get("retired_on") else None,
            )
            self._models[mh.model_id] = mh

    def get(self, model_id: str) -> ModelHorizon | None:
        return self._models.get(model_id)

    def all(self) -> list[ModelHorizon]:
        return list(self._models.values())

    def intercept(self, model_id: str, as_of: date | None = None) -> DriftEvent:
        ref = as_of or datetime.now(timezone.utc).date()
        mh = self._models.get(model_id)
        if mh is None:
            return DriftEvent(model_id, "unknown", "model not in horizon registry")
        if mh.is_retired:
            return DriftEvent(
                model_id,
                "retired",
                f"model retired on {mh.retired_on}; use successor",
                successor=mh.successor,
            )
        if mh.is_cutoff_stale(ref):
            return DriftEvent(
                model_id,
                "cutoff_stale",
                f"query date {ref} past official cutoff {mh.official_cutoff}",
                successor=mh.successor,
            )
        if mh.drift_days(ref) > 0:
            return DriftEvent(
                model_id,
                "freeze_drift",
                f"{mh.drift_days(ref)} days past training freeze {mh.training_freeze}",
            )
        return DriftEvent(model_id, "ok", "within horizon")


# Module-level singleton (lazy-friendly).
_registry: ModelHorizonRegistry | None = None


def get_registry() -> ModelHorizonRegistry:
    global _registry
    if _registry is None:
        _registry = ModelHorizonRegistry()
    return _registry


def intercept_drift(model_id: str, as_of: date | None = None) -> DriftEvent:
    return get_registry().intercept(model_id, as_of)


def reset_registry(path: Path | None = None) -> ModelHorizonRegistry:
    global _registry
    _registry = ModelHorizonRegistry(path) if path else ModelHorizonRegistry()
    return _registry
