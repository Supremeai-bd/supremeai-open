"""Content screening for browser scrape/audit agents (issue #1665).

Gives the browser verify chain a single, offline, stdlib-only seam to screen
untrusted page content for prompt-injection payloads BEFORE the text reaches
an agent's LLM context:

  * :func:`screen_scraped` — screen already-extracted plain text (the shape
    ``content_pruner`` / ``get_text`` paths yield). Normalizes zero-width
    obfuscation, then delegates the lexical core to the audited gateway
    detector (``gateway.prompt_injection``) instead of forking a weaker copy.
  * :func:`screen_page` — screen RAW HTML. Catches the payload classes plain
    text extraction silently drops or faithfully keeps: HTML comments, meta
    tag content, alt/title attribute payloads, and CSS-hidden elements
    (``display:none`` / ``visibility:hidden`` / ``font-size:0``) whose text
    survives ``get_text`` even though no human ever sees it.

Both functions return a :class:`ScreenResult` and NEVER raise on hostile
input — malformed/None input fails closed to "no match" rather than crashing
the fetch path. The DECISION of what to do with a flagged page (block, audit,
quarantine) belongs to the calling layer; this module only reports.

Supplemental patterns: the gateway detector targets USER-INPUT phrasings;
scraped pages add paraphrases the audited corpus pins as real attacks
("Disregard the above instructions…", "Bypass all safety filters…"). Those
live HERE, one layer above the gateway core, so the gateway module stays
byte-identical and this layer's corpus suite pins the union contract.

Canary corpus: :mod:`browser.runtime.injection_canaries` (pinned by
``tests/test_browser_injection_canary.py`` — any detection flip blocks CI).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gateway.prompt_injection import detect_injection

# Zero-width / soft-hyphen obfuscation ("i\u200bg\u200bnore ...") survives the
# gateway's lexical patterns; strip it before detection.
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\u00ad]")

# Scraped-content directive paraphrases (supplemental layer — see module doc).
_SUPPLEMENTAL: list[tuple[str, re.Pattern[str]]] = [
    (
        "directive_override",
        re.compile(
            r"\b(?:disregard|forget)\s+(?:all\s+|the\s+|any\s+)?"
            r"(?:previous|prior|above|earlier)\s+"
            r"(?:instructions|prompts|rules|directions|guidance)",
            re.IGNORECASE,
        ),
    ),
    (
        "bypass_qualified",
        re.compile(
            r"\bbypass\s+(?:all\s+|the\s+|any\s+|these\s+)?"
            r"(?:safety|guardrails|filters|restrictions)",
            re.IGNORECASE,
        ),
    ),
]

# Page-structure extractors. Each yields fragments that text extraction
# drops (comments, attributes) or keeps invisibly (hidden elements); every
# fragment is screened with the same lexical core.
_COMMENT_RX = re.compile(r"<!--(.*?)-->", re.DOTALL | re.IGNORECASE)
_META_RX = re.compile(
    r"<meta\b[^>]*?\bcontent\s*=\s*[\"']([^\"']+)[\"']", re.DOTALL | re.IGNORECASE
)
_ATTR_RX = re.compile(
    r"\b(?:alt|title)\s*=\s*[\"']([^\"']+)[\"']", re.DOTALL | re.IGNORECASE
)
_HIDDEN_TEXT_RX = re.compile(
    r"style\s*=\s*[\"'][^\"']*(?:display\s*:\s*none|visibility\s*:\s*hidden|"
    r"font-size\s*:\s*0(?:\.0+)?(?:px|em|rem|%)?\s*;?)[^\"']*[\"'][^>]*>([^<]{3,})<",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class ScreenResult:
    """Combined screening outcome across all extraction layers."""

    is_injection: bool
    score: float = 0.0
    matched: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # e.g. ["text", "html_comment"]
    sanitized: str = ""


@dataclass
class _FragmentVerdict:
    """One layer's verdict (same field shape as the gateway result)."""

    is_injection: bool
    score: float
    matched: list[str]
    sanitized: str = ""


def _detect_fragment(text: str | None) -> _FragmentVerdict:
    """Gateway core + supplemental scraped-content patterns (never raises here)."""
    if not text:
        return _FragmentVerdict(is_injection=False, score=0.0, matched=[])
    normalized = _ZERO_WIDTH.sub("", text)
    res = detect_injection(normalized)
    matched = list(res.matched)
    supplemental = 0
    for label, rx in _SUPPLEMENTAL:
        if rx.search(normalized) and label not in matched:
            matched.append(label)
            supplemental += 1
    score = float(res.score or 0.0)
    if supplemental:
        # One supplemental pattern class clears the same 0.3 threshold the
        # gateway uses for one core match (12 patterns / 4 → 1/3 = 0.33).
        score = max(score, min(1.0, 0.34 * supplemental + (0.34 if res.matched else 0.0)))
    is_injection = bool(res.is_injection or supplemental)
    return _FragmentVerdict(is_injection=is_injection, score=score, matched=matched, sanitized=res.sanitized)


def _combine(results: list[tuple[str, _FragmentVerdict]]) -> ScreenResult:
    """Merge layer results: union of matches, max score, any() verdict."""
    matched: list[str] = []
    sources: list[str] = []
    score = 0.0
    sanitized = ""
    is_injection = False
    for source, res in results:
        if res.is_injection:
            is_injection = True
            if source not in sources:
                sources.append(source)
        score = max(score, res.score)
        for label in res.matched:
            if label not in matched:
                matched.append(label)
        if source == "text" and not sanitized:
            sanitized = res.sanitized or ""
    return ScreenResult(
        is_injection=is_injection, score=score, matched=matched, sources=sources, sanitized=sanitized
    )


def screen_scraped(text: str | None) -> ScreenResult:
    """Screen plain text as extracted from a page (never raises)."""
    if not text:
        return ScreenResult(is_injection=False)
    try:
        return _combine([("text", _detect_fragment(text))])
    except Exception:  # noqa: BLE001 — hostile input must not crash the fetch path
        return ScreenResult(is_injection=False)


def screen_page(html: str | None) -> ScreenResult:
    """Screen raw HTML: body text plus comment/meta/attribute/hidden payloads."""
    if not html:
        return ScreenResult(is_injection=False)
    try:
        layers: list[tuple[str, _FragmentVerdict]] = [("text", _detect_fragment(html))]

        def frag_screen(source: str, fragments: list[str]) -> tuple[str, _FragmentVerdict]:
            matched: list[str] = []
            flagged = False
            best = 0.0
            for frag in fragments:
                if not frag or not frag.strip():
                    continue
                res = _detect_fragment(frag)
                if res.is_injection:
                    flagged = True
                    best = max(best, res.score)
                    for label in res.matched:
                        if label not in matched:
                            matched.append(label)
            return (source, _FragmentVerdict(is_injection=flagged, score=best, matched=matched))

        layers.append(frag_screen("html_comment", _COMMENT_RX.findall(html)))
        layers.append(frag_screen("meta_content", _META_RX.findall(html)))
        layers.append(frag_screen("attribute", _ATTR_RX.findall(html)))
        layers.append(frag_screen("hidden_text", _HIDDEN_TEXT_RX.findall(html)))
        return _combine(layers)
    except Exception:  # noqa: BLE001
        return ScreenResult(is_injection=False)
