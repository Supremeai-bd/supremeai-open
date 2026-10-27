"""status_publication.py — public status payload contracts for the SupremeAI
unified gateway (#1729).

Splits the former single health_check() payload (which leaked operator-grade
fleet detail on every public probe route) into three tiers:

  - public root (GET /): exactly the four consumer-relevant fields
  - liveness probes (GET /health, /healthz, /api/health, /api/v1/health,
    /v1/health): HTTP-200 probe fields only — the documented consumer contract
    (docs/CONSUMERS.md) branches on HTTP status, not body fields, and the
    SEQ453 watchdog + federation CI consume status/chat_ready semantics,
    which are preserved
  - operator fleet detail (GET /internal/status, GET /webhook/scout/status):
    full inventory behind the strict key gate (_require_operator_key in
    service/app.py — no guest pass-through, fail-closed)

stdlib-only and import-safe without fastapi so the payload contracts are
unit-testable offline (tests/test_status_publication.py).
"""

from __future__ import annotations

PUBLIC_ROOT_FIELDS: tuple[str, ...] = ("status", "service_name", "version", "chat_ready")
LIVENESS_FIELDS: tuple[str, ...] = ("status", "service_name", "version", "chat_ready", "timestamp")

# Recon-relevant fields that must never appear on an unauthenticated surface (#1729):
# capacity, provider topology, stealth infrastructure posture, internal naming
# conventions and cooldown/captcha states.
OPERATOR_ONLY_FIELDS: tuple[str, ...] = (
    "total_keys",
    "total_healthy_keys",
    "stealth_priority1_configured",
    "stealth_dns",
    "web_sessions_active",
    "web_session_status",
    "webhook_scout",
    "telegram_webhook_configured",
    "active_providers",
)


def build_public_root_payload(
    status: str = "healthy",
    service_name: str = "supremeai-api",
    version: str = "2.0.0",
    chat_ready: bool = False,
) -> dict:
    """Exactly the four public fields of the consumer contract (HTTP 200 unchanged)."""
    return {
        "status": status,
        "service_name": service_name,
        "version": version,
        "chat_ready": bool(chat_ready),
    }


def build_liveness_payload(
    status: str,
    service_name: str,
    version: str,
    chat_ready: bool,
    timestamp: str,
) -> dict:
    """200-OK liveness probe body: watchdog-consumed semantics preserved, no fleet detail."""
    return {
        "status": status,
        "service_name": service_name,
        "version": version,
        "chat_ready": bool(chat_ready),
        "timestamp": timestamp,
    }


def assert_no_operator_fields(payload: dict) -> dict:
    """Guard: raise if any operator-only field leaks into a public payload.

    Called by every public status handler so a future field added to the fleet
    payload cannot silently re-appear on the public surface (the #1729 drift
    class made structural, not procedural).
    """
    leaked = sorted(set(payload) & set(OPERATOR_ONLY_FIELDS))
    if leaked:
        raise ValueError(f"operator-only fields leaked into public payload: {leaked}")
    return payload
