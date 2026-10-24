import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from core.logging_config import logger

try:
    from playwright.async_api import Browser, Playwright, async_playwright
except ImportError:
    Browser = Any
    Playwright = Any
    async_playwright = None

_playwright_runner: Playwright | None = None
_global_browser: Browser | None = None
_browser_start_lock = asyncio.Lock()
_browser_max_pages = max(1, int(os.getenv("BROWSER_MAX_CONCURRENT_PAGES", "2")))
_browser_page_semaphore = asyncio.Semaphore(_browser_max_pages)


async def get_global_browser() -> Browser:
    """গ্লোবাল ব্রাউজার ইনস্ট্যান্স রিটার্ন করে (Lazy Initialization Pattern)"""
    global _playwright_runner, _global_browser
    if _global_browser is None:
        async with _browser_start_lock:
            if _global_browser is None:
                logger.info("🚀 Starting a new headless Global Chromium instance...")
                import sys

                current_module = sys.modules.get(
                    __name__, sys.modules.get("core.playwright_manager")
                )
                current_async_playwright = (
                    getattr(current_module, "async_playwright", async_playwright)
                    if current_module
                    else async_playwright
                )
                if not callable(current_async_playwright):
                    raise RuntimeError("Playwright is not installed.")
                _playwright_runner = await current_async_playwright().start()
                try:
                    _global_browser = await _playwright_runner.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                        ],
                    )
                except Exception:
                    await _playwright_runner.stop()
                    _playwright_runner = None
                    raise
    return _global_browser


async def browser_page_slot():
    """Return the bounded semaphore for callers that manage acquire/release."""
    return _browser_page_semaphore


@asynccontextmanager
async def browser_page_capacity() -> AsyncIterator[None]:
    """Reserve one bounded browser-work slot and always release it."""
    await _browser_page_semaphore.acquire()
    try:
        yield
    finally:
        _browser_page_semaphore.release()


async def shutdown_global_browser():
    """Lifespan Hook দ্বারা কল করা হবে - কন্টেইনার শাটডাউনের সময় জম্বি প্রসেস ক্লিন করে"""
    global _playwright_runner, _global_browser
    logger.info("🛡️ Initiating Playwright Global Lifespan Cleanup...")
    try:
        if _global_browser:
            logger.info("Closing active global Chromium engine...")
            import asyncio

            res = _global_browser.close()
            if asyncio.iscoroutine(res):
                await res
    except Exception as e:
        logger.critical(f"Error closing global browser: {e}")

    try:
        if _playwright_runner:
            logger.info("Stopping playwright runner core context...")
            import asyncio

            res = _playwright_runner.stop()
            if asyncio.iscoroutine(res):
                await res
    except Exception as e:
        logger.critical(f"Error stopping global playwright runner: {e}")
    finally:
        _global_browser = None
        _playwright_runner = None
        logger.info("✅ All Playwright OS processes terminated cleanly.")
