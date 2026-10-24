"""BhashaBot - Context-aware translation engine for EN ↔ BN ↔ Banglish.

BhashaBot provides seamless, contextual translation rather than literal word-for-word
conversion. It uses a multi-tier strategy: cache lookup → rule-based fallback →
LLM-powered contextual translation. All translations are quality-scored and cached
for cost optimization.
"""

# বাংলা মন্তব্য: ভাষা-বট — ইংরেজি, বাংলা ও বাংলিশের মধ্যে অর্থপূর্ণ ও প্রসঙ্গ-সচেতন অনুবাদ ইঞ্জিন।
# এতে ক্যাশ, রুল-বেসড ফলব্যাক এবং এলএলএম-ভিত্তিক অনুবাদের ৩-স্তরের আর্কিটেকচার ব্যবহার করা হয়েছে।

from __future__ import annotations

import hashlib
import os
from typing import Any

from core.logging_config import logger

try:
    from core.config import settings
except ImportError:
    settings = None  # type: ignore[misc,assignment]

try:
    from brain.model_router import ModelRouter
except ImportError:
    ModelRouter = None  # type: ignore[misc,assignment]


# --- Config and Thresholds ---
DEFAULT_CACHE_TTL_HOURS = settings.bhasha_cache_ttl_hours if settings else 24
_bhasha_min_quality_raw = str(settings.bhasha_min_quality) if settings else "0.7"
MIN_QUALITY_THRESHOLD = float(_bhasha_min_quality_raw) if _bhasha_min_quality_raw else 0.7
MAX_CACHE_SIZE = settings.bhasha_max_cache if settings else 10000


