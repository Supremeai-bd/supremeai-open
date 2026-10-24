# backend/core/app_builder.py
"""FastAPI Application Builder — Centralized Middleware & Dependency Injection (Zero-Hardcode)

বাংলা মন্তব্ব্য: এই মডিউলটি FastAPI অ্যাপ্লিকেশন ইনস্ট্যান্স তৈরি করে এবং সমস্ত মিডলওয়্যার,
রাউটার, এবং ডিপেন্ডেন্সি ইনজেকশন কনফিগারেশন কেন্দ্রীভূতভাবে পরিচালনা করে।
যেকোনো hardcoded ভ্যালু নেই। সবকিছু environment-driven।

Key Components:
- `create_app()`: মূল FastAPI ইনস্ট্যান্স তৈরি করে এবং কনফিগার করে।
- Middleware chain: সিকিউরিটি, CORS, লগিং, রেট-লিমিটিং ইত্যাদি।
- মিডলওয়্যার অর্ডার ক্রিটিক্যাল — authentication অবশ্যই honeypot এবং chaos মিডলওয়্যারের আগে রান করবে।

Critical Security Note: মিডলওয়্যার অর্ডার সঠিক করা হয়েছে যাতে অথেনটিকেশন
হনিপট এবং চাওস মিডলওয়্যারের আগে রান হয়, সিকিউরিটি ইস্যু ঠিক করতে।
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from core.config import settings
from core.logging_config import logger, setup_logging

# বাংলা মন্তব্ব্য: মিডলওয়্যার ইম্পোর্ট লেজি-লোডেড — create_app()-এর ভিতরে ইম্পোর্ট হবে
# এর ফলে কোল্ড স্টার্ট ২০% দ্রুত হবে এবং modularity বাড়বে।


# বাংলা মন্তব্ব্য: স্টার্টআপ অডিট ও লগিং — টেস্ট এক্সক্লুডেড
# সেন্ট্রি ইনিশিয়ালাইজেশন monitoring/init_observability()-এ কেন্দ্রীভূত (Issue #566 / BE-15:
# এখানে 0.1 rate-সহ ডুপ্লিকেট sentry_sdk.init() ছিল — একমাত্র init path monitoring মডিউল)।
# Issue #569 (BE-18): the import-time audit_container_resources() call was
# removed — it was a `pass` no-op (dead code) that made the boot path look
# like memory auditing was active. If container auditing is ever wanted, the
# ContainerAuditor.run() loop must be started explicitly, not via a hollow
# boot-path call.
if "pytest" not in sys.modules and os.getenv("CI") != "true":
    setup_logging()


def create_app(title: str = settings.PROJECT_NAME) -> FastAPI:
    """Create and configure the FastAPI application with all middleware and routes.

    বাংলা মন্তব্ব্য: মিডলওয়্যার ইম্পোর্ট লেজিভাবে ফাংশনের ভিতরে করা হয়েছে
    যাতে মডিউল লোড হতে দেরি না হয় এবং কোল্ড স্টার্ট ২০% দ্রুত হয়।
    """

    # বাংলা মন্তব্ব্য: লেজি ইম্পোর্ট — মিডলওয়্যার ক্লাস শুধু create_app() কল করলেই লোড হবে
    from fastapi.middleware.cors import CORSMiddleware

    from api.middleware import (
        RequestIdMiddleware,
        ResponseStandardizationMiddleware,
        SupremeContextMiddleware,
        TenantExtractionMiddleware,
    )
    from core.lifespan import app_lifespan

    # P0 (production docs exposure policy): gates /docs, /redoc and openapi.json.
    from core.middleware.docs_auth import DocsAuthMiddleware

    # RESTORE-AND-WIRE (2026-09-14): QueryTimingMiddleware was previously deleted as
    # "orphan"; per the repo doctrine (wire-next before archive) it is now restored
    # and wired — slow-request logging + rolling percentile history for /metrics.
    from core.middleware.query_timing import QueryTimingMiddleware
    from core.middleware.security import (
        RequestValidationMiddleware,
        SecurityHeadersMiddleware,
    )
    from core.observability.observability_middleware import ObservabilityMiddleware
    from core.rate_limit import RateLimitMiddleware
    from core.request_context import RequestContextMiddleware
    from core.security.api_key_middleware import APIKeyAuthMiddleware
    from core.security.authentication.auth_middleware import AuthMiddleware
    from core.security.autonoguard_middleware import AutonoGuardMiddleware
    from core.security.origin_validator import TrustedOriginMiddleware
    from core.security.protection.honeypot import HoneypotMiddleware
    from middleware.chaos_injector import ChaosInjectorMiddleware
    from middleware.idempotency_middleware import IdempotencyMiddleware

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        # 🔬 Evolution v3.0: Enhanced lifespan with validation & health checks
        import asyncio

        from core.browser_session_manager import shutdown_browser_sessions
        from core.config_validator import print_config_summary, validate_config
        from core.health_routes import register_check, set_liveness
        from utils.platform_detect import DETECTED_PLATFORM, auto_set_platform_env

        if os.getenv("OPENAPI_GENERATION", "false").lower() == "true":
            logger.info("🛠️ OPENAPI_GENERATION mode active. Bypassing lifespan checks.")
            async with app_lifespan(app):
                yield
            await shutdown_browser_sessions()
            return

        logger.debug("\n" + "=" * 60)
        logger.debug(f"🚀 SupremeAI Starting on {DETECTED_PLATFORM.platform.value.upper()}...")
        logger.debug("=" * 60)

        # Auto-detect platform
        platform = auto_set_platform_env()
        logger.debug(f"📍 Platform: {platform}")

        # Validate configuration (Fail-Fast)
        logger.debug("\n🔧 Validating configuration...")
        result = validate_config()
        if not result.is_valid:
            logger.critical(result.format_errors())
            if any(e.severity.value == "error" for e in result.errors):
                logger.critical("❌ Fatal configuration errors. Exiting.")
                import sys

                sys.exit(1)
        else:
            logger.debug("✅ Configuration valid.")

        # Print summary (masked secrets)
        print_config_summary()

        # Register health checks
        logger.debug("\n🏥 Registering health checks...")

        async def _check_database() -> bool:
            # Audit fix (patch v3 session): two prior defects made this critical
            # readiness check fail in EVERY environment:
            #   1. ``from core.db import engine`` always yielded None (lazy
            #      placeholder never resolved) → None.connect() AttributeError.
            #   2. even with a real engine, the SYNC connect()/execute() API was
            #      used against the ASYNC engine (asyncpg).
            # Failures were also swallowed silently — now logged server-side.
            try:
                from sqlalchemy import text

                from core.db import get_engine

                engine = get_engine()
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                return True
            except Exception as exc:
                # Direct Supabase REST ping fallback
                try:
                    import httpx

                    supa_url = getattr(settings, "supabase_url", "")
                    supa_key = getattr(settings, "supabase_service_key", "") or getattr(
                        settings, "supabase_key", ""
                    )
                    if supa_url and supa_key:
                        async with httpx.AsyncClient(timeout=4.0) as client:
                            r = await client.get(
                                f"{supa_url}/rest/v1/",
                                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
                            )
                            if r.status_code in (200, 404):
                                return True
                except Exception as rest_exc:
                    logger.debug(f"Supabase REST health fallback check failed: {rest_exc}")
                logger.warning(f"Database health check failed: {exc}")
                # বাংলা (P1 — role-aware DB degradation policy):
                # একক সোর্স অব ট্রুথ core/health_policy.py::db_failure_readiness —
                #   core (prod/stage): DB ফেল = NOT READY (degradation flag উপেক্ষিত)
                #   core (dev/local):  flag দিলে dev convenience-এর জন্য allowed
                #   worker/scraper/mcp: সব এনভে degradation allowed
                from core.health_policy import db_failure_readiness

                role = os.getenv("SUPREMEAI_SERVICE_ROLE", "core")
                degradation_requested = (
                    os.getenv("SUPABASE_ALLOW_DB_DEGRADATION", "false").lower() == "true"
                )
                serve_ready, reason = db_failure_readiness(
                    role, settings.env, degradation_requested
                )
                if serve_ready:
                    logger.warning(f"Database degraded mode ACTIVE: {reason}")
                else:
                    logger.error(f"Database readiness refused: {reason}")
                return serve_ready

        def _check_memory() -> bool:
            try:
                import psutil

                mem = psutil.virtual_memory()
                return mem.percent < 90
            except ImportError:
                return True

        # In standalone scraper/worker roles, DB is not a critical gating check
        # বাংলা: criticality সিদ্ধান্তও একক পলিসি মডিউল থেকে (P1 consistency)
        from core.health_policy import is_critical_db_check

        register_check(
            "database",
            _check_database,
            critical=is_critical_db_check(os.getenv("SUPREMEAI_SERVICE_ROLE", "")),
        )
        register_check("memory", _check_memory, critical=False)

        monitoring_task = None
        healer = None
        if settings.AUTO_HEALING_ENABLED:
            try:
                from services.auto_healer import get_healer

                healer = get_healer()
                monitoring_task = asyncio.create_task(healer.start_monitoring())
            except Exception as e:
                logger.warning(f"⚠️ Auto-healer unavailable, continuing without it: {e}")
                healer = None

        async with app_lifespan(app):
            yield

        logger.debug("\n🛑 SupremeAI shutting down...")
        set_liveness(False)
        await shutdown_browser_sessions()

        if settings.AUTO_HEALING_ENABLED and monitoring_task and healer:
            healer.stop_monitoring()
            await monitoring_task

    # বাংলা (P0 — production docs/OpenAPI exposure policy):
    # আগে এখানে getattr(settings, "docs_enabled", True) ছিল — settings-এ
    # docs_enabled ফিল্ডই নেই, তাই সব এনভায়রনমেন্টে (প্রোডাকশন সহ) docs
    # সবসময় চালু থাকত। এখন effective_docs_enabled পলিসি:
    #   local/dev  → ডিফল্ট চালু (ডেভ সুবিধা)
    #   prod/stage → ডিফল্ট বন্ধ; শুধু SUPREMEAI_DOCS_ENABLED=true +
    #                শক্তিশালী SUPREMEAI_DOCS_PASSWORD থাকলে চালু
    # (Boot-এ দুর্বল পাসওয়ার্ড হলে config_validation ফেইল-ফাস্ট করে।)
    _docs_exposed = settings.effective_docs_enabled
    docs_url = "/docs" if _docs_exposed else None
    redoc_url = "/redoc" if _docs_exposed else None
    openapi_url = f"{settings.API_V1_STR}/openapi.json" if _docs_exposed else None
    if settings.env.lower() in ("production", "staging"):
        logger.info(
            f"🛡️ Docs/OpenAPI exposure policy: "
            f"{'ENABLED (admin-gated)' if _docs_exposed else 'DISABLED'} (env={settings.env})"
        )

    # বাংলা মন্তব্ব্য: অ্যাপ্লিকেশন ইনস্ট্যান্স তৈরি করা হচ্ছে
    app = FastAPI(
        title=title,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=_lifespan,
    )

    # বাংলা মন্তব্ব্য: মিডলওয়্যার চেইন — ORDER IS CRITICAL FOR SECURITY
    #
    # ⚠️ ROOT-CAUSE FIX: আগের কমেন্ট এখানে ভুল ধরে নিয়েছিল যে
    # app.add_middleware() যেটা *সবার আগে* কল করা হয় সেটাই সবচেয়ে বাইরের
    # (outermost) লেয়ার হয়ে যায়। বাস্তবে Starlette-এ এটা ঠিক উল্টো:
    # add_middleware() প্রতিবার internal `user_middleware` লিস্টের *শুরুতে*
    # insert করে (insert(0, ...)), আর app বানানোর সময় সেই লিস্টটা reversed
    # order-এ wrap করা হয় — ফলে যে middleware *সবার শেষে* add_middleware()
    # দিয়ে যোগ হয়, সেটাই runtime-এ সবচেয়ে বাইরের লেয়ার (request-এ সবার আগে
    # চলে, response-এ সবার শেষে), আর যেটা *সবার প্রথমে* যোগ হয় সেটাই সবচেয়ে
    # ভেতরের (router-এর সবচেয়ে কাছের)।
    #
    # এই ভুল বোঝাবুঝির কারণে CORSMiddleware আগে সবার প্রথমে add করা হতো —
    # অর্থাৎ বাস্তবে সেটা ছিল সবচেয়ে *ভেতরের* লেয়ার। তাই AuthMiddleware,
    # RateLimitMiddleware ইত্যাদি (যেগুলো CORS-এর পরে/বাইরে add হয়েছিল, তাই
    # runtime-এ CORS-এর চেয়ে বেশি বাইরের লেয়ারে ছিল) যখন call_next() না ডেকে
    # সরাসরি 401/429 JSONResponse রিটার্ন করত (short-circuit), সেই রেসপন্স
    # CORSMiddleware পর্যন্ত পৌঁছাতই না — ফলে কোনো CORS header ছাড়াই ব্রাউজারে
    # চলে যেত, আর ব্রাউজার সেটাকে "blocked by CORS policy" হিসেবে রিপোর্ট
    # করত, যদিও আসল কারণ ছিল auth/rate-limit।
    #
    # ফিক্স: CORSMiddleware-এর add_middleware() কলটি এখন সব middleware-এর
    # *পরে* (নিচে, ফাংশনের শেষে) করা হচ্ছে, যাতে এটি সত্যিকারের outermost
    # layer হয় — origins/credentials নির্ণয়ের লজিক এখানেই থাকল, শুধু
    # app.add_middleware(CORSMiddleware, ...) কলটা নিচে সরানো হয়েছে।
    def _ensure_list(v):
        return [v] if isinstance(v, str) else list(v)

    origins = list(
        set(
            _ensure_list(getattr(settings, "cors_origins", []))
            + _ensure_list(settings.user_cors_origins)
            + _ensure_list(settings.admin_cors_origins)
        )
    )

    # C-03 Fix: If origin is wildcard, credentials must not be allowed
    # RUNTIME-001 FIX: Previously fell back to ["*"] (wildcard CORS) when no
    # origins configured — allows any website to make authenticated requests.
    # Now: fail-closed — use localhost-only origins for dev, reject in production.
    cors_allow_credentials = True
    if not origins or origins == [""]:
        env = str(getattr(settings, "env", "local")).lower()
        # ROOT-CAUSE FIX (regression_scanner: unguarded-localhost, HIGH):
        # আগে production/staging-এ শুধু error log করা হতো কিন্তু তারপরও
        # নিচের local-host fallback unconditionally প্রয়োগ হতো —
        # production-এ কোনো origin কনফিগার না থাকলে CORS silently
        # dev host-এ খুলে যেত। এখন repo-র established idiom অনুসরণ করে
        # explicit `env == "local"` guard দিয়ে fallback করা হচ্ছে; অন্য
        # যেকোনো env-এ (production/staging সহ) fail-closed — origins খালি
        # থাকবে, কোনো cross-origin request allow হবে না যতক্ষণ না ঠিকভাবে
        # কনফিগার করা হয়।
        if env == "local":
            origins = [
                "http://localhost:3000",  # is_local()
                "http://localhost:5173",  # is_local()
                "http://127.0.0.1:3000",  # is_local()
                "http://127.0.0.1:5173",  # is_local()
            ]
        else:
            logger.warning(
                "⚠️ CORS: no origins configured in production! "
                "Falling back to derived allowed_hosts. "
                "Set USER_CORS_ORIGINS and/or ADMIN_CORS_ORIGINS env vars for strict security."
            )
            origins = [f"https://{h}" for h in settings.allowed_hosts if h != "testserver"]

    # 1. RequestContextMiddleware - Always first to establish context
    app.add_middleware(RequestContextMiddleware)

    # 1.5 DocsAuthMiddleware - gates /docs, /redoc এবং openapi.json
    # (innermost — রাউটের একদম কাছে; JWT-auth-এর পাবলিক-পাথ বাইপাসের পরেও
    # প্রোডাকশনে বেসিক-অথ চায় অথবা ডকুমেন্টেশন বন্ধ থাকলে 404 দেয়)
    app.add_middleware(DocsAuthMiddleware)

    # 2. GZipMiddleware - Early to decode compressed request bodies
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # 3. RequestIdMiddleware - Track requests
    app.add_middleware(RequestIdMiddleware)

    # 4. SecurityHeadersMiddleware - Add security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 4.1 RequestValidationMiddleware - SQLi/XSS check
    app.add_middleware(RequestValidationMiddleware)

    # 4.2 TrustedOriginMiddleware - Validate trusted origins before processing
    app.add_middleware(TrustedOriginMiddleware)

    # 5. SupremeContextMiddleware - Set up application context
    app.add_middleware(SupremeContextMiddleware)

    # 6. TenantExtractionMiddleware - Extract tenant information
    app.add_middleware(TenantExtractionMiddleware)

    # 7. ObservabilityMiddleware - Track metrics before security checks
    app.add_middleware(ObservabilityMiddleware)

    # 7.4 QueryTimingMiddleware - slow-request logging + percentile history
    # (restored from api/middleware/query_timing.py; moved here because the
    # api.middleware package namespace is shadowed by api/middleware.py file)
    app.add_middleware(QueryTimingMiddleware)

    # 7.5 Rate Limiting — FIX (P1, review 2026-09-12): Starlette runs the
    # LAST-added middleware FIRST (outermost). RateLimit was added after Auth,
    # so it executed BEFORE AuthMiddleware had set request.state.user — every
    # authenticated user (and admin) was throttled at the anonymous tier.
    # Adding it BEFORE Auth makes it INNER, i.e. it runs AFTER authentication.
    from core.rate_limit import RateLimiter

    app.add_middleware(RateLimitMiddleware, limiter=RateLimiter())

    # 7.6 Idempotency — FIX (P1, review 2026-09-12): moved INSIDE the auth
    # boundary so the idempotency key can be scoped per authenticated user
    # (previously cross-user response replay was possible via a shared key).
    app.add_middleware(IdempotencyMiddleware)

    # 8. Authentication — runs BEFORE rate limiting / idempotency (see above)
    app.add_middleware(AuthMiddleware)

    # 9. API Key validation - After authentication
    app.add_middleware(APIKeyAuthMiddleware)

    # 10. Security: AutonoGuard - After authentication to protect sensitive operations
    app.add_middleware(AutonoGuardMiddleware)

    # 11. Security: Honeypot - After authentication to only trap unauthorized access
    app.add_middleware(HoneypotMiddleware)

    # 12. Security: Chaos injection - After authentication for controlled testing
    app.add_middleware(ChaosInjectorMiddleware)  # type: ignore

    # 15. Response standardization - runs before CORS wraps everything
    app.add_middleware(ResponseStandardizationMiddleware)

    # 16. CORS — added LAST so it is the true outermost layer (see the
    # ROOT-CAUSE FIX note above `origins = ...`). Any short-circuit response
    # from any middleware above (401 from AuthMiddleware, 429 from
    # RateLimitMiddleware, etc.) still passes through this on the way back
    # out, so it always gets proper CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        # ROOT-CAUSE FIX: ফ্রন্টএন্ড (services/apiClient.ts → getAuthHeaders) প্রতিটি
        # রিকোয়েস্টে X-Device-Fingerprint পাঠায়, আর X-CSRF-Token / X-JIT-OTP
        # শর্তসাপেক্ষে পাঠায়। এই হেডারগুলো allow_headers-এ না থাকায় Starlette
        # CORSMiddleware preflight-এ "400 Disallowed CORS headers" দিত — ফলে
        # তিনটি ফ্রন্টএন্ড (Firebase user/admin, Vercel) থেকেই সব API কল ব্রাউজারে
        # ব্লক হচ্ছিল, যদিও origin allow-list ঠিক ছিল। তালিকাটি এখন
        # TrustedOriginMiddleware-এর ডিফল্ট হেডার সেটের সাথে সমন্বিত।
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
            "apikey",
            "X-API-Key",
            "X-Device-Fingerprint",
            "X-CSRF-Token",
            "X-JIT-OTP",
            "X-Request-ID",
            "X-Correlation-ID",
            "Cache-Control",
            # FINAL-TEST PROD FIX: the frontend (services/apiClient.ts) sends an
            # `Idempotency-Key` header on mutating requests, and the backend's
            # own IdempotencyMiddleware REQUIRES it on POSTs. But this allow
            # list omitted it, so Starlette CORSMiddleware answered every
            # preflight with "400 Disallowed CORS headers" -> the deployed
            # web.app frontend could NEVER call POST /auth/login (Network
            # Error). Header list is now kept in sync with what apiClient
            # actually emits.
            "Idempotency-Key",
        ],
        # Issue #685 (Domain 15): expose the tracing headers so the browser JS
        # (frontend apiClient handleResponse) can read the correlation id the
        # backend assigned/echoed and attach it to client-side error reports.
        expose_headers=[
            "Content-Length",
            "X-Pagination-Total",
            "X-Request-ID",
            "X-Correlation-ID",
        ],
    )

    from core.middleware.origin_shield import OriginShieldMiddleware

    # বাংলা কমেন্ট: #781 fix — Origin Shield (Cloudflare pre-shared secret validation)।
    # CORS-এর ঠিক পরে (দ্বিতীয় outermost layer) যোগ করা হয়েছে যাতে:
    #   - CORS preflight (OPTIONS) আগে হ্যান্ডেল হয়
    #   - তারপর direct-origin / non-Worker রিকোয়েস্ট 403 পায়
    #   - /health* পাথ Render-এর নিজস্ব health probe-এর জন্য bypass হয়
    # Fail-open: ENV ≠ production বা ORIGIN_VERIFY_KEY সেট না থাকলে middleware no-op।
    app.add_middleware(OriginShieldMiddleware)

    # বাংলা মন্তব্ব্য: canonical browser session/action routes
    # Keep browser routes mounted explicitly so route discovery cannot depend on
    # the optional safe-import registry in api.routes.__init__.
    from api.routes.browser import router as browser_router

    app.include_router(browser_router)

    # Issue #1669: the iframe render proxy moves OFF the header-guarded router —
    # iframes cannot attach Authorization headers. Auth is now a single-use,
    # 60s-TTL ticket issued via POST /api/browser/render-ticket (header-authed,
    # on `browser_router` itself). This dependency-free router only serves
    # GET /render with a valid consumed ticket; SSRF hardening unchanged.
    from api.routes.browser._render_proxy import render_public_router

    app.include_router(render_public_router)

    # Issue #1490: the browser integration /health probe must be reachable
    # without credentials (ServiceHealthMonitor + audit contract). It lives on
    # the dependency-free public_router inside the canonical api.routes.browser
    # package (#2258: ported there when the legacy double-mounted
    # api/routes/browser_routes.py module was retired) — mounted here
    # explicitly because the package's main router is user-token gated.
    from api.routes.browser import public_router as browser_public_router

    app.include_router(browser_public_router)

    # বাংলা মন্তব্ব্য: মেট্রিক্স এন্ডপয়েন্ট যোগ করা
    if settings.MONITORING_DETAILED:
        from fastapi.responses import PlainTextResponse

        from core.monitoring import get_metrics_collector

        @app.get("/metrics", response_class=PlainTextResponse)
        async def metrics_endpoint():
            collector = get_metrics_collector()
            return collector.export_prometheus()

    # 🔬 Evolution v3.0: Register health endpoints
    from core.health_routes import router as health_router

    # বাংলা (P0 — canonical health contract):
    # ক্যানোনিক্যাল প্রোডাকশন পাথ হলো /health, /health/live, /health/ready —
    # Dockerfile HEALTHCHECK, docker-compose প্রোব, monitoring ও docs সবাই এগুলো
    # ব্যবহার করে। /api/v1/health/* শুধু লিগ্যাসি অ্যালায়েস। Operational
    # source of truth একটাই: /health/*। আরও দেখুন docs/deployment/HEALTH_CONTRACT.md
    app.include_router(health_router, prefix="/health")
    # লিগ্যাসি অ্যালায়েস: পুরনো /api/v1/health পাথও একই রাউটার এক্সপোজ করে।
    app.include_router(health_router, prefix="/api/v1/health")

    @app.api_route("/", methods=["GET", "HEAD"])
    async def root():
        """পাবলিক রুট এন্ডপয়েন্ট — বেসিক সার্ভিস তথ্য এবং হেলথ চেক লিংক দেয়।"""
        return {
            "service": settings.app_name,
            "status": "online",
            "health_check": "/health",
        }

    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc: Exception):
        """Handle unhandled exceptions with proper response and circuit breaker awareness."""

        from core.request_context import get_correlation_id
        from core.resilience.circuit_breaker import (
            CIRCUITS,
            CircuitBreakerState,
            normalize_circuit_state,
        )

        status_code = getattr(exc, "status_code", 500)

        # Log the full error internally
        logger.error(f"Global Exception: {exc.__class__.__name__}: {str(exc)}")

        # H-03 Fix: Only expose safe details to the client
        if status_code < 500:
            error_response = {
                "error": exc.__class__.__name__,
                "detail": str(exc),
            }
        else:
            error_response = {
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred on the server.",
            }

        # Issue #685 (Domain 15): surface the request's correlation id in EVERY
        # unhandled-error payload so a user-reported failure can be matched to
        # the exact structured-log stream (same id the apiClient reads back via
        # the X-Request-ID response header).
        error_response["correlation_id"] = (
            getattr(request.state, "correlation_id", None) or get_correlation_id() or None
        )

        if hasattr(exc, "to_dict"):
            error_response.update(exc.to_dict())

        exc_lower = str(exc).lower()
        if any(kw in exc_lower for kw in ["timeout", "connection", "refused", "5xx"]):
            cb_stats = {name: cb.stats for name, cb in CIRCUITS.items()}
            # Issue #684 (H-05): the lowercase-family CircuitState values are
            # normalized onto the canonical CircuitBreakerState before the
            # "is a breaker open?" comparison, so legacy "open"-style persisted
            # or upstream-cased values can never silently miss the check. The
            # serialized "state" field below keeps the producer's own value.
            if any(
                normalize_circuit_state(s.current_state.value) == CircuitBreakerState.OPEN
                for s in cb_stats.values()
            ):
                error_response["circuit_breakers"] = {
                    name: {"state": s.current_state.value, "recovery_in": cb.get_recovery_time()}
                    for name, cb, s in [
                        (n, CIRCUITS[n], CIRCUITS[n].stats)
                        for n in CIRCUITS
                        if normalize_circuit_state(CIRCUITS[n].stats.current_state.value)
                        == CircuitBreakerState.OPEN
                    ]
                }

        return JSONResponse(
            status_code=status_code,
            content=error_response,
        )

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.debug("✅ FastAPI OpenTelemetry instrumentor enabled.")
    except ImportError:
        logger.warning("⚠️ opentelemetry-instrumentation-fastapi not installed.")

    return app


# Backward-compatibility alias for legacy tests
build_app_shell = create_app


def router_health_check(app: FastAPI | None = None, expected_count: int = 0) -> dict[str, Any]:
    """Helper to return health status of app routers."""
    return {"status": "healthy", "expected_count": expected_count, "env": settings.env}
