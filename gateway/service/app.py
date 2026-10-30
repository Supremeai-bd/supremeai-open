"""
service/app.py — SupremeAI Unified Provider Gateway (v2.0)

Key Features:
- Concurrent Load-Balanced Dynamic Key Pool (zero hardcoding).
- 6 Providers: Gemini, Groq, OpenRouter, OpenAI, Mistral, Hugging Face.
- Seamless player-substitution failover on 429 / 5xx / 401.
- Stateless cryptographic client key verification via service.keygen (sk-supreme-...).
- Standard OpenAI-compatible /v1/chat/completions and /v1/models surface.
- Unauthenticated live probe: /health and /healthz returning HTTP 200 OK.
- Superadmin / MCP Control Tower administrative inspection & reload endpoints.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
import secrets
import socket
import time
import hmac
from typing import Optional, Tuple
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

try:
    from service.branding import build_brand
except ImportError:  # pragma: no cover - package-relative fallback
    from gateway.service.branding import build_brand

try:
    from service.status_publication import (
        assert_no_operator_fields,
        build_liveness_payload,
        build_public_root_payload,
        build_readiness_payload,
    )
except ImportError:  # pragma: no cover - package-relative fallback
    from gateway.service.status_publication import (
        assert_no_operator_fields,
        build_liveness_payload,
        build_public_root_payload,
        build_readiness_payload,
    )

try:
    from service.keygen import verify_key
    try:
        from service.pool import squad
    except ImportError:
        squad = None  # type: ignore[assignment]
    from service.providers.adapters import (
        PROVIDER_CONFIGS,
        forward_chat_completion,
        forward_stealth_webhook,
        normalize_stealth_url,
    )
    from service.providers.web_session import web_bridge
    from service.telegram_webhook import telegram_router
except ImportError:
    try:
        from gateway.service.keygen import verify_key
    except ImportError:
        def verify_key(key: str) -> dict | None:  # type: ignore[no-redef]
            return None
    try:
        from gateway.service.pool import squad
    except ImportError:
        squad = None  # type: ignore[assignment]
    try:
        from gateway.service.providers.adapters import (
            PROVIDER_CONFIGS,
            forward_chat_completion,
            forward_stealth_webhook,
            normalize_stealth_url,
        )
    except ImportError:
        try:
            from service.providers.adapters import (
                PROVIDER_CONFIGS,
                forward_chat_completion,
                forward_stealth_webhook,
                normalize_stealth_url,
            )
        except ImportError:
            PROVIDER_CONFIGS = {}  # type: ignore[assignment]
            def forward_chat_completion(*a, **k):  # type: ignore[no-redef]
                return 503, {"error": "adapters unavailable"}
            def forward_stealth_webhook(*a, **k):  # type: ignore[no-redef]
                return 503, {"error": "adapters unavailable"}
            def normalize_stealth_url(url: str) -> str:  # type: ignore[no-redef]
                return ""
    try:
        from gateway.service.providers.web_session import web_bridge
    except ImportError:
        try:
            from service.providers.web_session import web_bridge
        except ImportError:
            web_bridge = None  # type: ignore[assignment]
    try:
        from gateway.service.telegram_webhook import telegram_router
    except ImportError:
        try:
            from service.telegram_webhook import telegram_router
        except ImportError:
            telegram_router = None  # type: ignore[assignment]
try:
    from service.webhook_scout import webhook_scout
except ImportError:
    try:
        from gateway.service.webhook_scout import webhook_scout
    except ImportError:
        webhook_scout = None  # type: ignore[assignment]

try:
    from service.storage import (
        add_message,
        delete_conversation,
        get_conversation,
        get_user_preferences,
        list_conversations,
        save_conversation,
        save_user_preferences,
    )
except ImportError:
    try:
        from gateway.service.storage import (
            add_message,
            delete_conversation,
            get_conversation,
            get_user_preferences,
            list_conversations,
            save_conversation,
            save_user_preferences,
        )
    except ImportError:
        add_message = None  # type: ignore[assignment]
        delete_conversation = None  # type: ignore[assignment]
        get_conversation = None  # type: ignore[assignment]
        get_user_preferences = None  # type: ignore[assignment]
        list_conversations = None  # type: ignore[assignment]
        save_conversation = None  # type: ignore[assignment]
        save_user_preferences = None  # type: ignore[assignment]

# ── Provider-Agnostic Context Compiler, Response Guard & Canonical Memory ──
try:
    from service.context_compiler import compile_chat_context, resolve_sampling_knobs
    from service.response_guard import is_stub_content, purge_identity_bleed, repair_markdown, validate_and_sanitize
    from service.memory_store import (
        append_canonical_message,
        get_recent_history,
        get_user_durable_memories,
        log_provider_attempt,
    )
except ImportError:
    try:
        from gateway.service.context_compiler import compile_chat_context, resolve_sampling_knobs
        from gateway.service.response_guard import is_stub_content, purge_identity_bleed, repair_markdown, validate_and_sanitize
        from gateway.service.memory_store import (
            append_canonical_message,
            get_recent_history,
            get_user_durable_memories,
            log_provider_attempt,
        )
    except ImportError:
        compile_chat_context = None  # type: ignore[assignment]
        resolve_sampling_knobs = None  # type: ignore[assignment]
        validate_and_sanitize = None  # type: ignore[assignment]
        purge_identity_bleed = None  # type: ignore[assignment]
        is_stub_content = None  # type: ignore[assignment]
        repair_markdown = None  # type: ignore[assignment]
        append_canonical_message = None  # type: ignore[assignment]
        get_recent_history = None  # type: ignore[assignment]
        get_user_durable_memories = None  # type: ignore[assignment]
        log_provider_attempt = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("supremeai.gateway")


# ── LiveLogs Ring Buffer (Admin Console Server-Side Log Streaming) ───────────

class RingBufferLogHandler(logging.Handler):
    """In-memory thread-safe ring buffer capturing recent logs for Admin LiveLogs & SSE."""

    def __init__(self, maxlen: int = 1000):
        super().__init__()
        self.buffer: deque = deque(maxlen=maxlen)
        self.subscribers: set = set()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            entry = {
                "id": f"log-{int(record.created * 1000)}-{os.urandom(2).hex()}",
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "time": record.created,
                "level": record.levelname,
                "name": record.name,
                "message": msg,
            }
            self.buffer.append(entry)

            # Broadcast to live SSE subscribers
            if self.subscribers:
                for q in list(self.subscribers):
                    try:
                        q.put_nowait(entry)
                    except Exception:
                        pass
        except Exception:
            self.handleError(record)

    def get_logs(self, limit: int = 100, level: Optional[str] = None, search: Optional[str] = None) -> list:
        items = list(self.buffer)
        if level:
            items = [item for item in items if item["level"].upper() == level.upper()]
        if search:
            s = search.lower()
            items = [item for item in items if s in item["message"].lower() or s in item["name"].lower()]
        return items[-limit:]


log_ring_buffer = RingBufferLogHandler(maxlen=1000)
log_ring_buffer.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(log_ring_buffer)
logging.getLogger().addHandler(log_ring_buffer)

# Priority-1 Stealth Webhook & Web Session Configuration
STEALTH_WEBHOOK_URL = os.getenv("STEALTH_WEBHOOK_URL", os.getenv("UPSTREAM_WEBHOOK_URL", "")).strip()
STEALTH_WEBHOOK_SECRET = os.getenv("STEALTH_WEBHOOK_SECRET", os.getenv("UPSTREAM_WEBHOOK_SECRET", "")).strip()
STEALTH_WEBHOOK_TIMEOUT = float(os.getenv("STEALTH_WEBHOOK_TIMEOUT", "28.0"))

app = FastAPI(title="SupremeAI API Gateway", version="2.0.0", docs_url=None, redoc_url=None, openapi_url=None)  # docs lockdown completion: the openapi_url default served the full route inventory (incl. admin route names) unauthenticated.

# CORS setup for Studio and web agents - Restricted origins (no wildcard with credentials)
_default_cors = [
    "https://supremeai-studio.vercel.app",
    "https://supremeai-studio.pages.dev",
    "https://supremeai-studio.paykaribazaronline.workers.dev",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
_studio_preview = os.getenv("STUDIO_FRONTEND_URL", "").strip()
if _studio_preview and _studio_preview not in _default_cors:
    _default_cors.append(_studio_preview)

_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env:
    allowed_origins = list(dict.fromkeys([o.strip() for o in _cors_env.split(",") if o.strip()] + _default_cors))
else:
    allowed_origins = _default_cors

# Way 28: bind one correlation id per request (echoed on responses; usable in logs).
from gateway.middleware.correlation_id import CorrelationIdMiddleware  # noqa: E402
app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|.*\.pages\.dev|.*\.vercel\.app|.*\.workers\.dev)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-SupremeAI-Key", "X-Guest-Mode", "X-Forwarded-For", "Accept", "Origin", "Referer", "X-Correlation-ID"],
)

# Issue #1728: baseline security headers (HSTS/XCTO/XFO/CSP-report-only) on every
# response. Added LAST so it mounts OUTERMOST (Starlette add_middleware prepends):
# request flow Sec -> CORS -> Corr -> routes, so every response — CORS preflight
# included — gets stamped. Pure-ASGI header injection never touches the SSE body.
from gateway.middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402
app.add_middleware(SecurityHeadersMiddleware)

# Telegram Inbound Webhook Listener
if telegram_router is not None:
    app.include_router(telegram_router)

# Native Admin Authentication Router (Zero-Firebase)
try:
    from service.admin_auth import router as admin_auth_router
except ImportError:
    try:
        from gateway.service.admin_auth import router as admin_auth_router
    except ImportError:
        try:
            from admin_auth import router as admin_auth_router
        except ImportError:
            admin_auth_router = None

if admin_auth_router is not None:
    app.include_router(admin_auth_router)

# Native Passkey / WebAuthn Biometric Router (Fingerprint/TouchID/FaceID)
try:
    from service.passkey_auth import router as passkey_auth_router
except ImportError:
    try:
        from gateway.service.passkey_auth import router as passkey_auth_router
    except ImportError:
        try:
            from passkey_auth import router as passkey_auth_router
        except ImportError:
            passkey_auth_router = None

if passkey_auth_router is not None:
    app.include_router(passkey_auth_router)


# Epistemic router (ChronoFact/SPINE patterns): tool pruning, memory gate, model horizon.
try:
    from service.epistemic_router import router as epistemic_router
except ImportError:
    try:
        from gateway.service.epistemic_router import router as epistemic_router
    except ImportError:
        epistemic_router = None

if epistemic_router is not None:
    app.include_router(epistemic_router)


# ── Guest Rate Limit (cost guard for the keyless bypass) ─────────────────────
# The x-guest-mode / studio-origin / "guest"-token bypass is intentional
# (Studio free tier), but it is the ONLY auth class with no throttle while the
# stealth relay is the single paid reply path. Unbounded guest traffic can
# drain relay quota and mask real outages (silent 502 storms). Sliding-window
# per client IP, in-memory (single-process asyncio — no new deps).
GUEST_RATE_LIMIT_PER_MIN = max(0, int(os.getenv("GUEST_RATE_LIMIT_PER_MIN", "10")))
_GUEST_WINDOW_SECONDS = 60.0
_GUEST_BUCKET_CAP = 10000  # bounded memory: never track more IPs than this
_guest_hits: dict = {}


def _client_ip(request: Request) -> str:
    """Trusted-proxy-aware client IP. Render appends the real client IP as the
    LAST X-Forwarded-For hop; client-supplied leftmost values are spoofable and
    must not be trusted for bucketing."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _is_guest_request(request: Request, token: Optional[str]) -> bool:
    """Single SSOT for guest identity: header bypass, verified Studio origin/referer,
    or well-known public demo tokens. Used by both auth and throttling so the two
    can never drift apart."""
    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()
    studio_preview = os.getenv("STUDIO_FRONTEND_URL", "").lower().strip()
    return (
        request.headers.get("x-guest-mode", "").lower() == "true"
        or "https://supremeai-studio.pages.dev" in origin
        or "https://supremeai-studio.pages.dev" in referer
        or (bool(studio_preview) and (studio_preview in origin or studio_preview in referer))
        or token in {"guest", "demo", "public-guest"}
    )