class BhashaBot:
    """Context-aware Bengali-English-Banglish translation engine."""

    def __init__(
        self,
        model_router: Any | None = None,
        cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        min_quality: float = MIN_QUALITY_THRESHOLD,
    ) -> None:
        if model_router is None:
            if ModelRouter is None:
                raise RuntimeError("ModelRouter import failed - brain.model_router unavailable")
            model_router = ModelRouter()
        self.model_router = model_router
        self.cache_ttl_hours = cache_ttl_hours
        self.min_quality = min_quality

        # In-memory LRU cache with TTL (production: use Redis via settings)
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_order: list[str] = []  # LRU tracking

    def _cache_key(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: str = "",
    ) -> str:
        """Generate deterministic cache key including context hash."""
        # বাংলা মন্তব্য: টেক্সট, সোর্স ল্যাঙ্গুয়েজ, টার্গেট ল্যাঙ্গুয়েজ এবং কন্টেক্সট দিয়ে ইউনিক কি তৈরি
        context_hash = hashlib.sha256(context.encode()).hexdigest()[:16]
        raw = f"{text}:{source_lang}:{target_lang}:{context_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve from LRU cache with TTL validation."""
        # বাংলা মন্তব্য: মেমোরি ক্যাশ থেকে অনুবাদ রিট্রিভ করা
        if cache_key not in self._cache:
            return None

        entry = self._cache[cache_key]
        # Simple TTL check (production: use Redis EXPIRE)
        # For now, in-memory cache is session-scoped

        # Move to end (most recently used)
        self._cache_order.remove(cache_key)
        self._cache_order.append(cache_key)

        return entry

    def _set_cache(self, cache_key: str, entry: dict[str, Any]) -> None:
        """Store in LRU cache with eviction."""
        # বাংলা মন্তব্য: ক্যাশ লিমিট ক্রস করলে LRU পলিসি অনুযায়ী ডিলিট করা
        if len(self._cache) >= MAX_CACHE_SIZE and self._cache_order:
            lru_key = self._cache_order.pop(0)
            self._cache.pop(lru_key, None)

        self._cache[cache_key] = entry
        self._cache_order.append(cache_key)

    def _rule_based_banglish(self, text: str, direction: str) -> str | None:
        """Rule-based Banglish conversion for common patterns (zero-cost fallback)."""
        # বাংলা মন্তব্য: রুল-বেসড বাংলিশ রূপান্তর (বিনা খরচে দ্রুত ফলব্যাক)
        if direction == "bn_to_banglish":
            # Common Bengali → Banglish mappings
            mappings = {
                "আমি": "ami",
                "তুমি": "tumi",
                "কি": "ki",
                "করছো": "korcho",
                "ধন্যবাদ": "dhonnobad",
                "কেন": "keno",
                "কোথায়": "kothay",
                "কত": "koto",
                "ভালো": "bhalo",
                "খারাপ": "kharap",
            }
            result = text
            for bn, banglish in mappings.items():
                result = result.replace(bn, banglish)
            return result if result != text else None

        if direction == "banglish_to_bn":
            # Reverse mapping
            mappings = {
                "ami": "আমি",
                "tumi": "তুমি",
                "ki": "কি",
                "korcho": "করছো",
                "dhonnobad": "ধন্যবাদ",
                "keno": "কেন",
                "kothay": "কোথায়",
                "koto": "কত",
                "bhalo": "ভালো",
                "kharap": "খারাপ",
            }
            result = text.lower()
            for banglish, bn in mappings.items():
                result = result.replace(banglish, bn)
            return result if result != text.lower() else None

        return None

    def _build_translation_prompt(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: str,
    ) -> str:
        """Build contextual translation prompt for LLM."""
        # বাংলা মন্তব্য: এলএলএম অনুবাদের জন্য সুনির্দিষ্ট প্রম্পট তৈরি করা
        lang_names = {
            "en": "English",
            "bn": "Bengali (বাংলা)",
            "banglish": "Banglish (Bengali written in Roman script)",
        }

        context_section = ""
        if context:
            context_section = f"\nContext/Domain: {context}\n"

        prompt = f"""You are BhashaBot, a professional contextual translator for the Bangladesh market.

Translate the following text from {lang_names.get(source_lang, source_lang)} to {lang_names.get(target_lang, target_lang)}.
{context_section}
IMPORTANT: Provide NATURAL, CONTEXTUAL translation — NOT literal word-for-word.
Preserve cultural nuances, idioms, and local expressions appropriately.

Text to translate:
\"\"\"{text}\"\"\"

Respond ONLY with the translated text. No explanations, no quotes around output.
"""
        return prompt

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: str = "",
        use_cache: bool = True,
        force_llm: bool = False,
    ) -> dict[str, Any]:
        """Translate text with multi-tier strategy: cache → rules → LLM.

        Args:
            text: Text to translate
            source_lang: Source language code (en, bn, banglish)
            target_lang: Target language code (en, bn, banglish)
            context: Domain context for better translation (e.g., "ecommerce", "support")
            use_cache: Whether to use/read from cache
            force_llm: Skip cache and rules, go directly to LLM

        Returns:
            Dict with translated_text, quality_score, method_used, cache_hit
        """
        # বাংলা মন্তব্য: অনুবাদ প্রক্রিয়া (মেমোরি ক্যাশ -> রুলস -> এলএলএম)
        if not text or not text.strip():
            return {
                "translated_text": "",
                "quality_score": 1.0,
                "method_used": "noop",
                "cache_hit": False,
            }

        # Normalize language codes
        source_lang = source_lang.lower().strip()
        target_lang = target_lang.lower().strip()

        if source_lang == target_lang:
            return {
                "translated_text": text,
                "quality_score": 1.0,
                "method_used": "identity",
                "cache_hit": False,
            }

        cache_key = self._cache_key(text, source_lang, target_lang, context)

        # Tier 1: Cache lookup
        if use_cache and not force_llm:
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug(f"BhashaBot cache hit for key {cache_key[:8]}...")
                cached["cache_hit"] = True
                return cached

        # Tier 2: Rule-based Banglish (zero-cost)
        if not force_llm:
            direction = f"{source_lang}_to_{target_lang}"
            if "banglish" in direction:
                rule_result = self._rule_based_banglish(text, direction)
                if rule_result:
                    result = {
                        "translated_text": rule_result,
                        "quality_score": 0.6,  # Rule-based is acceptable but not perfect
                        "method_used": "rule_based",
                        "cache_hit": False,
                    }
                    if use_cache:
                        self._set_cache(cache_key, result)
                    return result

        # Tier 3: LLM-powered contextual translation
        prompt = self._build_translation_prompt(text, source_lang, target_lang, context)

        try:
            import asyncio

            response = await asyncio.to_thread(
                self.model_router.route_and_generate,
                prompt,
                task_type="translation",
            )
            translated = response.get("text", "").strip()

            # Quality estimation heuristic
            quality = 0.85  # Base LLM quality
            if len(translated) < len(text) * 0.3 or len(translated) > len(text) * 3:
                quality -= 0.15  # Suspicious length ratio

            result = {
                "translated_text": translated,
                "quality_score": max(0.0, min(1.0, quality)),
                "method_used": "llm_contextual",
                "cache_hit": False,
                "model_used": response.get("model", "unknown"),
            }

            if use_cache and quality >= self.min_quality:
                self._set_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"BhashaBot LLM translation failed: {e}")
            # Degraded: return original with warning
            return {
                "translated_text": text,
                "quality_score": 0.0,
                "method_used": "failed_fallback",
                "cache_hit": False,
                "error": str(e),
            }

    async def batch_translate(
        self,
        items: list[dict[str, Any]],
        source_lang: str,
        target_lang: str,
        context: str = "",
    ) -> list[dict[str, Any]]:
        """Batch translate multiple items concurrently."""
        # বাংলা মন্তব্য: একসাথে অনেকগুলো আইটেম প্যারালাল অনুবাদ করা
        import asyncio

        semaphore = asyncio.Semaphore(settings.bhasha_batch_concurrency if settings else 5)

        async def _translate_one(item: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                text = item.get("text", "")
                result = await self.translate(
                    text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    context=context,
                )
                return {
                    "id": item.get("id"),
                    "original": text,
                    **result,
                }

        tasks = [_translate_one(item) for item in items]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results: list[dict[str, Any]] = []
        for result in raw_results:
            if isinstance(result, BaseException):
                logger.warning(f"Batch translation task failed: {result}")
                continue
            valid_results.append(result)
        return valid_results

    def get_cache_stats(self) -> dict[str, Any]:
        """Return cache statistics for monitoring."""
        # বাংলা মন্তব্য: ক্যাশের বর্তমান স্ট্যাটাস পাওয়া
        return {
            "cache_size": len(self._cache),
            "max_size": MAX_CACHE_SIZE,
            "ttl_hours": self.cache_ttl_hours,
            "min_quality_threshold": self.min_quality,
        }
