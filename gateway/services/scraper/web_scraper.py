"""
Web scraper with HTTP fallback (extracted from backend/tools/browser/web_scraper.py).
Uses httpx + BeautifulSoup for lightweight HTTP fetching when Playwright
is unavailable or overkill.

Issue #511 (BE-05): httpx runs with follow_redirects=False. fetch_page walks
each redirect hop itself and re-runs the full SSRF gate (parse-time
is_safe_url + resolved-IP is_safe_url_resolved) on EVERY target before it is
requested, closing the redirect-to-metadata and DNS-rebinding bypasses of the
old follow_redirects=True call.
"""

import os
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from core.logging_config import logger

# বাংলা মন্তব্য: Dual-path import — standalone scraper service-এ `security`
# top-level (conftest sys.path), backend এর ভিতরে embedded হলে
# `services.scraper.security`।
try:
    from security import is_safe_url, is_safe_url_resolved  # standalone scraper microservice
except ImportError:  # embedded in main backend
    from services.scraper.security import (  # type: ignore[no-redef]
        is_safe_url,
        is_safe_url_resolved,
    )

# 🔧 DYNAMIC CONFIG: User-Agent from env, with safe default
_DEFAULT_USER_AGENT = os.getenv(
    "SCRAPER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
_HTTP_TIMEOUT = float(os.getenv("SCRAPER_HTTP_TIMEOUT", "15.0"))  # 🔧 DYNAMIC timeout

# Issue #511: manual redirect walking — every hop is re-validated.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = int(os.getenv("SCRAPER_MAX_REDIRECTS", "5"))

_SSRF_BLOCKED_RESULT = {
    "success": False,
    "error": "SSRF check failed: Unauthorized internal access",
}


def _is_safe_to_fetch(url: str) -> bool:
    """Full request-time SSRF gate for the fetch path (issue #511).

    Layer 1: parse-time ``is_safe_url`` (scheme/hostname literals).
    Layer 2: ``is_safe_url_resolved`` — resolves the hostname and screens
    every A/AAAA record against private/loopback/link-local/metadata ranges.
    Called immediately before each httpx request: the initial URL and every
    redirect hop. Residual TOCTOU risk (httpx re-resolves at connect time)
    is documented in security.py.
    """
    return is_safe_url(url) and is_safe_url_resolved(url)


class WebScraper:
    def fetch_page(self, url: str) -> dict[str, Any]:
        logger.info(f"Fetching page: {url}")
        if not _is_safe_to_fetch(url):
            logger.error(f"SSRF Attempt Blocked: {url}")
            return {**_SSRF_BLOCKED_RESULT, "url": url}
        try:
            headers = {"User-Agent": _DEFAULT_USER_AGENT}  # 🔧 DYNAMIC
            # Issue #511: follow_redirects=False — httpx must never hop without
            # re-validation. Each redirect target is screened (parse-time +
            # resolved IPs) before the next request is issued.
            response: Any = None
            current_url = url
            for _hop in range(_MAX_REDIRECTS + 1):
                response = httpx.get(
                    current_url, headers=headers, timeout=_HTTP_TIMEOUT, follow_redirects=False
                )
                if response.status_code not in _REDIRECT_STATUSES:
                    break
                location = response.headers.get("location")
                if not location:
                    break  # malformed 3xx without Location — nothing to follow
                current_url = urljoin(current_url, location)
                if not _is_safe_to_fetch(current_url):
                    logger.error(f"SSRF Attempt Blocked (redirect target): {current_url}")
                    return {**_SSRF_BLOCKED_RESULT, "url": url}
            else:
                logger.error(f"Too many redirects (>{_MAX_REDIRECTS}) fetching: {url}")
                return {
                    "success": False,
                    "error": f"Too many redirects (>{_MAX_REDIRECTS})",
                    "url": url,
                }
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else "No Title"
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = " ".join(soup.get_text(separator=" ").split())[:3000]
            links = [a.get("href", "") for a in soup.find_all("a", href=True)][:20]
            return {
                "success": True,
                "url": url,
                "title": title,
                "content": text,
                "links": links,
                "status_code": response.status_code,
            }
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return {"success": False, "error": str(e), "url": url}
