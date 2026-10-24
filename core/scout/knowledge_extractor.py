import os
from typing import Any

try:
    # বাংলা মন্তব্য: রেন্ডার ফ্রি টায়ারে মেমোরি সংকট এড়াতে LOW_MEMORY_MODE চেক করা হচ্ছে
    if os.getenv("LOW_MEMORY_MODE", "false").lower() == "true":
        raise ImportError("Low memory mode enabled. Skipping sentence-transformers.")
    from sentence_transformers import SentenceTransformer

    HAS_ST = True
except (ImportError, Exception):
    # বাংলা মন্তব্য: PyArrow কাস্টম এক্সটেনশন কনফ্লিক্ট (ArrowKeyError) বা ইম্পোর্ট ফেইলিয়র সেফলি হ্যান্ডেল করা হচ্ছে।
    HAS_ST = False


class KnowledgeExtractor:
    def __init__(self) -> None:
        if HAS_ST:
            self.model = SentenceTransformer("all-MiniLM-L6-v2")

    async def extract(self, content: str) -> list[dict[str, Any]]:
        if not HAS_ST:
            return []
        return [{"text": content, "embedding": self.model.encode(content).tolist()}]
