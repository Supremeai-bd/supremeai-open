"""bengali_text.py — বাংলা-সচেতন টেক্সট ইউটিলিটি (M19 P-D, single owner)।

পাঁচটি প্রতিযোগী ভাঙা estimator-fragment (token_budget / prompt_handler /
context_engine.budget / llm_router / token_juice) থেকে বাংলা-জ্ঞানের একক
উৎস। zero-dependency (stdlib only), deterministic, zero-hardcode:

- অনুপাত ও সীমা env-চালিত (``BENGALI_CHARS_PER_TOKEN``); ডিফল্ট শুধু
  conservative মান — আচরণ বদলাতে কোড-পরিবর্তন নয়, env-ই যথেষ্ট।
- সব ফাংশন pure — কোনো I/O, কোনো নীরব fallback নেই।

চুক্তি (P-D slice-1):
- :func:`nfc` — O(n) ইউনিকোড NFC গোছানো (ZWNJ/ZWJ-বাহুল্য ইনপুটে
  cache-key/vector অসঙ্গতি দূর করে);
- :func:`has_bengali` / :func:`bengali_ratio` — U+0980–U+09FF সনাক্তকরণ;
- :func:`estimate_tokens_bengali_aware` — বাংলা-অংশ আলাদা ওজনে blended
  অনুমান (ইংরেজি ~4 chars/token, বাংলা ~2 chars/token);
- :func:`truncate_dari_safe` — ডাঁড়ি (``।``/``॥``)-সচেতন ক্যারেক্টর-সীমা
  কাট; সংযুক্তাক্ষর/কার-চিহ্নের মাঝে কাটা নিষিদ্ধ।
"""

from __future__ import annotations

import os
import unicodedata

# বাংলা ইউনিকোড ব্লক: U+0980–U+09FF (ভাষা + বিশেষ অক্ষর যেমন ৺ লিগেচার)।
_BENGALI_BLOCK_START = 0x0980
_BENGALI_BLOCK_END = 0x09FF

#: বাংলা অক্ষরপ্রতি আনুমানিক token-সংখ্যার অন্বেষণ-ভিত্তিক বিপরীত —
#: অর্থাৎ প্রতি token-এ কতটি বাংলা অক্ষর (chars/token)। আধুনিক BPE
#: tokenizer-এ বাংলা ~1.5–2 অক্ষর/token; conservative ডিফল্ট 2.0 —
#: ইংরেজির (4.0) অর্ধেক, অর্থাৎ বাংলা টেক্সটে ২ গুণ token ধরা হয়।
#: zero-hardcode: env-দিয়ে টিউনযোগ্য, কোনো কোড-পরিবর্তন ছাড়াই।
DEFAULT_BENGALI_CHARS_PER_TOKEN = 2.0

#: ডাঁড়ি-বাক্যশেষ চিহ্ন — বাংলা বাক্য ``।`` বা ``॥`` দিয়ে শেষ হয়।
DARI_TERMINATORS = ("।", "॥")


def bengali_chars_per_token() -> float:
    """Env-চালিত বাংলা chars/token অনুপাত (অবৈধ মানে ডিফল্ট + loud)।"""
    raw = os.environ.get("BENGALI_CHARS_PER_TOKEN", "").strip()
    if not raw:
        return DEFAULT_BENGALI_CHARS_PER_TOKEN
    try:
        value = float(raw)
    except ValueError:
        # বাংলা: অবৈধ env-মানে নীরবভাবে ভুল অনুমান নয় — ডিফল্টে ফিরে
        # গিয়ে সতর্ক করা হয় যাতে ভুল টিউনিং লুকিয়ে থাকতে না পারে।
        import logging

        logging.getLogger(__name__).warning(
            f"BENGALI_CHARS_PER_TOKEN={raw!r} অবৈধ — ডিফল্ট "
            f"{DEFAULT_BENGALI_CHARS_PER_TOKEN} ব্যবহৃত হচ্ছে"
        )
        return DEFAULT_BENGALI_CHARS_PER_TOKEN
    if value <= 0:
        import logging

        logging.getLogger(__name__).warning(
            f"BENGALI_CHARS_PER_TOKEN={raw!r} অসঙ্গত (≤0) — ডিফল্ট ব্যবহৃত"
        )
        return DEFAULT_BENGALI_CHARS_PER_TOKEN
    return value


def _is_mark(ch: str) -> bool:
    """Combining/spacing mark (কার, হসন্ত, চন্দ্রবিন্দু) — একা অর্থহীন অক্ষর।

    বাংলা কার-চিহ্ন (যেমন ি U+09BF) ইউনিকোডে Mc (spacing mark) —
    ``unicodedata.combining()`` এগুলোর জন্য 0 দেয়, তাই category-চেক বাধ্যতামূলক।
    """
    return unicodedata.combining(ch) != 0 or unicodedata.category(ch) in {"Mn", "Mc"}


