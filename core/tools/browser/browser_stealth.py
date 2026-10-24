# LATENT-CRASH REPAIR (2026-09-15): this module is DESIGNED to work without
# playwright (HAS_PLAYWRIGHT guard + optional-dependency pragmas below), but
# without the deferred-annotations import the parameter annotation on
# simulate_human_behavior(page: Page) was evaluated at class-definition time
# and raised NameError in playwright-less environments (e.g. the CI services
# group venv) — making the whole tools.browser chain unimportable there.
from __future__ import annotations

import asyncio
import secrets

from core.config import settings

random = secrets.SystemRandom()
import string
import time
from pathlib import Path
from typing import Any

from core.logging_config import logger

HAS_PLAYWRIGHT = True
try:  # pragma: no cover - optional dependency
    from playwright.async_api import BrowserContext, Page, async_playwright
except ImportError:  # pragma: no cover - optional dependency
    HAS_PLAYWRIGHT = False

# A list of modern, realistic user agents to rotate through
REALISTIC_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class BrowserStealth:
    def __init__(self) -> None:
        self.playwright = None
        self.context: BrowserContext | None = None

    async def create_stealth_browser(self) -> Any:
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("playwright not installed")
        self.playwright = await async_playwright().start()
        browser = await self.playwright.chromium.launch(
            headless=getattr(settings, "browser_headless", "true").lower() != "false"
        )
        from tools.security_tools.proxy_manager import ProxyManager

        proxy_mgr = ProxyManager()
        next_proxy = proxy_mgr.get_next_proxy()

        context_kwargs = {
            "user_agent": random.choice(REALISTIC_USER_AGENTS),
            "locale": "en-US",
            "screen": {"width": 1920, "height": 1080},
            "viewport": {"width": 1920, "height": 1080},
            "java_script_enabled": True,
            "bypass_csp": True,
            "extra_http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
        }
        if next_proxy:
            context_kwargs["proxy"] = {"server": next_proxy}
            logger.info(f"Playwright stealth browser launching via proxy: {next_proxy}")

        self.context = await browser.new_context(**context_kwargs)
        await self.context.route(
            "**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort()
        )
        await self.context.add_init_script("""
            (() => {
                // --- General Navigator Spoofing ---
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
                    ],
                });

                // --- Spoof window.chrome ---
                window.chrome = window.chrome || {};
                window.chrome.runtime = window.chrome.runtime || {};

                // --- Permissions API Spoofing ---
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters)
                );

                // --- WebGL Fingerprint Spoofing ---
                try {
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {
                        if (parameter === 37445) return 'Intel Open Source Technology Center'; // UNMASKED_VENDOR_WEBGL
                        if (parameter === 37446) return 'Mesa DRI Intel(R) Ivybridge Mobile '; // UNMASKED_RENDERER_WEBGL
                        return getParameter.apply(this, arguments);
                    };
                } catch (e) { /* ignore */ }

                // --- Canvas Fingerprint Spoofing ---
                const toDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function() {
                    const context = this.getContext('2d');
                    if (context) {
                        // Add random noise to the canvas
                        const imageData = context.getImageData(0, 0, this.width, this.height);
                        for (let i = 0; i < imageData.data.length; i += 4) {
                            const noise = Math.floor(Math.random() * 10 - 5);
                            imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + noise));
                            imageData.data[i+1] = Math.max(0, Math.min(255, imageData.data[i+1] + noise));
                            imageData.data[i+2] = Math.max(0, Math.min(255, imageData.data[i+2] + noise));
                        }
                        context.putImageData(imageData, 0, 0);
                    }
                    return toDataURL.apply(this, arguments);
                };
            })();
            """)
        return self.context

    async def simulate_human_behavior(self, page: Page) -> None:
        try:
            for _ in range(random.randint(1, 3)):
                await page.mouse.move(
                    random.randint(0, 400),
                    random.randint(0, 400),
                    steps=random.randint(3, 6),
                )
                await asyncio.sleep(random.uniform(0.3, 1.2))
                await page.mouse.wheel(0, random.randint(-120, 120))
                await page.keyboard.press(random.choice(["Space", "PageDown", "End"]))
            if random.random() > 0.6:
                await page.mouse.click(
                    random.randint(50, 300),
                    random.randint(80, 300),
                    delay=random.randint(80, 220),
                )
        except Exception as exc:
            logger.debug(f"Human behavior simulation skipped: {exc}")

    async def safe_screenshot(self, page: Page, path: str | None = None) -> str | None:
        try:
            target = (
                path
                or f"data/artifacts/screenshot_{int(time.time())}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}.png"
            )
            Path("data/artifacts").mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=target, full_page=True)
            return target
        except Exception as exc:
            logger.debug(f"screenshot failed: {exc}")
            return None

    async def close(self) -> None:
        try:
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            pass
