"""SupremeAI Browser Service — Phase 11 (ROADMAP §33).

বাংলা: Browser/scraper আলাদা microservice. Playwright এখানে, Core API-তে নয়।
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

from aiohttp import web

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("supremeai.browser")
logger.info(f">>> booting browser service (env={os.getenv('ENV', 'production')})")

_BROWSER_SERVICE_TOKEN = os.getenv("BROWSER_SERVICE_TOKEN", "").strip()
_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.getenv("BROWSER_ALLOWED_HOSTS", "").split(",")
    if host.strip()
}
_MAX_RESPONSE_BYTES = int(os.getenv("BROWSER_MAX_RESPONSE_BYTES", "2000000"))
_BROWSER_SEMAPHORE = asyncio.Semaphore(int(os.getenv("BROWSER_MAX_CONCURRENCY", "2")))


def _authorized(request: web.Request) -> bool:
    """Fail closed in production; local development may explicitly opt out."""
    if not _BROWSER_SERVICE_TOKEN:
        return os.getenv("ENV", "production").lower() in {"development", "test"}
    return request.headers.get("authorization", "") == f"Bearer {_BROWSER_SERVICE_TOKEN}"


def _is_private_host(host: str) -> bool:
    try:
        return (
            ipaddress.ip_address(host).is_private
            or ipaddress.ip_address(host).is_loopback
            or ipaddress.ip_address(host).is_link_local
        )
    except ValueError:
        return False


async def _safe_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only public http(s) URLs are allowed")
    host = parsed.hostname.lower().rstrip(".")
    if _ALLOWED_HOSTS and host not in _ALLOWED_HOSTS:
        raise ValueError("destination host is not allowlisted")
    if _is_private_host(host):
        raise ValueError("private destination is not allowed")
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("destination could not be resolved") from exc
    for _, _, _, _, sockaddr in addresses:
        if _is_private_host(sockaddr[0]):
            raise ValueError("destination resolves to a private address")
    return parsed.geturl()


async def _guard_browser_route(route) -> None:
    """Revalidate every browser request, including redirect destinations and subresources."""
    try:
        await _safe_url(route.request.url)
    except ValueError:
        await route.abort()
    else:
        await route.continue_()


async def scrape(request: web.Request) -> web.Response:
    """Phase 11 — scrape a URL (ROADMAP §33)."""
    if not _authorized(request):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    data = await request.json()
    url = data.get("url", "")
    if not url:
        return web.json_response({"ok": False, "error": "url required"}, status=400)
    try:
        url = await _safe_url(str(url))
        async with _BROWSER_SEMAPHORE:
            return await _scrape_url(url)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    except Exception:
        logger.exception("browser scrape failed")
        return web.json_response({"ok": False, "error": "browser operation failed"}, status=502)


async def _scrape_url(url: str) -> web.Response:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route("**/*", _guard_browser_route)
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            title = await page.title()
            content = (await page.content())[:_MAX_RESPONSE_BYTES]
            await browser.close()
        return web.json_response(
            {"ok": True, "url": url, "title": title, "content_length": len(content)}
        )
    except ImportError:
        return web.json_response({"ok": False, "error": "playwright not installed"}, status=500)
    except Exception:
        logger.exception("browser scrape execution failed")
        return web.json_response({"ok": False, "error": "browser operation failed"}, status=502)


async def screenshot(request: web.Request) -> web.Response:
    """Take screenshot of a URL."""
    if not _authorized(request):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    data = await request.json()
    url = data.get("url", "")
    if not url:
        return web.json_response({"ok": False, "error": "url required"}, status=400)
    try:
        url = await _safe_url(str(url))
        async with _BROWSER_SEMAPHORE:
            return await _screenshot_url(url)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    except Exception:
        logger.exception("browser screenshot failed")
        return web.json_response({"ok": False, "error": "browser operation failed"}, status=502)


async def _screenshot_url(url: str) -> web.Response:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route("**/*", _guard_browser_route)
            await page.goto(url, timeout=30000)
            screenshot_bytes = await page.screenshot()
            await browser.close()
        return web.Response(body=screenshot_bytes, content_type="image/png")
    except ImportError:
        return web.json_response({"ok": False, "error": "playwright not installed"}, status=500)
    except Exception:
        logger.exception("browser screenshot execution failed")
        return web.json_response({"ok": False, "error": "browser operation failed"}, status=502)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "supremeai-browser"})


app = web.Application()
app.router.add_get("/health", health)
app.router.add_post("/scrape", scrape)
app.router.add_post("/screenshot", screenshot)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))
    web.run_app(app, host="0.0.0.0", port=port)
