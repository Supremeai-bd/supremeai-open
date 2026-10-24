"""Public browser-service liveness probe (dependency-free router).

Issue #1490 contract: ``/api/browser/health`` is a liveness probe consumed by
CI route-inventory checks and the audit contract — it must be reachable
without credentials, exactly like the core ``/health/*`` probes.

Ported from the retired ``api/routes/browser_routes.py`` (Phase 3.2 route
consolidation, #2258): the legacy module was double-mounted (its admin router
was shadowed by the ``api.routes.browser`` package which registers first, and
its public router was mounted directly by ``app.py`` / ``core/app_builder.py``).
The probe now lives inside the canonical browser package on its own
auth-free router, so the legacy module could be deleted.

The capability probes it reports were already best-effort/try-except safe
(lazy imports, ImportError → ``available: False``) — that behaviour is
preserved verbatim.
"""

from datetime import datetime

from fastapi import APIRouter

from core.logging_config import logger

# Dependency-free by design (see module docstring): NO router-level auth
# dependency here, unlike the package's main ``router``.
public_router = APIRouter(
    prefix="/api/browser",
    tags=["browser-integration"],
)


async def check_llm_gateway() -> bool:
    """Check if LLM gateway is available"""
    try:
        # FIX (import): canonical module path (was 'backend.core.*').
        from core.llm.llm_gateway import llm_gateway  # noqa: F401

        # Simple health check - can we reach the gateway?
        return True
    except ImportError:
        return False


async def check_security_modules() -> bool:
    """Check if security modules are available"""
    try:
        # FIX (import + api-drift): 'OriginValidator' never existed — the real
        # validator is TrustedOriginMiddleware in core.security.origin_validator.
        from core.security.origin_validator import TrustedOriginMiddleware  # noqa: F401
        from core.security.protection.ssrf_protection import SSRFProtection  # noqa: F401

        return True
    except ImportError:
        return False


async def check_playwright() -> bool:
    """Check if Playwright is available"""
    try:
        # FIX (import): real API is get_global_browser (was PlaywrightManager).
        from core.playwright_manager import get_global_browser  # noqa: F401

        return True
    except ImportError:
        return False


async def check_unified_memory() -> bool:
    """Check if unified memory is available"""
    try:
        # FIX (import): canonical facade is UnifiedMemoryInterface (was UnifiedMemory).
        from core.unified_memory import UnifiedMemoryInterface  # noqa: F401

        return True
    except ImportError:
        return False


@public_router.get("/health")
async def browser_service_health():
    """
    Health check endpoint for browser integration service.
    Called by CI route-inventory checks and the audit contract!
    """
    health_status = {
        "service": "browser-integration",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "capabilities": [],
    }

    # Check each capability
    capabilities_checks = [
        ("ai-action", check_llm_gateway),
        ("security-scan", check_security_modules),
        ("screenshot", check_playwright),
        ("memory-storage", check_unified_memory),
    ]

    for capability_name, check_func in capabilities_checks:
        try:
            available = await check_func()
            health_status["capabilities"].append({"name": capability_name, "available": available})
            if not available:
                health_status["status"] = "degraded"
        except Exception as e:
            logger.warning(f"[browser-health] capability {capability_name} check failed: {e}")
            health_status["capabilities"].append(
                {"name": capability_name, "available": False, "error": str(e)}
            )
            health_status["status"] = "degraded"

    return health_status
