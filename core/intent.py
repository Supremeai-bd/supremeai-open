import re
from dataclasses import dataclass
from enum import StrEnum


class TaskType(StrEnum):
    general = "general"
    coding = "coding"
    translation = "translation"
    sentiment = "sentiment"
    vision = "vision"
    reasoning = "reasoning"
    admin = "admin"


@dataclass
class Intent:
    task_type: TaskType
    confidence: float
    requires_admin: bool = False
    requires_vision: bool = False


class IntentClassifier:
    KEYWORDS = {
        TaskType.coding: [
            "code",
            "function",
            "python",
            "javascript",
            "bug",
            "debug",
            "api",
            "sql",
            "crash",
            "error",
            "program",
            "class",
            "method",
            "variable",
            "loop",
            "algorithm",
            "compile",
            "runtime",
            "exception",
            "stack",
            "syntax",
        ],
        TaskType.translation: [
            "translate",
            "translation",
            "bengali",
            "hindi",
            "french",
            "spanish",
            "arabic",
            "japanese",
            "german",
        ],
        TaskType.sentiment: ["sentiment", "mood", "emotion", "positive", "negative"],
        TaskType.vision: [
            "image",
            "picture",
            "screenshot",
            "photo",
            "vision",
            "see",
            "look",
        ],
        TaskType.reasoning: [
            "prove",
            "proof",
            "math",
            "logic",
            "deduce",
            "analyze",
            "plan",
        ],
        TaskType.admin: ["admin", "rule", "kill switch", "stop", "shutdown", "disable"],
    }

    def classify(self, prompt: str) -> Intent:
        text = prompt.lower()
        scores = dict.fromkeys(TaskType, 0)
        for task_type, words in self.KEYWORDS.items():
            for w in words:
                if re.search(r"(^|\W)" + re.escape(w) + r"(\W|$)", text):
                    scores[task_type] += 1
        if max(scores.values()) == 0:
            return Intent(task_type=TaskType.general, confidence=0.5)
        best = max(scores, key=lambda t: scores[t])
        total = sum(scores.values())
        confidence = scores[best] / total
        return Intent(
            task_type=best,
            confidence=round(confidence, 3),
            requires_admin=(best == TaskType.admin),
            requires_vision=(best == TaskType.vision),
        )
