"""Safe adapters for the chat-centered hub-and-spoke control plane.

Adapters intentionally expose bounded operations. They do not call HTTP routes or
bypass the policy gateway; each spoke can later replace its status handler with a
real task-backed implementation without changing the chat contract.
"""

from __future__ import annotations

from typing import Any

from core.orchestration.conversation_orchestrator import ConversationCommand


async def _status(command: ConversationCommand, spoke: str, message: str) -> dict[str, Any]:
    return {
        "spoke": spoke,
        "status": "connected",
        "message": message,
        "tenant_id": command.tenant_id,
        "project_id": command.project_id,
        "conversation_id": command.conversation_id,
        "capability_chain": command.metadata.get("capability_chain", []),
        "handoff_ready": True,
    }


async def task_handler(command: ConversationCommand) -> dict[str, Any]:
    """Submit a durable, tenant-scoped task through the canonical task engine."""
    from adaptive_engine.task_engine import TaskEngine, TaskOwner, TaskRecord

    record = TaskRecord(
        goal=command.prompt,
        owner=TaskOwner.ADMIN if command.role == "admin" else TaskOwner.USER,
        scope={"project_id": command.project_id, "conversation_id": command.conversation_id},
        correlation={"correlation_id": command.metadata.get("correlation_id")},
        created_by=command.user_id,
        tenant_id=command.tenant_id,
        risk_level="MEDIUM",
    )
    saved = TaskEngine().submit(record)
    return {
        "spoke": "task",
        "status": "queued",
        "task_id": saved.task_id,
        "state": saved.state,
        "tenant_id": command.tenant_id,
        "project_id": command.project_id,
    }


async def realtime_handler(command: ConversationCommand) -> dict[str, Any]:
    """Publish a governed orchestration event for connected realtime clients."""
    from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

    error_event_bus.emit(
        ErrorEvent(
            module="conversation_orchestrator",
            error_type="ORCHESTRATION_EVENT",
            message=command.prompt[:200],
            severity="INFO",
            structured_context=ErrorContext(
                module="conversation_orchestrator", user_id=command.user_id
            ),
            context={"tenant_id": command.tenant_id, "project_id": command.project_id},
        )
    )
    return await _status(command, "realtime", "Event published to the shared event bus.")


async def admin_handler(command: ConversationCommand) -> dict[str, Any]:
    return await _status(
        command, "admin", "Administrative control is connected and requires an admin principal."
    )


async def evolution_handler(command: ConversationCommand) -> dict[str, Any]:
    return await _status(
        command, "evolution", "Evolution services are connected behind an approval boundary."
    )


async def artifact_handler(command: ConversationCommand) -> dict[str, Any]:
    """Create a scoped artifact when chat provides content; otherwise expose handoff."""
    content = command.metadata.get("content")
    if not content:
        return await _status(
            command, "artifact", "Artifact handoff ready; provide content to create an artifact."
        )
    from uuid import uuid4

    from database.supabase_client import SupabaseDB

    row = {
        "id": str(uuid4()),
        "user_id": command.user_id,
        "title": str(command.metadata.get("title") or "Chat artifact")[:256],
        "artifact_type": str(command.metadata.get("artifact_type") or "code"),
        "content": str(content),
        "conversation_id": command.conversation_id,
    }
    response = await SupabaseDB().client.table("artifacts").insert(row).execute()
    if not response.data:
        raise RuntimeError("Artifact persistence returned no record")
    return {
        "spoke": "artifact",
        "status": "created",
        "artifact": response.data[0],
        "tenant_id": command.tenant_id,
        "project_id": command.project_id,
    }


async def external_handler(command: ConversationCommand) -> dict[str, Any]:
    return await _status(
        command, "external", "External tools are connected through governed capability dispatch."
    )


async def research_handler(command: ConversationCommand) -> dict[str, Any]:
    """Governed scout research — Phase 1 "Scout goes live" (orchestrator spoke).

    বাংলা: conversation orchestrator-এর মাধ্যমে agent-রা এখন governed scout crawl
    চালাতে পারে। Policy-gateway-রuled risk="medium"; crawl সবসময় টেন্যান্টের
    সক্রিয় CrawlPolicy মেনে হয় (robots.txt, rate pacing, SSRF gate) — policy
    না থাকলে fail-closed উত্তর।
    """
    tenant_id = str(command.tenant_id or "").strip()
    if not tenant_id:
        return {
            "spoke": "research",
            "status": "unavailable",
            "message": "An authenticated tenant_id is required for governed scout crawl.",
            "tenant_id": None,
            "project_id": command.project_id,
        }

    from scout.persistence import get_active_policy

    policy = await get_active_policy(tenant_id)
    if policy is None:
        return {
            "spoke": "research",
            "status": "unavailable",
            "message": "No active crawl policy for tenant; scout is fail-closed.",
            "tenant_id": tenant_id,
            "project_id": command.project_id,
        }
    url = str(command.metadata.get("url") or "").strip()
    if not url:
        return {
            "spoke": "research",
            "status": "invalid",
            "message": "metadata['url'] is required for governed scout crawl.",
            "tenant_id": tenant_id,
            "project_id": command.project_id,
        }
    from scout.crawler import CrawlerService
    from scout.models import CrawlRequest
    from scout.persistence import record_crawl_response

    service = CrawlerService(policy=policy)
    response = await service.execute_crawl(
        CrawlRequest(query_or_url=url, tenant_id=str(tenant_id), max_depth=1)
    )
    await record_crawl_response(response)
    return {
        "spoke": "research",
        "status": "crawled",
        "task_id": response.task_id,
        "pages": response.total_fetched,
        "duplicates_skipped": response.total_duplicates_skipped,
        "summary": (response.extractive_summary or "")[:500],
        "tenant_id": tenant_id,
        "project_id": command.project_id,
    }


__all__ = [
    "admin_handler",
    "artifact_handler",
    "evolution_handler",
    "external_handler",
    "realtime_handler",
    "research_handler",
    "task_handler",
]
