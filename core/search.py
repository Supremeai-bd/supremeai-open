"""Graceful web search SSOT — ddgs-first (free, no key) + env-keyed provider fallback.

বাংলা মন্তব্য: duckduckgo-search লাইব্রেরি (নতুন প্যাকেজ নাম `ddgs`, পুরনো `duckduckgo_search`)
ব্যবহার করে লাইভ ওয়েব সার্চ করে। প্যাকেজটি ইনস্টল না থাকলে ফাংশনগুলো খালি লিস্ট/None রিটার্ন
করে — কোনো ক্র্যাশ হয় না। প্যাকেজ ইনস্টল: `pip install duckduckgo-search` (বা `ddgs`)।

Issue #1751: এই মডিউলটি এখন repo-র একমাত্র search SSOT। এনভায়রনমেন্ট-কী থাকলে
Brave/Tavily প্রোভাইডার আগে চলে (plain JSON, কোনো নতুন SDK নেই); key অনুপস্থিত বা
প্রোভাইডার ব্যর্থ হলে fail-closed নীতিতে ddgs-only পথে ফিরে যাওয়া হয় (সৎ warning সহ)।
key-বিহীন রান আজকের মতোই শূন্য-খরচ (DuckDuckGo, কোনো API key নেই)।
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

from core.monitoring.logging_config import logger


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


def _brave_web_search(query: str, max_results: int, key: str) -> list[dict[str, Any]]:
    """Brave Search API via plain JSON (no SDK). Maps to the ddgs result contract."""
    import httpx

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    web = data.get("web") if isinstance(data, dict) else None
    items = (web or {}).get("results") if isinstance(web, dict) else None
    return [
        {
            "title": str(item.get("title", "") or ""),
            "href": str(item.get("url", "") or ""),
            "body": str(item.get("description", "") or ""),
        }
        for item in (items or [])
        if isinstance(item, dict)
    ]


def _tavily_web_search(query: str, max_results: int, key: str) -> list[dict[str, Any]]:
    """Tavily Search API via plain JSON (no SDK). Maps to the ddgs result contract."""
    import httpx

    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": max_results},
            headers={"Authorization": f"Bearer {key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    items = data.get("results") if isinstance(data, dict) else None
    return [
        {
            "title": str(item.get("title", "") or ""),
            "href": str(item.get("url", "") or ""),
            "body": str(item.get("content", "") or ""),
        }
        for item in (items or [])
        if isinstance(item, dict)
    ]


# Issue #1751: keyed providers are tried in this order BEFORE ddgs; a provider
# only participates when its env key is present (keys come from environment —
# provider_registry doctrine). Absence/failure degrades fail-closed to ddgs.
_KEYED_PROVIDERS: tuple[tuple[str, Any], ...] = (
    ("SUPREME_SEARCH_BRAVE_KEY", _brave_web_search),
    ("SUPREME_SEARCH_TAVILY_KEY", _tavily_web_search),
)


def _ddgs_search(query: str, max_results: int) -> list[dict[str, Any]]:
    """ddgs-client search lane. Returns [] when the package is unavailable."""
    client = _ddgs_client()
    if client is None:
        return []
    try:
        return client.text(query, max_results=max_results) or []
    except Exception as exc:
        logger.warning(f"[search] DDGS search failed: {exc}")
        return []


def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Single search SSOT (issue #1751). Order:

    1. env-keyed providers first (``SUPREME_SEARCH_BRAVE_KEY`` → Brave,
       ``SUPREME_SEARCH_TAVILY_KEY`` → Tavily) — plain JSON via httpx,
       results normalized to the ddgs contract ``{"title","href","body"}``;
    2. on missing key / transport failure / empty result → next provider,
       finally the free ddgs client (fail-closed, honest warn on failure).

    Key-less runs keep the zero-cost behavior: ddgs only. Returns a list of
    ``{"title": str, "href": str, "body": str}``; empty list if every lane
    yields nothing.
    """
    for env_name, provider in _KEYED_PROVIDERS:
        key = (os.environ.get(env_name) or "").strip()
        if not key:
            continue
        try:
            results = provider(query, max_results, key)
        except Exception as exc:
            logger.warning(f"[search] {env_name} provider failed, falling through: {exc}")
            continue
        if results:
            return results
        logger.warning(f"[search] {env_name} provider returned no results, falling through")
    return _ddgs_search(query, max_results)
