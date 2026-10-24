"""gateway/service/response_guard.py - Post-generation sanitizer (spec Phase 2)."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("supremeai.response_guard")

STUB_MARKERS = (
    "Web Session Active",
    "health=",
    "Authenticated via",
    "health=200",
)

IDENTITY_BRANDS = (
    "Gemini", "Google", "Llama", "Meta", "ChatGPT", "OpenAI",
    "Claude", "Anthropic", "Mistral", "Hugging Face", "HuggingFace",
)


def purge_identity_bleed(text: Any) -> str:
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    phrase_patterns = [
        (r"i am (?:a |an )?(?:gemini|chatgpt|gpt-?4|llama|claude|mistral)\b", "I am SupremeAI"),
        (r"developed by (?:google|meta|openai|anthropic|mistral)\b", "developed by SupremeAI"),
        (r"created by (?:google|meta|openai|anthropic|mistral)\b", "created by SupremeAI"),
        (r"built by (?:google|meta|openai|anthropic|mistral)\b", "built by SupremeAI"),
        (r"made by (?:google|meta|openai|anthropic|mistral)\b", "made by SupremeAI"),
    ]
    for pat, repl in phrase_patterns:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    for brand in IDENTITY_BRANDS:
        s = re.sub(r"\b" + re.escape(brand) + r"\b", "SupremeAI", s, flags=re.IGNORECASE)
    return s


def is_stub_content(text: Any) -> bool:
    if text is None:
        return True
    s = text if isinstance(text, str) else str(text)
    stripped = s.strip()
    if not stripped:
        return True
    low = stripped.lower()
    if low in {"ok", "hello", "hi", "test", "...", "n/a", "none"}:
        return True
    for marker in STUB_MARKERS:
        if marker.lower() in low:
            return True
    if len(stripped) < 4:
        return True
    return False


def repair_markdown(text: Any) -> str:
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    fence_count = s.count("```")
    if fence_count % 2 != 0:
        s = s.rstrip() + "\n```"
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def validate_and_sanitize(value: Any, *args, **kwargs) -> Any:
    if isinstance(value, dict):
        resp = dict(value)
        choices = resp.get("choices")
        content = ""
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                elif "text" in first:
                    content = first.get("text", "")
        if not content and "content" in resp:
            content = resp.get("content", "")
        if not content and "reply" in resp:
            content = resp.get("reply", "")

        if is_stub_content(content):
            raise ValueError("stub or broken content rejected")
        cleaned = repair_markdown(purge_identity_bleed(content))
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            msg = choices[0].get("message")
            if isinstance(msg, dict):
                msg["content"] = cleaned
                choices[0]["message"] = msg
            elif "text" in choices[0]:
                choices[0]["text"] = cleaned
            resp["choices"] = choices
        if "content" in resp and not isinstance(resp.get("choices"), list):
            resp["content"] = cleaned
        if "reply" in resp and "choices" not in resp:
            resp["reply"] = cleaned
        return resp

    s = "" if value is None else (value if isinstance(value, str) else str(value))
    if is_stub_content(s):
        raise ValueError("stub or broken content rejected")
    return repair_markdown(purge_identity_bleed(s))


def sanitize_response(*args, **kwargs) -> Any:
    try:
        return validate_and_sanitize(*args, **kwargs)
    except Exception:
        return None


purge = purge_identity_bleed
scrub_identity = purge_identity_bleed
sanitize = validate_and_sanitize

__all__ = [
    "STUB_MARKERS",
    "IDENTITY_BRANDS",
    "purge_identity_bleed",
    "is_stub_content",
    "repair_markdown",
    "validate_and_sanitize",
    "sanitize_response",
]
