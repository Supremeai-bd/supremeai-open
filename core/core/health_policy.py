"""Role-aware DB degradation policy (P1 — production readiness).

বাংলা: ডাটাবেস ফেল করলে কোন সার্ভিস কতটুকু degraded mode-এ চলবে —
এটা এখন একটা স্পষ্ট, টেস্ট-করা পলিসি (আর ছড়ানো-ছিটানো if-এর ভেতরে
লুকানো নয়):

    core (বা role unset)  → production/staging: DB ফেল = NOT READY
                            (SUPABASE_ALLOW_DB_DEGRADATION উপেক্ষিত + loud error)
    core                  → local/dev/test: dev convenience-এর জন্য
                            SUPABASE_ALLOW_DB_DEGRADATION=true হলে allowed
    worker/scraper/mcp    → সব এনভায়রনমেন্টে role-specific degradation allowed

আরও দেখুন: docs/deployment/HEALTH_CONTRACT.md (readiness semantics)
"""

from __future__ import annotations

CORE_ROLES = ("core", "")
DEGRADED_ROLES = ("worker", "scraper", "mcp")

PolicyDecision = tuple[bool, str]


def db_failure_readiness(
    role: str,
    env: str,
    degradation_requested: bool,
) -> PolicyDecision:
    """Decide whether the service may stay READY despite a DB failure.

    Returns (serve_ready, reason). This is the single source of truth used by
    the readiness database check in core/app_builder.py.
    """
    role_normalized = (role or "core").strip().lower()
    env_normalized = (env or "").lower()

    if role_normalized in DEGRADED_ROLES:
        return (
            True,
            f"role-specific degradation allowed (role={role_normalized})",
        )

    # core / unset role
    if degradation_requested:
        if env_normalized in ("production", "staging"):
            return (
                False,
                f"SUPABASE_ALLOW_DB_DEGRADATION is IGNORED for role={role_normalized} "
                f"in env={env_normalized} — core DB failure means NOT READY (fail-closed)",
            )
        return (
            True,
            f"dev degradation allowed (role={role_normalized}, env={env_normalized})",
        )

    return (False, f"no degradation policy matched (role={role_normalized}, env={env_normalized})")


def is_critical_db_check(role: str) -> bool:
    """Whether a DB failure is a critical readiness failure for this role."""
    return (role or "core").strip().lower() not in DEGRADED_ROLES


__all__ = [
    "CORE_ROLES",
    "DEGRADED_ROLES",
    "PolicyDecision",
    "db_failure_readiness",
    "is_critical_db_check",
]
