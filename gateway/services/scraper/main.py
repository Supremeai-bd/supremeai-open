"""SupremeAI standalone scraper microservice.

Self-contained FastAPI app. Deployed as its own Docker image / Render service so
Chromium + Playwright never live in the main backend API image.

Endpoints:
  GET  /health  — liveness + capability probe
  POST /scrape  — lightweight HTTP scraping (httpx + BeautifulSoup)
  POST /browse  — full browser automation (Playwright/Chromium)
  POST /recipe  — scripted multi-step browser actions
"""

from __future__ import annotations

import os

try:
    from browser_agent import BrowserAgent, BrowseRequest
    from security import is_safe_url
    from web_scraper import WebScraper
except ImportError:
    from services.scraper.browser_agent import BrowserAgent, BrowseRequest
    from services.scraper.security import is_safe_url
    from services.scraper.web_scraper import WebScraper
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

MAX_CONCURRENCY = int(os.getenv("SCRAPER_MAX_CONCURRENCY", "3"))
TIMEOUT_SECONDS = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "45"))

app = FastAPI(title="SupremeAI Scraper", docs_url="/docs", redoc_url="/redoc")
router = APIRouter(tags=["scraper"])

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
        "service": "supremeai-scraper",
        "max_concurrency": MAX_CONCURRENCY,
        "timeout_seconds": TIMEOUT_SECONDS,
        "playwright_available": playwright_ok,
    }


@router.post("/scrape")
async def scrape(request: ScrapeRequest):
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not is_safe_url(request.url):
        raise HTTPException(
            status_code=400, detail="SSRF check failed: Unauthorized internal access"
        )
    # FIX (P1, review 2026-09-12): fetch_page is a SYNC httpx call (up to 15s
    # timeout). Calling it directly froze the single event loop — one slow target
    # stalled /browse, /recipe and /health for the whole service. Offload to a
    # worker thread so concurrent scrapes stay responsive.
    import asyncio as _asyncio

    result = await _asyncio.to_thread(_scraper.fetch_page, request.url)
    return result


@router.post("/browse")
async def browse(request: BrowseRequest):
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not is_safe_url(request.url):
        raise HTTPException(
            status_code=400, detail="SSRF check failed: Unauthorized internal access"
        )
    result = await _agent.navigate_and_interact(
        url=request.url,
        action=request.action or "fetch",
        selector=request.selector,
        text=request.text,
        wait_for=request.wait_for,
    )
    return result


class RecipeRequest(BaseModel):
    steps: list = []
    initial_url: str | None = None


@router.post("/recipe")
async def recipe(request: RecipeRequest):
    if request.initial_url and not is_safe_url(request.initial_url):
        raise HTTPException(
            status_code=400, detail="SSRF check failed: Unauthorized internal access"
        )
    result = await _agent.execute_recipe(steps=request.steps, initial_url=request.initial_url)
    return result


app.include_router(router)
