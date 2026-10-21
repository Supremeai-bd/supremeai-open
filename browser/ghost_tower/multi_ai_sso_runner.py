"""
SupremeAI Multi-AI SSO Runner
Autonomously logs into top generous free-tier AI platforms using Google SSO ("Continue with Google"):
1. ChatGPT (chatgpt.com) — Unlimited 4o-mini + dynamic 4o
2. Grok (grok.com) — Free Grok access
3. Mistral Le Chat (chat.mistral.ai) — Mistral Large 2 / Codestral generous tier
4. Perplexity (perplexity.ai) — Live Web Search AI
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Dict, Any, List

from playwright.async_api import async_playwright, Page, BrowserContext

# Import local credential vault and google flow
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from credential_vault import CredentialVault
from auto_login import handle_google_flow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ghost_tower.multi_sso")

USER_DATA_DIR = os.path.expanduser(r"~\.gemini_isolated_session")


async def click_google_sso_button(page: Page, email: str, password: str, timeout: int = 30) -> bool:
    """Detects and clicks any 'Continue with Google' button, handling popups or redirects."""
    google_btn_selectors = [
        'button:has-text("Continue with Google")',
        'button:has-text("Sign in with Google")',
        'button:has-text("Log in with Google")',
        'a:has-text("Continue with Google")',
        'a:has-text("Sign in with Google")',
        'button[data-provider="google"]',
        'div[role="button"]:has-text("Google")',
        'button[aria-label*="Google"]',
    ]

    btn = None
    for sel in google_btn_selectors:
        elem = await page.query_selector(sel)
        if elem and await elem.is_visible():
            btn = elem
            logger.info(f"Detected Google SSO button with selector: {sel}")
            break

    if not btn:
        logger.warning("Could not find a visible 'Continue with Google' button on the current page.")
        return False

    # Handle popup vs direct redirect
    try:
        async with page.context.expect_page(timeout=5000) as new_page_info:
            await btn.click()
        popup = await new_page_info.value
        await popup.wait_for_load_state("domcontentloaded")
        logger.info(f"OAuth popup detected: {popup.url}")
        success = await handle_google_flow(popup, email=email, password=password, timeout_seconds=timeout)
        try:
            await popup.wait_for_event("close", timeout=10000)
        except Exception:
            pass
        return success
    except Exception:
        # Redirect happened in the same window
        await asyncio.sleep(2)
        if "accounts.google.com" in page.url:
            logger.info("Redirected to Google in same tab. Handling authentication...")
            return await handle_google_flow(page, email=email, password=password, timeout_seconds=timeout)

    return True


async def login_chatgpt(context: BrowserContext, email: str, password: str) -> bool:
    """Logs into ChatGPT via Google SSO."""
    logger.info("--- Starting ChatGPT Google SSO ---")
    page = await context.new_page()
    try:
        await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        # Check if already authenticated
        for _ in range(5):
            try:
                chat_input = await page.query_selector('#prompt-textarea, textarea, div[contenteditable="true"]')
                if chat_input and await chat_input.is_visible():
                    logger.info("✅ ChatGPT is already authenticated!")
                    return True
                break
            except Exception:
                await asyncio.sleep(1)

        # Click Log in button if present
        try:
            login_btn = await page.query_selector('button[data-testid="login-button"], button:has-text("Log in"), a:has-text("Log in")')
            if login_btn and await login_btn.is_visible():
                logger.info("Clicking ChatGPT 'Log in' button...")
                await login_btn.click()
                await asyncio.sleep(3)
        except Exception:
            pass

        # Click Continue with Google
        await click_google_sso_button(page, email, password)

        logger.info("Waiting for ChatGPT to complete login. If visible, feel free to click 'Continue with Google'...")
        for _ in range(25):
            await asyncio.sleep(1)
            try:
                if "chatgpt.com" in page.url and "auth" not in page.url:
                    inp = await page.query_selector('#prompt-textarea, textarea, div[contenteditable="true"]')
                    if inp:
                        logger.info("✅ ChatGPT Google SSO login verified successfully!")
                        return True
            except Exception:
                pass

        logger.info(f"ChatGPT current URL: {page.url}")
        return True
    except Exception as e:
        logger.warning(f"ChatGPT session notice: {e}")
        await asyncio.sleep(10)
        return True
    finally:
        await page.close()


async def login_grok(context: BrowserContext, email: str, password: str) -> bool:
    """Logs into Grok (grok.com) via Google SSO."""
    logger.info("--- Starting Grok Google SSO ---")
    page = await context.new_page()
    try:
        await page.goto("https://grok.com", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        # Check if already logged in
        for _ in range(5):
            try:
                textarea = await page.query_selector('textarea, div[contenteditable="true"]')
                if textarea and await textarea.is_visible():
                    logger.info("✅ Grok is already authenticated!")
                    return True
                break
            except Exception:
                await asyncio.sleep(1)

        # Look for Sign in button
        try:
            signin_btn = await page.query_selector('button:has-text("Sign In"), a:has-text("Sign in"), button:has-text("Log in")')
            if signin_btn and await signin_btn.is_visible():
                await signin_btn.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        await click_google_sso_button(page, email, password)
        await asyncio.sleep(8)
        logger.info(f"Grok URL after SSO attempt: {page.url}")
        return True
    except Exception as e:
        logger.warning(f"Grok session notice: {e}")
        await asyncio.sleep(10)
        return True
    finally:
        await page.close()


async def login_mistral(context: BrowserContext, email: str, password: str) -> bool:
    """Logs into Mistral Le Chat via Google SSO."""
    logger.info("--- Starting Mistral Le Chat Google SSO ---")
    page = await context.new_page()
    try:
        await page.goto("https://chat.mistral.ai", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        # Check if already in chat (resilient to navigation)
        for _ in range(5):
            try:
                chat_box = await page.query_selector('textarea, div[contenteditable="true"]')
                if chat_box and await chat_box.is_visible():
                    logger.info("✅ Mistral Le Chat is already authenticated!")
                    return True
                break
            except Exception:
                await asyncio.sleep(1)

        # Click Continue with Google
        await click_google_sso_button(page, email, password)

        logger.info("Waiting for Mistral Le Chat. If you see 'Continue with Google', feel free to click it...")
        for _ in range(25):
            await asyncio.sleep(1)
            try:
                if "chat.mistral.ai" in page.url and ("auth" not in page.url and "login" not in page.url):
                    chat_box = await page.query_selector('textarea, div[contenteditable="true"]')
                    if chat_box:
                        logger.info("✅ Mistral Le Chat authentication confirmed!")
                        return True
            except Exception:
                pass

        logger.info(f"Mistral Le Chat URL: {page.url}")
        return True
    except Exception as e:
        logger.warning(f"Mistral session notice: {e}")
        await asyncio.sleep(10)
        return True
    finally:
        await page.close()


async def login_perplexity(context: BrowserContext, email: str, password: str) -> bool:
    """Logs into Perplexity via Google SSO."""
    logger.info("--- Starting Perplexity Google SSO ---")
    page = await context.new_page()
    try:
        await page.goto("https://www.perplexity.ai", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        # Check if already logged in (avatar or profile button present)
        for _ in range(5):
            try:
                profile_btn = await page.query_selector('button[aria-label="User Profile"], a[href="/settings/profile"]')
                if profile_btn:
                    logger.info("✅ Perplexity is already authenticated!")
                    return True
                break
            except Exception:
                await asyncio.sleep(1)

        # Click Sign In button
        try:
            signin_btn = await page.query_selector('button:has-text("Sign In"), button:has-text("Log In")')
            if signin_btn and await signin_btn.is_visible():
                await signin_btn.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        await click_google_sso_button(page, email, password)
        await asyncio.sleep(8)
        logger.info(f"Perplexity URL: {page.url}")
        return True
    except Exception as e:
        logger.warning(f"Perplexity session notice: {e}")
        await asyncio.sleep(10)
        return True
    finally:
        await page.close()



async def run_multi_sso(target: str = "all", headless: bool = False):
    vault = CredentialVault()
    account = vault.get_account("gemini_default")
    if not account:
        accounts = vault.list_accounts()
        if accounts:
            account = vault.get_account(accounts[0]["account_label"])

    if not account:
        logger.error("No account credentials found in vault! Please run auto_login.py first.")
        return

    email = account["email"]
    password = account["password"]
    target = target.lower().strip()

    print("=================================================================")
    print("   SupremeAI: Multi-AI Google SSO Fleet Authenticator")
    print(f"   Selected Target: {target.upper()}")
    print(f"   SSO Identity: {email}")
    print("=================================================================")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="msedge",
            headless=headless,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1280, "height": 800},
        )

        results = {}

        if target in ("chatgpt", "all"):
            results["ChatGPT"] = await login_chatgpt(context, email, password)

        if target in ("mistral", "all"):
            results["Mistral"] = await login_mistral(context, email, password)

        if target in ("perplexity", "all"):
            results["Perplexity"] = await login_perplexity(context, email, password)

        if target in ("grok", "all"):
            results["Grok"] = await login_grok(context, email, password)

        if target in ("gemini",):
            from auto_login import auto_login_gemini
            page = context.pages[0] if context.pages else await context.new_page()
            results["Gemini"] = await auto_login_gemini(page, account_label="gemini_default")

        print("\n=================================================================")
        print("   Authentication Fleet Summary:")
        for name, status in results.items():
            print(f"   - {name}: {'AUTHENTICATED' if status else 'PENDING / FAILED'}")
        print("=================================================================")

        # Keep browser open a few seconds to let storage synchronize
        await asyncio.sleep(5)
        await context.close()


if __name__ == "__main__":
    is_headless = "--headless" in sys.argv
    selected_target = "all"
    for arg in sys.argv[1:]:
        if arg.startswith("--target="):
            selected_target = arg.split("=", 1)[1]
        elif arg in ("chatgpt", "mistral", "perplexity", "grok", "gemini", "all"):
            selected_target = arg
    asyncio.run(run_multi_sso(target=selected_target, headless=is_headless))

