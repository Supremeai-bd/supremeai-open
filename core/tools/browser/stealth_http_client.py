import random
from typing import Any

import httpx

from core.logging_config import logger
from tools.security_tools.proxy_manager import ProxyManager

# List of typical browser User-Agents for stealth scraping emulation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class StealthHTTPClient:
    """
    HTTP client wrapper for executing stealth, anonymized web requests.
    Enforces proxy rotation, fallback retries, and browser headers emulation.
    """

    def __init__(self, proxy_manager: ProxyManager | None = None):
        self.proxy_manager = proxy_manager or ProxyManager()

    def _get_headers(self, custom_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        if custom_headers:
            headers.update(custom_headers)
        return headers

    async def request(
        self, method: str, url: str, retries: int = 3, **kwargs: Any
    ) -> httpx.Response:
        # বাংলা মন্তব্য: প্রতিটি রিকোয়েস্টের জন্য নতুন প্রক্সি নির্বাচন ও র্যান্ডম ব্রাউজার হেডার এমুলেট করা হচ্ছে।
        headers = self._get_headers(kwargs.pop("headers", None))

        for attempt in range(retries):
            proxy = self.proxy_manager.get_next_proxy()
            client_kwargs = {
                "headers": headers,
                "timeout": kwargs.pop("timeout", 10.0),
                **kwargs,
            }
            proxy_kwarg = {"proxy": proxy} if proxy else {}
            if proxy:
                logger.info(f"Stealth request via proxy: {proxy} (Attempt {attempt + 1}/{retries})")
            else:
                logger.info(f"Stealth request without proxy (Attempt {attempt + 1}/{retries})")

            try:
                async with httpx.AsyncClient(timeout=15.0, **proxy_kwarg) as client:
                    response = await client.request(method, url, **client_kwargs)
                    response.raise_for_status()
                    return response
            except Exception as e:
                logger.warning(f"Request attempt {attempt + 1} failed: {e}")
                if proxy:
                    self.proxy_manager.report_failed_proxy(proxy)

                if attempt == retries - 1:
                    raise e from e

        raise httpx.RequestError("Stealth requests failed all retries.")

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)
