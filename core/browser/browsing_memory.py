"""
backend/browser/browsing_memory.py
==================================
L3: Browsing Memory Engine — Retains and accumulates site behavior patterns,
common dialogs (e.g. cookie banners, auth popups), flow histories, and latencies.
"""

from __future__ import annotations

import time
from typing import Any

from core.cache.semantic_cache import semantic_cache
from core.logging_config import logger


class BrowsingMemory:
    """Persistent cross-session site intelligence and preflight behavior synthesizer."""

    _site_history: dict[str, list[dict[str, Any]]] = {}

    async def observe(self, site: str, event: dict[str, Any]) -> None:
        """Record navigation, interaction, or outcome event for a site domain."""
        normalized_site = self._normalize_site(site)
        if normalized_site not in self._site_history:
            self._site_history[normalized_site] = []

        event_entry = {
            "timestamp": time.time(),
            **event,
        }
        self._site_history[normalized_site].append(event_entry)
        if len(self._site_history[normalized_site]) > 200:
            self._site_history[normalized_site].pop(0)

        # Invalidate site intelligence cache for immediate freshness
        try:
            await semantic_cache.set(f"siteintel::{normalized_site}", None, ttl=1)
        except Exception as e:
            logger.debug(f"BrowsingMemory cache invalidation error: {e}")

    async def site_intel(self, site: str) -> dict[str, Any]:
        """Retrieve aggregated behavioral intelligence for a site."""
        normalized_site = self._normalize_site(site)
        cache_key = f"siteintel::{normalized_site}"

        try:
            cached = await semantic_cache.get(cache_key)
            if cached and isinstance(cached, dict):
                return cached
        except Exception as e:
            logger.debug(f"BrowsingMemory cache read error: {e}")

        history = self._site_history.get(normalized_site, [])
        total_visits = len(history)

        cookie_events = sum(
            1 for e in history if e.get("has_cookie_banner") or e.get("dismissed_cookie")
        )
        cookie_rate = cookie_events / total_visits if total_visits > 0 else 0.0

        latencies = [
            e["load_ms"]
            for e in history
            if "load_ms" in e and isinstance(e["load_ms"], int | float)
        ]
        avg_latency = sum(latencies) / len(latencies) if latencies else 250.0

        intel = {
            "site": normalized_site,
            "total_observations": total_visits,
            "cookie_banner_rate": round(cookie_rate, 2),
            "avg_load_ms": round(avg_latency, 2),
            "known_selectors": list(set(e["selector"] for e in history if "selector" in e)),
            "common_failures": [e["error"] for e in history if "error" in e],
        }

        try:
            await semantic_cache.set(cache_key, intel, ttl=3600)
        except Exception as e:
            logger.debug(f"BrowsingMemory cache write error: {e}")

        return intel

    async def preflight_actions(self, site: str) -> list[str]:
        """Determine automated preflight actions upon navigating to a site (e.g. dismiss cookie banner)."""
        intel = await self.site_intel(site)
        actions = []
        if intel.get("cookie_banner_rate", 0) > 0.5:
            actions.append("dismiss_cookie_banner")
        if intel.get("avg_load_ms", 0) > 2000:
            actions.append("extended_timeout_30s")
        return actions

    @staticmethod
    def _normalize_site(site: str) -> str:
        s = site.lower().strip()
        if "://" in s:
            s = s.split("://")[1]
        return s.split("/")[0]
