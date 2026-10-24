"""Robots.txt compliance for the policy-driven crawler (Spec 002 FR-018).

বাংলা: Scout-এর প্রতিটি ফেচের আগে টার্গেট ডোমেইনের robots.txt সম্মান করা হয় —
এটা আমাদের Constitution-এর "third-party policies remain constraints on execution"
নীতির অংশ। robots.txt পাওয়া না গেলে (404/নেটওয়ার্ক ত্রুটি) আমরা allow করি —
কারণ RFC 9309 অনুযায়ী unreachable robots মানে কোনো নিষেধ নেই — তবে ঘটনাটি
log-এ থাকবে (No Silent Failure)।
"""

from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from core.logging_config import logger

_ROBOT_TIMEOUT = 5.0
_CACHE_TTL = 3600.0
_MAX_CACHE = 512


class RobotsCache:
    """Per-domain robots.txt cache with RFC 9309 directive evaluation."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        # বাংলা: crawler-এর shared client reuse করি — per-request client বানালে
        # connection leak হতো (services-perf-review ফাইন্ডিং শ্রেণি)
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_ROBOT_TIMEOUT, follow_redirects=False)
        return self._client

    async def _fetch_parser(self, robots_url: str) -> RobotFileParser | None:
        try:
            resp = await self._get_client().get(robots_url)
            if resp.status_code in (401, 403):
                # বাংলা: robots.txt পড়া নিষেধ মানে সাইট-ওনার সব কিছু নিষেধ করতে চায়
                parser = RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
                return parser
            if resp.status_code != 200:
                return None
            parser = RobotFileParser()
            parser.parse(resp.text.splitlines())
            return parser
        except Exception as exc:
            logger.debug(f"robots.txt fetch failed for {robots_url}: {exc}")
            return None

    async def is_allowed(self, url: str, user_agent: str = "SupremeAI-Scout") -> bool:
        """Returns whether `url` may be fetched per the domain's robots.txt directives."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return True
        domain = (parsed.hostname or "").lower()
        if not domain:
            return True

        now = time.monotonic()
        cached = self._cache.get(domain)
        parser: RobotFileParser | None
        if cached and (now - cached[0]) < _CACHE_TTL:
            parser = cached[1]
        else:
            if len(self._cache) >= _MAX_CACHE:
                # বাংলা: bounded cache — পুরনো এন্ট্রি বাদ (unbounded dict leak এড়াতে)
                oldest = min(self._cache.items(), key=lambda kv: kv[1][0])
                self._cache.pop(oldest[0], None)
            parser = await self._fetch_parser(
                urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
            )
            self._cache[domain] = (now, parser)

        if parser is None:
            return True
        try:
            return parser.can_fetch(user_agent, url)
        except Exception as exc:
            logger.debug(f"robots evaluation failed for {url}: {exc}")
            return True

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
