"""Token accounting + budget resolution for the Context Engine (M2).

বাংলা: provider-ভিত্তিক input budget নির্ধারণ ও নিরীহ (dependency-free)
token অনুমান। বাজেট অজানা provider-এর জন্য conservative default —
free-tier worst-common-case যাতে কোনো provider-এর TPM ভাঙে না।
"""

from __future__ import annotations

import os

from core.logging_config import logger

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

#: Conservative default input budget (tokens) when the target provider is
#: unknown. The tightest free-tier ceiling in PROVIDER_TOKEN_BUDGETS is
#: huggingface (1 500) — too tight as a universal default; cloudflare (3 000)
#: is the worst-common-case the gateway actually routes to.
DEFAULT_INPUT_BUDGET = 3_000

#: Fraction of the budget each non-user section may occupy at most.
#: user gets an implicit hard-reserve (see engine); system is capped so a
#: runaway system prompt can never crowd out the user's actual question.
SECTION_CAPS: dict[str, float] = {
    "system": 0.25,
    "memory": 0.40,
    "knowledge": 0.60,
    "history": 0.75,
}


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text`` — M07 P-E single-owner delegation.

    বাংলা: এস্টিমেটর এখন এক, মালিক এক — ``core.llm.token_budget.estimate_tokens``
    (M19 P-D-এর ``core.i18n.bengali_text`` blended ওজন)। এখানকার পুরনো
    chars÷4+1.3 heuristic ডুপ্লিকেট ছিল — বাংলা টেক্সটে under-count করে
    budget ভাঙত। ইঞ্জিনের প্রতিটি token-গণনা এখন ঐক্যবদ্ধ মালিকের কাছে যায়।
    """
    from core.llm.token_budget import estimate_tokens as _canonical_estimate

    return _canonical_estimate(text)


def resolve_input_budget(provider: str | None = None) -> int:
    """Resolve the per-request input token budget.

    বাংলা: provider জানা থাকলে ``core.llm.token_budget.PROVIDER_TOKEN_BUDGETS``
    থেকে তার ``max_input_tokens`` (M07 P-F মডেল-সচেতন ডাইনামিক উইন্ডো —
    vendor-সত্য রেজিস্ট্রি); না হলে ``CONTEXT_ENGINE_DEFAULT_INPUT_BUDGET``
    env (zero-hardcode), সেটাও না থাকলে :data:`DEFAULT_INPUT_BUDGET`।
    """
    if provider:
        from core.llm.token_budget import PROVIDER_TOKEN_BUDGETS

        entry = PROVIDER_TOKEN_BUDGETS.get(str(provider).lower())
        if entry and entry.get("max_input_tokens"):
            return int(entry["max_input_tokens"])

    raw = (os.getenv("CONTEXT_ENGINE_DEFAULT_INPUT_BUDGET", "") or "").strip()
    if raw:
        try:
            value = int(raw)
            if value <= 0:
                raise ValueError("must be positive")
            return value
        except ValueError:
            # বাংলা: অবৈধ env-মানে ডিফল্টে ফেরা — কিন্তু চুপ না করে জানানো।
            logger.warning(
                f"CONTEXT_ENGINE_DEFAULT_INPUT_BUDGET অবৈধ ({raw!r}) — "
                f"ডিফল্ট {DEFAULT_INPUT_BUDGET} ব্যবহৃত হচ্ছে।"
            )
    return DEFAULT_INPUT_BUDGET


def resolve_section_caps() -> dict[str, float]:
    """Env-চালিত per-section caps (M07 P-F zero-hardcode)।

    বাংলা: ডিফল্ট = :data:`SECTION_CAPS` (আজকের আচরণ অপরিবর্তিত);
    ``CONTEXT_ENGINE_{SYSTEM,MEMORY,KNOWLEDGE,HISTORY}_CAP`` env দিয়ে
    runtime-টিউনেবল। অবৈধ/সীমাবহির্ভূত মানে লাউড warning + ডিফল্ট —
    নীরব fallback নিষিদ্ধ।
    """
    caps = dict(SECTION_CAPS)
    for key, env_name in (
        ("system", "CONTEXT_ENGINE_SYSTEM_CAP"),
        ("memory", "CONTEXT_ENGINE_MEMORY_CAP"),
        ("knowledge", "CONTEXT_ENGINE_KNOWLEDGE_CAP"),
        ("history", "CONTEXT_ENGINE_HISTORY_CAP"),
    ):
        raw = (os.getenv(env_name, "") or "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
            if not 0.0 < value <= 1.0:
                raise ValueError("must be in (0, 1]")
            caps[key] = value
        except ValueError:
            logger.warning(f"{env_name} অবৈধ ({raw!r}) — ডিফল্ট {SECTION_CAPS[key]} ব্যবহৃত হচ্ছে।")
    return caps


def context_engine_enabled() -> bool:
    """Kill-switch gate: ``SUPREMEAI_CONTEXT_ENGINE=off`` → raw-prompt পথ।

    বাংলা (M07 P-F): সুইটেবল-ডিফল্ট true — আজকের আচরণ ইঞ্জিন-চালিত।
    স্পষ্ট ``off`` ছাড়া কোনো পথ raw নয়; ``on``/``true`` = চালু; অজানা-মান
    fail-closed (নীরব সক্রিয় নয়) — M05 P-A-র একই শৃঙ্খলা।
    """
    raw = (os.getenv("SUPREMEAI_CONTEXT_ENGINE", "") or "").strip().lower()
    if raw == "off":
        return False  # স্পষ্ট kill-switch
    if raw in ("on", "true"):
        return True
    if raw == "":
        return True  # ডিফল্ট: ইঞ্জিন চালু (আজকের আচরণ)
    logger.warning(f"SUPREMEAI_CONTEXT_ENGINE অজানা মান ({raw!r}) — fail-closed: ইঞ্জিন বন্ধ।")
    return False
