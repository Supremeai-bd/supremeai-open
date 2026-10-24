from core.logging_config import logger


class WebFallbackAgent:
    """
    WebFallbackAgent — Headless browser automation.
    বাংলা মন্তব্য: আগে এখানে সম্পূর্ণ মক স্টেপ রিটার্ন করা হতো।
    এখন এটি প্লেরাইট (Playwright) লাইব্রেরি ব্যবহার করে রিয়াল ব্রাউজার অটোমেশন টাস্ক
    যেমন নেভিগেশন, ইনপুট ফিলিং এবং বাটনে ক্লিক করতে পারে।
    """

    def __init__(self):
        logger.info("WebFallbackAgent initialized with Playwright automation support.")

    async def use_web_version(self, tool_name: str, url: str, task: dict) -> dict:
        """
        Runs headless browser commands using Playwright
        to automate tasks on third-party web tools when APIs are unavailable.
        """
        logger.info(
            "Navigating to %s to perform web-version fallback task for '%s'",
            url,
            tool_name,
        )

        steps_executed = []
        try:
            # বাংলা মন্তব্য: Playwright dynamically import করা হচ্ছে যাতে dependency না থাকলে ক্র্যাশ না হয়
            from playwright.async_api import async_playwright

            steps_executed.append(
                {
                    "step": 1,
                    "action": f"Launch browser and navigate to {url}",
                    "status": "running",
                }
            )

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                steps_executed[-1]["status"] = "completed"

                # Perform basic login sequence if credentials present in task
                if "login_selector" in task and "username" in task:
                    steps_executed.append(
                        {
                            "step": 2,
                            "action": "Perform auto-login sequence",
                            "status": "running",
                        }
                    )
                    await page.fill(task["login_selector"], task["username"])
                    if "password_selector" in task and "password" in task:
                        await page.fill(task["password_selector"], task["password"])
                    if "submit_selector" in task:
                        await page.click(task["submit_selector"])
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    steps_executed[-1]["status"] = "completed"

                # Perform custom action (e.g. click, fill or scrape)
                action = task.get("action")
                steps_executed.append(
                    {
                        "step": 3,
                        "action": f"Execute action: {action}",
                        "status": "running",
                    }
                )

                result_content = ""
                if action == "click" and "selector" in task:
                    await page.click(task["selector"])
                    await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    result_content = "Element clicked."
                elif action == "fill" and "selector" in task:
                    await page.fill(task["selector"], task.get("value", ""))
                    result_content = "Input field populated."
                elif action == "scrape":
                    # Extract text or body content
                    result_content = await page.inner_text(task.get("selector", "body"))
                else:
                    # Default: get page title and url
                    title = await page.title()
                    result_content = f"Page loaded. Title: {title}"

                steps_executed[-1]["status"] = "completed"

                # Capture final result screenshot (saved in temporary dir)
                steps_executed.append(
                    {
                        "step": 4,
                        "action": "Extract results and screenshot",
                        "status": "completed",
                    }
                )
                screenshot_data = await page.screenshot(type="png", full_page=False)

                await browser.close()

                return {
                    "success": True,
                    "tool": tool_name,
                    "url": url,
                    "steps_executed": steps_executed,
                    "result_summary": f"Task '{action}' automated via browser successfully.",
                    "scraped_data": result_content,
                    "has_screenshot": screenshot_data is not None,
                }

        except ImportError:
            # বাংলা মন্তব্য: Playwright না থাকলে আর ভুয়া "simulated" সফলতা রিটার্ন হয় না
            # (audit B-05 fix, 2026-09-17) — সৎ ব্যর্থতা, কোনো fabricated স্টেপ/ডেটা নেই।
            logger.error(
                "Playwright is not installed — web fallback automation CANNOT run. "
                "Returning honest failure instead of fabricated success."
            )
            return {
                "success": False,
                "tool": tool_name,
                "url": url,
                "steps_executed": steps_executed,
                "error": (
                    "Browser automation unavailable: the 'playwright' package is not "
                    "installed in this environment. Install it (and its chromium binary) "
                    "to enable web fallback automation."
                ),
            }
        except Exception as exc:
            logger.error(f"Playwright execution failed: {exc}")
            return {
                "success": False,
                "tool": tool_name,
                "url": url,
                "steps_executed": steps_executed,
                "error": str(exc),
            }
