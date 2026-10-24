"""Prompt Firewall — Constitutional AI + Local Pattern Blocking.

বাংলা: প্রম্পট ফায়ারওয়াল — কনস্টিটিউশনাল AI + লোকাল প্যাটার্ন ব্লকিং।
Anthropic Constitutional AI pattern implementation.
Validates model responses against constitutional principles before sending to user.

Key Features:
- Local heuristic pattern matching (LLM-free fast path)
- Constitutional AI critique-revision cycle
- Bengali native enforcement rules
- Intent classification (keyword-based)
"""

from __future__ import annotations

import re
from typing import Any

from core.config import settings
from core.llm.llm_gateway import GatewayManager
from core.logging_config import logger

CONSTITUTIONAL_PRINCIPLES: list[str] = [
    "Avoid generating harmful or dangerous content",
    "Do not assist with illegal activities",
    "Protect user privacy and do not leak PII",
    "Be honest about AI limitations and do not hallucinate facts",
]

_LOCAL_BLOCK_PATTERNS: dict[str, list[str]] = {
    "prompt_injection": [
        "disregard previous instructions",
        "ignore all prior",
        "forget your instructions",
        "new personality",
        "act as",
        "jailbreak",
    ],
    "sensitive_extraction": [
        "password=",
        "api_key=",
        "secret=",
        "token=",
        "credentials",
    ],
    "malicious_code": [
        "rm -rf",
        "DROP TABLE",
        "eval(",
        "__import__",
        "os.system",
        "echo malicious_payload_blocked",
    ],
}

import time  # বাংলা মন্তব্য: Dynamic TTL cache invalidation

# Pre-compiled regex cache for fast heuristic matching
_compiled_patterns: list[re.Pattern] = []
_patterns_loaded_at: float = 0.0
_PATTERNS_TTL_SECONDS: float = 60.0


def invalidate_pattern_cache() -> None:
    """DB/admin panel থেকে pattern আপডেট হলে caller এটি কল করে সাথে সাথে rebuild করাতে পারবে।"""
    global _compiled_patterns, _patterns_loaded_at
    _compiled_patterns, _patterns_loaded_at = [], 0.0


def _get_compiled_patterns() -> list[re.Pattern]:
    global _compiled_patterns, _patterns_loaded_at
    now = time.time()
    if not _compiled_patterns or (now - _patterns_loaded_at) > _PATTERNS_TTL_SECONDS:
        all_patterns = []
        for patterns in _LOCAL_BLOCK_PATTERNS.values():
            all_patterns.extend(patterns)
        # Add custom patterns from settings
        all_patterns.extend(settings.prompt_blocked_patterns)

        rebuilt: list[re.Pattern] = []
        for p in all_patterns:
            try:
                # Escape pattern to prevent regex injection, then compile case-insensitive
                rebuilt.append(re.compile(re.escape(p), re.IGNORECASE))
            except Exception as e:
                # বাংলা মন্তব্য: pattern compile ব্যর্থ হলে তা লগ করা হচ্ছে যাতে সিকিউরিটি রুল কার্যকর না হওয়ার কারণ বোঝা যায়।
                logger.error(f"[PromptFirewall] Failed to compile blocked pattern '{p}': {e}")
        _compiled_patterns, _patterns_loaded_at = rebuilt, now
    return _compiled_patterns


_BENGALI_ENFORCEMENT_HEADER: str = (
    "BENGALI NATIVE ENFORCEMENT RULES:\n"
    "- Always respond in Bangla (বাংলা) when the user writes in Bangla.\n"
    "- Be culturally sensitive and respectful to Bangladeshi users.\n"
    "- Prioritize clarity and helpfulness over formality.\n"
)


