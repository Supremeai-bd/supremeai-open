"""Shared secret-strength policy for boot-time and runtime validators.

Issue #542 (BE-10): the JWT secret minimum length previously disagreed
across validators — ``core/config_secrets.py`` required >= 64 bytes when
the secret is first accessed, ``core/config_validator.py`` enforced only a
32-char floor at boot, and ``core/env_validator.py`` had no length check
at all. Boot-time fail-fast therefore used the weakest 32-char floor, so a
40-char secret passed startup validation but raised ``RuntimeError``
mid-request (500s on every authenticated endpoint).

This module is the single source of truth for that floor; every validator
imports the same constant.

Issue #567 (BE-16): the JWT secret env-var name also disagreed across
validators — ``config_validation`` required ``JWT_SECRET``,
``env_validator`` registered ``SUPREMEAI_JWT_SECRET`` as CRITICAL, and
``config_secrets`` accepted either — so an operator following one name
could pass one validator and fail another. The canonical name is now
``SUPREMEAI_JWT_SECRET`` everywhere; ``JWT_SECRET`` is a deprecated alias
accepted with a deprecation warning.
"""

import logging

JWT_SECRET_MIN_LENGTH = 64

# Issue #567 (BE-16): single canonical env-var name for the JWT secret.
JWT_SECRET_ENV = "SUPREMEAI_JWT_SECRET"
JWT_SECRET_DEPRECATED_ENV = "JWT_SECRET"

_logger = logging.getLogger(__name__)


def resolve_jwt_secret_env() -> str:
    """Resolve the JWT secret from the process env (single source of truth).

    Prefers the canonical ``SUPREMEAI_JWT_SECRET``; falls back to the
    deprecated ``JWT_SECRET`` alias with a deprecation warning so legacy
    deployments keep booting while every validator agrees on one name.
    Returns "" when neither variable is set.
    """
    import os

    value = os.getenv(JWT_SECRET_ENV, "")
    if value.strip():
        return value
    legacy = os.getenv(JWT_SECRET_DEPRECATED_ENV, "")
    if legacy.strip():
        _logger.warning(
            "Env var %s is a deprecated alias for %s — update the deployment "
            "environment to use the canonical name (Issue #567 / BE-16).",
            JWT_SECRET_DEPRECATED_ENV,
            JWT_SECRET_ENV,
        )
        return legacy
    return ""
