"""browser-use inspired agentic browser-control adapter for SupremeAI.
STATUS: orphaned — see docs/operations/MODULE_STATUS_REGISTRY.md (#449).

browser-use (AI-agent browser automation) থেকে নেওয়া মূল ধারণা: প্রাকৃতিক ভাষার টাস্ক
দিয়ে এজেন্ট নিজে ব্রাউজার খুলে ক্লিক/টাইপ/ফর্ম/এক্সট্র্যাক্ট করতে পারে — মানুষের মতো।

এখানে browser-use-কে optional dependency হিসেবে ব্যবহার করা হয় (flag + dep থাকলে
আসল ইঞ্জিন, নাহলে একটি zero-cost fallback যেটা বাস্তিকে ওয়েব স্ক্রাপিং করে)।

## Zero-cost Fallback Architecture (Premium disabled / absent)

যখন SUPREMEAI_BROWSER_USE_ENABLED=false (ডিফল্ট), তখন এই adapter নিম্নোক্ত
ক্রমে ফ্রি সেবাগুলো ট্রিতে ব্যবহার করে — যে কোনোটা কাজ করবে:

1. **Jina Reader API** (https://r.jina.ai/{url}) — কোনো API key লাগে না
   (ফ্রি টি হয় কিন্তু rate-limited)। একটি সিম্পল HTTP GET দিয়ে পুরো পেজের
   টেক্সট আকৃতে পাওয়া যায়।
2. **Firecrawl API** (FIRECRAWL_API_KEY থাকলে) — richer extraction,
   scrape এন্ডপয়িন্ট ব্যবহার করে।
3. **WebScraper** (httpx + BeautifulSoup, tools/browser/web_scraper.py) —
   pure HTTP স্ক্রাপিং, SSRF guard সহ।

এই সবগুলোতে LLM (ModelRouter) ব্যবহার করে টাস্ক থেকে URL এবং এক্সট্র্যাকশন
ইনস্ট্রাকশন পার্স করা হয়, তারপর স্ক্রাপ করা কন্টেন্ট থেকে স্ট্রাকচার্ড ডাটা বের করা হয়।
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from core.logging_config import logger
from integrations._flags import flag, import_available

_ENABLED_FLAG = "SUPREMEAI_BROWSER_USE_ENABLED"

# ── Free-tier web-reading providers ──────────────────────────────────────────
_JINA_READER_ENDPOINT = "https://r.jina.ai/"
_FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"

# Regex to extract the first URL from a natural-language task
_URL_RE = re.compile(r"https?://[^\s)'\">]+", re.IGNORECASE)


def _extract_url(task: str) -> str | None:
    """Pull the first http(s) URL out of a natural-language task string."""
    m = _URL_RE.search(task)
    return m.group(0) if m else None


def _jina_read(url: str, timeout: float = 15.0) -> dict[str, Any]:
    """Fetch article text via Jina Reader (free, no API key needed)."""
    try:
        resp = httpx.get(
            _JINA_READER_ENDPOINT + url,
            headers={"Accept": "text/plain", "User-Agent": "SupremeAI/2.0"},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return {"ok": True, "content": resp.text, "engine": "jina_reader"}
    except Exception as exc:
        logger.debug(f"Jina Reader failed for {url}: {exc}")
        return {"ok": False, "error": str(exc), "engine": "jina_reader"}


def _firecrawl_scrape(url: str, api_key: str, timeout: float = 15.0) -> dict[str, Any]:
    """Scrape a URL via Firecrawl API (requires FIRECRAWL_API_KEY)."""
    try:
        resp = httpx.post(
            _FIRECRAWL_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["text"], "wait_for": 2000},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        content = result.get("markdown") or result.get("text") or result.get("html", "")
        return {"ok": True, "content": content[:30000], "engine": "firecrawl"}
    except Exception as exc:
        logger.debug(f"Firecrawl failed for {url}: {exc}")
        return {"ok": False, "error": str(exc), "engine": "firecrawl"}


def _webscraper_fallback(url: str) -> dict[str, Any]:
    """Last-resort: use the project's existing WebScraper (httpx + BeautifulSoup)."""
    try:
        from tools.browser.web_scraper import WebScraper

        scraper = WebScraper()
        result = scraper.fetch_page(url)
        if result.get("success"):
            content = result.get("content", "") + "\n" + result.get("title", "")
            return {"ok": True, "content": content, "engine": "webscraper"}
        return {"ok": False, "error": result.get("error", "scrape failed"), "engine": "webscraper"}
    except Exception as exc:
        logger.debug(f"WebScraper fallback failed for {url}: {exc}")
        return {"ok": False, "error": str(exc), "engine": "webscraper"}


def _try_extract_with_llm(content: str, task: str) -> str | None:
    """Use the free-tier LLM router to extract structured data from scraped content.

    NOTE: This is a SYNC function that calls an ASYNC method via asyncio.run().
    The original code was missing `await` AND missing asyncio.run(), so the
    call returned a coroutine that was never awaited → silently no-op.
    """
    try:
        import asyncio

        from brain.model_router import ModelRouter

        router = ModelRouter()
        prompt = (
            f"Task: {task}\n\n"
            f"Scraped content:\n{content[:2000]}\n\n"
            "Extract the specific information requested by the task. "
            "Return ONLY the extracted data, no formatting or preamble."
        )
        # FIX: wrap async call in asyncio.run() (sync caller can't use `await`)
        result = asyncio.run(
            router.async_route_and_generate(prompt, task_type="reasoning", max_cost=0.02)
        )
        if isinstance(result, dict):
            return result.get("text", "")
        if isinstance(result, str):
            return result
    except Exception as exc:
        logger.debug(f"LLM extraction failed: {exc}")
    return None


