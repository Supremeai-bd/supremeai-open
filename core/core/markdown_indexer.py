"""
backend/core/markdown_indexer.py
================================
Incremental Markdown Corpus Indexer for SupremeAI living documentation.
Chunks markdown documents by headings (#, ##, ###) and indexes them using EmbeddingEngine.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.embeddings import EmbeddingEngine
from core.logging_config import logger


class MarkdownIndexer:
    """Indexes markdown files and performs semantic vector search over snippets."""

    _instance: MarkdownIndexer | None = None

    def __init__(self, root_dir: str | Path | None = None):
        self.root_dir = Path(root_dir or ".")
        self.engine = EmbeddingEngine.get_instance()
        self.chunks: list[dict[str, Any]] = []

    @classmethod
    def get_instance(cls, root_dir: str | Path | None = None) -> MarkdownIndexer:
        if cls._instance is None:
            cls._instance = cls(root_dir)
        return cls._instance

    def _chunk_file(self, file_path: Path) -> list[dict[str, Any]]:
        """Split a markdown file into chunks delimited by markdown headings."""
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            logger.debug(f"[MarkdownIndexer] Failed to read {file_path}: {e}")
            return []

        lines = content.splitlines()
        chunks: list[dict[str, Any]] = []
        current_heading = "Overview"
        current_body: list[str] = []

        for line in lines:
            if re.match(r"^#{1,4}\s+", line):
                if current_body:
                    snippet = "\n".join(current_body).strip()
                    if snippet:
                        chunks.append(
                            {
                                "file": str(file_path.name),
                                "path": str(file_path),
                                "heading": current_heading,
                                "snippet": snippet[:400],
                                "text": f"{file_path.name} | {current_heading} | {snippet[:300]}",
                            }
                        )
                current_heading = line.lstrip("#").strip()
                current_body = []
            else:
                current_body.append(line)

        if current_body:
            snippet = "\n".join(current_body).strip()
            if snippet:
                chunks.append(
                    {
                        "file": str(file_path.name),
                        "path": str(file_path),
                        "heading": current_heading,
                        "snippet": snippet[:400],
                        "text": f"{file_path.name} | {current_heading} | {snippet[:300]}",
                    }
                )

        return chunks

    async def index(self) -> int:
        """Scan repository markdown files and index snippets."""
        self.chunks = []
        md_files = list(self.root_dir.glob("*.md")) + list((self.root_dir / "docs").glob("**/*.md"))
        for p in md_files:
            if "node_modules" in str(p) or ".git" in str(p):
                continue
            file_chunks = self._chunk_file(p)
            for chunk in file_chunks:
                chunk["vector"] = await self.engine.embed(chunk["text"])
                self.chunks.append(chunk)

        if not self.chunks:
            # Fallback default snippets if no markdown files are found
            self.chunks.append(
                {
                    "file": "README.md",
                    "heading": "SupremeAI Architecture",
                    "snippet": "SupremeAI is a self-evolving multi-model agentic operating system.",
                    "text": "SupremeAI architecture overview and multi-model agent system",
                    "vector": await self.engine.embed(
                        "SupremeAI architecture overview and multi-model agent system"
                    ),
                }
            )

        logger.info(f"[MarkdownIndexer] Indexed {len(self.chunks)} markdown chunks.")
        return len(self.chunks)

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Perform semantic vector search across markdown chunks."""
        if not self.chunks:
            await self.index()
        return await self.engine.vector_search(query=query, corpus=self.chunks, top_k=top_k)
