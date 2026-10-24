"""MCP Hub management API — vanity slugs, gateway tenancy stats, AI clients.

Personal MCP Gateway & Multi-Tenant Hub plan — Phase C only
(docs/plans/features/personal_mcp_gateway_multitenant_hub_plan.md §4 Phase C).

    GET    /api/v1/mcp/gateway                  caller's slug + gateway URL + tenant stats
    POST   /api/v1/mcp/slug/claim               claim a vanity slug
    GET    /api/v1/mcp/clients                  list caller's AI clients (no token material)
    POST   /api/v1/mcp/clients                  register an AI client (token shown ONCE)
    PATCH  /api/v1/mcp/clients/{client_id}      role/provider update only
    POST   /api/v1/mcp/clients/{client_id}/rotate  rotate the client token (shown ONCE)
    DELETE /api/v1/mcp/clients/{client_id}      soft-revoke (row kept for audit)

QUOTA-SAFETY / NO-ACCOUNT-MULTIPLICATION (hard constraint, Task 7-d):
    The hub manages ROUTING and PER-CLIENT credentials under the caller's
    EXISTING platform account/tenant. Identity is ALWAYS derived from the
    verified JWT (never from the request body). A lazily-created ``mcp_tenants``
    row is the hub's tenancy record for an existing identity — NOT a new
    account, quota pool, or circumvention path. Plan limits are enforced
    server-side here:
        - ``max_clients``      → 409 when the active-client budget is exhausted
        - ``max_token_days``   → client token expiry is stamped from it
        - ``max_tools_per_min``→ consumed by the Node control-plane data path
    This router is CONTROL-PLANE ONLY: it never proxies MCP traffic (that is
    the infrastructure/mcp-control-plane Node service, Phase B).

Scope contract (keep-simple, Task 7-d):
    A scope is ``"<category>:<action>"`` (e.g. ``"github:read"``,
    ``"tools:execute"``). Three BASELINE scopes from the plan's client DDL
    default are always allowed: ``health:read``, ``system:read``,
    ``tools:execute``. Any other scope's ``<category>`` must appear in the
    tenant's ``allowed_categories`` (DDL default ``["github", "ai", "docs",
    "notify", "knowledge"]``). Roles (``viewer`` | ``agent`` | ``admin``) are
    recorded per client and consumed by the control-plane policy engine
    (Phase E); they do not bypass the scope subset check.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_token
from core.config import settings
from core.logging_config import logger
from database.session import get_db_session
from models.mcp_gateway import (
    DEFAULT_CLIENT_SCOPES,
    RESERVED_SLUGS,
    McpClient,
    McpSlug,
    McpTenant,
    is_valid_slug,
)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp-hub"])

# Baseline scopes always permitted regardless of the tenant category allowlist.
BASELINE_SCOPES = frozenset(DEFAULT_CLIENT_SCOPES)

# Scope wire format: "<category>:<action>" (lowercase, no spaces).
SCOPE_RE = re.compile(r"^[a-z0-9_]+:[a-z0-9_-]+$")


# ── Request bodies ────────────────────────────────────────────────────────────
class SlugClaimBody(BaseModel):
    slug: str = Field(min_length=1, max_length=200, description="Vanity slug, e.g. 'niloy'")


class ClientCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=100, description='e.g. "Claude Desktop"')
    provider: str = Field(default="generic", max_length=50)
    role: Literal["viewer", "agent", "admin"] = "agent"
    scopes: list[str] | None = Field(default=None, max_length=64)


class ClientUpdateBody(BaseModel):
    role: Literal["viewer", "agent", "admin"] | None = None
    provider: str | None = Field(default=None, max_length=50)


# ── Identity & tenant helpers ─────────────────────────────────────────────────
def _hub_identity(user: dict) -> tuple[str, str]:
    """Derive (tenant_id, owner_email) from the verified JWT — never the body."""
    tenant_id = str(
        user.get("tenant_id") or user.get("org_id") or user.get("organization_id") or ""
    ).strip()
    owner_email = str(user.get("email") or user.get("sub") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )
    if len(tenant_id) > 64:  # mcp_tenants.id is VARCHAR(64) per the plan DDL
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant identity exceeds hub registry capacity",
        )
    return tenant_id, owner_email or tenant_id


def _hash_token(token: str) -> str:
    """SHA-256 hex digest — the only credential material we ever persist."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_client_token() -> tuple[str, str, str]:
    """Return (plaintext_token, sha256_hash, prefix). Plaintext is shown ONCE."""
    token = "mcp_" + secrets.token_urlsafe(32)
    return token, _hash_token(token), token[:12]


def _new_admin_token_hash() -> str:
    """Hash for the control-plane admin secret. Plaintext is never returned by
    this API (provisioning/delivery is Phase B, Node control-plane)."""
    return _hash_token(secrets.token_urlsafe(32))