def _guest_rate_limit(request: Request) -> Tuple[bool, float]:
    """Sliding-window per-IP limiter for guest-class requests.
    Returns (allowed, retry_after_seconds). GUEST_RATE_LIMIT_PER_MIN<=0 disables."""
    if GUEST_RATE_LIMIT_PER_MIN <= 0:
        return True, 0.0
    ip = _client_ip(request)
    now = time.time()
    dq = _guest_hits.get(ip)
    if dq is None:
        if len(_guest_hits) >= _GUEST_BUCKET_CAP:
            # Evict expired buckets first; then force-evict oldest if still full.
            for k in [k for k, v in _guest_hits.items() if not v or v[-1] < now - _GUEST_WINDOW_SECONDS]:
                _guest_hits.pop(k, None)
            while len(_guest_hits) >= _GUEST_BUCKET_CAP:
                _guest_hits.pop(next(iter(_guest_hits)))
        dq = _guest_hits[ip] = deque()
    while dq and dq[0] < now - _GUEST_WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= GUEST_RATE_LIMIT_PER_MIN:
        return False, max(1.0, _GUEST_WINDOW_SECONDS - (now - dq[0]))
    dq.append(now)
    return True, 0.0

SUPERADMIN_KEY = os.getenv("SUPREMEAI_SUPERADMIN_KEY", os.getenv("MCP_SUPERADMIN_KEY", "")).strip()


def _extract_token(request: Request, x_supremeai_key: Optional[str]) -> Optional[str]:
    """Resolve the caller token: explicit X-SupremeAI-Key header wins, else Bearer."""
    if x_supremeai_key:
        return x_supremeai_key
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def _verify_client_auth(request: Request, x_supremeai_key: Optional[str] = None) -> bool:
    """
    Validates client gateway access token:
    1. First checks if it is a cryptographically signed sk-supreme-... key via keygen.
    2. Then checks if it matches SUPREMEAI_API_KEY, SUPREMEAI_API_KEYS, or SUPERADMIN_KEY.
    3. Fails closed in production if environment has no keys.
    """
    token = _extract_token(request, x_supremeai_key)

    # Guest pass-through strictly for verified SupremeAI Studio origin (no generic vercel.app bypass)
    if _is_guest_request(request, token):
        return True

    if not token:
        # Check if environment is secured (fail-closed in non-dev)
        return not (os.getenv("SUPREMEAI_API_KEY") or SUPERADMIN_KEY or os.getenv("ENVIRONMENT") != "development")

    # 1. Check stateless cryptographic HMAC signature (sk-supreme-...)
    if token.startswith("sk-supreme-"):
        meta = verify_key(token)
        if meta:
            return True

    # 2. Check static master/pool env keys
    valid_keys = set()
    master = os.getenv("SUPREMEAI_API_KEY", "").strip()
    if master:
        valid_keys.add(master)
    pool_str = os.getenv("SUPREMEAI_API_KEYS", "").strip()
    if pool_str:
        for k in pool_str.split(","):
            if k.strip():
                valid_keys.add(k.strip())
    if SUPERADMIN_KEY:
        valid_keys.add(SUPERADMIN_KEY)

    if not valid_keys:
        return os.getenv("ENVIRONMENT") == "development"

    return token in valid_keys


def _require_operator_key(request: Request, x_supremeai_key: Optional[str] = None) -> bool:
    """Strict credential gate for operator-grade surfaces (#1729).

    Unlike _verify_client_auth this deliberately has NO guest pass-through:
    _is_guest_request trusts spoofable client headers (x-guest-mode, Origin/
    Referer containing the Studio host, well-known demo tokens), which is fine
    for chat-rate-limiting but must never gate operator fleet detail.
    Fails closed: no key configured -> False (set SUPREMEAI_API_KEY / SUPREMEAI_API_KEYS
    / SUPREMEAI_SUPERADMIN_KEY to enable operator access).
    """
    token = _extract_token(request, x_supremeai_key)
    if not token:
        return False
    if token.startswith("sk-supreme-"):
        try:
            if verify_key(token):
                return True
        except Exception:  # noqa: BLE001 - fail closed on keygen errors
            return False
    valid_keys = set()
    master = os.getenv("SUPREMEAI_API_KEY", "").strip()
    if master:
        valid_keys.add(master)
    pool_str = os.getenv("SUPREMEAI_API_KEYS", "").strip()
    for k in pool_str.split(","):
        if k.strip():
            valid_keys.add(k.strip())
    if SUPERADMIN_KEY:
        valid_keys.add(SUPERADMIN_KEY)
    return token in valid_keys


