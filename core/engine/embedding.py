import asyncio

from core.config import settings
from core.embeddings import embed_for_pgvector


class EmbeddingService:
    """
    Handles text-to-vector embedding generation.

    বাংলা মন্তব্য: লোকাল sentence-transformers (all-MiniLM-L6-v2, ৩৮৪-ডাইম, ফ্রি, অফলাইন)
    প্রাইমারি — sentence-transformers ইনস্টল না থাকলে LiteLLM দিয়ে OpenAI
    text-embedding-3-small (১৫৩৬-ডাইম) ফলব্যাক করে। $0 খরচ ভিশনের সাথে সামঞ্জস্যপূর্ণ।
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.embedding_model

    async def generate_embedding(self, text: str, pg_dim: int = 384) -> list[float]:
        """Generates a vector embedding for a single text string (local-first)."""
        return await asyncio.to_thread(embed_for_pgvector, text, pg_dim)

    async def generate_embeddings_batch(
        self, texts: list[str], pg_dim: int = 384
    ) -> list[list[float]]:
        """Generates vector embeddings for a batch of texts (local-first)."""
        return [await self.generate_embedding(t, pg_dim) for t in texts]


embedding_service = EmbeddingService()
