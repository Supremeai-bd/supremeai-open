"""
config_cache.py — Lightweight In-Memory Config Cache
======================================================
SupremeAI 2.0-এর জন্য TTL-based config cache layer.

কেন এটি দরকার:
    "Database-Driven" মানে প্রতি request-এ DB কল না — এতে latency ও cost দুটোই বাড়বে।
    এই ক্যাশ লেয়ার app startup-এ config load করে, TTL-এর মধ্যে in-memory serve করে,
    এবং Supabase Realtime / change-event এলে cache invalidate করে।

ব্যবহার:
    from core.config_cache import config_cache

    # Get a config value (cached with TTL)
    threshold = config_cache.get("cache_threshold_code", default=0.95)

    # Force refresh
    config_cache.refresh()

    # Set a config value (also persists to DB)
    await config_cache.set("cache_threshold_code", 0.90)
"""

import threading
import time
from typing import Any

from core.logging_config import logger

# ডিফল্ট কনফিগ — DB না থাকলেও অ্যাপ চালু থাকবে
DEFAULT_CONFIGS: dict[str, Any] = {
    # Semantic Cache Thresholds
    "cache_threshold_code": 0.95,
    "cache_threshold_generation": 0.95,
    "cache_threshold_general": 0.85,
    "cache_threshold_qa": 0.85,
    "cache_threshold_reasoning": 0.80,
    # Feature Flags
    "feature_semantic_cache": True,
    "feature_auto_pr": True,
    "feature_self_healing": True,
    "feature_budget_guardian": True,
    # Rate Limits (override per environment)
    "rate_limit_gemini_rpm": 9,
    "rate_limit_groq_rpm": 28,
    "rate_limit_openrouter_rpm": 19,
    # Provider Metadata
    "provider_base_url_groq": "https://api.groq.com/openai/v1",
    "provider_base_url_deepseek": "https://api.deepseek.com",
    "provider_base_url_openai": "https://api.openai.com/v1",
    "provider_models_groq": ["llama3-70b-8192", "mixtral-8x7b-32768"],
    "provider_models_deepseek": ["deepseek-coder", "deepseek-chat"],
    "provider_models_openai": ["gpt-4", "gpt-4o-mini", "gpt-3.5-turbo"],
    # Self-Healing
    "self_healing_max_retries": 3,
    "self_healing_cooldown_seconds": 300,
}


