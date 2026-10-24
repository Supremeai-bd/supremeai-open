"""Implements a dynamic, vector-based semantic cache for AI model responses.

This module provides the `SemanticCache` class, which leverages an `ExperienceDatabase`
(e.g., ChromaDB/Qdrant) as its vector backend. It stores and retrieves AI responses
based on semantic similarity to input prompts, aiming to reduce redundant model calls.
A key feature is its database-driven, dynamically configurable cache threshold,
which adapts based on the task type and can be adjusted by administrators
without requiring redeployment."""

# Vector Semantic Cache Engine for SupremeAI 2.0
# বাংলা মন্তব্য: এটি ফায়ারস্টোর বাদ দিয়ে সরাসরি experience_db.py (ChromaDB/Qdrant) ব্যবহার করে এবং ডাইনামিক থ্রেশহোল্ড সেট করে।
from typing import Any

from adaptive_engine.experience_db import Experience, ExperienceDatabase
from core.config_cache import config_cache
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

# বাংলা মন্তব্য: ক্যাশ পলিসি — এখন প্রকৃত অর্থে Database-Driven!
# get_cache_threshold() ConfigCache থেকে value নেয়, যা SystemConfig DB টেবিলে persist করে।
# Admin চাইলে Admin Dashboard বা API কলের মাধ্যমে threshold পরিবর্তন করতে পারে —
# কোন re-deploy লাগবে না। ConfigCache TTL (৬০ সেকেন্ড) পর্যন্ত in-memory serve করে,
# তারপর DB থেকে reload করে।


def get_cache_threshold(task_type: str) -> float:
    """
    task_type অনুযায়ী ক্যাশ থ্রেশহোল্ড রিটার্ন করে — **DB-Driven**।

    ConfigCache SystemConfig টেবিল থেকে কনফিগ লোড করে:
      - cache_threshold_code = 0.95
      - cache_threshold_general = 0.85
      - cache_threshold_reasoning = 0.80
      - ইত্যাদি

    Admin চাইলে Dashboard থেকে এগুলো পরিবর্তন করতে পারে — re-deploy ছাড়াই।
    TTL-এর মধ্যে in-memory ক্যাশ serve হবে, প্রতি request-এ DB hit হবে না।
    """
    task_lower = task_type.lower()

    # Try ConfigCache first (DB-driven)
    cached_default = config_cache.get(f"cache_threshold_{task_lower}")
    if cached_default is not None:
        return float(cached_default)

    # Fallback: check if any key prefix matches
    all_thresholds = config_cache.get_all("cache_threshold_")
    for key, threshold in all_thresholds.items():
        config_task = key.replace("cache_threshold_", "")
        if config_task in task_lower:
            return float(threshold)

    # Ultimate fallback
    return 0.85


class CacheEntry:
    def __init__(self, provider: str, model: str, response: str):
        self.provider = provider
        self.model = model
        self.response = response


class SemanticCache:
    def __init__(self):
        # Initialize Experience Database as the vector backend
        self.db = ExperienceDatabase()
        logger.info("SemanticCache initialized using ExperienceDatabase vector backend")

    @with_error_bus("query_similar")
    async def query_similar(
        self, prompt: str, task_type: str = "general", user_id: str | None = None
    ) -> CacheEntry | None:
        try:
            # বাংলা মন্তব্য: কাজের ধরণের ওপর ভিত্তি করে ডাইনামিক থ্রেশহোল্ড সেট করা হচ্ছে
            threshold = get_cache_threshold(task_type)

            hits = self.db.find_similar(prompt, limit=10, threshold=threshold, user_id=user_id)

            if hits:
                best_hit = hits[0]
                logger.info(
                    f"⚡ [SEMANTIC CACHE HIT] Task: {task_type} | User: {user_id} | Score: {best_hit['score']:.4f} | Source: {best_hit['source']}"
                )
                return CacheEntry(
                    provider=best_hit.get("source", "chroma"),
                    model="cached_semantic",
                    response=best_hit.get("response", ""),
                )
            return None
        except Exception as e:
            logger.error(f"⚠️ SemanticCache lookup failed: {e}")
            error_event_bus.emit(
                ErrorEvent(
                    module="semantic_cache",
                    error_type="CACHE_LOOKUP_FAILURE",
                    message=f"SemanticCache lookup failed: {e}",
                    severity="WARNING",
                    structured_context=ErrorContext(module="semantic_cache", env="production"),
                    context={
                        "task_type": task_type,
                        "prompt_preview": prompt[:100] if prompt else "",
                    },
                )
            )
            return None

    async def get(
        self, prompt: str, task_type: str = "general", user_id: str | None = None
    ) -> Any | None:
        """Convenience getter returning response string or object if hit."""
        entry = await self.query_similar(prompt, task_type=task_type, user_id=user_id)
        if entry:
            return entry.response
        return None

    @with_error_bus("set")
    async def set(
        self,
        prompt: str,
        response: Any,
        task_type: str = "general",
        ttl: int | None = None,
        user_id: str | None = None,
    ) -> None:
        try:
            # বাংলা মন্তব্য: সফল ও ভেরিফাইড কোড/রেসপন্স এক্সপেরিয়েন্স ডেটাবেসে রাইট করা হচ্ছে
            resp_str = str(response) if not isinstance(response, str) else response
            exp = Experience(
                user_id=user_id or "",
                request=prompt,
                generated_code=resp_str if "code" in task_type.lower() else None,
                action_taken=(resp_str if "code" not in task_type.lower() else "Code Generated"),
                result="success",
            )
            self.db.record_experience(exp)
            logger.info(f"💾 Successfully recorded successful experience pattern for {task_type}")
        except Exception as e:
            logger.debug(f"SemanticCache set fallback: {e}")


# Singleton instance
semantic_cache = SemanticCache()
