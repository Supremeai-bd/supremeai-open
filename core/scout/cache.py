"""Crawler caching layer backed by Redis and memory cache."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.cache.redis_manager import redis_manager
from core.logging_config import logger
from scout.models import CrawlResponse


class CrawlerCache:
    """Manages cached crawl responses to avoid redundant external network fetches."""

    def __init__(self, key_prefix: str = "scout:crawl:") -> None:
        self.key_prefix = key_prefix

    @staticmethod
    def generate_cache_key(tenant_id: str, query_or_url: str, max_depth: int) -> str:
        """Constructs a deterministic cache key."""
        raw_key = f"{tenant_id}:{query_or_url.strip().lower()}:{max_depth}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return f"scout:crawl:{digest}"

    async def get_cached_response(
        self, tenant_id: str, query_or_url: str, max_depth: int
    ) -> CrawlResponse | None:
        """Retrieves a cached CrawlResponse if present."""
        key = self.generate_cache_key(tenant_id, query_or_url, max_depth)
        try:
            cached_data = await redis_manager.get_json(key)
            if cached_data:
                logger.info(f"Crawl cache hit for query: {query_or_url}")
                return CrawlResponse.model_validate(cached_data)
        except Exception as exc:
            logger.warning(f"Error retrieving crawl cache: {exc}")
        return None

    async def store_response(
        self,
        tenant_id: str,
        query_or_url: str,
        max_depth: int,
        response: CrawlResponse,
        ttl_seconds: int = 86400,
    ) -> bool:
        """Stores a serialized CrawlResponse in cache."""
        key = self.generate_cache_key(tenant_id, query_or_url, max_depth)
        try:
            return await redis_manager.set_json(
                key, response.model_dump(mode="json"), ex=ttl_seconds
            )
        except Exception as exc:
            logger.warning(f"Error saving crawl cache: {exc}")
            return False
