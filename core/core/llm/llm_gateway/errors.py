# backend/core/llm/llm_gateway/errors.py
"""M03 P1 — স্ট্রাকচার্ড এরর ডোমেইন (False-Assurance Purge-এর অংশ)।

বাংলা মন্তব্য: আগে গেটওয়ে-বাইপাস পথগুলো ব্যর্থ হলে বানানো উত্তর
("[Response from …]", "Hello World" stream) ফেরত দিত — ব্যবহারকারী ভুয়া
সাফল্য পেত। এখন ব্যর্থতা স্ট্রাকচার্ড এরর টাইপে সৎভাবে যায়:

- :class:`GatewayUnavailableError` — গেটওয়ে/সব provider অপ্রাপ্য; caller
  চাইলে 503 + Retry-After দিতে পারে।
- :class:`GatewayExhaustionError` — fallback chain ও retry বাজেট শেষ।
- :class:`ProviderUnavailableError` — নির্দিষ্ট provider/model অপ্রাপ্য।
"""

from __future__ import annotations


class GatewayError(Exception):
    """LLM Gateway স্ট্রাকচার্ড এররের ভিত্তি।"""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        # বাংলা: 429-ধর্মী ব্যর্থতায় caller সৎ backoff-নির্দেশ দিতে পারে।
        self.retry_after_seconds = retry_after_seconds


class GatewayUnavailableError(GatewayError):
    """গেটওয়ে নিজেই অপ্রাপ্য (কনফিগ/নেটওয়ার্ক/সব-chain ব্যর্থ)।"""


class GatewayExhaustionError(GatewayUnavailableError):
    """fallback chain + retry বাজেট সম্পূর্ণ শেষ — আর চেষ্টা নেই।"""


class ProviderUnavailableError(GatewayError):
    """নির্দিষ্ট provider/model অপ্রাপ্য — বিকল্প চেইনে fallback সম্ভব ছিল না।"""
