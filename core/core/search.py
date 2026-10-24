"""Graceful DuckDuckGo (DDGS) web search — free, no API key required.

বাংলা মন্তব্য: duckduckgo-search লাইব্রেরি (নতুন প্যাকেজ নাম `ddgs`, পুরনো `duckduckgo_search`)
ব্যবহার করে লাইভ ওয়েব সার্চ করে। প্যাকেজটি ইনস্টল না থাকলে ফাংশনগুলো খালি লিস্ট/None রিটার্ন
করে — কোনো ক্র্যাশ হয় না। প্যাকেজ ইনস্টল: `pip install duckduckgo-search` (বা `ddgs`)।
"""

from __future__ import annotations

import importlib.util
from typing import Any

from core.logging_config import logger


def _ddgs_client():
    """Return a DDGS client instance, trying both package names. None if unavailable."""
    if importlib.util.find_spec("ddgs") is not None:
        try:
            from ddgs import DDGS

            return DDGS()
        except Exception as exc:  # pragma: no cover - import edge cases
            logger.debug(f"[search] ddgs import failed: {exc}")
    if importlib.util.find_spec("duckduckgo_search") is not None:
        try:
            from duckduckgo_search import DDGS

            return DDGS()
        except Exception as exc:  # pragma: no cover
            logger.debug(f"[search] duckduckgo_search import failed: {exc}")
    return None


def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Free web search via DuckDuckGo. Returns list of
    ``{"title": str, "href": str, "body": str}``. Empty list if DDGS unavailable.
    """
    client = _ddgs_client()
    if client is None:
        return []
    try:
        results = client.text(query, max_results=max_results)
        return results or []
    except Exception as exc:
        logger.warning(f"[search] DDGS search failed: {exc}")
        return []
