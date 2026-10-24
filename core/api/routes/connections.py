"""Universal Zero-Complexity Interface — Connections API (Phase 1).

বাংলা: এই মডিউল customer-facing connection engine-এর modular endpoints দেয়।
UI সহজ (একটা URL paste), কিন্তু backend modular — protocol detection, governed
registration, capability listing সব আলাদা ভাগে।

Security rules:
- Auth mandatory: প্রতিটি endpoint `get_current_user_token` ব্যবহার করে।
- কোনো secret (API key/token) এখানে গ্রহণ বা সংরক্ষণ করা হয় না।
- User শুধু নিজের স্কোপ দেখে — tenant ফিল্টার backend-authoritative।
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from adaptive_engine.capability_registry import (
    Capability,
    CapabilityRegistry,
    get_capability_registry,
)
from core.security.authentication.rbac import get_current_user_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class _CamelResponse(BaseModel):
    """বাংলা: response contract হলো frontend/types/contracts-এর camelCase vocabulary।

    Phase 2 contract-গুলো (capability-contract.ts, connection-contract.ts) camelCase
    পড়ে — কিন্তু backend আগে snake_case পাঠাত, ফলে `providerLabel`/`capabilityId`
    UI-তে `undefined` হয়ে যেত। alias generator দিয়ে wire format এখন contract-মুখী,
    আর `populate_by_name` রাখায় backend-internal snake_case construction অক্ষত থাকে।
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DetectionRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class DetectionResponse(_CamelResponse):
    detected: bool
    protocol: Literal["mcp", "oauth", "rest", "custom"]
    provider_label: str
    reasons: list[str]


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    label: str | None = Field(default=None, max_length=120)


class RegisterResponse(_CamelResponse):
    connection_id: str
    capability_id: str
    health: Literal["pending"] = "pending"
    message: str


class WorkspaceContext(_CamelResponse):
    id: str
    label: str
    active: bool


class WorkspaceCapability(_CamelResponse):
    capability_id: str
    name: str
    purpose: str
    status: Literal["ready", "idle", "unavailable", "requestable"]
    category: str
    unavailable_reason: str | None
    required_permission: str | None


class MyWorkspaceResponse(_CamelResponse):
    user_id: str
    authorized_contexts: list[WorkspaceContext]
    execution_mode: str = "ask_before_acting"
    capabilities: list[WorkspaceCapability]
    connections: list[dict[str, Any]]
    recent_activity: list[dict[str, Any]]


class SetModeRequest(BaseModel):
    mode: Literal["read_only", "ask_before_acting", "autonomous"]


class SetModeResponse(_CamelResponse):
    user_id: str
    mode: str
    persisted: bool
    message: str


# ---------------------------------------------------------------------------
# Provider/protocol detection (pure, no network fetch — Acid Test 10)
# ---------------------------------------------------------------------------

_PROVIDER_HINTS: tuple[tuple[str, str], ...] = (
    ("github.com", "GitHub"),
    ("gitlab.com", "GitLab"),
    ("googleapis.com", "Google"),
    ("drive.google.com", "Google Drive"),
    ("slack.com", "Slack"),
    ("notion.so", "Notion"),
    ("supabase.co", "Supabase"),
    ("render.com", "Render"),
    ("cloudflare.com", "Cloudflare"),
)