def _free_browse(task: str, max_steps: int) -> dict[str, Any]:
    """Zero-cost browser-use replacement: scrape real web content without a browser.

    Tries Jina Reader → Firecrawl → WebScraper in order. If the task contains
    a URL, the scraped content is returned. If no URL is found, a plan is
    returned (backward-compatible with the original fallback behaviour).
    """
    steps: list[dict[str, Any]] = []
    url = _extract_url(task)

    if url:
        steps.append({"step": 1, "action": f"Navigate to {url}", "status": "running"})
        jr = _jina_read(url)
        if jr["ok"]:
            steps[-1]["status"] = "completed"
            steps[-1]["engine"] = "jina_reader"
            extracted = _try_extract_with_llm(jr["content"], task)
            return {
                "status": "ok",
                "engine": "fallback",
                "result": {
                    "plan": f"browser-task: {task}",
                    "steps_planned": max_steps,
                    "url": url,
                    "scraped_content": jr["content"][:5000],
                    "extracted_data": extracted or "Extraction unavailable — raw content returned.",
                    "steps_executed": steps,
                },
                "note": "Scraped via Jina Reader (free) + LLM extraction.",
            }
        steps.append(
            {"step": 2, "action": "Jina unavailable — trying Firecrawl", "status": "running"}
        )
        fc_key = os.getenv("FIRECRAWL_API_KEY", "")
        if fc_key:
            fc = _firecrawl_scrape(url, fc_key)
            if fc["ok"]:
                steps[-1]["status"] = "completed"
                steps[-1]["engine"] = "firecrawl"
                extracted = _try_extract_with_llm(fc["content"], task)
                return {
                    "status": "ok",
                    "engine": "fallback",
                    "result": {
                        "plan": f"browser-task: {task}",
                        "steps_planned": max_steps,
                        "url": url,
                        "scraped_content": fc["content"][:5000],
                        "extracted_data": extracted
                        or "Extraction unavailable — raw content returned.",
                        "steps_executed": steps,
                    },
                    "note": "Scraped via Firecrawl (free tier) + LLM extraction.",
                }
        steps.append(
            {"step": 3, "action": "Firecrawl unavailable — trying WebScraper", "status": "running"}
        )
        ws = _webscraper_fallback(url)
        if ws["ok"]:
            steps[-1]["status"] = "completed"
            steps[-1]["engine"] = "webscraper"
            extracted = _try_extract_with_llm(ws["content"], task)
            return {
                "status": "ok",
                "engine": "fallback",
                "result": {
                    "plan": f"browser-task: {task}",
                    "steps_planned": max_steps,
                    "url": url,
                    "scraped_content": ws["content"][:5000],
                    "extracted_data": extracted or "Extraction unavailable — raw content returned.",
                    "steps_executed": steps,
                },
                "note": "Scraped via WebScraper (httpx+BS4, zero-cost) + LLM extraction.",
            }
        steps[-1]["status"] = "failed"
        return {
            "status": "error",
            "engine": "fallback",
            "result": {"plan": f"browser-task: {task}", "steps_planned": max_steps},
            "error": f"All web scrapers failed for {url}. Last error: {ws.get('error', 'unknown')}",
        }
    # No URL → return plan (backward-compatible)
    plan_steps = [
        {"step": i, "action": f"Step {i} of task: {task[:80]}", "status": "planned"}
        for i in range(1, max_steps + 1)
    ]
    return {
        "status": "ok",
        "engine": "fallback",
        "result": {
            "plan": f"browser-task: {task}",
            "steps_planned": max_steps,
            "steps_executed": plan_steps,
        },
        "note": "browser-use upstream disabled — no URL detected, plan returned without live browser.",
    }


class BrowserUseAdapter:
    """Agentic browser automation bridging optional browser-use with a safe fallback."""

    def __init__(self) -> None:
        self.enabled_flag = _ENABLED_FLAG
        self._engine = None
        if flag(_ENABLED_FLAG) and import_available("browser_use"):
            try:
                from browser_use import Agent  # type: ignore[import-not-found]

                self._engine = Agent  # class kept for lazy instantiation
                logger.info("BrowserUseAdapter: upstream browser agent available.")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"BrowserUseAdapter: upstream import failed: {exc}")
                self._engine = None
        else:
            logger.info(
                "BrowserUseAdapter: upstream disabled/absent, using fallback planner "
                f"(flag={flag(_ENABLED_FLAG)}, dep={import_available('browser_use')})."
            )

    @property
    def active(self) -> bool:
        return self._engine is not None

    def run_task(self, task: str, llm: Any = None, max_steps: int = 10) -> dict[str, Any]:
        """Execute a natural-language browser task; returns {status, result, engine}."""
        if self.active and self._engine is not None:
            try:
                agent = self._engine(task=task, llm=llm, max_steps=max_steps)
                result = agent.run()
                return {"status": "ok", "engine": "upstream", "result": result}
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"BrowserUseAdapter: run failed: {exc}")
                return {"status": "error", "engine": "upstream", "error": str(exc)}

        # zero-cost fallback: real web scraping without a browser
        return _free_browse(task, max_steps)
