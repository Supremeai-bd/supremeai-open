"""
Browser automation agent for the scraper microservice.
Extracted from backend/tools/ai_agents/browser_agent.py and backend/tools/browser/playwright_browser_agent.py.
Uses a per-request Playwright sandbox (no global singleton) to avoid
blocking the main backend worker.
"""

import asyncio
import base64
import os
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[misc, assignment]

from pydantic import BaseModel

from core.human_behavior import HumanBehaviorSimulators
from core.logging_config import logger

# বাংলা মন্তব্য: Dual-path import — standalone scraper-এ top-level `security`/
# `web_scraper`, backend-এ embedded হলে `services.scraper.*`। Scraper-এর নিজস্ব
# self-contained security.py ব্যবহার হয় (core.security টানে না — SSRF-minimal)।
try:
    from security import is_safe_url  # standalone scraper microservice
except ImportError:  # embedded in main backend
    from services.scraper.security import is_safe_url  # type: ignore[no-redef]

try:
    from web_scraper import WebScraper  # standalone scraper microservice
except ImportError:  # embedded in main backend
    from services.scraper.web_scraper import WebScraper  # type: ignore[no-redef]

# 🔧 DYNAMIC BROWSER CONFIG: All values from environment variables
_BROWSER_VIEWPORT_W = int(os.getenv("BROWSER_VIEWPORT_WIDTH", "1280"))
_BROWSER_VIEWPORT_H = int(os.getenv("BROWSER_VIEWPORT_HEIGHT", "1080"))
_BROWSER_PAGE_TIMEOUT = int(os.getenv("BROWSER_PAGE_TIMEOUT_MS", "30000"))
_BROWSER_SELECTOR_TIMEOUT = int(os.getenv("BROWSER_SELECTOR_TIMEOUT_MS", "10000"))
_BROWSER_NETWORK_TIMEOUT = int(os.getenv("BROWSER_NETWORK_IDLE_TIMEOUT_MS", "10000"))
_BROWSER_USER_AGENT = os.getenv(
    "BROWSER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None  # type: ignore[assignment]


class BrowseRequest(BaseModel):
    url: str
    action: str | None = "fetch"
    selector: str | None = None
    text: str | None = None
    wait_for: str | None = None


class BrowserAgent:
    """Controls browser actions — Playwright with httpx fallback.

    Self-contained: does NOT import core.playwright_manager (which uses a
    global singleton that blocks the main backend worker).
    """

    def __init__(self, headless: bool = True):
        self._pw_browser = None
        self.headless = headless
        self.scraper = WebScraper()
        # Concurrency guard — prevent OOM on Render free tier (512MB RAM)
        _max = int(os.getenv("SCRAPER_MAX_CONCURRENCY", "3"))
        self._semaphore = asyncio.Semaphore(_max)
        logger.info(
            f"Initialized BrowserAgent (max_concurrency={_max}, "
            f"viewport={_BROWSER_VIEWPORT_W}x{_BROWSER_VIEWPORT_H}) for scraper microservice"
        )

    async def navigate_and_interact(
        self,
        url: str,
        action: str = "fetch",
        selector: str | None = None,
        text: str | None = None,
        wait_for: str | None = None,
    ) -> dict[str, Any]:
        if not is_safe_url(url):
            logger.error(f"SSRF Attempt Blocked: {url}")
            return {
                "success": False,
                "error": "SSRF check failed: Unauthorized internal access",
                "url": url,
            }

        if not callable(async_playwright):
            logger.warning("Playwright not installed — falling back to httpx scraper")
            return self.scraper.fetch_page(url)

        # Per-request sandbox — no shared global state
        async with self._semaphore, async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(  # 🔧 DYNAMIC config
                viewport={"width": _BROWSER_VIEWPORT_W, "height": _BROWSER_VIEWPORT_H},
                user_agent=_BROWSER_USER_AGENT,
            )
            page = await context.new_page()
            # Feature 3 (old plan): stealth fingerprint — canvas/WebGL noise,
            # webdriver trace removal, realistic viewport (never raises)
            await HumanBehaviorSimulators.apply_stealth_fingerprint(page)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=_BROWSER_PAGE_TIMEOUT)

                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=_BROWSER_SELECTOR_TIMEOUT)

                if action == "click" and selector:
                    await page.click(selector)
                    await page.wait_for_load_state("networkidle", timeout=_BROWSER_NETWORK_TIMEOUT)

                elif action == "type" and selector and text:
                    await page.fill(selector, text)

                elif action == "scroll":
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)

                elif action == "screenshot":
                    screenshot = await page.screenshot(type="png")
                    b64 = base64.b64encode(screenshot).decode()
                    title = await page.title()
                    return {
                        "success": True,
                        "url": url,
                        "title": title,
                        "screenshot_base64": b64,
                    }

                title = await page.title()
                content_html = await page.content()
                if BeautifulSoup is not None:
                    soup = BeautifulSoup(content_html, "html.parser")
                    for tag in soup(["script", "style"]):
                        tag.decompose()
                    text_content = " ".join(soup.get_text(separator=" ").split())[:3000]
                    links = [a.get("href", "") for a in soup.find_all("a", href=True)][:20]
                else:
                    text_content = await page.inner_text("body")
                    links = []

                current_url = page.url
                return {
                    "success": True,
                    "url": current_url,
                    "title": title,
                    "content": text_content,
                    "links": links,
                    "action": action,
                }
            except (TimeoutError, Exception) as e:  # noqa: BLE001
                logger.error(f"Playwright action failed: {e}")
                return {"success": False, "error": str(e), "url": url}
            finally:
                await page.close()
                await context.close()
                await browser.close()

    async def execute_recipe(self, steps: list, initial_url: str | None = None) -> dict:
        """Execute a recipe of browser actions sequentially."""
        if not callable(async_playwright):
            return {"status": "failed", "error": "Playwright is not installed"}

        if not steps:
            return {"status": "success", "data": {}}

        logger.info(f"Initializing Recipe Interpreter with {len(steps)} steps.")
        extracted_data: dict[str, Any] = {}

        async with self._semaphore, async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport={
                    "width": _BROWSER_VIEWPORT_W,
                    "height": _BROWSER_VIEWPORT_H,
                },  # 🔧 DYNAMIC
                user_agent=_BROWSER_USER_AGENT,  # 🔧 DYNAMIC
            )
            page = await context.new_page()
            # Feature 3 (old plan): stealth fingerprint for recipe execution too
            await HumanBehaviorSimulators.apply_stealth_fingerprint(page)
            index = -1  # Guard: prevents NameError in except if loop never runs

            try:
                if initial_url:
                    logger.info(f"Navigating to initial target: {initial_url}")
                    await page.goto(initial_url, wait_until="networkidle", timeout=30000)

                for index, step in enumerate(steps):
                    action = step.get("action", "").lower()
                    selector = step.get("selector")
                    value = step.get("value")

                    if action == "navigate":
                        await page.goto(step["url"], wait_until="networkidle", timeout=30000)
                    elif action == "click" and selector:
                        await page.click(selector)
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    elif action == "type" and selector and value:
                        await page.fill(selector, str(value))
                    elif action == "wait":
                        if str(value).isdigit():
                            await asyncio.sleep(float(value))
                        else:
                            await page.wait_for_selector(str(value), state="visible", timeout=15000)
                    elif action == "extract" and selector:
                        await page.wait_for_selector(selector, state="visible", timeout=10000)
                        if step.get("type") == "list":
                            elements = await page.query_selector_all(selector)
                            extracted_data[selector] = [await el.inner_text() for el in elements]
                        else:
                            extracted_data[selector] = await page.inner_text(selector)
                        logger.success(f"Extracted data from: {selector}")

                return {"status": "success", "data": extracted_data}
            except (TimeoutError, Exception) as e:  # noqa: BLE001
                logger.error(f"Recipe Interpreter crashed at step {index + 1}: {e!s}")
                return {"status": "failed", "error": str(e), "step": index + 1}
            finally:
                await page.close()
                await context.close()
                await browser.close()
                logger.info("Playwright sandbox context cleaned up.")
