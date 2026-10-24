# backend/memory/repository.py
# SupremeAI 2.0 — Canonical Memory Repository Facade
# ==============================================================================
# বাংলা মন্তব্য: backend.memory নেমস্পেস থেকে ক্যানোনিকাল MemoryRepository এক্সেস করার ব্রিজ।

from core.ai_memory.repository import (
    EMBEDDING_DIM,
    MemoryRepository,
    get_memory_repository,
)

__all__ = ["EMBEDDING_DIM", "MemoryRepository", "get_memory_repository"]
