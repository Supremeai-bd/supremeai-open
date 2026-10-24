"""
Unified Memory Interface

This module provides a single point of access for all memory-related operations
within SupremeAI, abstracting the underlying implementations:
- Long-term memory (Eternal Brain): CascadeMemoryService
- Short-term memory (Context Window): SlidingWindowMemory
- Task state persistence: CheckpointManager

PLAN-004 (Letta-style write-time distillation): the long-term write path gains
an opt-in distilled variant that produces a dense summary + structured facts
via the existing zero-cost LLM gateway chain, instead of the legacy raw 200-char
truncation. On any distiller failure the write falls back to the legacy
behavior — memory is never lost, only less dense (Constitution #8/#13).
"""

import json
import os
import re
from typing import Any

from core.logging_config import logger
from memory.sliding_window import SlidingWindowMemory

# Import the underlying services
from services.memory_service import CascadeMemoryService
from services.memory_service import memory_service as global_memory_service
from tools.checkpoint_manager import (
    CheckpointManager,
)
from tools.checkpoint_manager import (
    checkpoint_manager as global_checkpoint_manager,
)

# PLAN-004 runtime kill-switch: SUPREMEAI_MEMORY_DISTILL=false forces the
# distilled variant to delegate straight to legacy truncation. Read at call
# time (not import time) so tests and ops can toggle it live.
MEMORY_DISTILL_ENV = "SUPREMEAI_MEMORY_DISTILL"


def _memory_distill_enabled() -> bool:
    return os.getenv(MEMORY_DISTILL_ENV, "true").lower() != "false"


# PLAN-004: distillation only pays off for substantial payloads; shorter
# content is stored verbatim via the legacy path (cost guard).
MEMORY_DISTILL_MIN_CONTENT_CHARS = 400