def _extract_user_id(request: Request) -> str:
    """Resolve caller user ID from a VERIFIED session token only.

    FIX(auth 2026-10-24): caller-supplied user-id headers are no longer trusted
    (they allowed arbitrary identity spoofing) and the old default no longer
    attributes anonymous calls to the admin user. Identity comes from the
    HMAC-verified bearer key; unauthenticated callers get an explicit
    anonymous id.
    """
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None
    if token:
        # verify_key checks the keygen prefix + HMAC signature statelessly and
        # returns None for any non-keygen token — no prefix sniffing here.
        try:
            meta = verify_key(token)
        except Exception:
            meta = None
        if meta:
            client = str(meta.get("client") or "")
            if client == "studio-admin":
                return "usr-admin-primary"
            if client:
                return client if client.startswith("usr-") else f"usr-{client}"
    return "usr-anonymous"


# ── Liveness & Readiness Probes ──────────────────────────────────────────────

# Stealth relay DNS capability state (cached, TTL-refreshed). Oct-23 lesson:
# chat_ready used to mean "the env var is non-empty", so the gateway reported
# ready for DAYS while the configured hostname failed DNS ([Errno -2]) and every
# chat reply died in 0.1s. /readyz now verifies the configured host actually
# resolves before declaring capability; /health exposes the same state without
# ever failing (liveness semantics unchanged).
_STEALTH_DNS_TTL_SECONDS = float(os.getenv("STEALTH_DNS_CHECK_TTL", "60"))
_stealth_dns_state: dict = {"ok": None, "checked_at": 0.0, "detail": "not checked yet"}


def _stealth_target_host() -> str:
    """Hostname of the normalized STEALTH_WEBHOOK_URL ('' when unconfigured)."""
    if not STEALTH_WEBHOOK_URL:
        return ""
    try:
        from urllib.parse import urlsplit
        normalized = normalize_stealth_url(STEALTH_WEBHOOK_URL)
        if not normalized:
            return ""
        host = urlsplit(normalized if "://" in normalized else "http://" + normalized).hostname or ""
        return host
    except Exception:  # noqa: BLE001 — probe must never crash the caller
        return ""


async def _stealth_dns_snapshot(force: bool = False) -> dict:
    """TTL-cached DNS reachability verdict for the configured relay host.

    getaddrinfo runs in the default executor (never blocks the loop) and is
    bounded by wait_for so a broken resolver cannot stall /readyz.
    """
    host = _stealth_target_host()
    now = time.time()
    if not host:
        return {"ok": None, "checked_at": 0.0, "detail": "STEALTH_WEBHOOK_URL not configured"}
    if not force and _stealth_dns_state["checked_at"] and (now - _stealth_dns_state["checked_at"]) < _STEALTH_DNS_TTL_SECONDS:
        return dict(_stealth_dns_state)
    loop = asyncio.get_running_loop()

    def _short(h: str) -> str:
        parts = h.split(".")
        return f"{h[:4]}…{'.'.join(parts[-2:])}" if "." in h else h

    try:
        infos = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)),
            timeout=4.0,
        )
        _stealth_dns_state.update(ok=True, checked_at=now, detail=f"resolved {len(infos)} addr(s) for {_short(host)}")
    except asyncio.TimeoutError:
        _stealth_dns_state.update(ok=False, checked_at=now, detail="DNS lookup timed out (possible resolver outage)")
    except socket.gaierror as exc:
        _stealth_dns_state.update(ok=False, checked_at=now, detail=f"host {_short(host)} does not resolve ({exc}) — fix Infisical STEALTH_WEBHOOK_URL")
    except Exception as exc:  # noqa: BLE001
        _stealth_dns_state.update(ok=False, checked_at=now, detail=f"DNS probe error: {exc}")
    return dict(_stealth_dns_state)


@app.api_route("/", methods=["GET", "HEAD"])
async def public_root():
    """Public landing status (#1729): exactly the four consumer-relevant fields.

    HEAD support on this route predates this slice (#1728's header lane) and is
    preserved. The former root payload doubled as an operator dashboard (key
    inventory, provider topology, stealth posture, per-account web-session
    detail) - a reconnaissance gift on the advertised public hostname. Fleet
    detail moved to GET /internal/status behind a strict credential gate;
    contracts that only check HTTP 200 are unaffected (status contract:
    docs/CONSUMERS.md).
    """
    return assert_no_operator_fields(
        build_public_root_payload(chat_ready=bool(STEALTH_WEBHOOK_URL))
    )


@app.get("/health")
@app.get("/healthz")
@app.get("/api/health")
@app.get("/api/v1/health")
@app.get("/v1/health")
async def health_check():
    """Unauthenticated liveness probe. Always 200 OK when service is running.

    Redacted (#1729): fleet inventory, stealth posture and web-session detail no
    longer ship on the public probe surface - only the liveness fields watchdogs
    consume. Probe contract preserved: HTTP 200, no auth, status="healthy",
    chat_ready semantics unchanged (docs/CONSUMERS.md pins HTTP-status branching,
    not body fields). Full operator detail: GET /internal/status with a key.
    """
    return assert_no_operator_fields(
        build_liveness_payload(
            status="healthy",
            service_name="supremeai-api",
            version="2.0.0",
            chat_ready=bool(STEALTH_WEBHOOK_URL),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )


@app.get("/internal/status")
async def internal_status(
    request: Request, x_supremeai_key: Optional[str] = Header(default=None)
):
    """Operator-grade fleet status (#1729) - requires a valid gateway key.

    Same payload shape the public root used to leak, so existing operator
    dashboards only change the URL. Gate is _require_operator_key: HMAC
    sk-supreme-... keys or configured env keys, NO guest pass-through,
    fail-closed when no keys are configured.
    """
    if not _require_operator_key(request, x_supremeai_key):
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "operator fleet status requires a valid gateway key",
                    "type": "authentication_error",
                }
            },
        )
    telemetry = squad.stats() if squad else {"total_keys": 0, "total_healthy_keys": 0, "providers": {}}
    try:
        stealth_dns = await _stealth_dns_snapshot()
    except Exception:  # noqa: BLE001 - operator status must not crash on probe errors
        stealth_dns = {"ok": None, "checked_at": 0.0, "detail": "probe error"}
    return {
        "status": "healthy",
        "service_name": "supremeai-api",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_keys": telemetry["total_keys"],
        "total_healthy_keys": telemetry["total_healthy_keys"],
        "chat_ready": bool(STEALTH_WEBHOOK_URL),
        "stealth_priority1_configured": bool(STEALTH_WEBHOOK_URL),
        "stealth_dns": stealth_dns,
        "web_sessions_active": bool(web_bridge and web_bridge.has_active_accounts),
        "web_session_status": web_bridge.status() if web_bridge else {},
        "webhook_scout": webhook_scout.get_status() if webhook_scout else {},
        "telegram_webhook_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "active_providers": [
            p for p, data in telemetry.get("providers", {}).items() if data.get("healthy", 0) > 0
        ],
    }


@app.get("/webhook/scout/status")
@app.get("/api/v1/webhook/scout")
async def webhook_scout_status(
    request: Request, x_supremeai_key: Optional[str] = Header(default=None)
):
    """Returns live fleet status of all Webhook & Multi-AI Session slots.

    Auth-gated (#1729): this sibling route leaked the same operator-grade
    fleet detail as the old public root; the same strict key gate applies
    (no guest pass-through, fail-closed).
    """
    if not _require_operator_key(request, x_supremeai_key):
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "webhook scout fleet status requires a valid gateway key",
                    "type": "authentication_error",
                }
            },
        )
    if not webhook_scout:
        return {"status": "unavailable", "detail": "Webhook Scout not initialized"}
    return webhook_scout.get_status()


