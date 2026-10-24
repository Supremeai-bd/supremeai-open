import base64
import hashlib
import hmac
import time
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_token
from core.config import settings
from core.logging_config import logger
from core.security.security_vault import encrypt_token
from database.session import get_db_session
from models.integration import Integration

# বাংলা মন্তব্য: GitHub OAuth — HMAC-SHA256 সাইনড স্টেট টোকেন দ্বারা সুরক্ষিত
# CSRF অ্যাটাক প্রতিরোধে signed, user-bound, 10-মিনিটের TTL স্টেট টোকেন বাধ্যতামূলক করা হয়েছে।
# এছাড়া Least-Privilege নীতি অনুযায়ী অপ্রয়োজনীয় 'user' স্কোপ পরিহার করে শুধুমাত্র 'repo' স্কোপ রাখা হয়েছে।

router = APIRouter()

_OAUTH_STATE_TTL_SECONDS = 600


# ═══════════════════════════════════════════════════════════════════════════
# Connected Platforms Vault listing (#1826): GET /api/v1/integrations আগে
# কখনোই built হয়নি — ফলে /platform-vault পেজ স্থায়ীভাবে "Unable to load"
# দেখাত। এখন caller-এর সংরক্ষিত integration rows (Integration মডেল) থেকে
# vault-এর প্রত্যাশিত shape-এ projection ফেরত দেওয়া হয়।
# ═══════════════════════════════════════════════════════════════════════════
class IntegrationSummary(BaseModel):
    """Shape the ConnectedPlatformsVault dashboard consumes (frontend contract)."""

    id: str
    name: str
    platform: str
    connected: bool
    lastAccessed: str
    permissions: list[str]
    status: Literal["active", "revoked", "expired", "pending"]


