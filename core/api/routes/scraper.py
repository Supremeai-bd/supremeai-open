"""
SupremeAI Scraper Routes

Exposes browser automation + web scraping as integrated endpoints.

Hardening (production-readiness plan, item 1):
- `/scrape`, `/browse`, `/recipe` now require an authenticated **admin** JWT
  (Playwright instances are heavy: memory + CPU must not be reachable by
  anonymous or regular tenant traffic).
- A module-level ``asyncio.Semaphore`` bounds concurrent scrape/browser
  sessions to ``SCRAPER_MAX_CONCURRENCY``; excess callers receive HTTP 429
  instead of piling up Playwright instances.
- The sync ``WebScraper.fetch_page`` httpx call is offloaded to a worker
  thread so it no longer stalls the event loop (parity with the standalone
  service in ``services/scraper/main.py``).
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin
from services.scraper.browser_agent import BrowserAgent, BrowseRequest
from services.scraper.security import is_safe_url
from services.scraper.web_scraper import WebScraper

MAX_CONCURRENCY = int(os.getenv("SCRAPER_MAX_CONCURRENCY", "3"))
TIMEOUT_SECONDS = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "45"))

router = APIRouter(tags=["scraper"])

# Bounded concurrency for ALL scraper endpoints (P1 hardening).
_scraper_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)


class _SemaphoreSlot:
    """Async context manager that acquires the semaphore or raises 429."""

    async def __aenter__(self) -> None:
        try:
            await asyncio.wait_for(_scraper_semaphore.acquire(), timeout=0.25)
        except TimeoutError as exc:
            raise HTTPException(
                status_code=429,
                detail="Scraper concurrency limit reached. Please retry shortly.",
            ) from exc
        return None

    async def __aexit__(self, *exc_info: object) -> None:
        _scraper_semaphore.release()


_scraper = WebScraper()
_agent = BrowserAgent(headless=True)


class ScrapeRequest(BaseModel):
    url: str
    extraction_prompt: str | None = None


@router.get("/health")
async def health_check():
    try:
        import playwright.async_api as _pw

        playwright_ok = callable(getattr(_pw, "async_playwright", None))
    except ImportError:
        playwright_ok = False

    return {
        "status": "healthy",
        "service": "supremeai-scraper-module",
        "max_concurrency": MAX_CONCURRENCY,
        "timeout_seconds": TIMEOUT_SECONDS,
        "playwright_available": playwright_ok,
    }


@router.post("/scrape")
async def scrape(request: ScrapeRequest, _: dict = Depends(get_current_admin)):
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not is_safe_url(request.url):
        raise HTTPException(
            status_code=400, detail="SSRF check failed: Unauthorized internal access"
        )
    # বাংলা: fetch_page একটি sync httpx কল — ইভেন্ট লুপ ব্লক এড়াতে worker thread-এ
    async with _SemaphoreSlot():
        result = await asyncio.to_thread(_scraper.fetch_page, request.url)
    return result


@router.post("/browse")
async def browse(request: BrowseRequest, _: dict = Depends(get_current_admin)):
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not is_safe_url(request.url):
        raise HTTPException(
            status_code=400, detail="SSRF check failed: Unauthorized internal access"
        )
    async with _SemaphoreSlot():
        result = await _agent.navigate_and_interact(
            url=request.url,
            action=request.action or "fetch",
            selector=request.selector,
            text=request.text,
            wait_for=request.wait_for,
        )
    return result


class RecipeRequest(BaseModel):
    steps: list[dict] = Field(default_factory=list, max_length=50)
    initial_url: str | None = None


@router.post("/recipe")
async def recipe(request: RecipeRequest, _: dict = Depends(get_current_admin)):
    if request.initial_url and not is_safe_url(request.initial_url):
        raise HTTPException(
            status_code=400, detail="SSRF check failed: Unauthorized internal access"
        )
    async with _SemaphoreSlot():
        result = await _agent.execute_recipe(steps=request.steps, initial_url=request.initial_url)
    return result
