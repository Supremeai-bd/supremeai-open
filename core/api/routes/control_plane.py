"""Versioned control-plane discovery and server-side service probes."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timezone

import httpx
from fastapi import APIRouter, Depends

from api.dependencies import get_current_user_token
from core.service_registry import (
    SERVICE_REGISTRY,
    public_capabilities,
    public_registry,
    service_url,
)

router = APIRouter(prefix="/api/v1/control-plane", tags=["control-plane"])


@router.get("/registry")
async def registry(_: str = Depends(get_current_user_token)) -> dict:
    return {
        "version": "v1",
        "timestamp": datetime.now(UTC),
        "services": public_registry(),
        "capabilities": public_capabilities(),
    }


@router.get("/health")
async def health(_: str = Depends(get_current_user_token)) -> dict:
    async def probe(service):
        base_url = service_url(service)
        if not base_url:
            return {
                **service.public_dict(),
                "status": "unconfigured",
                "latency_ms": None,
                "checked_at": datetime.now(UTC),
            }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}{service.health_path}")
            status = "healthy" if response.status_code < 400 else "unhealthy"
            return {
                **service.public_dict(),
                "status": status,
                "status_code": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "checked_at": datetime.now(UTC),
            }
        except httpx.TimeoutException:
            return {
                **service.public_dict(),
                "status": "timeout",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "checked_at": datetime.now(UTC),
            }
        except Exception as exc:
            return {
                **service.public_dict(),
                "status": "unreachable",
                "error": str(exc)[:160],
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "checked_at": datetime.now(UTC),
            }

    services = [await probe(service) for service in SERVICE_REGISTRY]
    critical = [service for service in services if service["critical"]]
    overall = (
        "healthy" if all(service["status"] == "healthy" for service in critical) else "degraded"
    )
    return {
        "version": "v1",
        "timestamp": datetime.now(UTC),
        "overall_status": overall,
        "services": services,
    }
