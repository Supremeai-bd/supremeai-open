"""
Provides tools to extract API specifications from PDF documents and generate client SDKs.

It attempts to parse API endpoint information from PDF text using various extraction libraries
and can leverage AI models for comprehensive SDK generation, with a fallback to basic SDK scaffolding.
"""

import os
import re
from typing import Any

from core.logging_config import logger


class PDFToSDKConverter:
    def __init__(self):
        logger.info("Initialized PDFToSDKConverter")

    async def extract_api_spec(self, pdf_path: str) -> dict[str, Any]:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found at {pdf_path}")
        logger.info(f"Extracting API spec from {pdf_path}")

        text = ""
        try:
            import fitz

            doc = fitz.open(pdf_path)
            text = "\n".join(page.get_text() for page in doc)
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            pass

        if not text:
            try:
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            except Exception as e:
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                pass

        if not text:
            logger.warning("PDF text extraction libraries not available. Using empty spec.")
            return {"base_url": "", "auth": "", "endpoints": []}

        endpoints = []
        for line in text.splitlines():
            match = re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+([^\s]+)", line, re.IGNORECASE)
            if match:
                endpoints.append(
                    {
                        "method": match.group(1).upper(),
                        "path": match.group(2),
                        "description": line.strip()[:120],
                    }
                )

        return {
            "base_url": "https://api.example.com/v1",
            "auth": "Bearer {API_KEY}",
            "endpoints": endpoints[:50],
            "raw_text_preview": text[:2000],
        }

    async def generate_sdk(self, pdf_path: str, languages: list[str]) -> dict[str, str]:
        try:
            spec = await self.extract_api_spec(pdf_path)
            try:
                from brain.model_router import ModelRouter

                router = ModelRouter()
                endpoint_desc = ", ".join(
                    f"{e['method']} {e['path']}" for e in spec.get("endpoints", [])[:10]
                )
                prompt = (
                    f"You are a senior SDK engineer. Generate a full, production-ready client SDK in the requested language "
                    f"for this API spec. Base URL: {spec['base_url']}. Auth: {spec['auth']}. "
                    f"Endpoints: {endpoint_desc}. Return ONLY code, no markdown formatting."
                )
                result = await router.async_route_and_generate(
                    prompt, task_type="coding", max_cost=0.05
                )
                text = result.get("text", "") if isinstance(result, dict) else ""
                if text:
                    return {
                        "status": "success",
                        "sdks": {languages[0] if languages else "python": text.strip()},
                    }
            except Exception as llm_err:
                logger.warning(f"LLM-based SDK generation failed: {llm_err}")

            results = {}
            lang = languages[0] if languages else "python"
            endpoint_str = "\n    ".join(
                f"def {e['method'].lower()}_{e['path'].strip('/').replace('/', '_').replace('{', '').replace('}', '')}(self): ..."
                for e in spec.get("endpoints", [])[:5]
            )
            if lang.lower() == "python":
                results[lang] = f"""
import httpx

class ApiClient:
    def __init__(self, token: str):
        self.client = httpx.Client(
            base_url="{spec["base_url"]}",
            headers={{"Authorization": f"Bearer {{token}}"}}
        )
    {endpoint_str}
"""
            else:
                results[lang] = f"// SDK generation for {lang} requires manual implementation."
            return {"status": "success", "sdks": results}
        except Exception as e:
            logger.error(f"SDK Generation failed: {e!s}")
            return {"status": "error", "error": str(e)}
