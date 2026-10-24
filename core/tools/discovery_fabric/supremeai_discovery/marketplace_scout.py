from __future__ import annotations

from typing import Any


def classify_artifact(item: dict[str, Any]) -> dict[str, Any]:
    license_name = item.get("license")
    signals = []
    if item.get("stars", 0) >= 5000 or item.get("downloads", 0) >= 1_000_000:
        signals.append("strong-adoption")
    if item.get("updated_at"):
        signals.append("has-freshness-signal")
    if license_name:
        signals.append("license-declared")
    if "security" in str(item).lower() or "vulnerability" in str(item).lower():
        signals.append("security-signal-present")
    return {"id": item.get("title"), "source": item.get("source"), "signals": signals, "license": license_name, "url": item.get("url")}


def build_shortlist(items: list[dict[str, Any]], *, max_risk: float = 0.35) -> list[dict[str, Any]]:
    usable = [x for x in items if float(x.get("risk", 0.0)) <= max_risk]
    usable.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return [classify_artifact(x) | {"score": x.get("score", 0.0)} for x in usable]
