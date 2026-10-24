"""Bolt.new deep-link automation adapter — MESH-5 Phase C (issue #943).

বাংলা সারসংক্ষেপ:
------------------
Tower → Bolt.new সরাসরি task-পুশ: spec টাইপ → "Export to GitHub" →
`mesh/task-{id}` branch → PR URL সংগ্রহ। সেশন পুনঃব্যবহারের জন্য
:class:`core.browser_session_vault.BrowserSessionVault` ব্যবহার করে।

নকশা-নোট:
- playwright **optional dependency** — না থাকলে adapter গঠন হয়, কিন্তু
  `available` মিথ্যা; ব্যবহারের চেষ্টায় স্পষ্ট AdapterUnavailable (ভান নেই)।
- sync API (spec অনুযায়ী) — নিজস্ব thread-বিচ্ছিন্ন প্রসেসে চালানোর জন্য
  কলার দায়িত্ব; এখানে শুধু সরল sequential ফ্লো।
- selectors ক্লাস-অ্যাট্রিবিউট — DOM বদলালে শুধু এগুলো বদলাবে; টেস্টে
  fake page দিয়ে পুরো ফ্লো যাচাই করা যায় (নেটওয়ার্ক/ব্রাউজার লাগে না)।
"""

from __future__ import annotations

import time
from typing import Any

from core.browser_session_vault import BrowserSessionVault
from core.logging_config import logger
from mcp_adapters.adapters import PLAYWRIGHT_AVAILABLE


class AdapterUnavailable(RuntimeError):
    """playwright ইনস্টল নেই — deep-link অটোমেশন অসম্ভব (fail-loud)।"""


class BoltAdapter:
    """Bolt.new সেশন-সচেতন deep-link অটোমেশন।"""

    BOLT_NEW_URL = "https://bolt.new/new"
    # DOM সিলেক্টর — এক জায়গায় কেন্দ্রীভূত (site পরিবর্তনে শুধু এগুলো টিউন)।
    SELECTOR_CHAT_INPUT = "textarea, div[contenteditable='true']"
    SELECTOR_EXPORT_BUTTON = "button:has-text('Export to GitHub')"
    SELECTOR_BRANCH_INPUT = "input[placeholder*='branch' i]"
    SELECTOR_PR_LINK = "a[href*='github.com']"

    def __init__(
        self,
        session_mgr: BrowserSessionVault | None = None,
        user_data_dir: str | None = None,
        service: str = "bolt",
    ) -> None:
        self.session_mgr = session_mgr
        self.service = service
        self.user_data_dir = user_data_dir
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    @property
    def available(self) -> bool:
        return PLAYWRIGHT_AVAILABLE

    def _require_playwright(self) -> None:
        if not PLAYWRIGHT_AVAILABLE:
            raise AdapterUnavailable(
                "playwright is not installed — Bolt deep-link automation unavailable"
            )

    def start(self) -> None:
        """ব্রাউজার চালু + ভল্টের সেশন state প্রয়োগ (থাকলে)।"""
        self._require_playwright()
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        kwargs: dict[str, Any] = {"headless": True}
        if self.user_data_dir:
            kwargs["user_data_dir"] = self.user_data_dir
        self._browser = self._playwright.chromium.launch_persistent_context(**kwargs)
        self._page = self._browser.pages[0] if self._browser.pages else self._browser.new_page()
        if self.session_mgr and self.session_mgr.is_session_valid(self.service):
            state = self.session_mgr.load_state(self.service)
            self._page.context.add_cookies(state.get("cookies", []))
            logger.info("[BoltAdapter] restored session cookies from vault")

    def stop(self) -> None:
        """ব্রাউজার বন্ধ + (ঐচ্ছিক) বর্তমান storage ভল্টে সেভ।"""
        if self._browser:
            try:
                if self.session_mgr and self._page:
                    self._capture_and_save()
            finally:
                self._browser.close()
                self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def _capture_and_save(self) -> None:
        """বর্তমান page থেকে cookies+localStorage ভল্টে সেভ (best-effort)।"""
        try:
            cookies = self._page.context.cookies()
            storage: dict[str, dict[str, str]] = {}
            origin = None
            try:
                origin = self._page.url.split("/")[2] if self._page.url.count("/") >= 2 else None
            except Exception:
                origin = None
            if origin:
                raw = self._page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
                storage[f"https://{origin}"] = raw or {}
            if cookies or storage:
                self.session_mgr.save_session(self.service, cookies, storage)
        except Exception as exc:  # best-effort — সেভ-ব্যর্থতা close আটকাবে না
            logger.warning(f"[BoltAdapter] session save failed: {exc}")

    # ── Public flow (#943 spec) ──────────────────────────────────────────────
    def is_session_valid(self) -> bool:
        """bolt.new-এ গিয়ে লগইন-পেজ/captcha না দেখলে বৈধ।"""
        self._require_playwright()
        if not self._page:
            self.start()
        self._page.goto(self.BOLT_NEW_URL, wait_until="domcontentloaded", timeout=45000)
        url = self._page.url.lower()
        if "login" in url or "captcha" in url or "signin" in url:
            return False
        # ভল্ট heuristic সহায়ক প্রমাণ
        if self.session_mgr and not self.session_mgr.is_session_valid(self.service):
            return False
        return True

    def push_task(self, task_id: str, spec: str, branch: str) -> str:
        """spec → Bolt → Export → branch → PR URL রিটার্ন।"""
        self._require_playwright()
        if not self._page:
            self.start()
        page = self._page
        page.goto(self.BOLT_NEW_URL, wait_until="domcontentloaded", timeout=45000)
        page.fill(self.SELECTOR_CHAT_INPUT, spec)
        page.keyboard.press("Enter")
        self._wait_for_export_ready(page)
        page.click(self.SELECTOR_EXPORT_BUTTON)
        page.fill(self.SELECTOR_BRANCH_INPUT, branch or f"mesh/task-{task_id}")
        page.keyboard.press("Enter")
        pr_url = self._wait_for_pr_url(page, timeout_seconds=180)
        logger.info(f"[BoltAdapter] task {task_id} exported → {pr_url}")
        return pr_url

    # ── Internal waits (টেস্টে override-বান্ধব) ───────────────────────────────
    def _wait_for_export_ready(self, page: Any, timeout_seconds: int = 300) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if page.locator(self.SELECTOR_EXPORT_BUTTON).count() > 0:
                return
            page.wait_for_timeout(2000)
        raise TimeoutError("Export to GitHub button never appeared")

    def _wait_for_pr_url(self, page: Any, timeout_seconds: int = 180) -> str:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            link = page.locator(self.SELECTOR_PR_LINK).first
            if link.count() > 0:
                href = link.get_attribute("href")
                if href and href.startswith("https://github.com/"):
                    return href
            page.wait_for_timeout(2000)
        raise TimeoutError("PR URL never appeared after export")


__all__ = ["AdapterUnavailable", "BoltAdapter"]