def detect_protocol(raw_url: str) -> DetectionResponse:
    """বাংলা: URL থেকে provider/protocol অনুমান — network call ছাড়াই, deterministic।"""
    text = (raw_url or "").strip()
    reasons: list[str] = []
    if not text:
        return DetectionResponse(
            detected=False, protocol="custom", provider_label="Custom tool", reasons=["empty input"]
        )

    lowered = text.lower()
    if lowered.startswith("mcp://") or "/mcp" in lowered or lowered.endswith("/sse"):
        reasons.append("MCP transport marker found in URL")
        return DetectionResponse(
            detected=True, protocol="mcp", provider_label="Custom MCP tool", reasons=reasons
        )

    if lowered.startswith("http://") or lowered.startswith("https://"):
        host = urlparse(text).netloc.lower()
        for marker, label in _PROVIDER_HINTS:
            if marker in host:
                reasons.append(f"host matches known provider: {marker}")
                return DetectionResponse(
                    detected=True, protocol="oauth", provider_label=label, reasons=reasons
                )
        reasons.append("generic https endpoint")
        return DetectionResponse(
            detected=True, protocol="rest", provider_label="Web service", reasons=reasons
        )

    reasons.append("no recognizable transport; treating as custom tool")
    return DetectionResponse(
        detected=False, protocol="custom", provider_label="Custom tool", reasons=reasons
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/my-workspace", response_model=MyWorkspaceResponse)
async def my_workspace(current_user: dict = Depends(get_current_user_token)) -> MyWorkspaceResponse:
    """বাংলা: backend-authoritative user স্কোপ — শুধু যা user ব্যবহার/অনুমোদিত, তাই ফেরত।"""
    user_id = str(current_user.get("sub") or current_user.get("uid") or "anonymous")
    tenant_id = current_user.get("tenant_id") or current_user.get("tid")

    capabilities: list[WorkspaceCapability] = []
    try:
        registry: CapabilityRegistry = get_capability_registry()
        rows = registry.list(tenant_id=tenant_id if isinstance(tenant_id, str) else None, limit=100)
        # বাংলা: শুধু বাস্তব lifecycle মান — capability_registry.LifecycleState-এ
        # "production"/"ready" নামে কোনো state নেই, তাই ওরা আগে dead entry ছিল।
        ready_states = {"measured", "active"}
        for cap in rows:
            state_value = str(getattr(cap.lifecycle_state, "value", cap.lifecycle_state)).lower()
            is_ready = state_value in ready_states
            has_permission = bool(cap.permissions)
            if is_ready:
                cap_status: Literal["ready", "idle", "unavailable", "requestable"] = "ready"
            elif has_permission:
                # বাংলা: permission আছে কিন্তু lifecycle এখনো পরিণত হয়নি —
                # user দরকার হলে access চাইতে পারবে (Explain-Why UX)
                cap_status = "requestable"
            else:
                cap_status = "unavailable"
            capabilities.append(
                WorkspaceCapability(
                    capability_id=cap.capability_id,
                    name=cap.name,
                    purpose=cap.purpose,
                    status=cap_status,
                    category=cap.category,
                    unavailable_reason=None if is_ready else f"capability lifecycle: {state_value}",
                    required_permission=(cap.permissions[0] if cap.permissions else None),
                )
            )
    except Exception as exc:  # pragma: no cover - registry storage failure
        # বাংলা: silent failure নয় — degrade করব কিন্তু log-এ evidence থাকবে
        logger.warning("capability registry unavailable for %s: %s", user_id, exc)

    # বাংলা: Zero-Friction stack (core.connection_registry) এখন একই response-এ
    # প্রবাহিত হয় — দুটি parallel engine-এর state আর আলাদা থাকবে না।
    connections: list[dict[str, Any]] = []
    try:
        from core.connection_registry import ConnectionRegistry

        connection_registry = ConnectionRegistry()
        for record in connection_registry.list_for_tenant(current_user):
            connections.append(
                {
                    "connectionId": record.id,
                    "name": record.name,
                    "health": "healthy" if record.status == "active" else "unreachable",
                }
            )
    except Exception as exc:  # pragma: no cover - registry storage failure
        logger.warning("connection registry unavailable for %s: %s", user_id, exc)

    # বাংলা: authorized contexts — বর্তমানে personal workspace; admin context শুধু
    # backend RBAC অনুমোদন করলেই যোগ হবে (Correction 2 — no client-side escalation)।
    contexts = [WorkspaceContext(id="personal", label="Personal Workspace", active=True)]

    return MyWorkspaceResponse(
        user_id=user_id,
        authorized_contexts=contexts,
        capabilities=capabilities,
        connections=connections,
        recent_activity=[],
    )


@router.post("/detect", response_model=DetectionResponse)
async def detect_connection(
    payload: DetectionRequest,
    current_user: dict = Depends(get_current_user_token),
) -> DetectionResponse:
    """বাংলা: URL paste করলেই কী ধরনের connection সেটা শনাক্ত করে (Acid Test 10)।"""
    del current_user  # auth-ই প্রধান গেট; detection-এ per-user state লাগে না
    return detect_protocol(payload.url)


@router.post("/register", response_model=RegisterResponse)
async def register_connection(
    payload: RegisterRequest,
    current_user: dict = Depends(get_current_user_token),
) -> RegisterResponse:
    """বাংলা: custom tool নিবন্ধন — governed path, audit log, tenant-scoped capability।

    Phase 1 (One connection registry): আগে registration শুধু capability registry-তে
    যেত, ConnectionRegistry (supremeai_connections টেবিল) ফাঁকা থাকত এবং
    connection_id ছিল ভুয়া (fabricated)। এখন দুটো রেজিস্ট্রিতেই write-through হয় —
    DB persist হলে সত্যিকারের connection record id ফেরত যায়; persist না হলেও
    capability path কাজ চালিয়ে যায় (Graceful Degradation, সঙ্গে সৎ warning log)।
    """
    user_id = str(current_user.get("sub") or current_user.get("uid") or "anonymous")
    if not payload.url.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A URL or identifier is required"
        )

    detection = detect_protocol(payload.url)
    registry = get_capability_registry()
    name = payload.label or payload.name
    capability = Capability(
        name=name,
        purpose=f"User-registered tool: {payload.url}",
        signature=f"user.connection.{uuid.uuid4().hex[:12]}.v1",
        category="user_connection",
        execution_method="external",
        security_level="standard",
        permissions=["capability:connection:use"],
        provenance={"registered_by": user_id, "url": payload.url, "protocol": detection.protocol},
    )
    try:
        created = registry.register(capability)
    except Exception as exc:
        logger.error("connection registration failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service unavailable",
        ) from exc

    # --- Phase 1: durable write-through to the ConnectionRegistry ---
    tenant_id = str(current_user.get("tenant_id") or current_user.get("org_id") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required for connection registration",
        )
    connection_id = f"conn-{uuid.uuid4().hex[:12]}"
    persisted = False
    try:
        from core.connection_registry import connection_registry

        record = connection_registry.register(
            user={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "role": current_user.get("role") or "user",
            },
            url=payload.url,
            capabilities=[{"protocol": detection.protocol, "capability_id": created.capability_id}],
            name=name,
            permission_level="user",
        )
        if record is not None and getattr(record, "id", None):
            connection_id = str(record.id)
        persisted = True
    except Exception as exc:
        logger.warning(
            "connection durable persistence degraded for %s (%s): %s",
            user_id,
            payload.url,
            exc,
        )

    logger.info(
        "AUDIT connection.registered user=%s capability=%s protocol=%s url=%s persisted=%s",
        user_id,
        created.capability_id,
        detection.protocol,
        payload.url,
        persisted,
    )
    return RegisterResponse(
        connection_id=connection_id,
        capability_id=created.capability_id,
        message=f"{detection.provider_label} is being connected. It will appear in your tools once healthy.",
    )