class ConfigCache:
    """
    TTL-based in-memory config cache.

    - App startup-এ DB থেকে config load করে
    - TTL (ডিফল্ট: ৬০ সেকেন্ড) পর্যন্ত in-memory serve করে
    - TTL expire হলে পরবর্তি request-এ DB reload করে
    - force_refresh() দিয়ে ম্যানুয়ালি invalidate করা যায়
    """

    def __init__(self, ttl_seconds: int = 60):
        self._cache: dict[str, Any] = {}
        self._ttl = ttl_seconds
        self._last_refresh: float = 0.0
        self._lock = threading.Lock()
        self._loaded = False
        self._refresh_pending = False

    def _should_refresh(self) -> bool:
        """TTL expire হয়েছে কিনা চেক করে।"""
        return (time.time() - self._last_refresh) > self._ttl

    async def _load_from_db_async(self) -> dict[str, Any]:
        """একমাত্র DB-load পথ — সবসময় বর্তমান event loop-এই চলে, নতুন থ্রেড/লুপ তৈরি করে না।"""
        configs = dict(DEFAULT_CONFIGS)
        try:
            from sqlalchemy import select

            from database.session import AsyncSessionLocal
            from models.system_config import SystemConfig

            async with AsyncSessionLocal() as session:
                stmt = select(SystemConfig).where(SystemConfig.is_active)
                result = await session.execute(stmt)
                for row in result.scalars().all():
                    configs[row.key] = row.value
            logger.info(f"ConfigCache: Loaded {len(configs)} configs from DB")
        except Exception as exc:  # — DB down হলেও app চলতে থাকুক, defaults দিয়ে
            logger.warning(f"ConfigCache: DB load failed, using defaults: {exc}")
        return configs

    async def refresh_async(self):
        new_cache = await self._load_from_db_async()
        with self._lock:
            self._cache = new_cache
            self._last_refresh = time.time()
            self._loaded = True

    def refresh_sync_bootstrap(self):
        """শুধু app startup-এ, event loop চালু হওয়ার আগে, একবারই ব্যবহারের জন্য।
        Request-handling চলাকালীন এটা কখনো কল করা যাবে না।"""
        import asyncio

        try:
            new_cache = asyncio.run(self._load_from_db_async())
        except Exception as exc:
            logger.warning(
                f"ConfigCache: DB load failed during sync bootstrap, using defaults: {exc}"
            )
            new_cache = dict(DEFAULT_CONFIGS)
        with self._lock:
            self._cache = new_cache
            self._last_refresh = time.time()
            self._loaded = True

    def _schedule_refresh(self) -> None:
        """Schedule a single async refresh task (coalescing guard).

        Multiple concurrent calls during TTL expiry will share one refresh task.
        """
        if self._refresh_pending:
            return
        self._refresh_pending = True
        try:
            import asyncio

            from core.utils.background_tasks import track_task

            loop = asyncio.get_running_loop()
            track_task(loop.create_task(self._coalesced_refresh()))
        except RuntimeError:
            self._refresh_pending = False

    async def _coalesced_refresh(self) -> None:
        try:
            await self.refresh_async()
        finally:
            with self._lock:
                self._refresh_pending = False

    def get(self, key: str, default: Any = None) -> Any:
        """
        কনফিগ ভ্যালু রিটার্ন করে।
        - TTL expire হলে auto-refresh করে
        - DB না থাকলে DEFAULT_CONFIGS থেকে নেয়
        """
        if not self._loaded:
            self.refresh_sync_bootstrap()
        elif self._should_refresh():
            self._schedule_refresh()

        with self._lock:
            if key in self._cache:
                return self._cache[key]
            return default

    def get_all(self, category: str | None = None) -> dict[str, Any]:
        """সব কনফিগ (অথবা নির্দিষ্ট category) রিটার্ন করে।"""
        if not self._loaded or self._should_refresh():
            self._schedule_refresh()

        with self._lock:
            if category:
                # Filter by key prefix pattern (e.g., "cache_threshold_", "provider_")
                return {k: v for k, v in self._cache.items() if k.startswith(category)}
            return dict(self._cache)

    async def set(self, key: str, value: Any, description: str = "") -> bool:
        """
        কনফিগ ভ্যালু সেট করে — DB-তেও persist করে + cache update করে।
        """
        from sqlalchemy import select

        from database.session import AsyncSessionLocal
        from models.system_config import SystemConfig

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.value = value
                    existing.version += 1
                    if description:
                        existing.description = description
                else:
                    new_config = SystemConfig(
                        key=key,
                        value=value,
                        description=description or f"Auto-created config for '{key}'",
                    )
                    session.add(new_config)

                await session.commit()

                # Update in-memory cache
                with self._lock:
                    self._cache[key] = value

                logger.info(f"ConfigCache: Set '{key}' = {value}")
                return True
        except Exception as exc:
            logger.error(f"ConfigCache: Failed to set '{key}': {exc}")
            return False

    def invalidate(self, key: str | None = None):
        """
        নির্দিষ্ট key (বা সব) ক্যাশ invalidate করে।
        পরবর্তি get() কল auto-refresh ট্রিগার করবে।
        """
        with self._lock:
            if key:
                self._cache.pop(key, None)
                logger.debug(f"ConfigCache: Invalidated key '{key}'")
            else:
                self._cache.clear()
                self._loaded = False
                logger.debug("ConfigCache: Fully invalidated")


# Global singleton
config_cache = ConfigCache(ttl_seconds=60)
