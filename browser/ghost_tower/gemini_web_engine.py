"""
gemini_web_engine.py — Live Playwright Browser Scraper for gemini.google.com ($0 Web Relay)
==========================================================================================
Uses Microsoft Edge (Chromium) persistent session so it NEVER locks or conflicts
with your open Google Chrome browser. Controls the browser, types the prompt into
gemini.google.com, waits for the response, and extracts the answer with ZERO API cost.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext, Page

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger("ghost_tower.gemini_web")
USER_DATA_DIR = os.path.expanduser(r"~\.gemini_isolated_session")


class GeminiWebEngine:
    def __init__(self, headless: bool = False, user_data_dir: str = USER_DATA_DIR):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._lock = asyncio.Lock()
        self._is_ready = False

    async def initialize(self):
        """Starts persistent Chromium (msedge) and navigates to gemini.google.com/app."""
        if self._is_ready and self.page and not self.page.is_closed():
            return

        logger.info(f"Initializing Gemini Web Engine with profile: {self.user_data_dir}")
        self.playwright = await async_playwright().start()
        
        os.makedirs(self.user_data_dir, exist_ok=True)
        
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            channel="msedge",
            headless=self.headless,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1280, "height": 800},
        )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        
        logger.info("Navigating to https://gemini.google.com/app ...")
        await self.page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        
        await asyncio.sleep(3)
        self._is_ready = True
        logger.info("Gemini Web Engine initialized successfully!")

    async def check_login_status(self) -> dict:
        """Checks if the user is logged into their Google account on Gemini."""
        if not self.page or self.page.is_closed():
            await self.initialize()

        current_url = self.page.url
        title = await self.page.title()

        # Check for visible Sign in buttons
        sign_in_btns = await self.page.locator('button:has-text("Sign in"), a:has-text("Sign in")').all()
        has_visible_signin = False
        for btn in sign_in_btns:
            try:
                if await btn.is_visible():
                    has_visible_signin = True
                    break
            except Exception:
                pass

        has_chat_input = await self.page.query_selector('rich-textarea, div[contenteditable="true"], textarea') is not None
        has_avatar = await self.page.query_selector('a[aria-label*="Google Account"], img[alt*="Google Account"]') is not None

        is_logged_in = (has_avatar or (has_chat_input and not has_visible_signin)) and "accounts.google.com" not in current_url

        return {
            "is_logged_in": is_logged_in,
            "url": current_url,
            "title": title,
            "needs_login": not is_logged_in,
        }

    async def ask(self, prompt: str, timeout_seconds: int = 60) -> str:
        """Types prompt into gemini.google.com, submits, and returns the response."""
        async with self._lock:
            if not self._is_ready or not self.page or self.page.is_closed():
                await self.initialize()

            if "gemini.google.com" not in self.page.url:
                logger.info("Navigating back to https://gemini.google.com/app")
                await self.page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                await asyncio.sleep(2)

            login_info = await self.check_login_status()
            if not login_info["is_logged_in"]:
                # Attempt autonomous login from vault if credentials exist
                logger.info("Session not logged in. Attempting autonomous login from vault...")
                try:
                    from auto_login import auto_login_gemini
                    auto_success = await auto_login_gemini(self.page)
                except Exception as login_err:
                    logger.warning(f"Auto-login attempt encountered: {login_err}")
                    auto_success = False

                if not auto_success:
                    return (
                        "⚠️ [ACTION REQUIRED]: Please log in to your Google Account on the opened browser window. "
                        "Once you log in to gemini.google.com, it will stay permanently saved!"
                    )

            logger.info(f"Submitting prompt to gemini.google.com: {prompt[:60]}...")

            input_selector = 'div.ql-editor, div[contenteditable="true"], textarea, rich-textarea p'
            try:
                await self.page.wait_for_selector(input_selector, timeout=10000)
            except Exception:
                await self.page.click('rich-textarea, .input-area', timeout=5000)

            input_elem = await self.page.query_selector(input_selector)
            if not input_elem:
                return "⚠️ Could not locate Gemini chat input field. Please check the browser window."

            await input_elem.click()
            await asyncio.sleep(0.1)
            
            # Fast synthetic fill (<100ms) with typing fallback
            try:
                await input_elem.fill(prompt)
            except Exception:
                await self.page.keyboard.type(prompt, delay=5)
            await asyncio.sleep(0.2)

            prev_responses = await self.page.query_selector_all('model-response, .model-response-text, message-content')
            prev_count = len(prev_responses)

            send_btn = await self.page.query_selector('button[aria-label*="Send"], button.send-button, .send-button-container button')
            if send_btn and await send_btn.is_enabled():
                await send_btn.click()
            else:
                await self.page.keyboard.press("Enter")

            logger.info("Prompt submitted. Waiting for Gemini response...")

            start_time = asyncio.get_event_loop().time()
            new_response_elem = None
            
            while asyncio.get_event_loop().time() - start_time < timeout_seconds:
                current_responses = await self.page.query_selector_all('model-response, .model-response-text, message-content')
                if len(current_responses) > prev_count:
                    new_response_elem = current_responses[-1]
                    break
                await asyncio.sleep(0.5)

            if not new_response_elem:
                current_responses = await self.page.query_selector_all('model-response, .model-response-text, message-content')
                if current_responses:
                    new_response_elem = current_responses[-1]
                else:
                    return "⚠️ Timeout waiting for Gemini response to start generating."

            logger.info("Streaming started. Waiting for completion...")
            await asyncio.sleep(2)
            
            last_text = ""
            stable_count = 0
            
            while asyncio.get_event_loop().time() - start_time < timeout_seconds:
                text = await new_response_elem.inner_text()
                text = text.strip()
                
                stop_btn = await self.page.query_selector('button[aria-label*="Stop"], button:has-text("Stop response")')
                
                if text and text == last_text:
                    stable_count += 1
                    if stable_count >= 4 and not stop_btn:
                        break
                else:
                    stable_count = 0
                    last_text = text

                await asyncio.sleep(0.5)

            if not last_text:
                last_text = await new_response_elem.inner_text()

            logger.info(f"Response successfully extracted ({len(last_text)} chars).")
            return last_text

    async def close(self):
        """Closes browser context and playwright."""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        self._is_ready = False
