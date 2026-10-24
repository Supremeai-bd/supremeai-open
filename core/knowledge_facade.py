"""Public facade and compatibility adapter for Knowledge capabilities."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from core.knowledge_contract import KnowledgeRequest
from services.knowledge_qa import KnowledgeQAService


class KnowledgeFacade:
    """The only public application entrypoint for tenant-scoped Knowledge Q&A."""

    def __init__(self, service: KnowledgeQAService | None = None) -> None:
        self._service = service or KnowledgeQAService()

    async def ask(self, request: KnowledgeRequest) -> dict[str, Any]:
        user = {
            "tenant_id": request.tenant_id,
            "sub": request.actor_id,
            "role": request.role,
        }
        return await self._service.answer(request.question, user, request.limit)


async def ask_legacy(
    question: str, user: dict[str, Any], limit: int = 3, facade: KnowledgeFacade | None = None
) -> dict[str, Any]:
    """Anti-corruption adapter preserving the legacy route response contract."""
    from core.knowledge_contract import KnowledgeContractError, request_from_user

    try:
        request = request_from_user(question, user, limit)
    except KnowledgeContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return await (facade or KnowledgeFacade()).ask(request)
