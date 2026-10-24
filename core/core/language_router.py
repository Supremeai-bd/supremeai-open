import re
from typing import Any

from core.config import settings


class LanguageRouter:
    BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
    CHINESE_RE = re.compile(r"[\u4E00-\u9FFF]")
    JAPANESE_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")
    ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
    HINDI_RE = re.compile(r"[\u0900-\u097F]")

    PROVIDER_MAP = {
        "bengali": "deepseek",
        "chinese": "openrouter",
        "japanese": "gemini",
        "arabic": "groq",
        "hindi": "deepseek",
        "english": "openrouter",
    }

    LANGUAGE_CODES = {
        "chinese": "zh",
        "japanese": "ja",
        "korean": "ko",
        "arabic": "ar",
        "bengali": "bn",
        "hindi": "hi",
        "english": "en",
    }

    def detect(self, text: str) -> str:
        if not text:
            return "english"
        if self.BENGALI_RE.search(text):
            return "bengali"
        if self.CHINESE_RE.search(text):
            return "chinese"
        if self.JAPANESE_RE.search(text):
            return "japanese"
        if self.ARABIC_RE.search(text):
            return "arabic"
        if self.HINDI_RE.search(text):
            return "hindi"
        return "english"

    def route(self, text: str, task_type: str = "general") -> dict[str, Any]:
        language = self.detect(text)
        provider = self.PROVIDER_MAP.get(language, "openrouter")
        return {
            "language": language,
            "provider": provider,
            "task_type": task_type,
            "reason": f"Detected language '{language}', routed to provider '{provider}'",
        }

    def route_by_language(self, text: str, detected_lang: str | None = None) -> dict[str, Any]:
        language = detected_lang or self.detect(text)
        language_code = self.LANGUAGE_CODES.get(language)
        model = settings.model_multilingual
        if language_code == "en" or (language_code is None and language.lower() == "english"):
            model = settings.model_general
        return {
            "language": language,
            "model": model,
            "task_type": None,
            "reason": f"Detected language '{language}', routed to model '{model}'",
        }
