from __future__ import annotations

import re
from typing import Any, ClassVar


class BengaliNLP:
    BENGALI_CHARS = re.compile(r"[\u0980-\u09FF]")
    STOP_WORDS: ClassVar[set[str]] = {
        "এই",
        "ওই",
        "তার",
        "তারা",
        "আর",
        "এবং",
        "কিন্তু",
        "যে",
        "এটা",
        "ওটা",
        "আমি",
        "তুমি",
        "সে",
        "আমার",
        "তোমার",
        "আছে",
        "ছিল",
        "হয়",
    }

    def is_bengali(self, text: str) -> bool:
        return bool(self.BENGALI_CHARS.search(text))

    def tokenize(self, text: str) -> list[str]:
        text = re.sub(r"[^\u0980-\u09FF\s]", " ", text)
        tokens = text.split()
        return [t for t in tokens if t and t not in self.STOP_WORDS]

    def keyword_count(self, text: str) -> int:
        return len(self.tokenize(text))

    def analyze_sentiment(self, text: str) -> dict[str, Any]:
        positive = {"ভালো", "সুন্দর", "চমৎকার", "উত্তম", "আনন্দ", "প্রিয়", "সফল", "ধন্যবাদ"}
        negative = {"খারাপ", "বrophy", "দুর্ঘটনা", "অসফল", "বিরক্তি", "দুঃখ", "রাগ", "ভয়"}
        tokens = self.tokenize(text)
        pos = len(set(tokens) & positive)
        neg = len(set(tokens) & negative)
        total = pos + neg
        if total == 0:
            label = "neutral"
            score = 0.5
        else:
            score = pos / total
            label = "positive" if score >= 0.6 else "negative" if score <= 0.4 else "neutral"
        return {
            "label": label,
            "score": round(score, 3),
            "positive_matches": pos,
            "negative_matches": neg,
        }

    def detect_language_mix(self, text: str) -> dict[str, Any]:
        bengali_chars = len(self.BENGALI_CHARS.findall(text))
        latin_chars = len(re.findall(r"[A-Za-z]", text))
        total = bengali_chars + latin_chars
        ratio = 0.0 if total == 0 else bengali_chars / total
        primary = "bengali" if ratio >= 0.7 else "english" if ratio <= 0.3 else "mixed"
        return {"primary": primary, "bengali_ratio": round(ratio, 3)}
