"""SupremeAI Browser Service — Phase 11 (ROADMAP §33).

বাংলা: Browser/scraper আলাদা microservice. Playwright এখানে, Core API-তে নয়।
"""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("supremeai.browser")
logger.info(f">>> booting browser service (env={os.getenv('ENV', 'production')})")


async def scrape(request: web.Request) -> web.Response:
    """Phase 11 — scrape a URL (ROADMAP §33)."""
    data = await request.json()
    url = data.get("url", "")
    if not url:
        return web.json_response({"ok": False, "error": "url required"}, status=400)
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            title = await page.title()
            content = await page.content()
            await browser.close()
        return web.json_response(
            {"ok": True, "url": url, "title": title, "content_length": len(content)}
        )
    except ImportError:
        return web.json_response({"ok": False, "error": "playwright not installed"}, status=500)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def screenshot(request: web.Request) -> web.Response:
    """Take screenshot of a URL."""
    data = await request.json()
    url = data.get("url", "")
    if not url:
        return web.json_response({"ok": False, "error": "url required"}, status=400)
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            screenshot_bytes = await page.screenshot()
            await browser.close()
        return web.Response(body=screenshot_bytes, content_type="image/png")
    except ImportError:
        return web.json_response({"ok": False, "error": "playwright not installed"}, status=500)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "supremeai-browser"})


app = web.Application()
app.router.add_get("/health", health)
app.router.add_post("/scrape", scrape)
app.router.add_post("/screenshot", screenshot)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))
    web.run_app(app, host="0.0.0.0", port=port)
