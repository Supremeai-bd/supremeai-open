"""Governed chat-centered hub-and-spoke orchestration runtime."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from core.automation.execution_recorder import execution_recorder
from core.automation.models import ExecutionEnvelope
from core.logging_config import logger
from core.security.tool_gateway import ToolPolicyGateway, tool_policy_gateway


@dataclass(frozen=True)
class ConversationCommand:
    prompt: str
    user_id: str
    tenant_id: str
    role: str = "user"
    project_id: str | None = None
    conversation_id: str | None = None
    confirmation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    """Canonical, serializable truth record for one governed dispatch."""

    execution_id: str
    correlation_id: str
    user_id: str
    tenant_id: str
    project_id: str | None
    conversation_id: str | None
    capability: str
    status: str = "started"
    evidence: list[dict[str, Any]] = field(default_factory=list)
    envelope: ExecutionEnvelope | None = None


@dataclass
class OrchestrationResult:
    correlation_id: str
    status: str
    capability: str
    response: Any = None
    requires_confirmation: bool = False
    task_id: str | None = None
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    execution: ExecutionRecord | None = None


@dataclass(frozen=True)
class Capability:
    name: str
    risk: str
    handler: Callable[[ConversationCommand], Awaitable[Any]]
    admin_only: bool = False
    destructive: bool = False
    # A registered handler is not automatically proof of a live dependency.
    availability: str = "connected"
    description: str = ""

    @property
    def is_available(self) -> bool:
        return self.availability == "connected"


class ConversationOrchestrator:
    """Single governed dispatch point; unknown capabilities fail closed."""

    def __init__(self, policy: ToolPolicyGateway | None = None) -> None:
        self.policy = policy or tool_policy_gateway
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability
        self.policy.register_tool(capability.name, capability.risk)

    def capabilities(self) -> list[dict[str, str | bool]]:
        return [
            {
                "name": c.name,
                "risk": c.risk,
                "availability": c.availability,
                "connected": c.is_available,
                "admin_only": c.admin_only,
                "destructive": c.destructive,
                "description": c.description,
            }
            for c in self._capabilities.values()
        ]

    @staticmethod
    def classify(prompt: str) -> str:
        text = prompt.lower()
        if any(word in text for word in ("browser", "website", "navigate", "url")):
            return "browser"
        if any(word in text for word in ("memory", "remember", "knowledge")):
            return "memory"
        if any(word in text for word in ("task", "job", "run this", "queue")):
            return "task"
        if any(word in text for word in ("realtime", "live update", "event", "stream")):
            return "realtime"
        if any(word in text for word in ("file", "artifact", "document")):
            return "artifact"
        if any(word in text for word in ("evolution", "improve yourself", "self improve")):
            return "evolution"
        if any(word in text for word in ("admin", "system setting", "user management")):
            return "admin"
        if any(word in text for word in ("external tool", "integration", "mcp", "send to")):
            return "external"
        return "chat"

    async def dispatch(self, command: ConversationCommand) -> OrchestrationResult:
        """Governed dispatch entry point.

        Delegates to the inner dispatch logic and then persists the canonical
        ExecutionRecord durably (best-effort). DB unavailability never blocks
        the dispatch — persistence is fire-and-forget with graceful degradation.

        বাংলা (M06 P-A): ডিসপ্যাচটি এখন ক্যানোনিকাল run হিসেবেও পর্যবেক্ষিত —
        ``runs.run_scope.run_scope`` (flag-gated: SUPREMEAI_RUN_FABRIC_UNIVERSAL,
        default OFF = আজকের আচরণ)। run-fabric ব্যর্থতা ডিসপ্যাচ কখনো ব্লক করে না।
        """
        result = await self._observe_dispatch(command)
        if result.execution is not None:
            # Durable truth record bridge (Board TODO: "Persist ExecutionRecord
            # durably"). ExecutionRecorder swallows DB errors and continues.
            await execution_recorder.persist_execution(result.execution)
        return result

    async def _observe_dispatch(self, command: ConversationCommand) -> OrchestrationResult:
        """Wrap one dispatch in a canonical run (M06 P-A, best-effort, flag-gated)."""
        try:
            from database.session import get_db_session_context
            from runs.run_scope import run_scope
            from runs.service import RunService
        except Exception as exc:
            # বাংলা: import-স্তরের অনুপস্থিতিও লাউড warning — নীরব ভান নয়।
            logger.warning(f"⚠️ run-scope unavailable, dispatching unobserved: {exc!r}")
            return await self._dispatch(command)

        try:
            async with get_db_session_context() as session:
                async with run_scope(
                    session,
                    RunService(),
                    run_type="agent",
                    user_id=str(command.user_id or "system"),
                    title=f"conversation:{command.conversation_id}",
                    source_type="conversation",
                    source_ref=str(command.conversation_id) if command.conversation_id else None,
                    correlation_id=str(command.metadata.get("correlation_id") or ""),
                ) as run_ctx:
                    result = await self._dispatch(command)
                    if run_ctx is not None:
                        # OrchestrationResult.status-ই সত্য — failed হলে run-ও failed।
                        run_ctx.finish("failed" if str(result.status) == "failed" else "succeeded")
                return result
        except Exception as exc:
            # বাংলা: session/run_scope নিজস্ব ব্যর্থতা কখনো ডিসপ্যাচ ব্লক করবে না।
            logger.warning(f"⚠️ run-scope dispatch-bridge skipped: {exc!r} — dispatch unaffected")
            return await self._dispatch(command)

    async def _dispatch(self, command: ConversationCommand) -> OrchestrationResult:
        correlation_id = str(command.metadata.get("correlation_id") or f"corr_{uuid.uuid4().hex}")
        capability_name = str(command.metadata.get("capability") or self.classify(command.prompt))
        chain = list(command.metadata.get("capability_chain", []))
        if capability_name in chain or len(chain) >= 5:
            return OrchestrationResult(
                correlation_id,
                "failed",
                capability_name,
                error="Capability delegation loop or depth limit",
                events=[{"type": "orchestration.rejected", "correlation_id": correlation_id}],
            )
        command = replace(
            command, metadata={**command.metadata, "capability_chain": [*chain, capability_name]}
        )
        execution_id = f"exec_{uuid.uuid4().hex}"
        execution = ExecutionRecord(
            execution_id=execution_id,
            correlation_id=correlation_id,
            user_id=command.user_id,
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            conversation_id=command.conversation_id,
            capability=capability_name,
            envelope=ExecutionEnvelope(
                execution_id=f"exec_{uuid.uuid4().hex}",
                actor_id=command.user_id,
                tenant_id=command.tenant_id,
                intent=command.prompt[:500],
                trace_id=correlation_id,
            ),
        )
        capability = self._capabilities.get(capability_name)
        event = {
            "type": "orchestration.started",
            "correlation_id": correlation_id,
            "conversation_id": command.conversation_id,
            "tenant_id": command.tenant_id,
            "project_id": command.project_id,
            "user_id": command.user_id,
            "capability": capability_name,
        }
        if not capability or not capability.is_available:
            event.update(type="orchestration.unavailable", status="unavailable")
            execution.status = "unavailable"
            execution.evidence.append(event)
            return OrchestrationResult(
                correlation_id,
                "failed",
                capability_name,
                error="Capability unavailable",
                events=[event],
                execution=execution,
            )
        if capability.admin_only and command.role != "admin":
            event.update(type="orchestration.denied", status="denied", reason="admin_required")
            execution.status = "denied"
            execution.evidence.append(event)
            return OrchestrationResult(
                correlation_id,
                "denied",
                capability_name,
                error="Admin permission required",
                events=[event],
                execution=execution,
            )
        if capability.destructive and not command.confirmation:
            event.update(
                type="orchestration.approval_required",
                status="blocked",
                approval_scope=capability.name,
            )
            execution.status = "confirmation_required"
            execution.evidence.append(event)
            return OrchestrationResult(
                correlation_id,
                "confirmation_required",
                capability_name,
                requires_confirmation=True,
                events=[event],
                execution=execution,
            )
        decision = await self.policy.evaluate(
            capability.name,
            {
                "sub": command.user_id,
                "tenant_id": command.tenant_id,
                "project_id": command.project_id,
                "conversation_id": command.conversation_id,
                "role": command.role,
            },
            risk=capability.risk,
            action="conversation.dispatch",
        )
        if execution.envelope is not None:
            execution.envelope.policy_decision = "allow" if decision.allowed else "deny"
            execution.envelope.status = "running" if decision.allowed else "blocked"
        if not decision.allowed:
            event.update(type="orchestration.denied", status="denied", reason=decision.reason)
            execution.status = "denied"
            execution.evidence.append(event)
            return OrchestrationResult(
                correlation_id,
                "denied",
                capability_name,
                error=decision.reason,
                events=[event],
                execution=execution,
            )
        try:
            handler_command = replace(
                command,
                metadata={**command.metadata, "correlation_id": correlation_id},
            )
            timeout_seconds = float(command.metadata.get("timeout_seconds", 60))
            if timeout_seconds > 300:
                timeout_seconds = 300
            response = await asyncio.wait_for(
                capability.handler(handler_command), timeout=timeout_seconds
            )
            event.update(type="orchestration.completed", status="completed")
            if isinstance(response, dict):
                response = {
                    **response,
                    "correlation_id": correlation_id,
                    "capability": capability_name,
                }
            execution.status = "completed"
            if execution.envelope is not None:
                execution.envelope.status = "succeeded"
            execution.evidence.append(event)
            return OrchestrationResult(
                correlation_id,
                "completed",
                capability_name,
                response=response,
                events=[event],
                execution=execution,
            )
        except TimeoutError:
            event.update(type="orchestration.timed_out", status="failed", retryable=True)
            execution.status = "timed_out"
            execution.evidence.append(event)
            return OrchestrationResult(
                correlation_id,
                "failed",
                capability_name,
                error="Capability execution timed out",
                events=[event],
                execution=execution,
            )
        except Exception:
            event.update(type="orchestration.failed", status="failed", retryable=False)
            execution.status = "failed"
            execution.evidence.append(event)
            return OrchestrationResult(
                correlation_id,
                "failed",
                capability_name,
                error="Capability execution failed",
                events=[event],
                execution=execution,
            )


async def _chat_handler(command: ConversationCommand) -> Any:
    from core.llm.llm_gateway import llm_gateway

    result = await llm_gateway.acompletion(prompt=command.prompt, task_type="chat", stream=False)
    return result.get("text", "") if isinstance(result, dict) else str(result)


async def _memory_handler(command: ConversationCommand) -> Any:
    from services.memory_service import recall_memories

    return await recall_memories(
        task_description=command.prompt, limit=3, threshold=0.55, user_id=command.user_id
    )


_orchestrator: ConversationOrchestrator | None = None


async def _browser_handler(command: ConversationCommand) -> Any:
    """Browser spoke: create or reuse an owner-scoped session and navigate."""
    from core.browser_session_manager import session_manager

    session_id = command.metadata.get("session_id")
    url = command.metadata.get("url")
    if not url:
        return {
            "status": "ready",
            "message": "Browser capability connected; provide a URL to navigate.",
        }
    from core.security import is_safe_url

    if not is_safe_url(str(url)):
        raise ValueError("Unsafe URL")
    session = (
        await session_manager.get(session_id, command.user_id)
        if session_id
        else await session_manager.create(command.user_id)
    )
    await session.page.goto(str(url), wait_until="domcontentloaded")
    return {"session_id": session.id, "status": "navigated", "url": session.page.url}


def get_conversation_orchestrator() -> ConversationOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ConversationOrchestrator()
        _orchestrator.register(
            Capability("chat", "low", _chat_handler, description="LLM response generation")
        )
        _orchestrator.register(
            Capability("memory", "low", _memory_handler, description="Tenant-scoped memory recall")
        )
        _orchestrator.register(
            Capability(
                "browser", "medium", _browser_handler, description="Owner-scoped browser navigation"
            )
        )
        from core.orchestration.capability_adapters import (
            admin_handler,
            artifact_handler,
            evolution_handler,
            external_handler,
            realtime_handler,
            research_handler,
            task_handler,
        )

        _orchestrator.register(
            Capability("task", "medium", task_handler, description="Durable task submission")
        )
        _orchestrator.register(
            Capability(
                "research",
                "medium",
                research_handler,
                description="Governed scout crawl (policy-gated, tenant-scoped)",
            )
        )
        _orchestrator.register(
            Capability("realtime", "low", realtime_handler, description="Shared event publication")
        )
        _orchestrator.register(
            Capability(
                "artifact", "medium", artifact_handler, description="Scoped artifact handoff"
            )
        )
        _orchestrator.register(
            Capability(
                "external",
                "high",
                external_handler,
                admin_only=True,
                description="Governed external tools",
            )
        )
        _orchestrator.register(
            Capability(
                "admin",
                "high",
                admin_handler,
                admin_only=True,
                description="Privileged administration",
            )
        )
        _orchestrator.register(
            Capability(
                "evolution",
                "high",
                evolution_handler,
                admin_only=True,
                destructive=True,
                description="Approved evolution workflow",
            )
        )
    return _orchestrator


__all__ = [
    "Capability",
    "ConversationCommand",
    "ConversationOrchestrator",
    "ExecutionRecord",
    "OrchestrationResult",
    "get_conversation_orchestrator",
]