@router.get("/integrations")
async def list_integrations(
    user: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db_session),
) -> list[IntegrationSummary]:
    """List the caller's connected integrations (Connected Platforms Vault, #1826)."""
    user_id = str(user.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(
        select(Integration)
        .where(Integration.user_id == user_id)
        .order_by(Integration.updated_at.desc())
    )
    rows = result.scalars().all()
    return [
        IntegrationSummary(
            id=str(row.id),
            name=row.provider,
            platform=row.provider,
            connected=bool(row.encrypted_access_token),
            lastAccessed=(row.updated_at or row.created_at).isoformat(),
            # Least-privilege scope actually granted by the GitHub link flow;
            # other providers carry no recorded scopes yet.
            permissions=["repo"] if row.provider == "github" else [],
            status="active",
        )
        for row in rows
    ]


def _sign_oauth_state(user_id: str, expires_at: int) -> str:
    """Creates a URL-safe signed state token binding user_id and expiration."""
    msg = f"{user_id}|{expires_at}".encode()
    sig = hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
    raw = f"{user_id}|{expires_at}|{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _verify_oauth_state(state: str, user_id: str) -> bool:
    """Verifies HMAC signature, expiry, and user matching of an OAuth state token."""
    try:
        raw = base64.urlsafe_b64decode(state.encode()).decode()
        state_user, expires_at_str, sig = raw.split("|", 2)
        expires_at = int(expires_at_str)
        msg = f"{state_user}|{expires_at}".encode()
        expected = hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return False
        if expires_at < int(time.time()):
            return False
        return state_user == str(user_id)
    except Exception:
        return False


def _build_github_redirect_uri() -> str:
    """
    ডায়নামিক রিডাইরেক্ট URI তৈরি করে — প্রোডাকশনে settings.frontend_base_url ব্যবহার করবে,
    লোকালে ডিফল্ট localhost:8000।
    """
    base = settings.frontend_base_url
    return f"{base}/api/v1/integrations/github/callback"


@router.get("/integrations/github/link")
async def link_github(
    token_payload: dict = Depends(get_current_user_token),
):
    """
    ইউজারকে GitHub OAuth লগইন পেইজে রিডাইরেক্ট করে।
    CSRF প্রটেকশনের জন্য HMAC সাইনড স্টেট টোকেন জেনারেট করে যুক্ত করা হয়।
    """
    user_id = str(token_payload.get("sub") or "")
    redirect_uri = _build_github_redirect_uri()
    expires_at = int(time.time()) + _OAUTH_STATE_TTL_SECONDS
    state = _sign_oauth_state(user_id, expires_at)
    params = {
        "client_id": settings.github_client_id,
        "scope": "repo",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    github_auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    return RedirectResponse(url=github_auth_url)


@router.get("/integrations/github/callback")
async def github_callback(
    code: str,
    request: Request,
    state: str = "",
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db_session),
):
    """
    GitHub OAuth কলব্যাক হ্যান্ডলার।
    কোড এক্সচেঞ্জ করার আগে অবশ্যই সাইনড স্টেট ভ্যালিডেট করে CSRF অ্যাটাক ব্লক করে।
    """
    # ১. JWT থেকে প্রকৃত user_id বের করা
    user_id = token_payload.get("sub")
    if not user_id:
        logger.error("GitHub OAuth callback: Token payload missing 'sub' claim.")
        return RedirectResponse(
            url=f"{settings.frontend_base_url}/integrations?status=error&message=Invalid token"
        )

    # ০. CSRF State Verification
    if not state or not _verify_oauth_state(state, str(user_id)):
        logger.warning(
            f"GitHub OAuth callback: invalid or expired state for user '{user_id}' — rejecting"
        )
        return RedirectResponse(
            url=f"{settings.frontend_base_url}/integrations?status=error&message=Invalid or expired state"
        )

    redirect_uri = _build_github_redirect_uri()
    token_url = "https://github.com/login/oauth/access_token"
    payload = {
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ⏱️ FIX: explicit timeout — default timeout infinite হলে serverless function hang করে বিল বাড়ায়
        response = await client.post(token_url, json=payload, headers=headers, timeout=30.0)
        data = response.json()

    access_token = data.get("access_token")
    if not access_token:
        logger.warning(f"GitHub OAuth failed for user {user_id}: no access_token in response")
        return RedirectResponse(
            url=f"{settings.frontend_base_url}/integrations?status=error&message=Failed to get access token"
        )

    # ২. টোকেন এনক্রিপ্ট করা (AES-256 Fernet)
    encrypted_token = encrypt_token(access_token)

    # ৩. DB-তে ইন্টিগ্রেশন সেভ করা (upsert — একই user_id + provider-এ আপডেট)
    # ⚠️ FIX: SQLAlchemy AsyncSession.get() শুধুমাত্র primary key নেয়, dict ফিল্টার নয়।
    # তাই select() + where() ব্যবহার করতে হবে — নাহলে runtime ArgumentError থ্রো করবে।
    try:
        stmt = select(Integration).where(
            Integration.user_id == user_id,
            Integration.provider == "github",
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.encrypted_access_token = encrypted_token
        else:
            new_integration = Integration(
                user_id=user_id,
                provider="github",
                encrypted_access_token=encrypted_token,
            )
            db.add(new_integration)
        await db.commit()
        logger.info(f"✅ GitHub integration saved for user '{user_id}'")
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to save GitHub integration for user '{user_id}': {exc}")
        return RedirectResponse(
            url=f"{settings.frontend_base_url}/integrations?status=error&message=Database error"
        )

    # ৪. ফ্রন্টএন্ডে রিডাইরেক্ট — ডায়নামিক URL
    frontend_base = settings.frontend_base_url
    return RedirectResponse(url=f"{frontend_base}/integrations?status=success")


# ═══════════════════════════════════════════════════════════════════════════
# 1-Line Connect (old plan, Feature 1): URL → auto-detected integration
# বাংলা: MCP/AI Provider/Webhook — একটি URL দিলেই auto-detect হয়ে যায়।
# ═══════════════════════════════════════════════════════════════════════════
from typing import Any  # noqa: E402  (endpoint-local import block bottom)

from pydantic import BaseModel, Field  # noqa: E402

from services.integration_discovery import IntegrationDiscoveryService  # noqa: E402


class DiscoverRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048, description="MCP/AI provider/webhook URL")
    register: bool = Field(False, description="Save to registry if detection succeeds")


@router.post("/integrations/discover")
async def discover_integration(
    payload: DiscoverRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """**1-Line Connect** — URL ইনপুট দিলে MCP/AI Provider/Webhook auto-detect।

    Detection order: MCP handshake (``/.well-known/mcp.json``) → AI provider
    pattern → webhook reachability fallback।
    """
    tenant_id = user.get("tenant_id") or user.get("sub")
    actor_id = user.get("sub")
    logger.info(f"[Integrations] 1-Line discover requested by {actor_id}")

    return await IntegrationDiscoveryService.discover(
        url=payload.url,
        tenant_id=str(tenant_id) if tenant_id else None,
        actor_id=str(actor_id) if actor_id else None,
        register=payload.register,
    )
