import asyncio
from typing import Any

# bs4 মডিউল না থাকলে যেন এজেন্ট ইমপোর্ট ক্র্যাশ না করে, সে জন্য সেফ ইমপোর্ট করা হলো।
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
from pydantic import BaseModel

from core.human_behavior import HumanBehaviorSimulators
from core.logging_config import logger
from core.playwright_manager import get_global_browser
from core.security import is_safe_url

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

from tools.browser.web_scraper import WebScraper


class BrowseRequest(BaseModel):
    url: str
    action: str | None = "fetch"  # fetch | click | screenshot | scroll | type
    selector: str | None = None
    text: str | None = None
    wait_for: str | None = None  # CSS selector to wait for


class BrowserAgent:
    """Controls browser actions — Playwright (full JS) and fallbacks."""

    def __init__(self, headless: bool = True):
        self._pw_browser = None
        self.headless = headless
        self.scraper = WebScraper()
        logger.info("Initialized BrowserAgent")

    async def execute_recipe(self, steps: list, initial_url: str | None = None) -> dict:
        """
        ডাটাবেজ বা স্কিল ম্যানেজার থেকে আসা JSON রেসিপি অ্যারে ডাইনামিকালি ইন্টারপ্রিট করবে।
        """
        if not callable(async_playwright):
            return {"status": "failed", "error": "Playwright is not installed"}

        logger.info(f"🎬 Initializing Dynamic Recipe Interpreter with {len(steps)} steps.")

        extracted_data = {}

        async with async_playwright() as p:
            # কন্টেইনার সেফ স্যান্ডবক্স মোডে ক্রমিয়াম লঞ্চ করা
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            try:
                # যদি ইনিশিয়াল কোনো ইউআরএল দেওয়া থাকে, প্রথমে সেখানে নেভিগেট করবে
                if initial_url:
                    logger.info(f"Navigating to initial target: {initial_url}")
                    await page.goto(initial_url, wait_until="networkidle", timeout=30000)

                # 🔄 ডায়নামিক রেসিপি লুপ স্টার্ট
                for index, step in enumerate(steps):
                    action = step.get("action", "").lower()
                    selector = step.get("selector")
                    value = step.get("value")

                    logger.debug(f"Processing Recipe Step [{index + 1}]: Action='{action}'")

                    if action == "navigate":
                        await page.goto(step["url"], wait_until="networkidle", timeout=30000)

                    elif action == "click":
                        await HumanBehaviorSimulators.natural_mouse_move_and_click(page, selector)

                    elif action == "type":
                        # স্মার্ট ক্ল্যাম্পিং: বড় টেক্সট হলে ডিরেক্ট পেস্ট/ফিল করবে, ছোট হলে হিউম্যান টাইপিং
                        if len(str(value)) > 50:
                            await page.wait_for_selector(selector, state="visible")
                            await page.fill(selector, str(value))
                        else:
                            await HumanBehaviorSimulators.natural_type(page, selector, str(value))

                    elif action == "wait":
                        # যদি ভ্যালু সংখ্যা হয় তবে সেকেন্ড স্লিপ করবে, টেক্সট হলে সিলেক্টর visible হওয়া পর্যন্ত ওয়েট করবে
                        if str(value).isdigit():
                            await asyncio.sleep(float(value))
                        else:
                            await page.wait_for_selector(str(value), state="visible", timeout=15000)

                    elif action == "extract":
                        await page.wait_for_selector(selector, state="visible", timeout=10000)

                        # যদি টেবিল ডেটা বা মাল্টিপল এলিমেন্ট স্ক্র্যাপ করতে বলা হয়
                        if step.get("type") == "list":
                            elements = await page.query_selector_all(selector)
                            extracted_data[selector] = [await el.inner_text() for el in elements]
                        else:
                            # ডিফল্ট সিঙ্গেল এলিমেন্ট টেক্সট এক্সট্রাকশন
                            extracted_data[selector] = await page.inner_text(selector)

                        logger.success(f"Successfully extracted target data node from: {selector}")

                # সমস্ত স্টেপ সফলভাবে শেষ হলে
                return {"status": "success", "data": extracted_data}

            except (TimeoutError, Exception) as e:
                # প্লে-রাইট বা অন্যান্য অপ্রত্যাশিত ত্রুটি সুনির্দিষ্টভাবে ক্যাচ করা হলো
                logger.error(f"❌ Recipe Interpreter crashed mid-execution: {e!s}")
                return {"status": "failed", "error": str(e), "step": index + 1}

            finally:
                # প্লে-রাইট মেমোরি লিক এবং অরফ্যান প্রসেস রুখতে কড়া ক্লিনআপ
                await page.close()
                await context.close()
                await browser.close()
                logger.info("🗑️ Playwright Sandbox context cleaned up successfully.")

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

        browser = await get_global_browser()
        if not browser:
            # Fallback to httpx
            return self.scraper.fetch_page(url)

        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=10000)

            if action == "click" and selector:
                await page.click(selector)
                await page.wait_for_load_state("networkidle", timeout=10000)

            elif action == "type" and selector and text:
                await page.fill(selector, text)

            elif action == "scroll":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)

            elif action == "screenshot":
                screenshot = await page.screenshot(type="png")
                import base64

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
            soup = BeautifulSoup(content_html, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text_content = " ".join(soup.get_text(separator=" ").split())[:3000]
            links = [a.get("href", "") for a in soup.find_all("a", href=True)][:20]
            current_url = page.url

            return {
                "success": True,
                "url": current_url,
                "title": title,
                "content": text_content,
                "links": links,
                "action": action,
            }
        except (TimeoutError, Exception) as e:
            # প্লে-রাইট সম্পর্কিত যেকোনো সাধারণ ত্রুটি এখানে ধরা হলো
            logger.error(f"Playwright action failed: {e}")
            return {"success": False, "error": str(e), "url": url}
        finally:
            # MEMLEAK-005: Enforce hard timeout on page.close() to prevent zombie pages
            try:
                await asyncio.wait_for(page.close(), timeout=2.0)
            except Exception as e:
                logger.warning(f"Failed to close Playwright page cleanly within timeout: {e}")
