"""
login_helper.py — Dedicated interactive login window for gemini.google.com
===========================================================================
Uses Microsoft Edge (Chromium engine) to completely prevent ProcessSingleton
lock conflicts with your running Google Chrome browser.
"""

import asyncio
import os

from playwright.async_api import async_playwright

USER_DATA_DIR = os.path.expanduser(r"~\.gemini_isolated_session")


async def main():
    print("=================================================================")
    print("   SupremeAI: Google Gemini Account Login Setup")
    print("=================================================================")
    print("\nOpening Chromium browser (Zero conflict with your main Chrome)...")

    os.makedirs(USER_DATA_DIR, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="msedge",
            headless=False,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        print("Navigating to https://gemini.google.com/app ...")
        await page.goto("https://gemini.google.com/app")

        print(
            "\n--> BROWSER OPENED! Please sign in with your Google Account on the window."
        )
        print(
            "--> The script is watching and will automatically detect when you sign in!\n"
        )

        while True:
            await asyncio.sleep(2)
            if page.is_closed():
                print("Browser window was closed.")
                break

            url = page.url
            try:
                sign_in = await page.query_selector(
                    'a[href*="accounts.google.com"], button:has-text("Sign in")'
                )
                if (
                    "accounts.google.com" not in url
                    and sign_in is None
                    and "gemini.google.com" in url
                ):
                    print(
                        "================================================================="
                    )
                    print("   SUCCESS! Google Login successfully detected and saved!")
                    print(
                        "================================================================="
                    )
                    await asyncio.sleep(3)
                    break
            except Exception:
                pass

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