async def _get_or_create_tenant(
    session: AsyncSession, tenant_id: str, owner_email: str
) -> McpTenant:
    """Fetch the hub tenancy record, lazily creating it for an EXISTING identity.

    This is the plan's "customer" tenancy row with free-plan defaults — it does
    NOT create a platform account and grants no additional quota anywhere.
    """
    tenant = await session.get(McpTenant, tenant_id)
    if tenant is not None:
        return tenant
    tenant = McpTenant(
        id=tenant_id,
        name=owner_email,
        owner_email=owner_email,
        type="customer",
        status="active",
        plan="free",
        admin_token_hash=_new_admin_token_hash(),
        max_clients=10,
        max_tools_per_min=120,
        max_token_days=90,
        allowed_categories=["github", "ai", "docs", "notify", "knowledge"],
    )
    session.add(tenant)
    await session.flush()
    logger.info(f"[mcp-hub] lazily provisioned hub tenancy record for existing tenant={tenant_id}")
    return tenant


def _validate_scopes(requested: list[str], allowed_categories: list[str]) -> list[str]:
    """Enforce the scope subset contract (see module docstring). 400 on breach."""
    allowed = set(allowed_categories)
    for scope in requested:
        if scope in BASELINE_SCOPES:
            continue
        if not SCOPE_RE.match(scope):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope format: {scope!r} (expected '<category>:<action>')",
            )
        category = scope.split(":", 1)[0]
        if category not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scope {scope!r} is outside the tenant's allowed categories",
            )
    return list(dict.fromkeys(requested))  # de-dup, order-preserving


def _gateway_url_for(slug: str | None) -> str | None:
    if not slug:
        return None
    return f"https://{slug}.{settings.mcp_gateway_domain}"


def _slug_dict(slug: McpSlug) -> dict:
    return {
        "slug": slug.slug,
        "target_type": slug.target_type,
        "is_primary": slug.is_primary,
        "status": slug.status,
    }


def _tenant_dict(tenant: McpTenant, clients_count: int) -> dict:
    return {
        "id": tenant.id,
        "plan": tenant.plan,
        "status": tenant.status,
        "max_clients": tenant.max_clients,
        "max_tools_per_min": tenant.max_tools_per_min,
        "max_token_days": tenant.max_token_days,
        "allowed_categories": list(tenant.allowed_categories or []),
        "clients_count": clients_count,
    }


def _client_dict(client: McpClient) -> dict:
    # NOTE: intentionally excludes token_hash — hashes are never client-facing.
    return {
        "id": client.id,
        "name": client.name,
        "provider": client.provider,
        "protocol": client.protocol,
        "role": client.role,
        "scopes": list(client.scopes or []),
        "status": client.status,
        "token_prefix": client.token_prefix,
        "expires_at": client.expires_at.isoformat() if client.expires_at else None,
        "last_seen_at": client.last_seen_at.isoformat() if client.last_seen_at else None,
        "created_at": client.created_at.isoformat() if client.created_at else None,
    }


async def _count_active_clients(session: AsyncSession, tenant_id: str) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(McpClient)
        .where(McpClient.tenant_id == tenant_id, McpClient.status == "active")
    )
    return int(result.scalar_one())


async def _get_tenant_client(session: AsyncSession, tenant_id: str, client_id: str) -> McpClient:
    """Tenant-scoped client fetch — ANY other tenant's object is a 404."""
    result = await session.execute(
        select(McpClient).where(McpClient.id == client_id, McpClient.tenant_id == tenant_id)
    )
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _stamp_expiry(tenant: McpTenant) -> datetime:
    days = max(int(tenant.max_token_days or 0), 1)
    return datetime.now(UTC) + timedelta(days=days)


