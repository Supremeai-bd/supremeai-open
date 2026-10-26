"""
auto_login.py — Autonomous Hands-Free Google / AI Account Login Engine.
======================================================================
Automates the Google sign-in flow using credentials from CredentialVault.
Supports automated 2FA verification via pyotp (Authenticator App).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import pyotp
except ImportError:
    pyotp = None

from credential_vault import CredentialVault
from playwright.async_api import Page

logger = logging.getLogger("ghost_tower.auto_login")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


async def handle_google_flow(
    page: Page,
    email: str,
    password: str,
    totp_secret: str = "",
    timeout_seconds: int = 35,
) -> bool:
    """
    Handles Google sign-in workflow including:
    - Account Chooser list ("Choose an account" / "Continue with Google")
    - Email entry
    - Password entry
    - 2FA / TOTP authentication
    - OAuth consent approval
    """
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        # Check if already reached Gemini app
        if "gemini.google.com" in page.url and "accounts.google.com" not in page.url:
            return True

        # A. Check for "Choose an account" list (Only if not already on password screen)
        password_input = await page.query_selector(
            'input[type="password"], input[name="Passwd"]'
        )
        if not password_input:
            account_chooser = await page.query_selector(
                f'div[data-identifier*="{email}"][role="link"], li[data-identifier*="{email}"], '
                f'div[data-email*="{email}"][role="link"]'
            )
            if account_chooser and await account_chooser.is_visible():
                logger.info(
                    f"[SSO] Account selector detected. Selecting stored account ({email})..."
                )
                await account_chooser.click()
                await asyncio.sleep(2)

        # B. Check for Email input
        email_selector = 'input[type="email"], input[name="identifier"]'
        email_elem = await page.query_selector(email_selector)
        if email_elem and await email_elem.is_visible():
            val = await email_elem.input_value()
            if not val or val != email:
                logger.info("[SSO] Entering email address...")
                await email_elem.click()
                await email_elem.fill(email)
                await asyncio.sleep(0.5)
                next_btn = await page.query_selector(
                    '#identifierNext, button:has-text("Next")'
                )
                if next_btn and await next_btn.is_visible():
                    await next_btn.click()
                else:
                    await page.keyboard.press("Enter")
                await asyncio.sleep(3)

        # C. Check for Password input
        password_selector = 'input[type="password"], input[name="Passwd"]'
        password_elem = await page.query_selector(password_selector)
        if password_elem and await password_elem.is_visible():
            logger.info("[SSO] Entering password...")
            await password_elem.click()
            await password_elem.fill(password)
            await asyncio.sleep(0.5)
            next_btn = await page.query_selector(
                '#passwordNext, button:has-text("Next")'
            )
            if next_btn and await next_btn.is_visible():
                await next_btn.click()
            else:
                await page.keyboard.press("Enter")
            await asyncio.sleep(4)

        # D. Check for 2FA TOTP Pin
        totp_selector = 'input[type="tel"], input#totpPin, input[name="totpPin"]'
        totp_elem = await page.query_selector(totp_selector)
        if totp_elem and await totp_elem.is_visible():
            if totp_secret and pyotp:
                logger.info(
                    "[SSO] Generating and injecting 2FA TOTP code from secret..."
                )
                current_otp = pyotp.TOTP(totp_secret).now()
                await totp_elem.fill(current_otp)
                await page.keyboard.press("Enter")
                logger.info("[SSO] Submitted 2FA code: [REDACTED_OTP]")
                await asyncio.sleep(3)
            else:
                logger.info("[NOTICE]: 2FA challenge detected.")

        # E. Check for Phone Prompt 2FA ("Tap Yes" / Device Challenge)
        page_text = ""
        try:
            page_text = await page.inner_text("body")
        except Exception:
            pass

        if any(
            phrase in page_text
            for phrase in [
                "Check your phone",
                "Tap Yes",
                "Google sent a notification",
                "2-Step Verification",
            ]
        ):
            print("\n" + "=" * 60)
            print(
                "[ACTION REQUIRED] Google sent a security verification to your phone!"
            )
            print("Please tap 'Yes' (or the matching number) on your phone now!")
            print("=" * 60 + "\n")
            logger.info("[PHONE 2FA] Waiting for user approval on phone...")
            await asyncio.sleep(4)

        # F. Check for OAuth Consent "Continue" / "Allow"
        consent_btn = await page.query_selector(
            'button:has-text("Continue"), button:has-text("Allow"), #submit_approve_access'
        )
        if consent_btn and await consent_btn.is_visible():
            logger.info("[SSO] OAuth consent button detected. Confirming access...")
            await consent_btn.click()
            await asyncio.sleep(2)

        # G. Break early if we have reached gemini.google.com/app
        if "gemini.google.com" in page.url and "accounts.google.com" not in page.url:
            return True

        await asyncio.sleep(1)

    return "accounts.google.com" not in page.url


async def auto_login_gemini(
    page: Page,
    account_label: str = "gemini_default",
    account_data: dict[str, Any] | None = None,
    timeout_seconds: int = 90,
) -> bool:
    """
    Executes automated login to Google Gemini.
    Handles direct credentials and Google SSO / Account Chooser.
    """
    vault = CredentialVault()
    credentials = account_data or vault.get_account(account_label)

    if not credentials:
        accounts = vault.list_accounts()
        if accounts:
            first_label = accounts[0]["account_label"]
            logger.info(f"Using default vault account: {first_label}")
            credentials = vault.get_account(first_label)

    if not credentials:
        logger.warning(
            "No credentials found in vault. Please save an account using credential_vault.py first."
        )
        return False

    email = credentials["email"]
    password = credentials["password"]
    totp_secret = credentials.get("totp_secret", "")

    logger.info(f"Initiating autonomous login for {email} ...")

    # 1. Navigate to Gemini to check if already logged in
    if "gemini.google.com" not in page.url:
        await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # 2. Check if already logged in
    sign_in_candidate = await page.query_selector(
        'a[href*="accounts.google.com"], button:has-text("Sign in")'
    )
    if not sign_in_candidate and "accounts.google.com" not in page.url:
        logger.info("Already logged in to Gemini!")
        return True

    # 3. Direct navigation to Google Accounts Login for Gemini
    logger.info("Navigating directly to Google Sign-in for Gemini...")
    await page.goto(
        "https://accounts.google.com/ServiceLogin?continue=https://gemini.google.com/app",
        wait_until="networkidle",
    )
    await asyncio.sleep(2)

    # 4. Handle Google Sign-in / Account Chooser workflow
    await handle_google_flow(
        page,
        email=email,
        password=password,
        totp_secret=totp_secret,
        timeout_seconds=timeout_seconds,
    )

    # 5. Wait for redirect back to gemini.google.com/app
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        if "gemini.google.com" in page.url and "accounts.google.com" not in page.url:
            sign_in_check = await page.query_selector('a[href*="accounts.google.com"]')
            if not sign_in_check:
                logger.info(
                    "[SUCCESS] Autonomous Google login successfully completed and verified!"
                )
                return True
        await asyncio.sleep(1)

    logger.warning("Timed out waiting for login completion. Please check the browser.")
    return False


async def auto_login_via_google_sso(
    page: Page,
    account_label: str = "gemini_default",
    timeout_seconds: int = 45,
) -> bool:
    """
    Generic Google SSO / 'Continue with Google' handler for any AI web platform.
    Automatically clicks 'Continue with Google', handles popup/redirect, and authenticates.
    """
    vault = CredentialVault()
    credentials = vault.get_account(account_label)
    if not credentials:
        accounts = vault.list_accounts()
        if accounts:
            credentials = vault.get_account(accounts[0]["account_label"])

    if not credentials:
        logger.warning("No credentials found in vault for Google SSO.")
        return False

    email = credentials["email"]
    password = credentials["password"]
    totp_secret = credentials.get("totp_secret", "")

    # Look for Google Sign-in / Continue with Google button
    google_btn_selector = (
        'button:has-text("Continue with Google"), button:has-text("Sign in with Google"), '
        'button:has-text("Log in with Google"), a:has-text("Continue with Google"), '
        'div[role="button"]:has-text("Google"), [data-provider="google"]'
    )

    btn = await page.query_selector(google_btn_selector)
    if not btn:
        logger.info("No 'Continue with Google' button detected on current page.")
        return False

    logger.info("Found 'Continue with Google' button. Initiating OAuth click...")

    # Some sites open a popup, others redirect in same window
    try:
        async with page.context.expect_page(timeout=5000) as new_page_info:
            await btn.click()
        popup_page = await new_page_info.value
        await popup_page.wait_for_load_state("domcontentloaded")
        logger.info(f"OAuth popup opened: {popup_page.url}")
        success = await handle_google_flow(
            popup_page, email=email, password=password, totp_secret=totp_secret
        )
        await asyncio.sleep(2)
        return success
    except Exception:
        # Redirect in same window
        await asyncio.sleep(2)
        if "accounts.google.com" in page.url:
            return await handle_google_flow(
                page, email=email, password=password, totp_secret=totp_secret
            )

    return True


async def run_standalone_login(account_label: str = "gemini_default"):
    """Standalone runner to open browser and test auto-login."""
    from playwright.async_api import async_playwright

    user_data_dir = os.path.expanduser(r"~\.gemini_isolated_session")

    print("=================================================================")
    print("   SupremeAI: Autonomous Google Login Runner")
    print("=================================================================")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
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
        success = await auto_login_gemini(page, account_label=account_label)
        if success:
            print(
                "\n[SUCCESS]: Account is permanently authenticated in isolated persistent profile!"
            )
        else:
            print(
                "\n[NOTICE]: Login could not complete automatically. You can finish it manually in the opened window."
            )

        await asyncio.sleep(5)
        await context.close()


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "gemini_default"
    asyncio.run(run_standalone_login(label))
