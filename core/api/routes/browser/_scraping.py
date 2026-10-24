"""Scrape/browse/extract endpoints proxying to the scraper microservice.

Split out of the former single-module api/routes/browser.py verbatim.
Import-time side effects of the original module (``MultiLevelCache``
instantiation, ``settings.scraper_service_url`` read) live HERE and only
here, matching the original single-module behavior.
"""

import asyncio
import hashlib
import json

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel

from api.routes.admin_dashboard import require_admin_token
from api.routes.browser import router
from core.cache.redis_manager import MultiLevelCache
from core.config import settings
from core.logging_config import logger
from tools.ai_agents.browser_agent import BrowseRequest


class ScrapeRequest(BaseModel):
    url: str


# বাংলা মন্তব্য: আগের BrowserAgent গ্লোবাল সিঙ্গলটন সরিয়ে দিয়েছি।
# এখন ব্রাউজার অটোমেশন স্ক্র্যাপার মাইক্রোসার্ভিসে HTTP প্রক্সি করে (zero-cost,
# decoupled)। AGENTS.md §2: "Never treat tasks in isolation" — এই পরিবর্তনের পাশাপাশি
# Cloudflare Worker (worker.js) এবং render.yaml-এ scraper route যোগ করতে হবে।

_SCRAPER_URL = settings.scraper_service_url.rstrip("/") if settings.scraper_service_url else None

# Hybrid-plan cache: keep scraped results in Upstash Redis (L2) + in-memory (L1)
# so the (off-Render, scale-to-zero) scraper microservice is invoked as rarely as
# possible — directly cutting its compute/quota consumption.
_SCRAPE_CACHE_TTL = 3600  # 1h
_scrape_cache = MultiLevelCache(l2_ttl=_SCRAPE_CACHE_TTL)


def _scrape_cache_key(url: str) -> str:
    return "scrape_cache:" + hashlib.sha256(url.encode("utf-8")).hexdigest()


async def _proxy_to_scraper(endpoint: str, payload: dict) -> dict:
    """Forward browser/scrape requests to the standalone scraper microservice."""
    if not _SCRAPER_URL:
        # Fallback: use local BrowserAgent (for local dev / when scraper service is not deployed)
        from tools.ai_agents.browser_agent import BrowserAgent

        agent = BrowserAgent()
        return await agent.navigate_and_interact(**payload)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{_SCRAPER_URL}/{endpoint}", json=payload)
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.error(f"Scraper service proxy failed: {e}")
        return {"success": False, "error": str(e)}


async def _cached_scrape(payload: dict) -> dict:
    """Scrape with a Redis-backed cache (idempotent fetch only)."""
    url = payload.get("url", "")
    if not url:
        return await _proxy_to_scraper("scrape", payload)
    key = _scrape_cache_key(url)
    cached = await _scrape_cache.get(key)
    if cached is not None:
        try:
            return json.loads(cached)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")
    result = await _proxy_to_scraper("scrape", payload)
    if isinstance(result, dict) and result.get("success"):
        await _scrape_cache.set(key, json.dumps(result), ttl=_SCRAPE_CACHE_TTL)
    return result


@router.post("/scrape", dependencies=[Depends(require_admin_token)])
async def scrape(request: ScrapeRequest):
    """Fetch URL and return cleaned content via the Scraper Microservice."""
    result = await _cached_scrape({"url": request.url})
    return result


@router.post("/browse", dependencies=[Depends(require_admin_token)])
async def browse(request: BrowseRequest):
    """Navigate to a URL and perform browser actions via the Scraper Microservice (Admin Only)."""
    if request.action in ("click", "type", "scroll", "screenshot"):
        result = await _proxy_to_scraper(
            "browse",
            {
                "url": request.url,
                "action": request.action,
                "selector": request.selector,
                "text": request.text,
                "wait_for": request.wait_for,
            },
        )
        return result

    # Default action (fetch) — delegate to scraper service (cache-backed)
    result = await _cached_scrape({"url": request.url})
    return result


@router.post("/extract", dependencies=[Depends(require_admin_token)])
async def extract(url: str, extraction_prompt: str):
    """Fetch page and extract structured data with AI (Admin Only).

    Now proxies to the standalone scraper microservice for browser automation,
    then performs AI extraction on the returned content.
    """
    from core.security.protection.ssrf_protection import is_safe_url

    if not is_safe_url(url):
        raise HTTPException(
            status_code=400,
            detail="URL is not allowed: restricted by SSRF protection policy",
        )

    from tools.browser.ai_web_extractor import AIWebExtractor

    extractor = AIWebExtractor()
    return await extractor.extract_data(url, extraction_prompt)