# ── Gateway overview ──────────────────────────────────────────────────────────
@router.get("/gateway")
async def get_gateway(
    user: dict = Depends(get_current_user_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Caller's slug (or null), settings-driven gateway URL and tenant stats."""
    tenant_id, _ = _hub_identity(user)

    tenant_row = await session.get(McpTenant, tenant_id)
    slug_row = None
    if tenant_row is not None:
        result = await session.execute(
            select(McpSlug)
            .where(
                McpSlug.tenant_id == tenant_id,
                McpSlug.status == "active",
                McpSlug.is_primary.is_(True),
            )
            .order_by(McpSlug.created_at)
            .limit(1)
        )
        slug_row = result.scalar_one_or_none()
        if slug_row is None:
            result = await session.execute(
                select(McpSlug)
                .where(McpSlug.tenant_id == tenant_id, McpSlug.status == "active")
                .order_by(McpSlug.created_at)
                .limit(1)
            )
            slug_row = result.scalar_one_or_none()

    slug = slug_row.slug if slug_row else None
    return {
        "slug": slug,
        "gateway_url": _gateway_url_for(slug),
        "gateway_base_domain": settings.mcp_gateway_domain,
        "tenant": (
            _tenant_dict(tenant_row, await _count_active_clients(session, tenant_id))
            if tenant_row is not None
            else None
        ),
    }


# ── Slug claiming ─────────────────────────────────────────────────────────────
@router.post("/slug/claim", status_code=status.HTTP_201_CREATED)
async def claim_slug(
    body: SlugClaimBody,
    user: dict = Depends(get_current_user_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Validate + claim a vanity slug for the caller's EXISTING tenant."""
    tenant_id, owner_email = _hub_identity(user)
    slug_value = body.slug.strip().lower()

    if not is_valid_slug(slug_value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid slug format: use 1-63 lowercase letters, digits or hyphens "
            "(no leading/trailing hyphen)",
        )
    if slug_value in RESERVED_SLUGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Slug {slug_value!r} is reserved by the platform",
        )

    existing = (
        await session.execute(select(McpSlug).where(McpSlug.slug == slug_value))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slug already claimed",
        )

    # Lazily provision the hub tenancy record for the EXISTING identity.
    await _get_or_create_tenant(session, tenant_id, owner_email)

    primary_row = (
        await session.execute(
            select(McpSlug).where(
                McpSlug.tenant_id == tenant_id,
                McpSlug.status == "active",
                McpSlug.is_primary.is_(True),
            )
        )
    ).scalar_one_or_none()

    slug_row = McpSlug(
        slug=slug_value,
        tenant_id=tenant_id,
        target_type="user",
        is_primary=primary_row is None,
        status="active",
    )
    session.add(slug_row)
    try:
        await session.commit()
    except IntegrityError as exc:  # concurrent claim race — same 409 contract
        await session.rollback()
        logger.warning(f"[mcp-hub] slug race on {slug_value!r}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slug already claimed",
        ) from exc
    await session.refresh(slug_row)

    return {**_slug_dict(slug_row), "gateway_url": _gateway_url_for(slug_value)}


# ── Client management ─────────────────────────────────────────────────────────
@router.get("/clients")
async def list_clients(
    user: dict = Depends(get_current_user_token),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """List the caller's AI clients. Never returns token material (only prefix)."""
    tenant_id, _ = _hub_identity(user)
    result = await session.execute(
        select(McpClient).where(McpClient.tenant_id == tenant_id).order_by(McpClient.created_at)
    )
    return [_client_dict(c) for c in result.scalars().all()]


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreateBody,
    user: dict = Depends(get_current_user_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Register an AI client. The plaintext token appears in THIS response only."""
    tenant_id, owner_email = _hub_identity(user)
    tenant = await _get_or_create_tenant(session, tenant_id, owner_email)

    active_count = await _count_active_clients(session, tenant_id)
    if active_count >= tenant.max_clients:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Client limit reached ({tenant.max_clients}) for plan {tenant.plan!r}",
        )

    scopes = (
        _validate_scopes(body.scopes, list(tenant.allowed_categories or []))
        if body.scopes is not None
        else list(DEFAULT_CLIENT_SCOPES)
    )

    token, token_hash, token_prefix = _new_client_token()
    client = McpClient(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        name=body.name,
        provider=(body.provider or "generic").strip().lower()[:50],
        protocol="streamable-http",
        role=body.role,
        scopes=scopes,
        token_hash=token_hash,
        token_prefix=token_prefix,
        status="active",
        expires_at=_stamp_expiry(tenant),
    )
    session.add(client)
    await session.commit()
    await session.refresh(client)

    logger.info(f"[mcp-hub] client {client.token_prefix}… created for tenant={tenant_id}")
    return {**_client_dict(client), "token": token}


@router.patch("/clients/{client_id}")
async def update_client(
    client_id: str,
    body: ClientUpdateBody,
    user: dict = Depends(get_current_user_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Role/provider update only — cross-tenant objects are 404 (not 403)."""
    tenant_id, _ = _hub_identity(user)
    client = await _get_tenant_client(session, tenant_id, client_id)

    if body.role is None and body.provider is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to update: provide 'role' and/or 'provider'",
        )

    if body.role is not None:
        client.role = body.role
    if body.provider is not None:
        client.provider = body.provider.strip().lower()[:50]
    await session.commit()
    await session.refresh(client)
    return _client_dict(client)


@router.post("/clients/{client_id}/rotate")
async def rotate_client_token(
    client_id: str,
    user: dict = Depends(get_current_user_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Rotate the client token — plaintext appears in THIS response only."""
    tenant_id, _ = _hub_identity(user)
    client = await _get_tenant_client(session, tenant_id, client_id)
    tenant = await session.get(McpTenant, tenant_id)
    if tenant is None:  # defensive: FK guarantees this never happens
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    token, token_hash, token_prefix = _new_client_token()
    client.token_hash = token_hash
    client.token_prefix = token_prefix
    client.status = "active"
    client.expires_at = _stamp_expiry(tenant)
    await session.commit()
    await session.refresh(client)

    logger.info(f"[mcp-hub] token rotated for client prefix {client.token_prefix}…")
    return {**_client_dict(client), "token": token}


@router.delete("/clients/{client_id}")
async def revoke_client(
    client_id: str,
    user: dict = Depends(get_current_user_token),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Soft revoke — the row is kept for audit, tokens stop being honoured."""
    tenant_id, _ = _hub_identity(user)
    client = await _get_tenant_client(session, tenant_id, client_id)
    client.status = "revoked"
    await session.commit()
    await session.refresh(client)
    return _client_dict(client)
