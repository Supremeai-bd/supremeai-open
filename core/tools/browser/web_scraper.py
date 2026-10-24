from typing import Any

import httpx
from bs4 import BeautifulSoup

from core.logging_config import logger
from core.security import is_safe_url


class WebScraper:
    def fetch_page(self, url: str) -> dict[str, Any]:
        logger.info(f"Fetching page: {url}")
        if not is_safe_url(url):
            logger.error(f"SSRF Attempt Blocked: {url}")
            return {
                "success": False,
                "error": "SSRF check failed: Unauthorized internal access",
                "url": url,
            }
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.string.strip() if soup.title else "No Title"
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
            # HTTP রিকোয়েস্ট সম্পর্কিত সুনির্দিষ্ট ত্রুটি ক্যাচ করা হলো
            logger.error(f"Failed to fetch {url}: {e}")
            return {"success": False, "error": str(e), "url": url}
