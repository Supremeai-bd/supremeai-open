"""SupremeAI Standalone Scraper & Gemini Cookie Relay Entrypoint.

Provides the FastAPI application entrypoint for Render (uvicorn main:app)
and local deployments. Seamlessly integrates the lightweight Gemini Cookie
Relay engine (server.py) with optional scraping routes.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("supremeai.scraper")

# Ensure local directory is in path
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

# Import primary application from server.py (Cookie Relay Engine)
try:
    from server import app, relay_engine, duck_engine, ChatRequest
except ImportError:
    from browser.server import app, relay_engine, duck_engine, ChatRequest  # type: ignore

# Register optional browser scraper routes if dependencies are available
try:
    try:
        from browser_agent import BrowserAgent, BrowseRequest
        from security import is_safe_url
        from web_scraper import WebScraper
    except ImportError:
        from services.scraper.browser_agent import BrowserAgent, BrowseRequest
        from services.scraper.security import is_safe_url
        from services.scraper.web_scraper import WebScraper

    from fastapi import HTTPException
    from pydantic import BaseModel

    MAX_CONCURRENCY = int(os.getenv("SCRAPER_MAX_CONCURRENCY", "3"))
    TIMEOUT_SECONDS = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "45"))

    _scraper = WebScraper()
    _agent = BrowserAgent(headless=True)

    class ScrapeRequest(BaseModel):
        url: str
        extraction_prompt: str | None = None

    class RecipeRequest(BaseModel):
        steps: list = []
        initial_url: str | None = None

    @app.post("/scrape", tags=["scraper"])
    async def scrape(request: ScrapeRequest):
        if not request.url:
            raise HTTPException(status_code=400, detail="URL is required")
        if not is_safe_url(request.url):
            raise HTTPException(
                status_code=400, detail="SSRF check failed: Unauthorized internal access"
            )
        import asyncio
        return await asyncio.to_thread(_scraper.fetch_page, request.url)

    @app.post("/browse", tags=["scraper"])
    async def browse(request: BrowseRequest):
        if not request.url:
            raise HTTPException(status_code=400, detail="URL is required")
        if not is_safe_url(request.url):
            raise HTTPException(
                status_code=400, detail="SSRF check failed: Unauthorized internal access"
            )
        return await _agent.navigate_and_interact(
            url=request.url,
            action=request.action or "fetch",
            selector=request.selector,
            text=request.text,
            wait_for=request.wait_for,
        )

    @app.post("/recipe", tags=["scraper"])
    async def recipe(request: RecipeRequest):
        if request.initial_url and not is_safe_url(request.initial_url):
            raise HTTPException(
                status_code=400, detail="SSRF check failed: Unauthorized internal access"
            )
        return await _agent.execute_recipe(steps=request.steps, initial_url=request.initial_url)

    logger.info("Scraper browser routes registered successfully")

except Exception as _scraper_err:
    logger.info(
        f"Scraper engine dependencies unavailable ({_scraper_err}); "
        "operating in lightweight Gemini Cookie Relay mode."
    )

