from typing import Any

from tools.browser.web_scraper import WebScraper


class AIWebExtractor:
    def __init__(self):
        self.scraper = WebScraper()

    async def extract_data(self, url: str, extraction_prompt: str) -> dict[str, Any]:
        """Fetch page and use AI to extract structured data."""
        page_data = self.scraper.fetch_page(url)
        if not page_data["success"]:
            return page_data

        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()
            prompt = (
                f"Extract the following from this web page content:\n{extraction_prompt}\n\n"
                f"Page Title: {page_data.get('title')}\n"
                f"Content: {page_data.get('content', '')[:2000]}\n\n"
                "Return a clean JSON object with the extracted data."
            )
            result = await router.async_route_and_generate(
                prompt, task_type="reasoning", max_cost=0.02
            )
            extracted = result.get("text", "") if isinstance(result, dict) else ""
            return {
                "success": True,
                "url": url,
                "extracted": extracted,
                "raw": page_data,
            }
        except Exception as e:
            # মডেল রাউটার বা ডেটা এক্সট্র্যাকশন সম্পর্কিত যেকোনো ত্রুটি এখানে ধরা হলো
            return {"success": False, "error": str(e)}
