# backend/agents/morphic_adapter.py
import os
import re
from typing import Any

from core.config_cache import config_cache

# 🚀 Google modern SDK is optional during test/CI
try:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]


class MorphicAdapter:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key and genai is not None:
            # নতুন SDK-তে Client ইনিশিয়ালাইজেশন ইন্টারফেস
            self.client = genai.Client(api_key=self.api_key)
            # ২০২৬ সালের জন্য হাইলি স্টেবল, ফাস্ট এবং কস্ট-ইফেক্টিভ প্রোডাকশন মডেল
            self.model_name = "gemini-2.5-flash"
        else:
            self.client = None

    def _get_morphic_system_prompt(self) -> str:
        """মর্ফিক ইঞ্জিনের জন্য ওয়াটারটাইট প্রম্পট আর্কিটেকচার"""
        return """
        You are the Core Morphic Adaptation Engine of SupremeAI 2.0.
        Your sole task is to refactor arbitrary, raw Python code or MCP tools into a standardized Supreme Tool Contract.

        [STRICT CODE CONTRACT]
        1. The output MUST contain a single entry-point function exactly named: `execute_tool(payload: dict) -> dict:`
        2. All inner logic, variables, and helper functions must be self-contained within the code.
        3. The input `payload` will contain all necessary arguments passed as a dictionary.
        4. The function MUST return a dictionary containing the keys: 'success' (bool) and 'result' (any data) or 'error' (str).

        [SECURITY GUARDRAILS]
        - DO NOT import or use forbidden libraries: `os`, `subprocess`, `sys`, `requests`, `urllib`, `socket`.
        - If the raw code requires web scraping, network fetch, or system commands, wrap them into abstract logic or safely fail.
        - NEVER output markdown text, conversational explanations, or backticks (```python). Output ONLY clean, valid, executable Python code.
        """

    def adapt_code_to_contract(self, raw_code: str, skill_description: str) -> dict[str, Any]:
        """কাঁচা পাইথন কোডকে মডার্ন জেমিনি ক্লায়েন্ট দিয়ে সুপ্রীম চুক্তিতে রি-রাইট করে"""
        if not self.client:
            return {
                "success": False,
                "code": "",
                "detail": "Gemini API Client is not configured in environment.",
            }

        prompt = f"""
        Refactor the following raw code to fit the execute_tool(payload: dict) -> dict contract.

        [Skill Description]
        {skill_description}

        [Raw Source Code]
        {raw_code}
        """

        if types is None:
            return {
                "success": False,
                "code": "",
                "detail": "Google GenAI SDK is not installed.",
            }

        try:
            # মডার্ন SDK-র স্ট্যান্ডার্ড জেনারেশন মেথড এবং সিস্টেম ইন্সট্রাকশন বাইন্ডিং
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self._get_morphic_system_prompt(),
                    temperature=config_cache.get(
                        "morphic_adapter_temperature", 0.1
                    ),  # কাঠামোগত কোড আউটপুটের জন্য একদম লো-টেম্পারেচার
                ),
            )

            if not response.text:
                return {
                    "success": False,
                    "code": "",
                    "detail": "LLM returned an empty response.",
                }

            adapted_code = response.text.strip()

            # ডিফেন্সিভ ক্লিনআপ: মডেল যদি ভুল করে মার্কডাউন ব্যাকটিকস (```) দেয়, তা ছেঁটে ফেলা
            adapted_code = re.sub(r"^```python\s*", "", adapted_code)
            adapted_code = re.sub(r"^```\s*", "", adapted_code)
            adapted_code = re.sub(r"\s*```$", "", adapted_code)
            adapted_code = adapted_code.strip()

            return {
                "success": True,
                "code": adapted_code,
                "detail": "Morphic adaptation rewrite completed successfully via modern SDK.",
            }
        except Exception as e:
            return {
                "success": False,
                "code": "",
                "detail": f"LLM Morphic adaptation failure: {e!s}",
            }