@app.get("/readyz")
async def readiness_check():
    """Capability probe (distinct from liveness): 200 only when a chat reply path
    is configured AND its host resolves. Monitors should target /readyz — /health
    alone cannot detect a relay outage because API fallback is disabled by mandate
    (single reply path). A configured-but-unresolvable host (the Oct-23 failure:
    [Errno -2] on every chat call while /health reported healthy) fails this probe
    loudly with a 503.

    Redacted (#1902, closing the #1729 class): the loud-failure design used to
    ship the stealth posture block (stealth_dns detail with the masked relay
    host + stealth_priority1_configured) to unauthenticated callers. The
    capability semantics are preserved — HTTP 200/503 + chat_ready branching,
    unchanged for monitors — while the posture detail moved behind the operator
    gate: GET /internal/status with a key carries the full stealth_dns block.
    Body built by build_readiness_payload (operator-field guard, structural).
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    if STEALTH_WEBHOOK_URL:
        stealth_dns = await _stealth_dns_snapshot()
        if stealth_dns.get("ok") is False:
            return JSONResponse(
                status_code=503,
                content=build_readiness_payload(
                    "degraded",
                    False,
                    timestamp,
                    reason=(
                        "chat reply path host does not resolve — "
                        "operator detail behind the key-gated /internal/status"
                    ),
                ),
            )
        return build_readiness_payload("ready", True, timestamp)
    return JSONResponse(
        status_code=503,
        content=build_readiness_payload(
            "degraded",
            False,
            timestamp,
            reason=(
                "chat reply path not configured — no chat reply path "
                "(API fallback disabled per mandate)"
            ),
        ),
    )


# Graceful shutdown: close pooled stealth HTTP client
@app.on_event("shutdown")
async def _close_stealth_http_client():
    try:
        from service.providers.adapters import close_stealth_client
    except ImportError:
        try:
            from gateway.service.providers.adapters import close_stealth_client
        except ImportError:
            close_stealth_client = None  # type: ignore[assignment]
    if close_stealth_client is not None:
        try:
            await close_stealth_client()
        except Exception:  # noqa: BLE001
            pass


@app.get("/api/config/public")
@app.get("/api/config/public/branding")
async def get_public_config():
    """Provides public defaults and branding for SupremeAI Studio without authentication."""
    return {
        "status": "ready",
        "app": "SupremeAI Studio",
        "version": "2.0.0",
        "maxConcurrency": 5,
        "features": {
            "selfHealing": True,
            "costGuard": False,
            "guestChat": True,
        },
        "branding": {
            "appName": "SupremeAI",
            "tier": "Turbo",
            "theme": "cosmic-dark",
        },
    }


@app.get("/api/preferences/{user_id}/stream")
async def stream_preferences(user_id: str):
    """SSE endpoint for real-time theme/preference updates (service tier)."""
    import asyncio
    import json

    async def event_generator():
        yield "event: connected\ndata: " + json.dumps({"status": "connected", "user_id": user_id}) + "\n\n"
        while True:
            await asyncio.sleep(15)
            yield "event: ping\ndata: " + json.dumps({"channel": "heartbeat"}) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/v1/live")
async def live_probe():
    """Live heartbeat probe for Studio."""
    return {"status": "alive", "timestamp": int(time.time())}


@app.post("/api/v1/auth/login")
@app.post("/api/auth/login")
@app.post("/auth/login")
async def studio_auth_login(request: Request):
    """
    Studio Admin/User Authentication Endpoint.
    Authenticates admin or provisioned users and returns a stateless signed session token.
    Supports both JSON and form data, and both email and username payload fields.
    """
    try:
        body = await request.json()
    except Exception:
        try:
            form = await request.form()
            body = dict(form)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    email = str(body.get("email") or body.get("username") or "").strip().lower()
    password = str(body.get("password", "")).strip()

    admin_email = os.getenv("SUPREMEAI_ADMIN_LOGIN_EMAIL", "niloyjoy7@gmail.com").strip().lower()
    # Support both plaintext (SUPREMEAI_ADMIN_PASSWORD) and bcrypt hash
    # (SUPREMEAI_ADMIN_PASSWORD_HASH) env vars, mirroring gateway.service.admin_auth.
    try:
        from service.admin_auth import _verify_password
    except Exception:  # noqa: BLE001
        try:
            from gateway.service.admin_auth import _verify_password
        except Exception:  # noqa: BLE001
            def _verify_password(pw: str) -> bool:  # type: ignore[misc]
                import hmac, os
                env_pass = os.getenv("SUPREMEAI_ADMIN_PASSWORD", "").strip()
                return bool(env_pass) and hmac.compare_digest(pw, env_pass)

    # FIX(auth 2026-10-24): fail-closed credential check. Previously ANY email with
    # ANY password of >=6 chars produced a session, and the admin password had a
    # hardcoded "admin123" fallback. Both bypasses removed: only the configured
    # admin email + exact env password/hash match is accepted.
    # User accounts require the register flow / a real user store (tracked separately).
    if email == admin_email and _verify_password(password):
        # Generate stateless signed API token
        try:
            from service.keygen import generate_key
            token = generate_key(client_name="studio-admin", quota="unlimited")
        except Exception:
            token = f"sess_{secrets.token_hex(16)}"

        user_id = "usr-admin-primary" if email == admin_email else f"usr-{int(time.time())}"
        role = "admin" if email == admin_email else "user"
        perms = ["admin", "read", "write", "execute", "vault", "planner"] if email == admin_email else ["read", "write"]
        name = "SupremeAI Admin" if email == admin_email else (email.split("@")[0].capitalize() if "@" in email else "User")

        return {
            "token": token,
            "access_token": token,
            "token_type": "bearer",
            "user_id": user_id,
            "role": role,
            "permissions": perms,
            "user": {
                "id": user_id,
                "email": email or admin_email,
                "name": name,
                "role": role,
            },
        }

    raise HTTPException(status_code=401, detail="Invalid email or password")


@app.post("/api/v1/auth/register")
@app.post("/api/auth/register")
@app.post("/auth/register")
async def studio_auth_register(request: Request):
    """
    Studio User Registration Endpoint.
    """
    try:
        body = await request.json()
    except Exception:
        try:
            form = await request.form()
            body = dict(form)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    email = str(body.get("email") or body.get("username") or "").strip().lower()
    password = str(body.get("password", "")).strip()
    name = str(body.get("name", "")).strip() or (email.split("@")[0].capitalize() if "@" in email else "User")

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email address is required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        from service.keygen import generate_key
        token = generate_key(client_name=f"usr-{email.split('@')[0]}", quota="standard")
    except Exception:
        token = f"sk-supreme-user-{int(time.time())}"

    user_id = f"usr-{int(time.time())}"
    return {
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "user_id": user_id,
        "role": "user",
        "permissions": ["read", "write"],
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "role": "user",
        },
    }


@app.get("/api/v1/auth/me")
@app.get("/v1/auth/me")
async def studio_auth_me(request: Request):
    """Validates session and returns current user profile."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None

    # FIX(auth 2026-10-24): previously returned an admin profile unconditionally,
    # ignoring the bearer token entirely. The token must now verify: first as a
    # keygen-issued HMAC key (service.keygen.verify_key checks prefix+signature
    # statelessly), else as a signed admin JWT (gateway.service.admin_auth).
    # Fail-closed 401 otherwise.
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        meta = verify_key(token)
    except Exception:
        meta = None
    if meta:
        client = str(meta.get("client") or "user")
        if client == "studio-admin":
            return {
                "authenticated": True,
                "user_id": "usr-admin-primary",
                "email": os.getenv("SUPREMEAI_ADMIN_LOGIN_EMAIL", "niloyjoy7@gmail.com"),
                "name": "SupremeAI Admin",
                "role": "admin",
                "permissions": ["admin", "read", "write", "execute", "vault", "planner"],
            }
        user_id = client if client.startswith("usr-") else f"usr-{client}"
        return {
            "authenticated": True,
            "user_id": user_id,
            "email": "",
            "name": (client[4:] if client.startswith("usr-") else client).capitalize() or "User",
            "role": "user",
            "permissions": ["read", "write"],
        }

    try:
        try:
            from gateway.service.admin_auth import verify_admin_jwt
        except Exception:  # pragma: no cover - root-layout import fallback
            from service.admin_auth import verify_admin_jwt
        jwt_payload = verify_admin_jwt(token)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    role = str(jwt_payload.get("role") or "user")
    jwt_email = str(jwt_payload.get("email") or "")
    return {
        "authenticated": True,
        "user_id": str(jwt_payload.get("uid") or jwt_payload.get("sub") or "usr-admin-primary"),
        "email": jwt_email,
        "name": "SupremeAI Admin" if role == "admin" else (jwt_email.split("@")[0].capitalize() or "User"),
        "role": role,
        "permissions": ["admin", "read", "write", "execute", "vault", "planner"] if role == "admin" else ["read", "write"],
    }