class PromptFirewall:
    """Validates prompts and responses against constitutional principles and local patterns.

    বাংলা: সাংবিধানিক নীতি এবং স্থানীয় প্যাটার্নের বিরুদ্ধে প্রম্পট এবং প্রতিক্রিয়া বৈধতা দেয়।
    """

    def __init__(self, gateway: GatewayManager | None = None) -> None:
        self.gateway = gateway or GatewayManager()
        # Model for quick critique — env-driven via settings
        self.cheap_model: str = settings.claude_openrouter_model or "gemini/gemini-2.5-flash"

    def enforce_bengali_rules(self, system_prompt: str) -> str:
        """Inject Bengali enforcement header if not already present.

        বাংলা: বাংলা এনফোর্সমেন্ট হেডার যোগ করে যদি না থাকে।
        """
        if "BENGALI NATIVE ENFORCEMENT RULES" in system_prompt:
            return system_prompt
        return system_prompt + "\n" + _BENGALI_ENFORCEMENT_HEADER

    def validate_agent_response(self, response: str) -> bool:
        """Validate that a response is non-empty and contains Bangla text.

        বাংলা: রেসপন্স খালি নয় কিনা এবং বাংলা টেক্সট আছে কিনা চেক করে।
        """
        if not response or not response.strip():
            return False
        return bool(re.search(r"[\u0980-\u09FF]", response))

    def _check_local_patterns(self, text: str) -> str | None:
        """Local heuristic check — LLM-free fast path with pre-compiled regex.

        বাংলা: স্থানীয় হিউরিস্টিক চেক — LLM ছাড়া দ্রুত পাথ।
        """
        for pattern in _get_compiled_patterns():
            if pattern.search(text):
                return "policy_violation"
        return None

    async def constitutional_filter(self, response_text: str) -> tuple[str, bool]:
        """Anthropic Constitutional AI pattern with critique-revision cycle.

        Returns:
            Tuple of (filtered_response, was_revised).

        বাংলা: কনস্টিটিউশনাল AI প্যাটার্ন — সমালোচনা-সংশোধন চক্র।
        """
        # Local check first — avoids LLM call for obvious violations
        local_threat = self._check_local_patterns(response_text)
        if local_threat:
            logger.warning(f"Local pattern blocked: {local_threat}")
            return "[Content blocked by local policy filter]", True

        for principle in CONSTITUTIONAL_PRINCIPLES:
            try:
                # 1. Critique phase
                critique_prompt = (
                    f"Does the following response violate this principle: '{principle}'?\n\n"
                    f"Response:\n{response_text}\n\nAnswer ONLY with 'YES' or 'NO'."
                )
                critique_response = await self.gateway.acompletion(
                    prompt=critique_prompt, model=self.cheap_model
                )
                critique_text = critique_response.get("text", "").strip().upper()

                if "YES" in critique_text:
                    logger.warning(f"Constitutional AI triggered on principle: '{principle}'")

                    # 2. Revision phase
                    revision_prompt = (
                        f"The following response violates the principle: '{principle}'. "
                        f"Please revise it to be compliant while preserving the original intent.\n\n"
                        f"Response:\n{response_text}"
                    )
                    revised_response = await self.gateway.acompletion(
                        prompt=revision_prompt, model=self.cheap_model
                    )
                    return revised_response.get("text", response_text), True

            except Exception as exc:
                # বাংলা মন্তব্য: httpx/provider-নির্দিষ্ট exception সহ যেকোনো ব্যর্থতায় পরের
                # principle-এ এগিয়ে যাওয়া হচ্ছে, পুরো pipeline crash করার বদলে।
                logger.error(
                    f"Constitutional filter error on principle '{principle}': {type(exc).__name__}: {exc}"
                )
                continue

        return response_text, False


# Singleton instance
firewall = PromptFirewall()


async def pre_flight_scan(prompt: str) -> dict[str, Any]:
    """Quick local check before submitting prompt to LLM.

    বাংলা: LLM-এ প্রম্পট সাবমিট করার আগে দ্রুত স্থানীয় চেক।

    Returns:
        dict with 'allowed' and optional 'threat_type' keys.
    """
    threat = firewall._check_local_patterns(prompt)
    if threat:
        return {
            "allowed": False,
            "threat_type": threat,
            "reason": f"Local pattern match: {threat}",
        }
    return {"allowed": True, "threat_type": None}


async def classify_intent(prompt: str) -> dict[str, Any]:
    """Keyword-based intent classification without LLM call.

    বাংলা: LLM কল ছাড়া কীওয়ার্ড-ভিত্তিক ইন্টেন্ট ক্লাসিফিকেশন।
    """
    lower = prompt.lower()

    coding_keywords = [
        "write",
        "code",
        "script",
        "function",
        "implement",
        "debug",
        "python",
        "javascript",
    ]
    reasoning_keywords = [
        "why",
        "explain",
        "analyze",
        "compare",
        "difference",
        "reason",
        "because",
    ]
    creative_keywords = ["story", "poem", "creative", "imagine", "write a", "compose"]

    if any(kw in lower for kw in coding_keywords):
        return {"intent": "coding", "confidence": 0.9}
    if any(kw in lower for kw in reasoning_keywords):
        return {"intent": "reasoning", "confidence": 0.85}
    if any(kw in lower for kw in creative_keywords):
        return {"intent": "creative", "confidence": 0.8}

    return {"intent": "general", "confidence": 0.6}
