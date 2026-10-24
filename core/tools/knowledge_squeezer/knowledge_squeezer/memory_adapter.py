from __future__ import annotations

from typing import Any

from .models import KnowledgeArtifact


def build_memory_payload(artifact: KnowledgeArtifact) -> dict[str, Any]:
    """Adapter payload for SupremeAI's existing long-term memory API/service."""
    return {
        "session_id": f"knowledge:{artifact.artifact_id}",
        "agent_type": "KnowledgeSqueezer",
        "task_type": "knowledge_distillation",
        "content": artifact.stable_text(),
        "metadata": {
            "artifact_id": artifact.artifact_id,
            "domain": artifact.domain,
            "confidence": artifact.confidence,
            "verification_status": artifact.verification_status,
            "tags": artifact.tags,
            "source_count": len(artifact.provenance),
        },
    }


async def write_via_unified_memory(
    artifact: KnowledgeArtifact,
    memory_service: Any,
) -> bool:
    payload = build_memory_payload(artifact)
    result = memory_service.store_long_term_memory(**payload)
    if hasattr(result, "__await__"):
        result = await result
    return bool(result)