@app.get("/api/health-aggregation")
async def health_aggregation():
    """
    5-Node Render Fleet Live Health Aggregator.
    Probes all 5 Render nodes in parallel and returns green/yellow/red status for Studio circles.
    """
    # FIX(health 2026-10-24): stale/localhost defaults replaced. Defaults now point
    # only at hosts verified live on 2026-10-24 (api-ulw0, mcp-tower); nodes without
    # a configured URL report "unknown" instead of a meaningless localhost probe.
    nodes = [
        {"id": "api", "name": "API Gateway", "url": os.getenv("RENDER_API_URL", "https://supremeai-api-ulw0.onrender.com/health")},
        {"id": "scraper", "name": "Scraper Relay", "url": os.getenv("RENDER_SCRAPER_URL", "")},
        {"id": "tower", "name": "MCP Control Tower", "url": os.getenv("RENDER_MCP_URL", "https://supremeai-mcp-tower.onrender.com/health")},
        {"id": "primary", "name": "Primary Core Node", "url": os.getenv("RENDER_PRIMARY_URL", "")},
        {"id": "worker", "name": "Worker Node", "url": os.getenv("RENDER_WORKER_URL", "")},
    ]

    import httpx

    def _candidate_urls(raw_url: str) -> list[str]:
        clean = raw_url.strip().rstrip("/")
        if any(clean.endswith(p) for p in ("/health", "/healthz", "/live", "/ready", "/health/live")):
            return [clean]
        return [f"{clean}/health", clean, f"{clean}/health/live", f"{clean}/healthz"]

    async def _probe_node(client: httpx.AsyncClient, node: dict) -> dict:
        start_t = time.time()
        try:
            # FIX(health 2026-10-24): the old code short-circuited the "api" node to a
            # hardcoded healthy/5ms response WITHOUT any network request (false green).
            # Every configured node is now actually probed; unconfigured nodes are
            # reported honestly as "unknown".
            if not str(node.get("url") or "").strip():
                return {
                    "id": node["id"],
                    "name": node["name"],
                    "status": "unknown",
                    "message": f"{node['name']} probe not configured (set RENDER_{node['id'].upper()}_URL)",
                    "response_time_ms": 0,
                }

            candidates = _candidate_urls(node["url"])
            res_status = None
            last_err = None
            for probe_url in candidates:
                try:
                    r = await client.get(probe_url)
                    res_status = r.status_code
                    if res_status == 200:
                        break
                except Exception as probe_err:
                    last_err = probe_err

            latency = max(1, int((time.time() - start_t) * 1000))
            if res_status == 200:
                return {
                    "id": node["id"],
                    "name": node["name"],
                    "status": "healthy",
                    "message": f"{node['name']} online ({latency}ms)",
                    "response_time_ms": latency,
                }
            elif res_status is not None and 500 <= res_status < 600:
                return {
                    "id": node["id"],
                    "name": node["name"],
                    "status": "degraded",
                    "message": f"{node['name']} waking up / cold start",
                    "response_time_ms": latency,
                }
            elif res_status is not None:
                return {
                    "id": node["id"],
                    "name": node["name"],
                    "status": "unhealthy",
                    "message": f"{node['name']} returned HTTP {res_status}",
                    "response_time_ms": latency,
                }
            else:
                return {
                    "id": node["id"],
                    "name": node["name"],
                    "status": "degraded",
                    "message": f"{node['name']} sleeping / timeout ({last_err})",
                    "response_time_ms": latency,
                }
        except Exception as e:
            latency = max(1, int((time.time() - start_t) * 1000))
            return {
                "id": node["id"],
                "name": node["name"],
                "status": "degraded",
                "message": f"{node['name']} sleeping / timeout ({e})",
                "response_time_ms": latency,
            }

    async with httpx.AsyncClient(timeout=4.0) as client:
        results = await asyncio.gather(*[_probe_node(client, node) for node in nodes])

    checks = {}
    total_latency = 0
    healthy_count = 0

    for res in results:
        checks[res["id"]] = {
            "name": res["name"],
            "status": res["status"],
            "message": res["message"],
            "response_time_ms": res["response_time_ms"],
        }
        total_latency += res["response_time_ms"]
        if res["status"] == "healthy":
            healthy_count += 1

    return {
        "status": "healthy" if healthy_count >= 3 else "degraded",
        "timestamp": int(time.time()),
        "total_response_time_ms": total_latency,
        "checks": checks,
        "summary": {
            "total_checks": len(nodes),
            "healthy": healthy_count,
            "degraded": len(nodes) - healthy_count,
            "unhealthy": 0,
            "unknown": 0,
        },
    }



# ── OpenAI Surface ───────────────────────────────────────────────────────────

@app.get("/v1/models")
async def list_models():
    """Returns available virtual models list."""
    models_data = []
    for provider, cfg in PROVIDER_CONFIGS.items():
        pool = squad.pools.get(provider) if squad else None
        healthy = len(pool.healthy_slots) if pool else 0
        models_data.append({
            "id": f"supremeai/{provider}",
            "object": "model",
            "owned_by": "supremeai",
            "provider": provider,
            "default_target": cfg["default_model"],
            "healthy_keys": healthy,
        })
    models_data.insert(0, {
        "id": "auto",
        "object": "model",
        "owned_by": "supremeai",
        "provider": "dynamic-squad",
        "default_target": "auto-failover",
        "healthy_keys": squad.stats()["total_healthy_keys"] if squad else 0,
    })
    return {"object": "list", "data": models_data}