def nfc(text: str) -> str:
    """ইউনিকোড NFC গোছানো — O(n), idempotent।"""
    return unicodedata.normalize("NFC", text)


def _is_bengali(ch: str) -> bool:
    return _BENGALI_BLOCK_START <= ord(ch) <= _BENGALI_BLOCK_END


def has_bengali(text: str) -> bool:
    """টেক্সটে অন্তত একটি বাংলা অক্ষর আছে কি না।"""
    return any(_is_bengali(ch) for ch in text)


def bengali_ratio(text: str) -> float:
    """মোট অক্ষরের কত ভগ্নাংশ বাংলা-ব্লক অক্ষর (0.0–1.0)।"""
    if not text:
        return 0.0
    bengali = sum(1 for ch in text if _is_bengali(ch))
    return bengali / len(text)


def estimate_tokens_bengali_aware(text: str) -> int:
    """বাংলা-সচেতন token অনুমান — blended, deterministic, tiktoken-মুক্ত।

    বাংলা: টেক্সটকে বাংলা ও অবাংলা অংশে ভেঙে আলাদা অনুপাতে গোনা হয় —
    মিশ্র-ভাষার প্রম্পটে (বাংলা প্রশ্ন + ইংরেজি কোড) এক-অনুপাত মডেল
    ব্যবস্থাগতভাবে under-estimate করত; বাজেট এনফোর্সমেন্টে তা quota-ভাঙার
    ঝুঁকি। কোড-ব্লক ও CJK সনাক্তি caller-চুক্তির সাথে সামঞ্জস্যে এখানেও রাখা।
    """
    if not text:
        return 0

    # কোড-ব্লক সনাক্তি — token_budget-এর বিদ্যমান অনুপাত-চুক্তি অক্ষুণ্ণ।
    if "```" in text or "def " in text or "class " in text:
        return max(1, int(len(text) / 3.5))

    bengali = sum(1 for ch in text if _is_bengali(ch))
    rest = len(text) - bengali

    # CJK আধিপত্য — বিদ্যমান 2.0 অনুপাত অক্ষুণ্ণ (token_budget চুক্তি)।
    if bengali == 0 and any("\u4e00" <= c <= "\u9fff" for c in text[:100]):
        return max(1, int(len(text) / 2.0))

    tokens = bengali / bengali_chars_per_token()
    if rest:
        tokens += rest / 4.0
    return max(1, int(tokens) + (1 if tokens > int(tokens) else 0))


def truncate_dari_safe(text: str, max_chars: int) -> str:
    """ক্যারেক্টর-সীমায় বাংলা-নিরাপদ কাট — ডাঁড়ি-পছন্দী, সংযুক্তি-সচেতন।

    বাংলা: কাট-পয়েন্ট যতটা সম্ভব বাক্যশেষ ডাঁড়ির (``।``/``॥``) পরে বসে;
    না পেলে hard cut, তবে কাট-পয়েন্ট কোনো combining mark (কার/হসন্ত/
    চন্দ্রবিন্দু)-এর মাঝে পড়লে পূর্ববর্তী অক্ষর-সীমায় সরিয়ে নেওয়া হয় —
    অর্ধ-অক্ষর ফেলে অর্থ ভাঙা নিষিদ্ধ। NFC-গোছানো ইনপুটে কাজ করে।
    """
    if max_chars <= 0:
        return ""
    text = nfc(text)
    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]

    # 1) সংযুক্তি-নিরাপত্তা: কাট-পয়েন্টে থাকা শেষ অক্ষর mark হলে
    #    কাট-পয়েন্ট পিছানো হয় (mark তার মূল অক্ষর ছাড়া অর্থহীন)।
    while len(cut) > 1 and _is_mark(cut[-1]):
        cut = cut[:-1]

    # 2) ডাঁড়ি-পছন্দ: ৬০%-এর পরে শেষ ডাঁড়ি-বাক্যশেষ খোঁজা হয়।
    search_start = int(len(cut) * 0.6)
    best = -1
    for sep in DARI_TERMINATORS:
        idx = cut.rfind(sep, search_start)
        if idx > best:
            best = idx
    if best != -1:
        end = best + 1
        # ডাঁড়ি-পরবর্তী mark থাকলে তা সহ নেওয়া হয়।
        while end < len(cut) and _is_mark(cut[end]):
            end += 1
        return cut[:end].rstrip()

    return cut.rstrip()
