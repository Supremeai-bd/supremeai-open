# backend/core/llm/llm_gateway/context.py
"""M03 P0 — ক্যানোনিকাল ``InferenceContext`` চুক্তি (contract baseline)।

বাংলা মন্তব্য: এটি LLM অনুমানের একক-দরজা চুক্তি — কেউ যখন গেটওয়ে দিয়ে
inference করবে, তখন টেন্যান্ট/টাস্ক/বাজেট/ট্রেস প্রসঙ্গ এই এক কাঠামোয় যাবে।
ফলে কস্ট-অ্যাট্রিবিউশন, বাজেট-এনফোর্সমেন্ট ও টেলিমেট্রি আর কল-সাইট ভেদে
ছড়িয়ে থাকবে না।

সীমা-সত্য: এটি চুক্তির ভিত্তি (baseline) — ১৩টি serving route-এ বাধ্যতামূলক
প্রসঙ্গ-পাসিং (P0-র পূর্ণ অংশ) ধাপে ধাপে গ্রহণ করা হবে; এই ফাইল নিজে কোনো
ভুয়া "সব-রুট ওয়্যারড" দাবি করে না।
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class InferenceContext:
    """একটি inference-কলের ক্যানোনিকাল প্রসঙ্গ (immutable)।

    Attributes:
        tenant_id: খরচ/বাজেট-অ্যাট্রিবিউশনের মালিক — ফাঁকা হলে CostGuard
            পথ বাইপাস হয়, তাই নীতিগতভাবে ফাঁকা রাখা নিষিদ্ধ (সৎ অজানা
            টেন্যান্ট = "anonymous" — আলাদা নীতির অধীন)।
        task_type: routing/scheduling সিদ্ধান্তের ইনপুট।
        tier: tenant-এর সার্ভিস স্তর (free/pro/...) — বাজেট-ম্যাট্রিক্স কী।
        prompt/messages: নির্বাহ-ইনপুট (দুটোর ঠিক একটি)।
        stream: স্ট্রিমিং কি না — টেলিমেট্রি-প্যারিটি হিসাবের ভিত্তি।
        max_cost_usd / max_latency_seconds: per-call বাজেট সীমা।
        trace_id / correlation_id: পর্যবেক্ষণযোগ্যতা-সংযোগ।
        created_at: চুক্তি-জন্মের সময় (লেটেন্সি হিসাবের ভিত্তি)।
    """

    prompt: str | None = None
    messages: tuple[dict[str, Any], ...] | None = None
    tenant_id: str = "anonymous"
    task_type: str = "general"
    tier: str | None = None
    stream: bool = False
    max_cost_usd: float | None = None
    max_latency_seconds: float | None = None
    trace_id: str = field(default_factory=_new_trace_id)
    correlation_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> list[str]:
        """চুক্তি-লঙ্ঘনের সৎ তালিকা ফেরত দেয় — খালি মানে বৈধ।"""
        errors: list[str] = []
        if (self.prompt is None) == (self.messages is None):
            errors.append("exactly one of prompt/messages must be provided")
        if self.messages is not None and not self.messages:
            errors.append("messages must be non-empty when provided")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            errors.append("max_cost_usd must be non-negative")
        if self.max_latency_seconds is not None and self.max_latency_seconds <= 0:
            errors.append("max_latency_seconds must be positive")
        return errors

    def validate_attribution(self) -> list[str]:
        """M03 P0-পূর্ণাংশ: attribution-only ব্যবহারের যাচাই (payload ঐচ্ছিক)।

        বাংলা মন্তব্য: ১৩ serving route context-কে খরচ-অ্যাট্রিবিউশন বাহক হিসেবে
        পাস করে — প্রম্পট-পেলোড সাধারণত কল-আর্গে থাকে। তাই payload-নিয়ম
        (prompt/messages ঠিক-একটি) এখানে প্রযোজ্য নয়; কেবল অ্যাট্রিবিউশন-সত্য
        যাচাই হয়। টেন্যান্ট ফাঁকা = চুক্তি-লঙ্ঘন (সৎ-অজানা হলে "anonymous"।)
        """
        errors: list[str] = []
        if not self.tenant_id:
            errors.append("tenant_id must be non-empty (use 'anonymous' for honest-unknown)")
        if not self.task_type:
            errors.append("task_type must be non-empty")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            errors.append("max_cost_usd must be non-negative")
        if self.max_latency_seconds is not None and self.max_latency_seconds <= 0:
            errors.append("max_latency_seconds must be positive")
        return errors

    def to_log_fields(self) -> dict[str, Any]:
        """টেলিমেট্রি-লগের জন্য নিরাপদ ক্ষেত্র — প্রম্পট কনটেন্ট কখনো যায় না।"""
        return {
            "tenant_id": self.tenant_id,
            "task_type": self.task_type,
            "tier": self.tier,
            "stream": self.stream,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "prompt_chars": len(self.prompt) if self.prompt else 0,
            "message_count": len(self.messages) if self.messages else 0,
        }
