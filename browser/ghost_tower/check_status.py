import asyncio
import os

from playwright.async_api import async_playwright

USER_DATA_DIR = os.path.expanduser(r"~\.gemini_chrome_session")


async def check():
    print(f"Checking session directory: {USER_DATA_DIR}")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=True,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        url = page.url
        title = await page.title()

        sign_in = await page.query_selector(
            'a[href*="accounts.google.com"], button:has-text("Sign in")'
        )
        input_elem = await page.query_selector(
            'div.ql-editor, div[contenteditable="true"], textarea, rich-textarea'
        )
        avatar = await page.query_selector(
            'a[aria-label*="Google Account"], img[alt*="Google Account"], button[aria-label*="Google Account"]'
        )

        print(f"CURRENT URL: {url}")
        print(f"PAGE TITLE: {title}")
        print(f"SIGN IN BUTTON DETECTED: {sign_in is not None}")
        print(f"CHAT INPUT DETECTED: {input_elem is not None}")
        print(f"ACCOUNT AVATAR DETECTED: {avatar is not None}")

        if (
            "gemini.google.com" in url
            and "accounts.google.com" not in url
            and sign_in is None
        ):
            print("==> RESULT: LOGIN IS ACTIVE & VERIFIED!")
        else:
            print("==> RESULT: NOT LOGGED IN YET.")

        await context.close()


if __name__ == "__main__":
    asyncio.run(check())