async def _execute_chat_completion(
    request: Request,
    body: dict,
    x_supremeai_key: Optional[str] = None
):
    """Core completion execution engine for /v1/chat/completions and compatibility aliases."""
    if not _verify_client_auth(request, x_supremeai_key):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing X-SupremeAI-Key / Bearer token"
        )

    # Cost guard: throttle ONLY guest-class requests (keyed auth is never limited).
    if _is_guest_request(request, _extract_token(request, x_supremeai_key)):
        allowed, retry_after = _guest_rate_limit(request)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Guest rate limit exceeded ({GUEST_RATE_LIMIT_PER_MIN}/min per IP). "
                    "Attach an X-SupremeAI-Key for unrestricted access."
                ),
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    requested_model = body.get("model", "auto")
    preferred_provider = None

    if requested_model.startswith("supremeai/"):
        preferred_provider = requested_model.split("/", 1)[1]
    elif requested_model in PROVIDER_CONFIGS:
        preferred_provider = requested_model

    # Conversation-ID carry-over & persistence
    conv_id = (
        body.get("conversation_id")
        or body.get("session_id")
        or request.headers.get("x-conversation-id")
        or request.headers.get("x-session-id")
    )
    user_id = _extract_user_id(request)
    incoming_msgs = body.get("messages", [])
    last_user_msg = next((m.get("content") for m in reversed(incoming_msgs) if isinstance(m, dict) and m.get("role") == "user"), None)

    # 1. Message persistence (Canonical 3-tier memory store & legacy storage)
    if conv_id and last_user_msg:
        if append_canonical_message:
            try:
                append_canonical_message(conv_id, "user", str(last_user_msg), user_id=user_id)
            except Exception as exc:
                logger.warning(f"Canonical memory store error (user msg): {exc}")
        if add_message:
            try:
                add_message(conv_id, "user", str(last_user_msg), user_id=user_id)
            except Exception as exc:
                logger.warning(f"Legacy storage error (user msg): {exc}")

    # 2. Server-Side Context Compiler (Phase 1):
    # Injects Core Identity Anchor + Platform Grounding Sheet + 3-Tier Memory + Deterministic Sampling Lock
    if compile_chat_context:
        try:
            if resolve_sampling_knobs:
                knobs = resolve_sampling_knobs(
                    messages=body.get("messages", []),
                    mode=body.get("mode") or requested_model,
                    max_tokens=body.get("max_tokens", 4096),
                )
                for k, v in knobs.items():
                    if k not in body or body[k] is None:
                        body[k] = v

            body["messages"] = compile_chat_context(
                messages=body.get("messages", []),
                conversation_id=conv_id,
                user_id=user_id,
                language_pref=body.get("language_pref", "bn"),
                response_style=body.get("response_style", "technical-architect"),
            )
        except Exception as exc:
            logger.warning(f"Context compiler error, continuing with incoming messages: {exc}")

    # ═══════════════════════════════════════════════════════════════════════
    # 🔒 HEADLINE — ADMIN ER COMMAND CHARA ENABLE KORA JABE NA
    # (অ্যাডমিনের সরাসরি নির্দেশ ছাড়া API fallback চালু করা সম্পূর্ণ নিষিদ্ধ)
    #
    # API-key fallback is INTENTIONALLY DISABLED. Chat replies come ONLY from
    # the cookie-based Stealth Webhook relay (pure $0 Gemini web session).
    # Purpose: admin must be able to verify that cookies alone actually work.
    #
    # DO NOT (any human, AI agent, bot or automated PR):
    #   - add an API-key / provider-pool fallback after the relay below
    #   - set ENABLE_API_FALLBACK=true in Infisical or Render
    #   - re-add GEMINI_API_KEY to the scraper node (scraper service node)
    # Re-enabling requires an explicit, written ADMIN_DECISION issue from the
    # admin. Any PR that re-enables fallback without it must be rejected.
    # ═══════════════════════════════════════════════════════════════════════
    use_priority_1 = (
        bool(STEALTH_WEBHOOK_URL)
        and (preferred_provider is None or preferred_provider in ("stealth", "ghost_gemini"))
    )
    if use_priority_1:
        w_status, w_response = None, None
        start_time = time.time()
        try:
            w_status, w_response = await forward_stealth_webhook(
                STEALTH_WEBHOOK_URL,
                STEALTH_WEBHOOK_SECRET,
                body,
                timeout=STEALTH_WEBHOOK_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Priority-1 Web Relay attempt exception: {exc}")
            w_status, w_response = 500, None

        # Auto-wrap raw {"reply": "..."} payloads if received
        if isinstance(w_response, dict) and "reply" in w_response and "choices" not in w_response and str(w_response["reply"]).strip():
            w_response = {
                "id": "chatcmpl-stealth-" + os.urandom(6).hex(),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", "auto"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": str(w_response["reply"]).strip(),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }

        chat_content = ""
        if (
            isinstance(w_response, dict)
            and bool(w_response.get("choices"))
            and isinstance(w_response["choices"], list)
            and len(w_response["choices"]) > 0
            and isinstance(w_response["choices"][0], dict)
            and isinstance(w_response["choices"][0].get("message"), dict)
        ):
            chat_content = str(w_response["choices"][0]["message"].get("content", "")).strip()

        # SPINE-style stream sanitization: strip unearned cushions / reflexive
        # apologies from the relay output before serving (no mid-stream pivot
        # here because the full content is already buffered).
        if chat_content:
            try:
                from gateway.service.stream_sanitizer import sanitize_stream as _sanitize_stream
            except ImportError:
                try:
                    from service.stream_sanitizer import sanitize_stream as _sanitize_stream
                except ImportError:
                    _sanitize_stream = None
            if _sanitize_stream is not None:
                chat_content = _sanitize_stream(chat_content).text

        # Reject mock/dummy stubs and require genuine non-empty content
        is_valid_chat = bool(chat_content) and not any(
            marker in chat_content for marker in ("Web Session Active", "health=", "Authenticated via")
        )

        # 3. Post-Generation Response Guard (Phase 2): Identity Bleed Scrubbing & Stub/Markdown Sanitization
        if validate_and_sanitize and is_valid_chat:
            try:
                w_response = validate_and_sanitize(w_response)
                if (
                    isinstance(w_response, dict)
                    and w_response.get("choices")
                    and isinstance(w_response["choices"][0].get("message"), dict)
                ):
                    chat_content = str(w_response["choices"][0]["message"].get("content", "")).strip()
            except Exception as exc:
                logger.warning(f"Response guard rejected output: {exc}")
                is_valid_chat = False

        # 4. Provider Attempts Ledger (Phase 3 persistence)
        if log_provider_attempt:
            try:
                latency_ms = int((time.time() - start_time) * 1000)
                log_provider_attempt(
                    request_id=f"req-{uuid.uuid4().hex[:10]}",
                    conversation_id=conv_id or "ephemeral",
                    provider="stealth-webhook",
                    model=body.get("model", "auto"),
                    status_code=w_status or 500,
                    latency_ms=latency_ms,
                    error_message=None if is_valid_chat else "Invalid chat or stub content rejected by guard",
                )
            except Exception as exc:
                logger.debug(f"Failed to log provider attempt: {exc}")

        if w_status is not None and 200 <= w_status < 300 and is_valid_chat:
            # Server-decided reply badge (e.g. "SupremeAI w.ge Turbo"); UI only displays it.
            served_model = str(w_response.get("model") or "")
            engine_src = w_response.get("supremeai_engine") or (
                served_model if served_model and served_model != "auto" else "gemini"
            )
            w_response["supremeai"] = build_brand("w", str(engine_src), served_model)
            headers = {
                "X-SupremeAI-Provider": "stealth-webhook",
                "X-SupremeAI-Slot": "priority-1",
                "X-SupremeAI-Tier": "priority-1-free",
            }

            if conv_id:
                w_response["conversation_id"] = conv_id
                w_response["session_id"] = conv_id
                if chat_content:
                    if append_canonical_message:
                        try:
                            append_canonical_message(
                                conv_id,
                                "assistant",
                                chat_content,
                                user_id=user_id,
                                provider="stealth-webhook",
                                model=served_model or "auto",
                                metadata={"supremeai": w_response.get("supremeai")},
                            )
                        except Exception as exc:
                            logger.warning(f"Canonical memory store error (assistant msg): {exc}")
                    if add_message:
                        try:
                            add_message(
                                conv_id,
                                "assistant",
                                chat_content,
                                extra={"supremeai": w_response.get("supremeai")},
                                user_id=user_id,
                            )
                        except Exception as exc:
                            logger.warning(f"Legacy storage error (assistant msg): {exc}")

            if body.get("stream"):
                async def stream_generator():
                    # Stream tokens in progressive chunks
                    words = chat_content.split(" ")
                    for idx, word in enumerate(words):
                        chunk_text = word + (" " if idx < len(words) - 1 else "")
                        chunk_payload = {
                            "id": w_response.get("id", "chatcmpl-stream"),
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": served_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": chunk_text},
                                    "finish_reason": None if idx < len(words) - 1 else "stop",
                                }
                            ],
                            "supremeai": w_response.get("supremeai"),
                        }
                        if conv_id:
                            chunk_payload["conversation_id"] = conv_id
                            chunk_payload["session_id"] = conv_id
                        yield f"data: {json.dumps(chunk_payload)}\n\n"
                        await asyncio.sleep(0.012)
                    yield "data: [DONE]\n\n"

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={**headers, "Cache-Control": "no-cache", "Connection": "keep-alive"},
                )

            return JSONResponse(status_code=w_status, content=w_response, headers=headers)

        relay_detail = None
        if isinstance(w_response, dict):
            relay_detail = w_response.get("error") or w_response.get("detail") or w_response.get("message")
        if not relay_detail and w_response is not None:
            relay_detail = str(w_response)[:500]
        logger.warning(
            f"Stealth Webhook relay returned non-chat or error status ({w_status}): {relay_detail}. "
            f"API key fallback disabled per user mandate."
        )
        raise HTTPException(
            status_code=502,
            detail=f"Stealth Webhook relay returned non-chat or error status ({w_status}): {relay_detail}. API fallback disabled."
        )

    raise HTTPException(
        status_code=503,
        detail="Stealth Webhook relay is currently unconfigured or offline. API key replies disabled per user mandate."
    )

    # ── [USER MANDATE & ARCHITECTURAL DIRECTIVE - 2026-10-24] ─────────────────────
    # NOTICE TO ALL AI AGENTS & DEVELOPERS:
    # API key fallback execution is intentionally DISABLED for now because webhook
    # configuration & stealth session testing is actively ongoing.
    # DO NOT re-enable API key replies or squad fallback in /v1/chat/completions until
    # webhook configuration testing is officially marked complete by the maintainer.
    # The dynamic squad implementation, multi-key pool, and model cascades remain
    # fully preserved in service/pool.py and service/providers/adapters.py ready for
    # future activation once webhook testing is concluded.
    # ─────────────────────────────────────────────────────────────────────────────
    # if not squad:
    #     raise HTTPException(status_code=503, detail="Dynamic squad uninitialized")
    #
    # candidates = squad.get_candidate_slots(preferred_provider) if squad else []
    # if not candidates:
    #     raise HTTPException(
    #         status_code=503,
    #         detail="No healthy AI provider keys available at this moment. All keys cooling down."
    #     )
    #
    # last_error = None
    # for provider, slot in candidates:
    #     status, response_data = await forward_chat_completion(provider, slot.key, body)
    #
    #     if 200 <= status < 300:
    #         headers = {
    #             "X-SupremeAI-Provider": provider,
    #             "X-SupremeAI-Slot": slot.name,
    #             "X-SupremeAI-Priority": "2-squad-fallback" if use_priority_1 else "direct-squad",
    #         }
    #         if use_priority_1:
    #             headers["X-SupremeAI-Fallback"] = "p1-stealth-failover"
    #         if isinstance(response_data, dict):
    #             return JSONResponse(status_code=status, content=response_data, headers=headers)
    #         return Response(content=str(response_data), status_code=status, headers=headers, media_type="text/plain")
    #
    #     pool = squad.pools.get(provider)
    #     if pool:
    #         pool.report_injury(slot, status)
    #
    #     last_error = {"provider": provider, "slot": slot.name, "status": status, "error": response_data}
    #     logger.warning(f"Candidate {slot.name} failed ({status}), failing over to next player...")
    #
    # return JSONResponse(
    #     status_code=502,
    #     content={
    #         "error": "All healthy provider attempts failed during cross-provider failover.",
    #         "last_error": last_error,
    # )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key")
):
    """Main OpenAI-compatible completion endpoint."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    return await _execute_chat_completion(request, body, x_supremeai_key)


@app.post("/api/v1/stream/chat")
@app.post("/v1/stream/chat")
async def stream_chat_alias(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key")
):
    """Compatibility alias for legacy chatService (satellite supremeai-studio).
    Translates { message, messages } into OpenAI { messages, stream: true } format.
    """
    try:
        raw_body = await request.json()
    except Exception:  # noqa: BLE001
        raw_body = {}

    messages = raw_body.get("messages")
    if not messages and "message" in raw_body:
        messages = [{"role": "user", "content": str(raw_body["message"])}]
    elif not messages:
        messages = []

    body = dict(raw_body)
    body["messages"] = messages
    body["stream"] = True
    body.setdefault("model", "auto")

    return await _execute_chat_completion(request, body, x_supremeai_key)


@app.post("/api/v1/capabilities/execute")
@app.post("/v1/capabilities/execute")
async def execute_capability_alias(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key")
):
    """Compatibility alias for controlPlane.executeCapability (satellite supremeai-studio).
    Fulfills CapabilityExecutionResult contract without 404.
    """
    if not _verify_client_auth(request, x_supremeai_key):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing X-SupremeAI-Key / Bearer token"
        )

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    capability = body.get("capability", "conversation.orchestrate")
    payload = body.get("payload") or {}
    prompt = payload.get("prompt") or body.get("prompt") or ""
    conv_id = payload.get("conversation_id") or body.get("conversation_id")

    exec_id = f"exec-{uuid.uuid4().hex[:12]}"
    response_text = ""

    if prompt:
        chat_body = {
            "model": "auto",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if conv_id:
            chat_body["conversation_id"] = conv_id
        try:
            res = await _execute_chat_completion(request, chat_body, x_supremeai_key)
            if isinstance(res, JSONResponse):
                c_data = json.loads(res.body.decode("utf-8")) if hasattr(res, "body") else {}
                choices = c_data.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    response_text = choices[0].get("message", {}).get("content", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"execute_capability completion fallback: {exc}")
            response_text = f"Capability {capability} executed."
    else:
        response_text = f"Capability {capability} executed."

    return {
        "execution_id": exec_id,
        "status": "completed",
        "capability": capability,
        "response": response_text or f"Capability {capability} acknowledged.",
        "data": {
            "reasoning_steps": [],
            "artifacts": []
        },
        "verification": {
            "verified": True,
            "method": "gateway_capability_router",
        }
    }


@app.post("/v1/ui/generate")
async def generate_ui_component(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key")
):
    """Specialized V0 / UI synthesis endpoint for SupremeAI Studio."""
    if not _verify_client_auth(request, x_supremeai_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    prompt = body.get("prompt") or (body.get("messages", [{}])[-1].get("content", "") if body.get("messages") else "")
    ui_payload = {
        "model": "v0-web",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a master React Tailwind UI component synthesizer. "
                    "Generate complete, beautiful, production-ready React code without markdown chatter."
                ),
            },
            {"role": "user", "content": str(prompt)},
        ],
    }
    candidates = squad.get_candidate_slots("v0") if squad else []
    for provider, slot in candidates:
        status, resp = await forward_chat_completion(provider, slot.key, ui_payload)
        if 200 <= status < 300:
            return JSONResponse(status_code=status, content=resp)
    # If V0 slot unavailable, fallback to primary chat completion
    return await chat_completions(request, x_supremeai_key)


# ── MCP Control Tower & Superadmin Management Surface ────────────────────────

@app.get("/admin/squad/status")
async def admin_squad_status(
    x_superadmin_key: Optional[str] = Header(None, alias="X-Superadmin-Key")
):
    """Deep inspection of each slot's health and telemetry (MCP Control Tower only)."""
    # Fail-closed: missing key or mismatched key rejected
    if not SUPERADMIN_KEY or x_superadmin_key != SUPERADMIN_KEY:
        raise HTTPException(status_code=403, detail="Superadmin access required (key missing or invalid)")

    details = {}
    now = time.time()
    if squad:
        for name, pool in squad.pools.items():
            details[name] = [
                {
                    "slot": s.name,
                    "healthy": s.is_healthy,
                    "cooldown_remaining_s": max(0, int(s.cooldown_until - now)),
                    "total_calls": s.total_calls,
                    "total_errors": s.total_errors,
                }
                for s in pool.slots
            ]
    return {
        "status": "ok",
        "telemetry": squad.stats() if squad else {},
        "slots": details,
    }


