"""Healing statistics & health-prediction endpoints.

বাংলা: এই রুটগুলো আগে hardcoded dummy JSON দিত (#1617) — /healing/stats
সবসময় `success_rate: 0.95` আর /health/predictions সবসময় খালি list দিত।
এখন দুটোই সরাসরি services/auto_healer.py ও core/health/proactive_healer.py
singleton-এর আসল state থেকে dynamic ভাবে গণনা হয়। কোনো মেট্রিক hardcode নেই।
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends

from api.deps import get_current_user_token
from core.health.proactive_healer import get_proactive_healer
from services.auto_healer import get_healer

# Issue #1648: healing endpoints leak system state to anonymous callers.
# The /api/v1/health prefix is intentionally public for liveness probes, which
# silently exposed /api/v1/health/predictions as well — so auth is enforced
# HERE at the router level, independent of where the router is mounted.
router = APIRouter(tags=["healing"], dependencies=[Depends(get_current_user_token)])

_NON_NORMAL_BREAKER_STATES = ("open", "half_open")


def _enum_value(value: Any) -> Any:
    """Enum হলে .value, নাহলে কাঁচা মান — JSON-safe representation।"""
    return getattr(value, "value", value)


def _proactive_stats(healer: Any) -> dict[str, int]:
    """ProactiveHealer-এর স্ট্যাট ব্লক (private _stats-এর নিরাপদ read-only view)।"""
    return dict(getattr(healer, "_stats", {}) or {})


def _build_predictions(healer: Any) -> list[dict[str, Any]]:
    """আসল healer signal থেকে risk forecast — signal না থাকলে খালি list।"""
    predictions: list[dict[str, Any]] = []

    # 1) Recurrence risk: unresolved issue গুলোর category distribution
    unresolved = [i for i in healer.issue_history if not i.resolved]
    by_category = Counter(i.category.value for i in unresolved)
    total_unresolved = len(unresolved)
    for category, count in by_category.most_common():
        predictions.append(
            {
                "type": "issue_recurrence",
                "risk": category,
                "probability": round(count / total_unresolved, 4),
                "basis": f"{count} unresolved '{category}' issue(s) in healer history",
                "recommended_action": healer.known_fixes.get(category)
                or "inspect recent unresolved issues in this category",
            }
        )

    # 2) Dependency risk: non-normal circuit breaker state
    for name, cb in healer.circuit_breakers.items():
        status = cb.status
        state = str(_enum_value(status.get("state"))).lower()
        if state in _NON_NORMAL_BREAKER_STATES:
            predictions.append(
                {
                    "type": "circuit_breaker",
                    "risk": status.get("name", name),
                    "probability": None,
                    "basis": (
                        f"circuit breaker '{name}' is {state} "
                        f"({status.get('failure_count', 0)} failures)"
                    ),
                    "recommended_action": (
                        "back off and verify dependency health before further calls"
                    ),
                }
            )

    return predictions


@router.get("/health/predictions")
async def get_predictions() -> dict[str, Any]:
    """Health risk forecasts — সবসময় আসল healer state থেকে গণনা করা।"""
    healer = get_healer()
    predictions = _build_predictions(healer)
    proactive = get_proactive_healer()
    pstats = _proactive_stats(proactive)
    return {
        "predictions": predictions,
        "status": "active" if predictions or pstats.get("total_issues_detected", 0) else "idle",
        "basis": {
            "issues_in_history": len(healer.issue_history),
            "unresolved_issues": sum(1 for i in healer.issue_history if not i.resolved),
            "circuit_breakers_tracked": len(healer.circuit_breakers),
            "proactive_issues_detected": pstats.get("total_issues_detected", 0),
        },
    }


@router.get("/healing/stats")
async def get_stats() -> dict[str, Any]:
    """Live healing statistics — AutoHealer-এর আসল history/counters থেকে।"""
    healer = get_healer()
    fix_history = healer.fix_history
    total_fixes = len(fix_history)
    successes = sum(1 for r in fix_history if r.success)
    stats = healer.stats
    auto_fixed = stats.get("issues_auto_fixed", 0)
    pstats = _proactive_stats(get_proactive_healer())

    return {
        # remedy outcome rates — data না থাকলে None (আগের ভুয়া 0.95 নয়)
        "remedies_applied": total_fixes,
        "successful_remedies": successes,
        "success_rate": round(successes / total_fixes, 4) if total_fixes else None,
        "rollbacks_available": sum(1 for r in fix_history if r.rollback_available),
        # detection counters
        "issues_detected": stats.get("issues_detected", 0),
        "issues_auto_fixed": auto_fixed,
        "issues_manual_required": stats.get("issues_manual_required", 0),
        "avg_heal_time_seconds": (
            round(stats.get("total_heal_time_seconds", 0) / auto_fixed, 4) if auto_fixed else None
        ),
        # knowledge growth
        "known_fixes_learned": len(healer.known_fixes),
        "issue_history_size": len(healer.issue_history),
        "unresolved_issues": sum(1 for i in healer.issue_history if not i.resolved),
        # proactive (tiered) healer counters
        "proactive": {
            "total_issues_detected": pstats.get("total_issues_detected", 0),
            "successful_heals": pstats.get("successful_heals", 0),
            "failed_heals": pstats.get("failed_heals", 0),
            "escalated_issues": pstats.get("escalated_issues", 0),
        },
        # circuit breakers — live state per dependency
        "circuit_breakers": {
            name: {
                "state": _enum_value(cb.status.get("state")),
                "failure_count": cb.status.get("failure_count", 0),
                "threshold": cb.status.get("threshold", 0),
            }
            for name, cb in healer.circuit_breakers.items()
        },
        "recent_issues": [i.to_dict() for i in healer.issue_history[-10:]],
    }
