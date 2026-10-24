"""Secrets-health endpoint (GET /admin-api/secrets-health).

Issue #1820: the Command Center "Secrets Health" module
(frontend/src/commandcenter/modules/secure/SecretsHealth.tsx) polls
``GET /admin-api/secrets-health`` — an endpoint that never existed, so every
poll 404'd and the module permanently rendered ``OVERALL: UNKNOWN``.

This endpoint gives the module real data using ONLY structural checks
(value-presence / strength heuristics) — no secret material is ever
returned. The JWT-strength logic mirrors ``run_security_scan``
(endpoints_security.py), which the issue explicitly nominates for reuse.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse

from api.routes.admin_dashboard import router
from core.config import settings
from core.logging_config import logger

# Same known-weak set the security-scan endpoint enforces (single source of
# truth duplicated structurally on purpose: both surfaces must stay in sync
# with Settings.validate_jwt_secret_strength, not with each other).
_WEAK_SECRETS = {
    "secret",
    "password",
    "123456",
    "changeme",
    "admin",
    "jwt_secret",
}


def _check_jwt_secret() -> dict[str, Any]:
    """JWT secret strength — same heuristics as run_security_scan."""
    try:
        secret = settings.jwt_secret or ""
    except Exception:
        # Production fail-closed: jwt_secret raises RuntimeError when the
        # mandated secret is missing/short — surface that as unhealthy
        # instead of 500-ing the whole health view.
        logger.warning("[secrets-health] jwt_secret unavailable (raised)")
        return {"name": "jwt_secret", "healthy": False}
    weak = not secret or len(secret) < 64 or secret.lower() in _WEAK_SECRETS
    return {"name": "jwt_secret", "healthy": not weak}


def _check_stripe_api_key() -> dict[str, Any]:
    """Billing-critical Stripe key must be configured (presence-only)."""
    try:
        configured = bool(
            getattr(settings, "stripe_api_key", None)
            and settings.stripe_api_key.get_secret_value().strip()
        )
    except Exception:
        configured = False
    return {"name": "stripe_api_key", "healthy": configured}


def _check_credential_encryption_key() -> dict[str, Any]:
    """Fail-closed credential store (#1570) needs one of these env keys.

    Without it every credential-persisting flow (browser credentials, IMAP
    connect) raises CredentialEncryptionUnavailableError — a real
    operational health signal, not just config drift.
    """
    configured = any(
        os.getenv(name, "").strip()
        for name in (
            "SUPREMEAI_CREDENTIAL_ENC_KEY",
            "BROWSER_CREDENTIALS_ENCRYPTION_KEY",
            "ENCRYPTION_KEY",
        )
    )
    return {"name": "credential_encryption_key", "healthy": configured}


@router.get("/secrets-health")
def get_secrets_health():
    """Aggregated secret-config health for the Command Center module.

    Returns the exact shape the frontend expects:
    ``{ status: 'healthy' | 'degraded', secrets: [{ name, healthy }] }``
    """
    try:
        secrets = [
            _check_jwt_secret(),
            _check_stripe_api_key(),
            _check_credential_encryption_key(),
        ]
    except Exception as exc:  # fail loud but structured — module degrades, no crash
        logger.error(f"[secrets-health] aggregation failed: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "detail": str(exc), "secrets": []},
        )
    overall = "healthy" if all(s["healthy"] for s in secrets) else "degraded"
    return {"status": overall, "secrets": secrets}
