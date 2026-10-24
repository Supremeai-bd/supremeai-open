"""Stable public contract for the Knowledge bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class KnowledgeRequest:
    question: str
    tenant_id: str
    actor_id: str
    role: str
    limit: int = 3


class KnowledgeCapability(Protocol):
    async def ask(self, request: KnowledgeRequest) -> dict[str, Any]: ...


class KnowledgeContractError(ValueError):
    """Raised when a caller does not provide the required security context."""


def request_from_user(question: str, user: dict[str, Any], limit: int = 3) -> KnowledgeRequest:
    tenant_id = str(user.get("tenant_id") or user.get("sub") or "")
    actor_id = str(user.get("sub") or "")
    role = str(user.get("role") or "").lower()
    if not tenant_id or not actor_id or not role:
        raise KnowledgeContractError("tenant, actor, and role context are required")
    return KnowledgeRequest(
        question=question,
        tenant_id=tenant_id,
        actor_id=actor_id,
        role=role,
        limit=max(1, min(limit, 5)),
    )
