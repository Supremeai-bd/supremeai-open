# backend/api/deps.py
"""Canonical Dependency Re-export Module (Unified Auth DI - Audit B-006 Fix).

All authentication and infrastructure dependencies are canonically defined in
`api.dependencies`. This module re-exports them so existing callers keep working
with 100% architectural consistency and without duplicate authentication bypass logic.

Issue #685 (Domain 15) correlation contract: this module intentionally adds no
logging of its own — request correlation ids are established once per request by
the RequestContextMiddleware / SupremeContextMiddleware pair (X-Correlation-ID →
X-Request-ID → fresh UUID) and flow through loguru's contextualize scope into
every log line emitted by the resolved dependencies and their routes. The DI
layer in `api.dependencies` already threads `request.state.correlation_id` into
ErrorEvents (see verify_autonomous_agent_token).
"""

from __future__ import annotations

from api.dependencies import (
    get_ai_integrator,
    get_current_admin,
    get_current_tenant,
    get_current_user_token,
    get_fitness_engine,
    get_rate_limiter,
    get_tenant_db,
    verify_autonomous_agent_token,
)

__all__ = [
    "get_ai_integrator",
    "get_current_admin",
    "get_current_tenant",
    "get_current_user_token",
    "get_fitness_engine",
    "get_rate_limiter",
    "get_tenant_db",
    "verify_autonomous_agent_token",
]