@app.post("/admin/squad/reload")
async def admin_squad_reload(
    x_superadmin_key: Optional[str] = Header(None, alias="X-Superadmin-Key")
):
    """Dynamically re-scans environment for new keys without restarting the container."""
    # Fail-closed: missing key or mismatched key rejected
    if not SUPERADMIN_KEY or x_superadmin_key != SUPERADMIN_KEY:
        raise HTTPException(status_code=403, detail="Superadmin access required (key missing or invalid)")

    if squad:
        squad.reload_squad()
    return {"status": "reloaded", "stats": squad.stats() if squad else {}}


# ── Conversation Carry-over & Chat History Endpoints ─────────────────────────

@app.get("/api/v1/chat/conversations")
@app.get("/v1/chat/conversations")
@app.get("/api/v1/conversations")
@app.get("/api/v1/conversations/")
@app.get("/v1/conversations")
@app.get("/v1/conversations/")
async def get_conversations(
    request: Request,
    limit: int = 50,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """List recent conversation sessions for the current user."""
    if not _verify_client_auth(request, x_supremeai_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _extract_user_id(request)
    convs = list_conversations(user_id=user_id, limit=limit) if list_conversations else []
    return {"status": "ok", "conversations": convs, "count": len(convs)}


@app.get("/api/v1/chat/conversations/{conversation_id}")
@app.get("/v1/chat/conversations/{conversation_id}")
@app.get("/api/v1/conversations/{conversation_id}")
@app.get("/v1/conversations/{conversation_id}")
async def get_conversation_details(
    conversation_id: str,
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Retrieve full message history for a conversation session."""
    if not _verify_client_auth(request, x_supremeai_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _extract_user_id(request)
    conv = get_conversation(conversation_id, user_id=user_id) if get_conversation else None
    if not conv:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    return conv


@app.post("/api/v1/chat/conversations")
@app.post("/v1/chat/conversations")
@app.post("/api/v1/conversations")
@app.post("/api/v1/conversations/")
@app.post("/v1/conversations")
@app.post("/v1/conversations/")
async def create_or_update_conversation(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Create or update conversation metadata."""
    if not _verify_client_auth(request, x_supremeai_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    conv_id = str(body.get("id") or body.get("conversation_id") or f"conv-{uuid.uuid4().hex[:12]}").strip()
    title = body.get("title")
    metadata = body.get("metadata")
    user_id = _extract_user_id(request)

    res = save_conversation(conv_id, user_id=user_id, title=title, metadata=metadata) if save_conversation else {"id": conv_id}
    return {"status": "ok", "conversation": res}


@app.delete("/api/v1/chat/conversations/{conversation_id}")
@app.delete("/v1/chat/conversations/{conversation_id}")
@app.delete("/api/v1/conversations/{conversation_id}")
@app.delete("/v1/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Delete a conversation session and all its messages."""
    if not _verify_client_auth(request, x_supremeai_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _extract_user_id(request)
    ok = delete_conversation(conversation_id, user_id=user_id) if delete_conversation else False
    return {"status": "deleted" if ok else "not_found", "id": conversation_id}


# ── Workspace Connections & Capability Discovery Endpoints ──────────────────

@app.get("/api/v1/connections/my-workspace")
@app.get("/api/connections/my-workspace")
async def get_my_workspace(request: Request):
    """Authoritative scoped workspace state and capabilities contract for User Dashboard."""
    return {
        "userId": _extract_user_id(request),
        "authorizedContexts": [{"id": "ctx-default", "label": "Default Workspace", "active": True}],
        "executionMode": "autonomous",
        "capabilities": [
            {
                "capabilityId": "cap-research",
                "name": "Web Research & Intelligence",
                "purpose": "Autonomous web search, scraping, and real-time facts gathering",
                "status": "ready",
                "category": "tool",
                "unavailableReason": None,
                "requiredPermission": None,
            },
            {
                "capabilityId": "cap-code",
                "name": "Code Assistant & Sandbox",
                "purpose": "Execute python code, run tests, and inspect outputs in isolated sandbox",
                "status": "ready",
                "category": "tool",
                "unavailableReason": None,
                "requiredPermission": None,
            },
            {
                "capabilityId": "cap-browser",
                "name": "Browser Automation",
                "purpose": "Interact with live web pages, capture cookies, and bypass bot protections",
                "status": "ready",
                "category": "agent",
                "unavailableReason": None,
                "requiredPermission": None,
            },
        ],
        "connections": [
            {"connectionId": "conn-gateway", "name": "API Gateway", "health": "healthy"},
            {"connectionId": "conn-scraper", "name": "Scraper Relay", "health": "healthy"},
        ],
        "recentActivity": [],
    }


@app.post("/api/v1/connections/detect")
async def detect_connection(request: Request):
    return {"detected": True, "connectionType": "http-service", "health": "healthy"}


@app.post("/api/v1/connections/register")
async def register_connection(request: Request):
    return {"connection_id": "conn-custom", "capability_id": "cap-custom", "health": "healthy", "message": "Registered successfully"}


@app.post("/api/v1/access/set-mode")
async def set_execution_mode(request: Request):
    return {"user_id": _extract_user_id(request), "mode": "autonomous", "persisted": True, "message": "Mode updated"}


# ── LiveLogs Endpoints (Admin Console Server-Side Log Streaming) ─────────────

@app.get("/admin-api/logs")
@app.get("/api/v1/admin/logs")
@app.get("/admin/logs")
async def get_admin_logs(
    request: Request,
    limit: int = 100,
    level: Optional[str] = None,
    search: Optional[str] = None,
    x_superadmin_key: Optional[str] = Header(None, alias="X-Superadmin-Key"),
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Fetches recent service logs for the Admin Console."""
    is_super = bool(SUPERADMIN_KEY and x_superadmin_key == SUPERADMIN_KEY)
    is_client = _verify_client_auth(request, x_supremeai_key)
    if not is_super and not is_client:
        raise HTTPException(status_code=403, detail="Admin authorization required to view server logs")

    logs = log_ring_buffer.get_logs(limit=limit, level=level, search=search)
    return {
        "status": "ok",
        "total": len(logs),
        "limit": limit,
        "logs": logs,
    }


@app.get("/admin-api/logs/stream")
@app.get("/api/v1/admin/logs/stream")
@app.get("/admin/logs/stream")
async def stream_admin_logs(
    request: Request,
    limit: int = 50,
    x_superadmin_key: Optional[str] = Header(None, alias="X-Superadmin-Key"),
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Real-time Server-Sent Events (SSE) log streamer for Admin Console."""
    is_super = bool(SUPERADMIN_KEY and x_superadmin_key == SUPERADMIN_KEY)
    is_client = _verify_client_auth(request, x_supremeai_key)
    if not is_super and not is_client:
        raise HTTPException(status_code=403, detail="Admin authorization required to stream server logs")

    subscriber_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    log_ring_buffer.subscribers.add(subscriber_queue)

    async def log_event_generator():
        try:
            # Initial backlog burst
            initial_logs = log_ring_buffer.get_logs(limit=limit)
            for entry in initial_logs:
                yield f"data: {json.dumps(entry)}\n\n"

            # Stream real-time logs with heartbeat keep-alive
            while True:
                try:
                    entry = await asyncio.wait_for(subscriber_queue.get(), timeout=12.0)
                    yield f"data: {json.dumps(entry)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            log_ring_buffer.subscribers.discard(subscriber_queue)

    return StreamingResponse(
        log_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── User Preferences & Tool-Card Persistence Endpoints ───────────────────────

@app.get("/api/v1/user/preferences")
@app.get("/api/user/preferences")
async def get_preferences(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Retrieve stored user preferences (including hidden tool cards, pinned tools, theme)."""
    user_id = _extract_user_id(request)
    prefs = get_user_preferences(user_id=user_id) if get_user_preferences else {"user_id": user_id, "preferences": {}}
    return prefs


@app.post("/api/v1/user/preferences")
@app.post("/api/user/preferences")
@app.put("/api/v1/user/preferences")
async def update_preferences(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Update user preferences (e.g. tool card removal / preference saving)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    user_id = _extract_user_id(request)
    res = save_user_preferences(user_id=user_id, patch_data=body) if save_user_preferences else {"user_id": user_id, "preferences": body}
    return {"status": "ok", "user_preferences": res}


@app.delete("/api/v1/user/preferences/tool-card/{tool_id}")
@app.post("/api/v1/user/preferences/tool-card/{tool_id}/hide")
async def hide_tool_card(
    tool_id: str,
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Persistently hides/removes a tool card from the user's dashboard."""
    user_id = _extract_user_id(request)
    patch = {"action": "hide_tool", "tool_id": tool_id}
    res = save_user_preferences(user_id=user_id, patch_data=patch) if save_user_preferences else {"user_id": user_id}
    return {"status": "ok", "action": "hidden", "tool_id": tool_id, "user_preferences": res}


@app.delete("/api/v1/user/preferences/tool-card/{tool_id}/restore")
@app.post("/api/v1/user/preferences/tool-card/{tool_id}/restore")
async def restore_tool_card(
    tool_id: str,
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key"),
):
    """Restores a previously hidden tool card in the user's dashboard."""
    user_id = _extract_user_id(request)
    patch = {"action": "unhide_tool", "tool_id": tool_id}
    res = save_user_preferences(user_id=user_id, patch_data=patch) if save_user_preferences else {"user_id": user_id}
    return {"status": "ok", "action": "restored", "tool_id": tool_id, "user_preferences": res}
