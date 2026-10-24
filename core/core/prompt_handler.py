import re
from typing import Any


def normalize_prompt(prompt: str | list[dict[str, Any]]) -> str:
    """
    Extracts the textual representation of a prompt for hashing, token estimation,
    or complexity checks.
    """
    if isinstance(prompt, str):
        return prompt
    elif isinstance(prompt, list) and len(prompt) > 0:
        return str(prompt[-1].get("content", ""))
    return ""


def estimate_tokens(text: str | list[dict[str, Any]]) -> int:
    """
    Estimates the number of tokens in a prompt (rough estimate: 4 chars = 1 token).
    """
    normalized_text = normalize_prompt(text)
    return len(normalized_text) // 4


def format_unified_chat_prompt(message: str, history: list[dict[str, str]] | None = None) -> str:
    """
    Centralized prompt builder for unifying chat history with the current task.
    Prevents context loss and DRY violations across multiple routers.
    """
    if not history:
        return message

    formatted_prompt = ""
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        formatted_prompt += f"{role}: {msg.get('content', '')}\n"
    formatted_prompt += f"User: {message}\nAssistant:"
    return formatted_prompt


def compress_prompt_text(text: str) -> str:
    """
    OmniRoute-inspired 'Caveman-lite' compression.
    Removes HTML/Markdown comments and collapses duplicate whitespaces/newlines.
    """
    if not isinstance(text, str):
        return text
    # Remove HTML/Markdown comments (e.g., <!-- comment -->)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Collapse 3 or more newlines into 2 newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse 2 or more spaces into a single space, but leave newlines intact
    text = re.sub(r"[^\S\r\n]{2,}", " ", text)
    return text.strip()


def compress_prompt_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Applies Caveman-lite compression to a list of message dicts to save tokens.
    """
    compressed_messages = []
    for msg in messages:
        new_msg = msg.copy()
        if "content" in new_msg and isinstance(new_msg["content"], str):
            new_msg["content"] = compress_prompt_text(new_msg["content"])
        compressed_messages.append(new_msg)
    return compressed_messages


# ============================================================================
# PLAN-002: Claude Code-style semantic context compaction (2026-09-17)
# ---------------------------------------------------------------------------
# Pure helpers (no I/O) that let the WebSocket chat loop turn silent history
# eviction into a semantic compaction: evicted messages are summarized into a
# labeled `compacted_context` block instead of being dropped without a trace.
# Constitution anchors: #11 Memory Must Compound, #13 No Silent Failure,
# #8 Graceful Degradation. Zero new dependency, zero new infra.
# ============================================================================

COMPACTION_SYSTEM_PROMPT = (
    "You are a conversation memory compressor for SupremeAI. "
    "Summarize the conversation so far into <=350 tokens. "
    "Preserve: decisions made, file paths/commands mentioned, "
    "user preferences, open tasks, unresolved errors. "
    "Drop: greetings, filler, repeated content. "
    "Output ONLY the summary as plain text."
)

# বাংলা মন্তব্য: সামারির defensive হার্ড-ক্যাপ (≈350 টোকেন × ৪ অক্ষর) — মডেল
# ইনস্ট্রাকশন উপেক্ষা করে দীর্ঘ আউটপুট দিলেও কনটেক্সট ব্লক সীমাবদ্ধ থাকবে।
COMPACTION_SUMMARY_CHAR_CAP = 1400

COMPACTION_BLOCK_LABEL = "[CONTEXT SUMMARY — এর আগের কথোপকথনের সারসংক্ষেপ]"


def build_compaction_messages(
    evicted_messages: list[dict[str, Any]],
    prior_summary: str | None = None,
) -> list[dict[str, Any]]:
    """Claude Code-style compaction prompt তৈরি করে (pure function, no I/O).

    আগের summary থাকলে merge-নির্দেশনা সহ প্রম্পটে যুক্ত হয়, যাতে ধারাবাহিক
    compaction সাইকেলেও পুরনো তথ্য হারিয়ে না যায়।
    """
    transcript = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in evicted_messages
    )
    prior_block = f"Previous summary (merge it):\n{prior_summary}\n\n" if prior_summary else ""
    return [
        {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"{prior_block}Conversation:\n{transcript}"},
    ]


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """একই 4-chars≈1-token heuristic দিয়ে হিস্ট্রি ব্লকের আনুমানিক টোকেন (reuse estimate_tokens)."""
    return sum(estimate_tokens(m.get("content", "")) for m in messages)
