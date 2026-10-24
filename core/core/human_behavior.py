import asyncio
import random
from typing import Any

from core.logging_config import logger

try:
    from playwright.async_api import ElementHandle, Page
except ImportError:
    # বাংলা মন্তব্য: মেইন ব্যাকএন্ড কন্টেইনারে playwright না থাকলে fallback setup
    Page = Any
    ElementHandle = Any


class HumanBehaviorSimulators:
    """
    মানুষের আচরণ সিমুলেট করার জন্য হেল্পার ক্লাস।
    এটি বট-ডিটেকশন বাইপাস করতে সাহায্য করে।
    """

    # বাংলা: বাস্তব ডেস্কটপ ভিউপোর্টের সেট — প্রতিবার একই fixed-size
    # ভিউপোর্ট বট-ফিঙ্গারপ্রিন্ট হিসেবে ধরা পড়ে (Feature 3, old plan)।
    _REAL_VIEWPORT_WIDTHS = [1280, 1366, 1440, 1536, 1600, 1920]
    _REAL_VIEWPORT_HEIGHTS = [720, 768, 800, 864, 900, 1080]

    # ═══════════════════════════════════════════════════════════════════
    # Feature 3 (old plan): Biometric Stealth Fingerprint Layer
    # Canvas/WebGL ফিঙ্গারপ্রিন্ট noise + navigator.webdriver trace removal +
    # বাস্তবসম্মত plugins — Cloudflare/Akamai-শ্রেণির bot-detection এড়াতে।
    # tools/browser/browser_stealth.py-এর সাথে সামঞ্জস্যপূর্ণ, কিন্তু এটি
    # context/page-agnostic — যেকোনো Playwright page/context-এ প্রয়োগযোগ্য।
    # ═══════════════════════════════════════════════════════════════════
    STEALTH_INIT_SCRIPT = """
    // 1. Canvas fingerprint noise — প্রতি রেন্ডারে অদৃশ্য পার্থক্য যোগ হয়
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, ...args) {
        const dataURL = origToDataURL.apply(this, [type, ...args]);
        return dataURL.replace(/.$/, String.fromCharCode(
            dataURL.charCodeAt(dataURL.length - 1) ^ (Math.random() * 4 | 0)
        ));
    };
    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    if (origToBlob) {
        HTMLCanvasElement.prototype.toBlob = function(cb, type, quality) {
            return origToBlob.call(this, cb, type, quality);
        };
    }

    // 2. WebGL renderer/vendor string spoofing (37445=UNMASKED_VENDOR, 37446=UNMASKED_RENDERER)
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Intel Open Source Technology Center';
        if (param === 37446) return 'Mesa DRI Intel(R) Iris(R) Plus Graphics (ICL GT2)';
        return getParam.apply(this, [param]);
    };
    if (window.WebGL2RenderingContext) {
        const getParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {
            if (param === 37445) return 'Intel Open Source Technology Center';
            if (param === 37446) return 'Mesa DRI Intel(R) Iris(R) Plus Graphics (ICL GT2)';
            return getParam2.apply(this, [param]);
        };
    }

    // 3. Remove navigator.webdriver trace (headless Chrome-এর সবচেয়ে সহজ টেল)
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 4. Realistic plugins array (headless-এ plugins খালি থাকে — বড় টেল)
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ],
    });

    // 5. Consistent languages / hardwareConcurrency
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    """

    @classmethod
    async def apply_stealth_fingerprint(cls, page: Page) -> None:
        """Cloudflare/Akamai bot-detection এড়াতে page-এ stealth fingerprint প্রয়োগ।

        - Canvas/WebGL fingerprint noise (init script — page-এর সব ফ্রেমে চলে)
        - navigator.webdriver ট্রেস মুছে ফেলা
        - Random realistic viewport (fixed-size bot detection এড়াতে)

        Never raises — stealth ব্যর্থ হলে scraping স্বাভাবিকভাবে চলবে।
        """
        try:
            await page.add_init_script(cls.STEALTH_INIT_SCRIPT)
        except Exception as exc:
            logger.debug(f"Stealth init script failed (non-fatal): {exc}")

        try:
            # বাংলা: init script পেজ নেভিগেশনের পরেও থাকে; viewport এখনই সেট করা হয়।
            viewport = {
                "width": random.choice(cls._REAL_VIEWPORT_WIDTHS),
                "height": random.choice(cls._REAL_VIEWPORT_HEIGHTS),
            }
            await page.set_viewport_size(viewport)
            logger.debug(f"Stealth fingerprint applied with viewport {viewport}")
        except Exception as exc:
            logger.debug(f"Stealth viewport randomization failed (non-fatal): {exc}")

    @staticmethod
    def _generate_bezier_points(start: tuple, end: tuple, steps: int = 20) -> list:
        """মানুষের হাতের সামান্য কাঁপুনি সিমুলেট করার জন্য Bezier পাথ পয়েন্ট জেনারেট করে।"""
        x1, y1 = start
        x2, y2 = end

        # র্যান্ডম কন্ট্রোল পয়েন্ট নিয়ে ন্যাচারাল কার্ভ তৈরি করা হচ্ছে
        control1_x = x1 + (x2 - x1) * random.uniform(0.1, 0.4)
        control1_y = y1 + (y2 - y1) * random.uniform(0.1, 0.3)
        control2_x = x1 + (x2 - x1) * random.uniform(0.6, 0.9)
        control2_y = y1 + (y2 - y1) * random.uniform(0.7, 0.9)

        points = []
        for i in range(steps):
            t = i / float(steps - 1)
            # Cubic Bezier ফর্মুলা
            x = (
                (1 - t) ** 3 * x1
                + 3 * (1 - t) ** 2 * t * control1_x
                + 3 * (1 - t) * t**2 * control2_x
                + t**3 * x2
            )
            y = (
                (1 - t) ** 3 * y1
                + 3 * (1 - t) ** 2 * t * control1_y
                + 3 * (1 - t) * t**2 * control2_y
                + t**3 * y2
            )
            points.append((x, y))
        return points

    @classmethod
    async def natural_mouse_move_and_click(cls, page: Page, selector: str):
        """মাউস কার্সারকে Bezier কার্ভ দিয়ে মুভ করিয়ে র্যান্ডম অফসেট ক্লিক করবে।"""
        try:
            element = await page.wait_for_selector(selector, state="visible", timeout=10000)
            box = await element.bounding_box()
            if not box:
                raise ValueError(f"Element {selector} has no layout bounding box.")

            # এলিমেন্টের সেন্টারে সামান্য র্যান্ডম অফসেট নিয়ে ক্লিক কোঅর্ডিনেট নির্ধারণ
            target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)

            # এন্ট্রি ভেক্টর সিমুলেট করার জন্য র্যান্ডম শুরু পয়েন্ট নেওয়া হলো
            start_x = random.uniform(0, 100)
            start_y = random.uniform(0, 100)

            path = cls._generate_bezier_points(
                (start_x, start_y), (target_x, target_y), steps=random.randint(15, 30)
            )

            for x, y in path:
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.005, 0.015))  # মাইক্রো ডিলে

            await asyncio.sleep(random.uniform(0.1, 0.25))  # ক্লিকের আগে সামান্য থামা
            await page.mouse.click(target_x, target_y)
            logger.debug(f"Simulated natural human click on selector: {selector}")
        except Exception as e:
            logger.error(f"Human-like click failed on {selector}: {e!s}")
            raise

    @classmethod
    async def natural_type(cls, page: Page, selector: str, text: str):
        """Gaussian ডিস্ট্রিবিউশন ডিলে ব্যবহার করে কিবোর্ড টাইপিং সিমুলেট করবে।"""
        try:
            element = await page.wait_for_selector(selector, state="visible", timeout=10000)
            await element.focus()
            await asyncio.sleep(random.uniform(0.15, 0.3))

            for char in text:
                await page.keyboard.type(char)
                # Gaussian ডিস্ট্রিবিউশন: Mean=100ms, StdDev=30ms
                delay = random.gauss(0.10, 0.03)
                # বাস্তবসম্মত বাউন্ডারি লিমিট (50ms থেকে 250ms)
                delay = max(0.05, min(delay, 0.25))
                await asyncio.sleep(delay)

            logger.debug(f"Simulated natural typing into selector: {selector}")
        except Exception as e:
            logger.error(f"Human-like typing failed on {selector}: {e!s}")
            raise