MEMORY_DISTILL_SYSTEM_PROMPT = (
    "You are SupremeAI's memory distiller (Letta/MemGPT-style write-time block builder). "
    "From the raw content, produce: (1) a dense summary <=180 tokens preserving durable "
    "facts, decisions, preferences, entity names, paths/commands, unresolved issues; "
    '(2) a JSON object {"facts": [...], "preferences": [...], "entities": [...], '
    '"open_items": [...]} (empty arrays allowed; NO prose outside JSON).'
)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Tolerant JSON extractor — returns the first {...} object, or None.

    বাংলা: LLM আউটপুট থেকে প্রথম JSON অবজেক্ট বের করে; ব্যর্থ হলে None —
    কোনো exception কলারে ছড়ায় না (#13 সৎ ব্যর্থতা, প্রমাণিত টলারেন্স)।
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


async def distill_content(content: str) -> tuple[str, dict[str, Any] | None]:
    """Distill raw content into (dense_summary, structure_dict).

    বাংলা: বিদ্যমান zero-cost LLM gateway chain-এ পাঠিয়ে (summary, structure)
    রিটার্ন করে। যেকোনো ব্যর্থতায় ("", None) রিটার্ন করে — কলার legacy পথে
    নামবে; এখান থেকে কখনো exception বের হয় না।
    """
    try:
        from core.llm.llm_gateway import llm_gateway  # established lazy singleton pattern

        result = await llm_gateway.acompletion(
            prompt=[
                {"role": "system", "content": MEMORY_DISTILL_SYSTEM_PROMPT},
                {"role": "user", "content": content[:8000]},
            ],
            task_type="summarization",
        )
        # Non-stream acompletion contract (locked on implementation PR):
        # {"success": True, "text": <str>, "model": ..., "cost": ...}
        if isinstance(result, dict):
            text = result.get("text") or ""
        else:
            text = str(result) if result else ""
        if not text.strip():
            logger.warning("memory distillation returned empty text; caller will fall back")
            return "", None
        dense_summary = " ".join(text.split())[:1200]
        return dense_summary, _extract_json_object(text)
    except Exception as exc:  # never escape — caller falls back to legacy truncation
        logger.warning(f"memory distillation failed ({exc}); caller will use legacy fallback")
        return "", None


class UnifiedMemoryInterface:
    """
    A facade providing a unified API for interacting with different memory systems.
    """

    def __init__(self):
        self.long_term_memory = global_memory_service
        self.short_term_memory = SlidingWindowMemory()
        self.checkpoint_manager = global_checkpoint_manager

    # --- Long-term Memory (Eternal Brain) ---
    def store_long_term_memory(
        self,
        session_id: str,
        agent_type: str,
        task_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Store information in the long-term 'Eternal Brain' memory.

        AUD-5.1: ``user_id`` binds the memory to its owner so retrieval can be
        tenant-scoped. Callers MUST supply the authenticated user id.
        """
        try:
            # Parse content and extract summary/structure using the service's built-in logic
            # This might need adjustment based on how content is passed
            # For now, assuming it's called from an agent context where summary is pre-made
            summary = content[:200]  # Placeholder
            structure = "{}"  # Placeholder
            self.long_term_memory.store_memory(
                file_path=session_id,  # Map session_id to file_path for now
                content=content,
                summary=summary,
                structure=structure,
                session_id=session_id,
                agent_type=agent_type,
                task_type=task_type,
                metadata=metadata or {},
                user_id=user_id,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to store long-term memory: {e}")
            return False

    def _store_long_term_with_summary(
        self,
        *,
        session_id: str,
        agent_type: str,
        task_type: str,
        content: str,
        summary: str,
        structure: str,
        metadata: dict[str, Any] | None,
        user_id: str | None,
    ) -> bool:
        """PLAN-004 helper: legacy write path with an explicit summary override.

        বাংলা: distilled summary-টি সরাসরি CascadeMemoryService.store_memory-তে
        যায় (public store_long_term_memory-র সিগনেচার অপরিবর্তিত থাকে — ৩টি
        বিদ্যমান কলার ভাঙে না)। embedding সেই summary থেকেই তৈরি হয়।
        """
        try:
            self.long_term_memory.store_memory(
                file_path=session_id,
                content=content,
                summary=summary,
                structure=structure,
                session_id=session_id,
                agent_type=agent_type,
                task_type=task_type,
                metadata=metadata or {},
                user_id=user_id,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to store distilled long-term memory: {e}")
            return False

    async def store_long_term_memory_distilled(
        self,
        *,
        session_id: str,
        agent_type: str,
        task_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> bool:
        """PLAN-004: Letta-style write-time distillation on the Eternal Brain path.

        বাংলা: ব্যর্থ হলে হৃদয়ংকুপিত fallback — ঠিক আজকের মতো legacy truncation
        লেখা হয়; memory কখনো হারায় না, শুধু ঘনত্ব কমে (#8/#13)। সফল হলে
        metadata-তে ``distilled: true`` ও (পারলে) ``memory_structure`` যায় —
        বিদ্যমান JSON কলামে, শূন্য schema change।
        """
        summary: str | None = None
        structure: dict[str, Any] | None = None
        if (
            _memory_distill_enabled()
            and content
            and len(content) > MEMORY_DISTILL_MIN_CONTENT_CHARS
        ):
            summary, structure = await distill_content(content)
        if summary:
            enriched = dict(metadata or {})
            if structure:
                enriched["memory_structure"] = structure
            enriched["distilled"] = True
            return self._store_long_term_with_summary(
                session_id=session_id,
                agent_type=agent_type,
                task_type=task_type,
                content=content,
                summary=summary,
                structure=json.dumps(structure) if structure else "{}",
                metadata=enriched,
                user_id=user_id,
            )
        # Legacy path — exactly today's behavior (structure stays "{}").
        return self.store_long_term_memory(
            session_id=session_id,
            agent_type=agent_type,
            task_type=task_type,
            content=content,
            metadata=metadata,
            user_id=user_id,
        )

    def query_long_term_memory(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query the long-term 'Eternal Brain' memory.

        AUD-5.1: when ``user_id`` is supplied, results are restricted to that
        user's memories (no cross-tenant recall).
        """
        try:
            return self.long_term_memory.query_context(
                prompt=query, top_k=top_k, session_id=session_id, user_id=user_id
            )
        except Exception as e:
            logger.error(f"Failed to query long-term memory: {e}")
            return []

    # --- Short-term Memory (Context Window) ---
    def store_short_term_memory(self, session_id: str, text: str) -> bool:
        """Store information in the short-term conversation context."""
        try:
            self.short_term_memory.chunk(text=text, session_id=session_id)
            return True
        except Exception as e:
            logger.error(f"Failed to store short-term memory: {e}")
            return False

    def get_short_term_memory(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve information from the short-term conversation context."""
        try:
            return self.short_term_memory.recall(session_id=session_id, limit=limit)
        except Exception as e:
            logger.error(f"Failed to retrieve short-term memory: {e}")
            return []

    # --- Task Checkpointing ---
    def save_checkpoint(self, task_id: str, step_index: int, state: dict[str, Any]) -> bool:
        """Save the current state of a task."""
        try:
            return self.checkpoint_manager.save(task_id=task_id, step_index=step_index, state=state)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

    def load_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        """Load the state of a task."""
        try:
            cp_obj = self.checkpoint_manager.load(task_id=task_id)
            if cp_obj:
                return {
                    "task_id": cp_obj.task_id,
                    "step_index": cp_obj.step_index,
                    "state": cp_obj.state,
                    "resumed": cp_obj.resumed,
                }
            return None
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None


# Global instance (singleton pattern)
unified_memory = UnifiedMemoryInterface()
