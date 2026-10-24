"""Dynamic-AI interaction-learning component (canonical, post-#2259 D1).

বাংলা: UnifiedLearningEngine (core/unified_learning.py, PATCH-05 layer) retired —
এই মডিউল এখন সরাসরি canonical দোকানগুলো ব্যবহার করে:
  * interaction telemetry → ``core.learning.store.LearningStore`` (durable,
    privacy-safe, buffered PostgREST pipeline)
  * provider ranking → registry order (unchanged; a real learned ranking
    model is future work — see #2259 D2 collective experience layer)

Orchestrator contract (guards regression 0f4482b6, see
tests/services/dynamic_ai/test_learning_engine_shim.py — DO NOT break):
  * ``LearningEngine(storage_path=...)`` must accept + ignore constructor args
  * ``load_learning_data()``  — async, no-op, never raises
  * ``detect_task_type(str)`` — pure keyword classifier, returns TaskType-value strings
  * ``get_best_providers_for_task(...)`` — async, list[tuple[str, float]]
  * ``record_interaction(...)`` — sync, fire-and-forget, NEVER raises
"""

from __future__ import annotations

from core.learning import get_learning_store
from core.logging_config import logger

# বাংলা মন্তব্য (ROOT-CAUSE FIX 2): কীওয়ার্ড-ভিত্তিক হালকা task detector।
# এখানে `.orchestrator` মডিউলের `TaskType`-কে import করা যাবে না (circular
# import: orchestrator.py -> .learning_engine -> orchestrator.py)। তাই এখানে
# শুধু ম্যাচিং স্ট্রিং ভ্যালু রিটার্ন করা হয় (orchestrator.TaskType একটি
# StrEnum, তাই এই প্লেইন স্ট্রিং-গুলোর সাথে `==`/dict-lookup স্বাভাবিকভাবেই
# কাজ করবে)।
_TASK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "code_generation": ("code", "function", "python", "javascript", "script", "implement"),
    "code_review": ("review", "refactor", "bug", "debug", "fix"),
    "reasoning": ("why", "explain", "analyze", "reason", "prove", "calculate"),
    "creative_writing": ("story", "poem", "write a", "creative", "essay"),
    "summarization": ("summarize", "summary", "tl;dr", "shorten"),
}


class LearningEngine:
    def __init__(self, *_args, **_kwargs):
        # বাংলা মন্তব্য: caller (orchestrator.py) এখনো পুরনো
        # `LearningEngine(storage_path=...)` সিগনেচার দিয়ে কল করে — backward
        # compatibility রাখতে *args/**kwargs নিয়ে ignore করা হলো।
        pass

    # ------------------------------------------------------------------
    # বাংলা মন্তব্য (ROOT-CAUSE FIX 2): নিচের মেথডগুলো `orchestrator.py`-এর
    # `DynamicAIOrchestrator` কল করে (`load_learning_data`,
    # `detect_task_type`, `get_best_providers_for_task`,
    # `record_interaction`)। যেহেতু `LLMRouter.route()` (প্রোডাকশনের মূল
    # non-streaming এন্ট্রি পয়েন্ট) সরাসরি `get_ai_orchestrator().generate()`
    # কল করে, এই মেথডগুলোর signature/behavior ভাঙা যাবে না।
    # ------------------------------------------------------------------

    async def load_learning_data(self) -> None:
        """No-op: the canonical LearningStore owns its own lifecycle
        (started by app lifespan via core.startup.agents)."""
        return None

    def detect_task_type(self, prompt: str) -> str:
        """Lightweight keyword-based task classifier (see _TASK_KEYWORDS)."""
        lowered = (prompt or "").lower()
        for task_type, keywords in _TASK_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return task_type
        return "general"

    async def get_best_providers_for_task(
        self, prompt: str, available_providers: list, context: dict | None = None
    ) -> list[tuple[str, float]]:
        """Rank available providers for this task.

        No historical-performance model is wired up yet, so this falls back
        to registry order with a flat confidence score — callers only need
        a `(provider_id, confidence_score)` list and iterate in order, so
        this is a safe, non-crashing default rather than true learned
        ranking. (Unchanged from the pre-retirement behavior.)
        """
        return [
            (getattr(p, "provider_id", p), 1.0) if not isinstance(p, str) else (p, 1.0)
            for p in available_providers
        ]

    def record_interaction(
        self,
        provider_id: str,
        task_type: str,
        success: bool,
        latency_ms: float = 0.0,
        estimated_cost: float = 0.0,
    ) -> None:
        """Fire-and-forget interaction telemetry via the canonical LearningStore.

        বাংলা (#2259 D1): আগে এটি in-memory UnifiedLearningEngine-এ যেত;
        এখন সরাসরি durable LearningStore-এ যায় (privacy-safe, buffered
        PostgREST write)। ``record_event`` শুধু enqueue করে — কখনো network
        touch বা raise করে না, তাই synchronous call-site-ও নিরাপদ।
        """
        try:
            get_learning_store().record_llm_event(
                provider=str(provider_id),
                model=None,
                task_type=str(task_type),
                success=bool(success),
                latency_ms=int(latency_ms) if latency_ms else None,
                estimated_cost=float(estimated_cost) if estimated_cost else None,
                metadata={"source": "dynamic_ai.interaction"},
            )
        except Exception as e:  # pragma: no cover — record_event never raises by design
            logger.warning(f"record_interaction telemetry enqueue failed (silenced): {e}")
