"""
SupremeAI — Bangla/NLP Agent
=============================
Specialized for Bengali language processing and cultural adaptation.
Provides transliteration, sentiment analysis, and Bangla text processing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.errors.error_bus import with_error_bus
from core.logging_config import logger

BANGLA_CACHE_TTL = 3600

# Unicode ranges for Bengali script
BANGLA_UNICODE_RANGE = r"[\u0980-\u09FF]"
BANGLA_DIGITS = r"[\u09E6-\u09EF]"

# Common Bangla stop words
BANGLA_STOP_WORDS = {
    "এবং",
    "এই",
    "ও",
    "করে",
    "করা",
    "হয়ে",
    "হয়",
    "কিন্তু",
    "সে",
    "তারা",
    "আমি",
    "তুমি",
    "আপনি",
    "আমরা",
    "তার",
    "তাদের",
    "আমার",
    "আমাদের",
    "জন্য",
    "কাছে",
    "মধ্যে",
    "বিরুদ্ধে",
    "সাথে",
    "ছাড়া",
    "কোন",
    "সব",
    "কিছু",
    "অনেক",
    "প্রতি",
    "পরে",
    "আগে",
    "উপর",
    "নিচে",
    "ভিতরে",
    "বাইরে",
    "এখানে",
    "সেখানে",
    "এখন",
    "তখন",
    "আজ",
    "কাল",
    "এখনই",
}


@dataclass(frozen=True)
class BanglaSentiment:
    """Immutable sentiment analysis result for Bangla text."""

    text: str
    sentiment: str  # positive, negative, neutral
    confidence: float
    key_phrases: list[str]


@dataclass(frozen=True)
class TransliterationResult:
    """Immutable transliteration result."""

    bangla_text: str
    romanized: str
    confidence: float


class BanglaTextProcessor:
    """
    Bangla text processing utilities.
    """

    @staticmethod
    def contains_bangla(text: str) -> bool:
        """Check if text contains Bengali characters."""
        return bool(re.search(BANGLA_UNICODE_RANGE, text))

    @staticmethod
    def get_bangla_ratio(text: str) -> float:
        """Get ratio of Bengali characters in text."""
        if not text:
            return 0.0
        bangla_chars = len(re.findall(BANGLA_UNICODE_RANGE, text))
        return bangla_chars / len(text) if len(text) > 0 else 0.0

    @staticmethod
    def remove_stopwords(tokens: list[str]) -> list[str]:
        """Remove Bangla stop words from token list."""
        return [t for t in tokens if t not in BANGLA_STOP_WORDS]

    @staticmethod
    def simple_tokenize(text: str) -> list[str]:
        """Simple Bangla word tokenization."""
        # Split on whitespace and punctuation
        tokens = re.findall(r"[\u0980-\u09FF\w]+", text)
        return tokens


class BanglaNLPAgent:
    """
    Specialized for Bengali language processing and cultural adaptation.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm = llm_router or ModelRouter()
        self.cache = get_cache()
        self.processor = BanglaTextProcessor()

    def _cache_key(self, prefix: str, text_hash: str) -> str:
        raw = f"bangla:{prefix}:{text_hash}"
        return f"bangla:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    @with_error_bus("analyze_sentiment")
    async def analyze_sentiment(self, text: str) -> BanglaSentiment:
        """Analyze sentiment of Bangla text."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
        cache_key = self._cache_key("sentiment", text_hash)
        cached = await self.cache.get(cache_key)
        if cached:
            return BanglaSentiment(**cached)

        prompt = (
            f"Analyze the sentiment of this Bengali text:\n\n{text}\n\n"
            f"Respond in JSON format with: sentiment (positive/negative/neutral), "
            f"confidence (0-1), and key_phrases (list of important phrases)."
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("bangla_nlp_agent_max_tokens", 200),
            )
            content = result.get("text", "{}")
            import json

            data = json.loads(content) if isinstance(content, str) else content
            sentiment = BanglaSentiment(
                text=text,
                sentiment=data.get("sentiment", "neutral"),
                confidence=float(data.get("confidence", 0.5)),
                key_phrases=data.get("key_phrases", []),
            )
        except Exception:
            sentiment = BanglaSentiment(
                text=text,
                sentiment="neutral",
                confidence=0.5,
                key_phrases=[],
            )

        await self.cache.set(
            cache_key,
            {
                "text": sentiment.text,
                "sentiment": sentiment.sentiment,
                "confidence": sentiment.confidence,
                "key_phrases": sentiment.key_phrases,
            },
            ttl=BANGLA_CACHE_TTL,
        )

        return sentiment

    @with_error_bus("transliterate")
    async def transliterate(self, romanized_text: str) -> TransliterationResult:
        """Convert Romanized Bangla (Banglish) to proper Bangla."""
        text_hash = hashlib.sha256(romanized_text.encode()).hexdigest()[:12]
        cache_key = self._cache_key("transliterate", text_hash)
        cached = await self.cache.get(cache_key)
        if cached:
            return TransliterationResult(**cached)

        prompt = (
            f"Convert this Banglish (Romanized Bengali) text to proper Bengali script:\n\n"
            f"{romanized_text}\n\n"
            f"Respond with ONLY the Bengali text, no explanation."
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("bangla_nlp_agent_max_tokens", 200),
            )
            bangla_text = result.get("text", romanized_text)
            confidence = self.processor.get_bangla_ratio(bangla_text)
            transliteration = TransliterationResult(
                bangla_text=bangla_text,
                romanized=romanized_text,
                confidence=confidence,
            )
        except Exception:
            transliteration = TransliterationResult(
                bangla_text=romanized_text,
                romanized=romanized_text,
                confidence=0.0,
            )

        await self.cache.set(
            cache_key,
            {
                "bangla_text": transliteration.bangla_text,
                "romanized": transliteration.romanized,
                "confidence": transliteration.confidence,
            },
            ttl=BANGLA_CACHE_TTL,
        )

        return transliteration

    async def generate_bangla_response(self, context: str, intent: str) -> str:
        """Generate a culturally appropriate Bangla response."""
        prompt = (
            f"You are a Bengali language AI assistant. Generate a response in Bangla "
            f"(Bengali) for the following context and intent.\n\n"
            f"Context: {context}\n"
            f"Intent: {intent}\n\n"
            f"Make the response culturally appropriate for Bangladesh audience. "
            f"Use polite Bangla (shadhu bhasha or chalit bhasha as appropriate)."
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="text_generation",
                max_tokens=config_cache.get("bangla_nlp_agent_max_tokens", 500),
            )
            return result.get("text", "")
        except Exception as e:
            logger.error("Failed to generate Bangla response: %s", e)
            return ""

    def extract_bangla_keywords(self, text: str) -> list[str]:
        """Extract keywords from Bangla text."""
        tokens = self.processor.simple_tokenize(text)
        filtered = self.processor.remove_stopwords(tokens)
        # Return unique, meaningful keywords
        seen = set()
        keywords = []
        for t in filtered:
            if t not in seen and len(t) > 1:
                seen.add(t)
                keywords.append(t)
        return keywords[:10]


# Singleton
_bangla_nlp_instance: BanglaNLPAgent | None = None


def get_bangla_nlp() -> BanglaNLPAgent:
    """Get or create the singleton BanglaNLPAgent."""
    global _bangla_nlp_instance
    if _bangla_nlp_instance is None:
        _bangla_nlp_instance = BanglaNLPAgent()
    return _bangla_nlp_instance
