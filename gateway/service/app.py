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

import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
        )
    except ImportError:
        try:
            from service.providers.adapters import (
                PROVIDER_CONFIGS,
                forward_chat_completion,
                forward_stealth_webhook,
            )
        except ImportError:
            PROVIDER_CONFIGS = {}  # type: ignore[assignment]
            def forward_chat_completion(*a, **k):  # type: ignore[no-redef]
                return 503, {"error": "adapters unavailable"}
            def forward_stealth_webhook(*a, **k):  # type: ignore[no-redef]
                return 503, {"error": "adapters unavailable"}
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("supremeai.gateway")

# Priority-1 Stealth Webhook & Web Session Configuration
STEALTH_WEBHOOK_URL = os.getenv("STEALTH_WEBHOOK_URL", os.getenv("UPSTREAM_WEBHOOK_URL", "")).strip()
STEALTH_WEBHOOK_SECRET = os.getenv("STEALTH_WEBHOOK_SECRET", os.getenv("UPSTREAM_WEBHOOK_SECRET", "")).strip()
STEALTH_WEBHOOK_TIMEOUT = float(os.getenv("STEALTH_WEBHOOK_TIMEOUT", "28.0"))

app = FastAPI(title="SupremeAI API Gateway", version="2.0.0", docs_url=None, redoc_url=None)

# CORS setup for Studio and web agents - Restricted origins (no wildcard with credentials)
_default_cors = [
    "https://supremeai-studio.pages.dev",
    "https://supremeai-studio.paykaribazaronline.workers.dev",
    "https://supremeai-studio.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env:
    allowed_origins = list(dict.fromkeys([o.strip() for o in _cors_env.split(",") if o.strip()] + _default_cors))
else:
    allowed_origins = _default_cors

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Telegram Inbound Webhook Listener
if telegram_router is not None:
    app.include_router(telegram_router)


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
    return (
        request.headers.get("x-guest-mode", "").lower() == "true"
        or "https://supremeai-studio.pages.dev" in origin
        or "https://supremeai-studio.pages.dev" in referer
        or "https://supremeai-studio.vercel.app" in origin
        or "https://supremeai-studio.vercel.app" in referer
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


# ── Liveness & Readiness Probes ──────────────────────────────────────────────

@app.get("/")
@app.get("/health")
@app.get("/healthz")
async def health_check():
    """Unauthenticated liveness probe. Always 200 OK when service is running."""
    telemetry = squad.stats() if squad else {"total_keys": 0, "total_healthy_keys": 0, "providers": {}}
    return {
        "status": "healthy",
        "service_name": "supremeai-api",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_keys": telemetry["total_keys"],
        "total_healthy_keys": telemetry["total_healthy_keys"],
        "chat_ready": bool(STEALTH_WEBHOOK_URL),
        "stealth_priority1_configured": bool(STEALTH_WEBHOOK_URL),
        "web_sessions_active": bool(web_bridge and web_bridge.has_active_accounts),
        "web_session_status": web_bridge.status() if web_bridge else {},
        "telegram_webhook_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "active_providers": [
            p for p, data in telemetry.get("providers", {}).items() if data.get("healthy", 0) > 0
        ],
    }


@app.get("/readyz")
async def readiness_check():
    """Capability probe (distinct from liveness): 200 only when a chat reply path
    is configured. Monitors should target /readyz — /health alone cannot detect a
    relay outage because API fallback is disabled by mandate (single reply path)."""
    if STEALTH_WEBHOOK_URL:
        return {
            "status": "ready",
            "chat_ready": True,
            "stealth_priority1_configured": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    return JSONResponse(
        status_code=503,
        content={
            "status": "degraded",
            "chat_ready": False,
            "reason": "STEALTH_WEBHOOK_URL not configured — no chat reply path (API fallback disabled per mandate)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


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


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    x_supremeai_key: Optional[str] = Header(None, alias="X-SupremeAI-Key")
):
    """
    Main OpenAI-compatible completion endpoint.
    Performs dynamic load-balancing and instant substitution across healthy slots.
    """
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

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    requested_model = body.get("model", "auto")
    preferred_provider = None

    if requested_model.startswith("supremeai/"):
        preferred_provider = requested_model.split("/", 1)[1]
    elif requested_model in PROVIDER_CONFIGS:
        preferred_provider = requested_model

    use_priority_1 = (
        bool(STEALTH_WEBHOOK_URL)
        and (preferred_provider is None or preferred_provider in ("stealth", "ghost_gemini"))
    )
    if use_priority_1:
        w_status, w_response = None, None
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

        # Reject mock/dummy stubs and require genuine non-empty content
        is_valid_chat = bool(chat_content) and not any(
            marker in chat_content for marker in ("Web Session Active", "health=", "Authenticated via")
        )

        if w_status is not None and 200 <= w_status < 300 and is_valid_chat:
            headers = {
                "X-SupremeAI-Provider": "stealth-webhook",
                "X-SupremeAI-Slot": "priority-1",
                "X-SupremeAI-Tier": "priority-1-free",
            }
            return JSONResponse(status_code=w_status, content=w_response, headers=headers)

        relay_detail = None
        if isinstance(w_response, dict):
            relay_detail = w_response.get("error") or w_response.get("detail") or w_response.get("message")
        if not relay_detail and w_response is not None:
            relay_detail = str(w_response)[:500]
        logger.warning(
            f"Stealth Webhook relay returned non-chat or error status ({w_status}): {relay_detail}. "
            f"Cascading to Tier-1/Tier-2 Squad..."
        )

    # ── Tier-1 / Tier-2 Dynamic Key-Plane Squad with Model Cascades ───────────
    candidates = squad.get_candidate_slots(preferred_provider) if squad else []
    if not candidates:
        if use_priority_1:
            raise HTTPException(
                status_code=502,
                detail=f"Stealth Webhook relay returned non-chat or error status ({w_status}): {relay_detail}."
            )
        raise HTTPException(
            status_code=503,
            detail="No healthy AI provider keys available at this moment. All keys cooling down."
        )

    last_error = None
    for provider, slot in candidates:
        status, response_data = await forward_chat_completion(provider, slot.key, body)

        if 200 <= status < 300:
            headers = {
                "X-SupremeAI-Provider": provider,
                "X-SupremeAI-Slot": slot.name,
                "X-SupremeAI-Priority": "2-squad-fallback" if use_priority_1 else "direct-squad",
            }
            if use_priority_1:
                headers["X-SupremeAI-Fallback"] = "p1-stealth-failover"
            if isinstance(response_data, dict):
                return JSONResponse(status_code=status, content=response_data, headers=headers)
            return Response(content=str(response_data), status_code=status, headers=headers, media_type="text/plain")

        pool = squad.pools.get(provider)
        if pool:
            pool.report_injury(slot, status)

        last_error = {"provider": provider, "slot": slot.name, "status": status, "error": response_data}
        logger.warning(f"Candidate {slot.name} failed ({status}), failing over to next player...")

    return JSONResponse(
        status_code=502,
        content={
            "error": "All healthy provider attempts failed during cross-provider failover.",
            "last_error": last_error,
        }
    )


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
