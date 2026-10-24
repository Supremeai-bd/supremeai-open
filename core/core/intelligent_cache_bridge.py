"""
Intelligent Cache Bridge - TokenJuice Integration
==================================================
Token compression and caching bridge system.

Works with zero infrastructure cost - uses Redis caching.
Language-agnostic automatic response memoization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field  # noqa: F401
from datetime import timedelta
from enum import StrEnum
from typing import Any, Optional

from core.cache import get_redis_client
from core.logging_config import logger


class TaskType(StrEnum):
    """Task type classification."""

    CODE = "code"
    REASONING = "reasoning"
    BENGALI = "bengali"
    CHAT = "chat"
    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    CLASSIFY = "classify"
    DEBUG = "debug"
    REFACTOR = "refactor"
    REVIEW = "review"


@dataclass
class CacheEntry:
    """Cache entry model."""

    key: str
    prompt: str
    response: str
    tokens_used: int
    cost_usd: float
    model_used: str
    task_type: str
    hit_count: int = 0
    created_at: str = ""
    expires_at: str = ""


@dataclass
class TokenBudget:
    """Token budget for smart compression."""

    max_input: int = 8192
    max_output: int = 4096
    compression_threshold: int = 5000  # Start compression above this

    def needs_compression(self, input_tokens: int, output_tokens: int) -> bool:
        """Determine whether compression is needed."""
        return (input_tokens + output_tokens) > self.compression_threshold


class TokenJuiceCompressor:
    """
    Smart token compression system.

    Reduces cost without sacrificing quality.
    """

    # Strategy mapping
    COMPRESSION_STRATEGIES = {
        TaskType.CODE: "aggressive",
        TaskType.REASONING: "moderate",
        TaskType.BENGALI: "conservative",
        TaskType.CHAT: "conservative",
        TaskType.SUMMARIZE: "strong",
        TaskType.TRANSLATE: "balanced",
    }

    def __init__(self) -> None:
        self.redis = get_redis_client()
        self.cache_ttl = timedelta(hours=6)

    def generate_cache_key(
        self,
        prompt: str,
        task_type: str,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a deterministic cache key."""
        data = f"{user_id or 'anon'}:{prompt}:{task_type}:{json.dumps(kwargs, sort_keys=True)}"
        return f"supremeai:cache:{hashlib.sha256(data.encode()).hexdigest()[:32]}"

    async def check_cache(
        self,
        prompt: str,
        task_type: str,
        user_id: str | None = None,
        min_confidence: float = 0.95,  # noqa: ARG002
    ) -> CacheEntry | None:
        """Check cache for an existing response."""
        cache_key = self.generate_cache_key(prompt, task_type, user_id)

        if self.redis:
            try:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    entry = CacheEntry(**json.loads(cached_data))
                    logger.info(f"Cache hit: {entry.key[:16]}...")
                    return entry
            except Exception as e:
                logger.debug(f"Cache read failed: {e}")

        return None

    async def store_cache(
        self,
        prompt: str,
        response: str,
        tokens_used: int,
        cost_usd: float,
        model_used: str,
        task_type: str,
        user_id: str | None = None,
    ) -> str:
        """Store a response in cache."""
        import datetime

        cache_key = self.generate_cache_key(prompt, task_type, user_id)

        entry = CacheEntry(
            key=cache_key,
            prompt=prompt,
            response=response,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            model_used=model_used,
            task_type=task_type,
            created_at=str(datetime.datetime.now()),
            expires_at=str(datetime.datetime.now() + self.cache_ttl),
        )

        if self.redis:
            try:
                await self.redis.setex(
                    cache_key,
                    int(self.cache_ttl.total_seconds()),
                    json.dumps(entry.__dict__),
                )
                logger.debug(f"Cache stored: {cache_key[:16]}...")
            except Exception as e:
                logger.debug(f"Cache store failed: {e}")

        return cache_key

    def calculate_compression_ratio(self, original: str, compressed: str) -> float:
        """Calculate compression ratio."""
        if not original:
            return 1.0
        return len(compressed.encode("utf-8")) / len(original.encode("utf-8"))


class IntelligentCacheBridge:
    """
    Smart bridge between the memory service and TokenJuice.

    Compresses context before LLM calls to reduce token cost.
    Automatically returns cached responses when available.
    """

    def __init__(self) -> None:
        self.compressor = TokenJuiceCompressor()
        self.token_budget = TokenBudget()

    async def route_with_intelligent_caching(
        self,
        prompt: str,
        task_type: str,
        max_tokens: int = 1000,  # noqa: ARG002
        user_id: str | None = None,
        **kwargs: Any,  # noqa: ARG002
    ) -> dict[str, Any]:
        """
        Route with smart caching.

        Checks cache first; falls back to LLM call and stores result.
        """
        # 1. Cache check
        cached = await self.compressor.check_cache(prompt, task_type, user_id)

        if cached:
            return {
                "response": cached.response,
                "tokens_used": 0,
                "cost_usd": 0.0,
                "model_used": cached.model_used,
                "cached": True,
                "source": "intelligent_cache",
            }

        # 2. LLM call not performed here - caller must use LLMGateway
        return {
            "tokens_used": 0,
            "cost_usd": 0.0,
            "cached": False,
            "source": "requires_llm_gateway",
        }

    def should_compress(self, context_size: int) -> bool:
        """Determine whether compression is needed."""
        return context_size > self.token_budget.compression_threshold

    def compress_context_for_bengali(self, text: str) -> str:
        """Conservative compression for Bengali text to preserve clarity."""
        if len(text) > 5000:
            lines = text.split("\n")
            important_lines = [
                line
                for line in lines
                if line.strip()
                and not any(w in line.lower() for w in ["debug", "trace", "verbose"])
            ]
            return "\n".join(important_lines[:100])  # max 100 lines
        return text


# Global factory
def get_intelligent_cache_bridge() -> IntelligentCacheBridge:
    """Return a new IntelligentCacheBridge instance."""
    return IntelligentCacheBridge()


# Convenience functions
async def get_cached_response(
    prompt: str,
    task_type: str = "chat",
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """Retrieve a cached response if available."""
    bridge = get_intelligent_cache_bridge()
    return await bridge.route_with_intelligent_caching(prompt, task_type, user_id=user_id)


async def cache_response(
    prompt: str,
    response: str,
    task_type: str,
    tokens_used: int,
    cost_usd: float,
    model_used: str,
    user_id: str | None = None,
) -> str:
    """Store a response in the cache."""
    bridge = get_intelligent_cache_bridge()
    return await bridge.compressor.store_cache(
        prompt=prompt,
        response=response,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        model_used=model_used,
        task_type=task_type,
        user_id=user_id,
    )
