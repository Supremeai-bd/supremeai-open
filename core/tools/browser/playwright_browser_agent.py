from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from concurrent.futures import ThreadPoolExecutor

random = secrets.SystemRandom()
import base64
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from core.logging_config import logger

try:
    from playwright.sync_api import Page
except ImportError:
    # বাংলা মন্তব্য (DEP-AUDIT): playwright এখন optional `browser` group-এ।
    # Core image-এ না থাকলে module import ক্র্যাশ না করে Any-তে fallback হয়।
    Page = Any  # type: ignore[assignment,misc]

from brain.model_router import ModelRouter
from browser.action_cascade import execute_click_cascade
from core.security.secure_credential_store import (
    CredentialEncryptionUnavailableError,
    SecureCredentialStore,
)
from database.supabase_client import db
from memory.long_term_memory import MemoryManager
from tools.browser.browser_stealth import BrowserStealth

TRUST_SCORE_THRESHOLD = 0.95


class PlaywrightBrowserAgent:
    COOKIE_STORAGE_BASE: ClassVar[Any] = (
        Path(__file__).resolve().parents[1] / ".cache" / "playwright_cookies"
    )

    def __init__(self, headless: bool = True, timeout_ms: int = 30000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.playwright = None
        self.browser = None
        self.memory = MemoryManager()
        self.secure_store = SecureCredentialStore()
        self._bound_page: Any = None
        self.COOKIE_STORAGE_BASE.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Stateful page binding (ISSUE-1570) — MCP wrappers can act on a live
    # session page without re-creating a browser per call.
    # ------------------------------------------------------------------
    def bind_page(self, page: Any) -> None:
        """Bind a live browser page for stateful cascade/typing operations."""
        self._bound_page = page

    def unbind_page(self) -> None:
        self._bound_page = None

    def _resolve_bound_page(self, session: Any = None) -> Any:
        if session is not None:
            return getattr(session, "page", None)
        return self._bound_page

    def is_available(self) -> bool:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None

    def _cookie_file_path(self, session_name: str) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_name)
        return self.COOKIE_STORAGE_BASE / f"{safe_name}_cookies.json"

    def _load_cookies(self, context: Any, session_name: str) -> None:
        cookie_path = self._cookie_file_path(session_name)
        if not cookie_path.exists():
            return

        try:
            raw = cookie_path.read_text()
            payload = json.loads(raw)
            cookies = self._unwrap_cookie_payload(payload)
            if not isinstance(cookies, list):
                raise ValueError("Cookie payload is not a list")
            context.add_cookies(cookies)
            logger.info(
                "Loaded Playwright cookies for session '%s' from %s",
                session_name,
                cookie_path,
            )
        except Exception as exc:
            logger.warning(
                "Failed to load cookies from %s: %s. Removing stale cookie file.",
                cookie_path,
                exc,
            )
            with contextlib.suppress(OSError):
                cookie_path.unlink()

    def _unwrap_cookie_payload(self, payload: Any) -> Any:
        """ISSUE-1570: decrypt cookie envelope without ever emitting plaintext.

        Handles three storage generations:
          * envelope ``{"__enc__": True, "blob": <ciphertext str>}`` — real
            Fernet store (tuple contract); blob is decrypted then JSON-parsed.
          * envelope ``{"__enc__": True, "blob": <list>}`` — legacy mapping
            contract (kept for existing persisted stores / test doubles).
          * raw list — legacy PLAINTEXT artifact; loadable for migration but
            always re-saved encrypted on the next ``_save_cookies`` call.
        """
        if isinstance(payload, dict) and payload.get("__enc__"):
            blob = payload.get("blob", payload)
            if isinstance(blob, str):
                plain = self.secure_store.decrypt(blob)
                if isinstance(plain, str):
                    return json.loads(plain)
                return plain
            cookies = self.secure_store.decrypt(payload)
            if isinstance(cookies, dict) and cookies.get("__enc__"):
                cookies = self.secure_store.decrypt(cookies)
            return cookies
        if isinstance(payload, list):
            # Legacy plaintext cookie file — migrate silently, never re-write plaintext.
            logger.warning(
                "Legacy plaintext cookie payload detected; it will be re-encrypted on next save."
            )
            return payload
        # Unknown shape → let the store try once, then validate upstream.
        return self.secure_store.decrypt(payload)

    def _save_cookies(self, context: Any, session_name: str) -> None:
        """Persist cookies ENCRYPTED — fail closed instead of writing plaintext.

        ISSUE-1570: the previous implementation passed the raw cookie list
        straight into a bytes-oriented Fernet store, hit the type error and
        silently fell back to PLAINTEXT on disk. Now: serialize once, encrypt
        the serialized string, and refuse (raise) if encryption is unavailable
        or a provider attempts a plaintext fallback.
        """
        cookie_path = self._cookie_file_path(session_name)
        cookies = context.cookies()
        serialized = json.dumps(cookies)
        try:
            result = self.secure_store.encrypt(serialized)
        except CredentialEncryptionUnavailableError:
            raise
        except Exception as exc:
            raise CredentialEncryptionUnavailableError(
                f"Cookie encryption failed for session '{session_name}': {exc} — "
                "refusing to persist plaintext credentials (fail-closed)."
            ) from exc

        if isinstance(result, tuple):
            ciphertext = result[0]
        elif isinstance(result, dict) and result.get("__enc__"):
            ciphertext = result  # legacy mapping contract (persisted as-is)
        elif isinstance(result, str):
            ciphertext = result
        else:
            raise CredentialEncryptionUnavailableError(
                f"Cookie store returned unsupported payload type {type(result).__name__} "
                "— refusing to persist credentials (fail-closed)."
            )

        if isinstance(ciphertext, str) and ciphertext == serialized:
            # Provider fell back to plaintext — that is exactly what must NEVER land on disk.
            raise CredentialEncryptionUnavailableError(
                "Credential provider is unavailable (plaintext fallback detected) — "
                "cookie save aborted (fail-closed)."
            )

        envelope = (
            ciphertext if isinstance(ciphertext, dict) else {"__enc__": True, "blob": ciphertext}
        )
        cookie_path.write_text(json.dumps(envelope, indent=2, default=str))
        logger.info("Saved Playwright cookies for session '%s' to %s", session_name, cookie_path)

    def _human_like_type(self, page: Page, selector: str, text: str):
        """Types text into a field character by character with 30–100ms jitter."""
        if not text:
            return 0
        for char in text:
            page.type(selector, char, delay=random.uniform(30, 100))
        return len(text)

    def _human_like_click(self, page: Page, selector: str, steps: int = 25):
        """
        Moves the mouse in a human-like curve to an element and clicks it.
        This uses a Bezier curve to simulate a more natural mouse movement.
        """
        try:
            element = page.wait_for_selector(selector, timeout=self.timeout_ms)
            if not element:
                raise RuntimeError(f"Element '{selector}' not found.")

            bb = element.bounding_box()
            if not bb:
                # Fallback for elements without a clear bounding box
                logger.warning(f"Element '{selector}' has no bounding box. Using simple click.")
                page.click(selector)
                return

            # Target coordinates (center of the element with some randomness)
            target_x = bb["x"] + bb["width"] / 2 + random.uniform(-bb["width"] / 4, bb["width"] / 4)
            target_y = (
                bb["y"] + bb["height"] / 2 + random.uniform(-bb["height"] / 4, bb["height"] / 4)
            )

            # Starting coordinates (random point on the screen)
            start_x, start_y = random.uniform(0, 500), random.uniform(0, 500)

            # Control points for the Bezier curve
            control_1_x = start_x + random.uniform(50, 150) * random.choice([-1, 1])
            control_1_y = start_y + random.uniform(50, 150) * random.choice([-1, 1])
            control_2_x = target_x + random.uniform(50, 150) * random.choice([-1, 1])
            control_2_y = target_y + random.uniform(50, 150) * random.choice([-1, 1])

            # Move mouse along the curve
            page.mouse.move(start_x, start_y)
            page.mouse.move(control_1_x, control_1_y)
            page.mouse.move(control_2_x, control_2_y)
            page.mouse.move(target_x, target_y, steps=steps)
            page.mouse.click(target_x, target_y)

        except Exception as e:
            logger.error(
                f"Human-like click failed for selector '{selector}': {e}. Falling back to simple click."
            )
            page.click(selector)  # Fallback to a simple click if anything goes wrong

    def _new_context(self, session_name: str | None = None) -> tuple[Any, BrowserStealth]:
        """
        Creates a new, stealthy browser context using the BrowserStealth class.
        This method runs the async setup from BrowserStealth in a sync context.
        """
        stealth_manager = BrowserStealth()

        # Since this is a sync method, we run the async setup in a new event loop.
        # LATENT-CRASH REPAIR (2026-09-15): the original code used the RUNNING
        # loop when one was active (e.g. when the async upload_file path calls
        # this method) and then called run_until_complete on it, which raises
        # "RuntimeError: This event loop is already running". When a loop is
        # already running, complete the coroutine on a private loop inside a
        # worker thread instead of nesting on the caller's loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            context = loop.run_until_complete(stealth_manager.create_stealth_browser())
        else:
            with ThreadPoolExecutor(max_workers=1) as pool:
                context = pool.submit(
                    asyncio.run, stealth_manager.create_stealth_browser()
                ).result()

        if session_name:
            self._load_cookies(context, session_name)

        # LATENT-CRASH REPAIR (2026-09-15): this method returned only `context`,
        # but every caller (perform_task/open/screenshot/click/text/upload_file/
        # cross_verify_prompt/execute_goal) unpacks a (context, stealth_manager)
        # tuple — a TypeError made all eight public methods unreachable at
        # runtime (module measured 0% coverage). Return both, matching the
        # callers' established contract, so each task can close its own stealth
        # manager in its finally block.
        return context, stealth_manager

    def start(self) -> None:
        if not self.is_available():
            raise RuntimeError("playwright is not installed")

        # The BrowserStealth class now handles Playwright startup.
        # This method is now just a check.
        logger.debug("Playwright availability checked.")

    def stop(self) -> None:
        """
        Stops the Playwright instance. Now handled by stealth_manager cleanup.
        This method can be kept for explicit cleanup if needed, but the primary
        mechanism is now within each task's finally block.
        """
        logger.debug("Browser and context are now closed within each task.")

    def perform_task(
        self,
        url: str,
        task_function: Callable[[Any], Any],
        session_name: str | None = None,
        login_check_selector: str | None = None,
        login_flow: Callable[[Any, dict[str, str]], None] | None = None,
        credentials: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.start()
        context, stealth_manager = self._new_context(session_name)
        page = context.new_page()
        # Stealth is now applied at context creation, so stealth_sync(page) is not needed here.
        if hasattr(page, "set_default_timeout"):
            page.set_default_timeout(self.timeout_ms)

        try:
            page.goto(url)

            if login_check_selector and login_flow and credentials:
                try:
                    is_authenticated = page.is_visible(login_check_selector)
                except Exception as e:
                    try:
                        import loguru

                        loguru.logger.error(f"Tool execution error: {e}")
                    except Exception as e:
                        logger.warning(f"Exception suppressed: {e}")
                    is_authenticated = False

                if not is_authenticated:
                    logger.info(
                        "Session invalid or expired, running login flow for '%s'.",
                        session_name,
                    )
                    # Add a delay to mimic human reading time; Playwright wait keeps it observable
                    page.wait_for_timeout(int(random.uniform(1000, 2500)))
                    login_flow(page, credentials)
                    page.wait_for_load_state("networkidle")
                    self._save_cookies(context, session_name)
                else:
                    logger.info("Session restored from cookies for '%s'.", session_name)

            result = task_function(page)
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("Playwright task failed: %s", exc)
            return {"success": False, "error": str(exc)}
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    def open(self, url: str, session_name: str | None = None) -> dict[str, Any]:
        self.start()
        context, stealth_manager = self._new_context(session_name)
        page = context.new_page()
        (
            page.set_default_timeout(self.timeout_ms)
            if hasattr(page, "set_default_timeout")
            else None
        )

        try:
            page.goto(url)
            title = page.title()
            return {"success": True, "url": url, "title": title}
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    def screenshot(
        self,
        url: str,
        path: str = "browser_screenshot.png",
        session_name: str | None = None,
    ) -> dict[str, Any]:
        self.start()
        context, stealth_manager = self._new_context(session_name)
        page = context.new_page()
        (
            page.set_default_timeout(self.timeout_ms)
            if hasattr(page, "set_default_timeout")
            else None
        )

        try:
            page.goto(url)
            page.screenshot(path=path, full_page=False)
            return {"success": True, "path": path}
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    def click(self, url: str, selector: str, session_name: str | None = None) -> dict[str, Any]:
        self.start()
        context, stealth_manager = self._new_context(session_name)
        page = context.new_page()
        (
            page.set_default_timeout(self.timeout_ms)
            if hasattr(page, "set_default_timeout")
            else None
        )

        try:
            page.goto(url)
            self._human_like_click(page, selector)
            return {"success": True}
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    def text(self, url: str, selector: str, session_name: str | None = None) -> dict[str, Any]:
        self.start()
        context, stealth_manager = self._new_context(session_name)
        page = context.new_page()
        (
            page.set_default_timeout(self.timeout_ms)
            if hasattr(page, "set_default_timeout")
            else None
        )

        try:
            page.goto(url)
            content = page.text_content(selector) or ""
            return {"success": True, "text": content}
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    async def upload_file(self, selector: str, file_path: str) -> dict:
        """
        browser_file_upload - Per Master Plan Pillar 2
        Upload files through file input elements
        """
        self.start()
        # Create a new session specifically for this upload action
        # Note: In a real system, the agent should ideally maintain a live session,
        # but following the existing pattern of creating context/page per action for now
        context, stealth_manager = self._new_context("upload-session")
        page = context.new_page()
        (
            page.set_default_timeout(self.timeout_ms)
            if hasattr(page, "set_default_timeout")
            else None
        )

        try:
            # Locate file input element
            file_input = page.locator(selector)
            if not file_input:
                return {"success": False, "error": f"File input not found: {selector}"}

            # Set files
            file_input.set_input_files(file_path)

            return {
                "success": True,
                "message": f"Uploaded: {file_path}",
                "selector": selector,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            page.close()
            context.close()
            # LATENT-CRASH REPAIR (2026-09-15): asyncio.run() cannot be called
            # from inside a coroutine (a loop is already running whenever this
            # async method is awaited), so the old call raised in the finally
            # block and masked every upload_file result. Await on the running
            # loop instead — this method only ever executes inside one.
            await stealth_manager.close()

    def _update_model_behavior_in_background(
        self, model_name: str, latency_ms: float, success: bool
    ):
        """Runs the DB update in a background thread to avoid blocking."""
        try:
            import threading

            thread = threading.Thread(
                target=self._update_model_behavior,
                args=(model_name, latency_ms, success),
            )
            thread.start()
        except Exception as e:
            logger.warning(f"Failed to spawn background thread for model behavior update: {e}")

    def _update_model_behavior(self, model_name: str, latency_ms: float, success: bool):
        """The actual database update logic."""
        # This logic would be more sophisticated in a real scenario, calculating rolling averages.
        # For now, we just upsert the latest data.
        db.upsert_model_behavior(
            {
                "model_name": model_name,
                "avg_latency_ms": latency_ms,
                "last_seen_success": success,
            }
        )

    def cross_verify_prompt(
        self,
        prompt: str,
        primary_site: dict[str, str],
        verifier_site: dict[str, str],
    ) -> dict[str, Any]:
        """
        Asks a question to a primary AI, gets the result, and asks a second AI to verify it.
        """
        logger.info(f"Starting cross-verification for prompt: '{prompt[:50]}...'")
        self.start()
        context, stealth_manager = self._new_context("cross-verification-session")
        page = context.new_page()
        page.set_default_timeout(self.timeout_ms)

        try:
            # Step 0: Check if the primary AI needs verification
            primary_behavior = db.get_model_behavior(primary_site["name"])
            # Default to verifying if no data is found
            requires_verification = True
            if primary_behavior:
                # Trust score could be a mix of success rate, latency, etc.
                # For now, we use a simple flag.
                trust_score = primary_behavior.get("trust_score", 0)
                if (
                    primary_behavior.get("requires_verification") is False
                    or trust_score > TRUST_SCORE_THRESHOLD
                ):
                    requires_verification = False

            logger.info(
                f"Checking primary AI '{primary_site['name']}'. Verification required: {requires_verification}"
            )

            # Step 1: Get response from the primary AI site
            logger.info(f"Querying Primary AI: {primary_site['name']}")
            start_time = time.time()
            initial_response, primary_success = self._query_ai_site(page, primary_site, prompt)
            latency_ms = (time.time() - start_time) * 1000
            self._update_model_behavior_in_background(
                primary_site["name"], latency_ms, primary_success
            )

            if not primary_success:
                raise RuntimeError(f"Failed to get a response from {primary_site['name']}")
            logger.info(
                f"Got initial response from {primary_site['name']}: '{initial_response[:100]}...'"
            )

            # If verification is not required, return early
            if not requires_verification:
                logger.info(f"Skipping verification for trusted AI: {primary_site['name']}")
                return {
                    "success": True,
                    "prompt": prompt,
                    "initial_response": initial_response,
                    "is_confirmed": True,
                    "final_action": "implement",
                    "verification_skipped": True,
                }

            # Step 2: Ask the verifier AI to check the response
            logger.info(f"Querying Verifier AI: {verifier_site['name']}")
            verification_prompt = (
                f"Please verify the following statement and determine if it is correct. "
                f"Answer with only 'CORRECT' or 'INCORRECT'.\n\nStatement: '{initial_response}'"
            )

            start_time_verifier = time.time()
            verification_result, verifier_success = self._query_ai_site(
                page, verifier_site, verification_prompt
            )
            latency_ms_verifier = (time.time() - start_time_verifier) * 1000
            self._update_model_behavior_in_background(
                verifier_site["name"], latency_ms_verifier, verifier_success
            )

            if not verifier_success:
                raise RuntimeError(f"Failed to get a response from {verifier_site['name']}")
            logger.info(
                f"Got verification result from {verifier_site['name']}: '{verification_result}'"
            )

            # Step 3: Analyze the verification and return the final result
            is_confirmed = "correct" in verification_result.lower()

            return {
                "success": True,
                "prompt": prompt,
                "initial_response": initial_response,
                "verification_response": verification_result,
                "is_confirmed": is_confirmed,
                "final_action": "implement" if is_confirmed else "reject",
            }

        except Exception as exc:
            logger.error(f"Cross-verification failed: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    def _query_ai_site(
        self, page: Page, site_config: dict[str, str], prompt: str
    ) -> tuple[str, bool]:
        """Helper function to interact with a single AI chat website."""
        try:
            page.goto(site_config["url"])
            page.wait_for_selector(site_config["input_selector"], state="visible", timeout=20000)

            # Use human-like typing
            self._human_like_type(page, site_config["input_selector"], prompt)
            # Non-blocking pause while waiting for UI readiness
            page.wait_for_timeout(int(random.uniform(500, 1000)))

            # Click submit
            self._human_like_click(page, site_config["submit_button"])

            # Wait for the response to be generated.
            # This waits until the text content of the last message stops changing.
            page.wait_for_function(
                """
                () => {
                    const outputElements = document.querySelectorAll(arguments[0]);
                    if (outputElements.length === 0) return false;
                    const lastElement = outputElements[outputElements.length - 1];
                    if (!lastElement) return false;
                    const initialText = lastElement.textContent;
                    return new Promise(resolve => {
                        setTimeout(() => {
                            const currentText = lastElement.textContent;
                            resolve(initialText === currentText && currentText.length > 0);
                        }, 2500); // Wait 2.5 seconds to see if text changes
                    });
                }
                """,
                site_config["output_selector"],
                timeout=60000,
            )

            # Extract the text from the last message element
            response_text = page.evaluate(
                f"Array.from(document.querySelectorAll('{site_config['output_selector']}')).pop()?.textContent"
            )

            if response_text and response_text.strip():
                return response_text.strip(), True
            return "", False
        except Exception as e:
            logger.error(f"Querying AI site {site_config['name']} failed: {e}")
            return "", False

    # Example Usage:
    # agent = PlaywrightBrowserAgent(headless=False)
    # GROQ_CONFIG = {"name": "Groq", "url": "https://chat.groq.com/", "input_selector": 'textarea[aria-label="Prompt"]', "output_selector": '.message-content', "submit_button": 'button[aria-label="Submit"]'}
    # GEMINI_CONFIG = {"name": "Gemini", "url": "https://gemini.google.com/", "input_selector": '.query-input > .input-area > .ql-editor', "output_selector": '.model-response-text .markdown', "submit_button": '.send-button-container > button'}
    # result = agent.cross_verify_prompt("What is the capital of Bangladesh?", GROQ_CONFIG, GEMINI_CONFIG)
    # logger.info(result)
    # agent.stop()

    def execute_goal(self, url: str, goal: str, max_steps: int = 10) -> dict[str, Any]:
        """
        Executes a high-level goal using a vision-capable AI model.
        This is a conceptual implementation. Requires a VLM provider.
        """
        logger.info(f"Attempting to achieve goal: '{goal}' at {url}")
        self.start()
        context, stealth_manager = self._new_context("goal-execution-session")
        page = context.new_page()
        (
            page.set_default_timeout(self.timeout_ms)
            if hasattr(page, "set_default_timeout")
            else None
        )

        try:
            page.goto(url)
            # Use Playwright-native timeout instead of blocking sleep
            page.wait_for_timeout(2000)

            for step in range(max_steps):
                logger.info(f"Goal Execution Step {step + 1}/{max_steps}")

                # 1. Observe: Take a screenshot
                screenshot_path = f"step_{step}_screenshot.png"
                page.screenshot(path=screenshot_path)
                with open(screenshot_path, "rb") as image_file:
                    b64_image = base64.b64encode(image_file.read()).decode("utf-8")

                # 1.5. Recall: Consult long-term memory
                relevant_memories = asyncio.run(
                    self.memory.retrieve_relevant_memories(f"Goal: {goal} on URL: {url}")
                )

                # 2. Reason: Ask a VLM what to do next
                vlm_prompt = (
                    "You are an autonomous web agent. Your goal is to navigate a website to achieve an objective. "
                    "Based on the current screenshot and your past experiences, decide the next action to take. "
                    "Return a single JSON object with 'type' ('CLICK', 'TYPE', or 'FINISH'), 'selector' (a CSS selector for the element), "
                    "and 'text' (if typing). Provide a 'reason' for your choice.\n\n"
                    f"Objective: {goal}\n\n"
                    "Past Learnings (if any):\n"
                    f"{relevant_memories if relevant_memories else 'None'}\n\n"
                    "Analyze the screenshot and determine the next best action."
                )

                model_router = ModelRouter()
                # বাংলা: আগে model_filter=["gpt-4o", "gemini-2.5-pro-vision-latest"] হার্ডকোড ছিল —
                # দুটোই unavailable হলে browser agent সম্পূর্ণ ব্যর্থ হতো।
                # এখন task_type="vision" শুধু দিয়ে gateway সব available vision model থেকে failover করবে।
                vlm_response = asyncio.run(
                    model_router.async_route_and_generate(
                        prompt=vlm_prompt,
                        task_type="vision",
                        image_base64=b64_image,
                    )
                )

                if not vlm_response.get("success"):
                    raise RuntimeError(
                        f"VLM failed to provide an action: {vlm_response.get('text')}"
                    )

                try:
                    # Clean up potential markdown code blocks from the response
                    action_text = (
                        vlm_response["text"].strip().replace("```json", "").replace("```", "")
                    )
                    action = json.loads(action_text)
                    logger.info(f"VLM Reason: {action.get('reason', 'No reason provided.')}")
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(
                        f"Failed to parse VLM action response: {e}\nResponse was: {vlm_response['text']}"
                    )
                    return {"success": False, "error": "Failed to parse VLM action."}

                if action.get("type", "").upper() == "FINISH":
                    logger.success(f"Goal '{goal}' achieved as per VLM instruction.")
                    return {
                        "success": True,
                        "result": f"Goal achieved: {action.get('reason')}",
                    }

                logger.info(f"AI Action: {action['type']} on '{action.get('selector')}'")

                # 3. Act: Execute the action
                if action["type"] == "CLICK":
                    self._human_like_click(page, action["selector"])
                elif action["type"] == "TYPE":
                    self._human_like_type(page, action["selector"], action["text"])

                # 4. Learn: Reflect on the action and save a memory
                learning = f"For the goal '{goal}', I performed the action '{action['type']}' on the element '{action.get('selector')}'."
                asyncio.run(self.memory.add_memory(learning, url, metadata=action))

                page.wait_for_load_state("networkidle")
                # Page-settling pause via Playwright timeout to avoid blocking the event loop
                page.wait_for_timeout(2000)

            return {"success": True, "result": f"Completed {max_steps} steps."}
        except Exception as exc:
            logger.error(f"Goal execution failed: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    # =========================================================================
    # Circle C6 & FastMCP Control Tower Compatibility Layer
    # =========================================================================
    async def navigate(self, url: str) -> dict[str, Any]:
        """Async MCP wrapper for opening a URL."""
        return await asyncio.to_thread(self.open, url)

    def _click_cascade_in_fresh_context(self, url: str, target: str) -> dict[str, Any]:
        """Run the guarded cascade on a fresh context inside a worker thread."""
        context, stealth_manager = self._new_context()
        page = context.new_page()
        if hasattr(page, "set_default_timeout"):
            page.set_default_timeout(self.timeout_ms)
        try:
            page.goto(url)
            return asyncio.run(
                execute_click_cascade(page, target, human_click=self._human_like_click)
            )
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    def _type_text_in_fresh_context(self, url: str, selector: str, text: str) -> dict[str, Any]:
        """Perform TRUE keystroke insertion on a fresh context (worker thread)."""
        context, stealth_manager = self._new_context()
        page = context.new_page()
        if hasattr(page, "set_default_timeout"):
            page.set_default_timeout(self.timeout_ms)
        try:
            page.goto(url)
            typed_chars = self._human_like_type(page, selector, text)
            return {
                "success": True,
                "status": "success",
                "selector": selector,
                "typed": text,
                "typed_chars": typed_chars,
                "method": "human_like_type",
            }
        finally:
            page.close()
            context.close()
            asyncio.run(stealth_manager.close())

    async def click_target(
        self,
        target: str,
        url: str | None = None,
        session: Any = None,
    ) -> dict[str, Any]:
        """Async MCP wrapper — REAL click dispatch via the 5-step cascade.

        ISSUE-1570: the previous implementation returned ``{"success": True}``
        when no URL was supplied WITHOUT executing any click — a fake success.
        Now: a bound page (session or ``bind_page``) runs the cascade directly;
        a URL spins a fresh context in a worker thread; and with neither, the
        call FAILS HONESTLY instead of pretending.
        """
        page = self._resolve_bound_page(session)
        if page is not None:
            return await execute_click_cascade(page, target, human_click=self._human_like_click)
        if url:
            return await asyncio.to_thread(self._click_cascade_in_fresh_context, url, target)
        return {
            "success": False,
            "status": "PAUSED_HITL",
            "method": "hitl",
            "target": target,
            "reason": (
                "click_target requires a URL or an active browser session/page — "
                "refusing to report success without executing a click."
            ),
        }

    async def type_text(
        self,
        selector: str,
        text: str,
        url: str | None = None,
        session: Any = None,
    ) -> dict[str, Any]:
        """Async MCP wrapper — TRUE human-like keystroke insertion.

        ISSUE-1570: the previous implementation mapped typing to ``self.text()``
        (a READ operation) and fake-succeeded without a URL. Now typing always
        performs real per-character insertion with 30–100ms jitter.
        """
        page = self._resolve_bound_page(session)
        if page is not None:
            typed_chars = self._human_like_type(page, selector, text)
            return {
                "success": True,
                "status": "success",
                "selector": selector,
                "typed": text,
                "typed_chars": typed_chars,
                "method": "human_like_type",
            }
        if url:
            return await asyncio.to_thread(self._type_text_in_fresh_context, url, selector, text)
        return {
            "success": False,
            "status": "error",
            "selector": selector,
            "error": (
                "type_text requires a URL or an active browser session/page — "
                "refusing to fake success without typing."
            ),
        }
