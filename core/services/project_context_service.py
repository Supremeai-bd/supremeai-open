"""
SupremeAI — Project Context Service
===================================

Full codebase context injection for deep AI understanding.
- Walks project directory structure
- Extracts key definitions (classes, functions, routes)
- Builds searchable context index
- Injects relevant context into LLM prompts
- .gitignore-aware file filtering
- Caching layer
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from core.cache import get_cache
from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
CONTEXT_CACHE_TTL = 3600
MAX_FILE_SIZE = 100 * 1024  # 100KB
MAX_CONTEXT_SIZE = 50000  # Characters


class ContextType(StrEnum):
    CLASS = "class"
    FUNCTION = "function"
    ROUTE = "route"
    CONFIG = "config"
    SCHEMA = "schema"


@dataclass(frozen=True)
class ContextEntry:
    """Single context entry."""

    file_path: str
    context_type: ContextType
    name: str
    signature: str | None
    docstring: str | None
    line_number: int


class ProjectContextService:
    """
    Builds and maintains project context for AI prompts.
    """

    def __init__(self) -> None:
        self.cache = get_cache()
        self._gitignore_patterns: list[str] = []

    def _is_ignored(self, file_path: Path) -> bool:
        """Check if file matches gitignore patterns."""
        path_str = str(file_path)
        for pattern in self._gitignore_patterns:
            if pattern in path_str:
                return True
        return any(p.startswith(".") for p in file_path.parts)  # Hide hidden dirs

    def _extract_definitions(self, content: str, file_path: str) -> list[ContextEntry]:
        """Extract class/function definitions from code."""
        entries = []

        # Python classes
        for match in re.finditer(r"^class\s+(\w+)(?:\(([^)]*)\))?:", content, re.MULTILINE):
            entries.append(
                ContextEntry(
                    file_path=file_path,
                    context_type=ContextType.CLASS,
                    name=match.group(1),
                    signature=match.group(2),
                    docstring=None,
                    line_number=content[: match.start()].count("\n") + 1,
                )
            )

        # Python functions
        for match in re.finditer(r"^def\s+(\w+)\s*\(([^)]*)\):", content, re.MULTILINE):
            entries.append(
                ContextEntry(
                    file_path=file_path,
                    context_type=ContextType.FUNCTION,
                    name=match.group(1),
                    signature=match.group(2),
                    docstring=None,
                    line_number=content[: match.start()].count("\n") + 1,
                )
            )

        return entries

    def _extract_routes(self, content: str, file_path: str) -> list[ContextEntry]:
        """Extract FastAPI route decorators."""
        entries = []

        for match in re.finditer(
            r"@router\.(get|post|put|delete)\s*\(\s*[\"']([^\"']*)[\"']",
            content,
        ):
            entries.append(
                ContextEntry(
                    file_path=file_path,
                    context_type=ContextType.ROUTE,
                    name=match.group(2),
                    signature=f"{match.group(1).upper()} {match.group(2)}",
                    docstring=None,
                    line_number=content[: match.start()].count("\n") + 1,
                )
            )

        return entries

    def _build_index(self, project_path: str) -> list[ContextEntry]:
        """Build context index from project."""
        all_entries: list[ContextEntry] = []

        for file_path in Path(project_path).rglob("*.py"):
            if self._is_ignored(file_path):
                continue

            try:
                stat = file_path.stat()
                if stat.st_size > MAX_FILE_SIZE:
                    continue

                content = file_path.read_text(encoding="utf-8", errors="ignore")
                all_entries.extend(self._extract_definitions(content, str(file_path)))
                all_entries.extend(self._extract_routes(content, str(file_path)))
            except Exception as e:
                logger.debug(f"Failed to index {file_path}: {e}")

        return all_entries

    async def get_context_for_prompt(
        self,
        project_path: str,
        query: str,
        max_entries: int = 50,
    ) -> str:
        """
        Get relevant context for LLM prompt.

        Args:
            project_path: Project root path.
            query: User query.
            max_entries: Max context entries.

        Returns:
            Formatted context string.
        """
        cache_key = f"context:{hashlib.sha256((project_path + query).encode()).hexdigest()[:16]}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached  # type: ignore

        entries = self._build_index(project_path)

        # Filter by relevance to query
        query_terms = set(re.findall(r"[a-zA-Z_]+", query.lower()))
        relevant = [e for e in entries if any(term in e.name.lower() for term in query_terms)][
            :max_entries
        ]

        # Format context
        context_lines = []
        for e in relevant:
            context_lines.append(f"File: {e.file_path}")
            context_lines.append(f"{e.context_type.value}: {e.name}")
            if e.signature:
                context_lines.append(f"Signature: {e.signature}")

        context = "\n".join(context_lines)[:MAX_CONTEXT_SIZE]

        await self.cache.set(cache_key, context, ttl=CONTEXT_CACHE_TTL)
        return context

    async def inject_context(self, system_prompt: str, user_query: str, project_path: str) -> str:
        """
        Inject context into system prompt.

        Args:
            system_prompt: Base system prompt.
            user_query: User query.
            project_path: Project path.

        Returns:
            Enhanced prompt with context.
        """
        context = await self.get_context_for_prompt(project_path, user_query)

        if context:
            return f"{system_prompt}\n\n## Project Context ##\n{context}"
        return system_prompt


# Singleton
_service_instance: ProjectContextService | None = None


def get_project_context_service() -> ProjectContextService:
    """Get or create the singleton ProjectContextService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ProjectContextService()
    return _service_instance
