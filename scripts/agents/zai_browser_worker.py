"""SupremeAI Z.ai Autonomous Browser Worker (Track A Compute Engine).

Monitors all active Z.ai agent chats (git pr merge and regration, long run 3rd party platform),
detects completion/idle state with precise DOM hydration waiting,
and clicks the exact '#send-message-button' to keep agents running 24/7.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime
from playwright.async_api import async_playwright, BrowserContext, Page

DEFAULT_PROFILE_DIR = os.path.abspath(".zai_browser_profile")
SEND_BUTTON_SELECTOR = "#send-message-button, button.sendMessageButton, button[type='submit']"
STOP_BUTTON_SELECTOR = "button:has-text('Stop'), button[aria-label*='Stop'], svg[class*='animate-spin']"


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [Z.ai-Worker] {msg}", flush=True)


async def wait_for_chat_ready(page: Page, timeout_ms: int = 25000) -> bool:
    """Wait for Next.js chat to hydrate and show textarea."""
    try:
        textarea = page.locator("textarea").first
        await textarea.wait_for(state="visible", timeout=timeout_ms)
        await asyncio.sleep(1.5)
        return True
    except Exception:
        return False


async def detect_agent_status(page: Page) -> str:
    """Detect whether Z.ai agent is currently generating, idle, or ready for input."""
    try:
        # Check for active generation
        stop_count = await page.locator(STOP_BUTTON_SELECTOR).count()
        if stop_count > 0:
            return "GENERATING"

        # Check textarea visibility
        textarea = page.locator("textarea").first
        if await textarea.is_visible():
            return "READY_FOR_INPUT"

        return "LOADING"
    except Exception as e:
        return f"ERROR: {e}"


async def trigger_continue(page: Page, message: str = "continue working") -> bool:
    """Types message into textarea and clicks #send-message-button."""
    try:
        textarea = page.locator("textarea").first
        if not await textarea.is_visible():
            log("Textarea not visible.")
            return False

        # Click and fill
        await textarea.click()
        await textarea.fill(message)
        await asyncio.sleep(0.5)

        # Click the dedicated send button
        send_btn = page.locator(SEND_BUTTON_SELECTOR).first
        if await send_btn.is_visible():
            await send_btn.click()
            log(f"SUCCESS: Clicked #send-message-button with payload '{message}'!")
            await asyncio.sleep(3.0)
            return True
        else:
            # Fallback to Enter key
            await textarea.press("Enter")
            log(f"Send button not visible. Fallback: dispatched '{message}' via Enter key.")
            await asyncio.sleep(2.0)
            return True
    except Exception as exc:
        log(f"Failed to send message: {exc}")
        return False


async def run_worker(
    profile_dir: str,
    headed: bool,
    cdp_url: str | None,
    poll_interval: int,
):
    log("=" * 60)
    log("Starting SupremeAI Z.ai Multi-Agent Autonomous Worker")
    log(f"Mode: {'CDP' if cdp_url else ('Headed' if headed else 'Headless')}")
    log(f"Poll Interval: {poll_interval}s")
    log(f"Send Button Selector: {SEND_BUTTON_SELECTOR}")
    log("=" * 60)

    target_chats = [
        ("git pr merge and regration", "https://chat.z.ai/c/c3604601-2df7-479f-9711-037cb72b8177"),
        ("long run 3rd party platform", "https://chat.z.ai/c/be9e179f-3a7b-441c-b386-5809866a92dc"),
    ]

    async with async_playwright() as p:
        context: BrowserContext = None
        if cdp_url:
            log(f"Connecting to Chrome via CDP: {cdp_url} ...")
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
        else:
            os.makedirs(profile_dir, exist_ok=True)
            log(f"Using persistent profile at: {profile_dir}")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=not headed,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )

        page = context.pages[0] if context.pages else await context.new_page()

        log(f"Opening initial chat: {target_chats[0][0]} ...")
        await page.goto(target_chats[0][1], wait_until="domcontentloaded", timeout=60000)
        await wait_for_chat_ready(page, timeout_ms=25000)

        log("Worker active. Entering continuous multi-agent loop...")

        while True:
            try:
                for chat_name, chat_url in target_chats:
                    log(f"\n--- Checking Agent: [{chat_name}] ---")
                    try:
                        if page.url != chat_url:
                            log(f"Navigating to {chat_url} ...")
                            await page.goto(chat_url, wait_until="domcontentloaded", timeout=30000)
                            ready = await wait_for_chat_ready(page, timeout_ms=20000)
                            if not ready:
                                log(f"Page still hydrating for {chat_name}. Skipping to next round.")
                                continue

                        status = await detect_agent_status(page)
                        log(f"[{chat_name}] Status: {status}")

                        if status == "READY_FOR_INPUT":
                            log(f"Agent [{chat_name}] is IDLE! Triggering continue...")
                            success = await trigger_continue(page, "continue working")
                            if success:
                                log(f"Triggered [{chat_name}] successfully!")
                                await asyncio.sleep(5)

                        elif status == "GENERATING":
                            log(f"Agent [{chat_name}] is ACTIVELY WORKING. Leaving it to proceed.")

                        else:
                            log(f"[{chat_name}] Status: {status}. Standing by.")

                    except Exception as chat_err:
                        log(f"Error checking [{chat_name}]: {chat_err}")

            except Exception as loop_err:
                log(f"Loop error: {loop_err}")

            log(f"\nRound complete. Sleeping {poll_interval}s before next sweep...")
            await asyncio.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(description="SupremeAI Z.ai Autonomous Background Worker")
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR, help="Persistent browser profile path")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    parser.add_argument("--headless", action="store_true", help="Run headless in background")
    parser.add_argument("--cdp", default=None, help="Connect via CDP (e.g. http://localhost:9222)")
    parser.add_argument("--interval", type=int, default=30, help="Check interval in seconds")

    args = parser.parse_args()
    is_headed = args.headed or (not args.headless and not args.cdp)

    try:
        asyncio.run(
            run_worker(
                profile_dir=args.profile_dir,
                headed=is_headed,
                cdp_url=args.cdp,
                poll_interval=args.interval,
            )
        )
    except KeyboardInterrupt:
        log("Worker stopped by user.")


if __name__ == "__main__":
    main()