async def set_execution_mode(payload: SetModeRequest, current_user: dict) -> SetModeResponse:
    """বাংলা: execution-mode self-service — access.py থেকে reuse হয় (duplicate logic নয়)।"""
    from datetime import UTC, datetime

    user_id = str(current_user.get("sub") or current_user.get("uid") or "anonymous")
    persisted = False
    try:
        from database.supabase_client import (
            db,
        )  # local import: avoid hard dependency at import time

        db.upsert(
            "user_execution_mode",
            {"user_id": user_id, "mode": payload.mode, "updated_at": datetime.now(UTC).isoformat()},
        )
        persisted = True
    except Exception as exc:
        logger.warning("execution-mode persistence degraded for %s: %s", user_id, exc)

    logger.info(
        "AUDIT access.set_mode user=%s mode=%s persisted=%s", user_id, payload.mode, persisted
    )
    labels = {
        "read_only": "Read-only mode",
        "ask_before_acting": "Ask before acting",
        "autonomous": "Act autonomously",
    }
    return SetModeResponse(
        user_id=user_id,
        mode=payload.mode,
        persisted=persisted,
        message=f"Execution mode set to {labels[payload.mode]}."
        + ("" if persisted else " (will persist when storage recovers)"),
    )


# বাংলা: NOTE — এই ফাইলের শেষে detect_protocol-এর একটি duplicate definition ছিল
# যা উপরের canonical version-কে shadow করত (dead code + confusion source)।
# Reuse-Before-Creation constitution অনুযায়ী সরানো হয়েছে।
