"""
backend/browser/semantic_dom.py
================================
L4: Semantic DOM Engine — Embeds interactive DOM elements to resolve queries by MEANING,
not fragile CSS/XPath syntax (e.g. 'click the checkout button', 'open user profile').
"""

from __future__ import annotations

import inspect
import math
from typing import Any

from core.embeddings import EmbeddingEngine
from core.logging_config import logger

# ── Confidence Guardrails (issue #1570 Part 1) ────────────────────────────
# score >= 0.85   → execute immediately
# score 0.65–0.85 → secondary verification before acting
# score <  0.65   → escalate to HITL (never blind-act)
CONFIDENCE_EXECUTE = 0.85
CONFIDENCE_VERIFY = 0.65


def confidence_band(score: float) -> str:
    """Map a raw match score onto the guardrail decision bands."""
    if score >= CONFIDENCE_EXECUTE:
        return "execute"
    if score >= CONFIDENCE_VERIFY:
        return "verify"
    return "hitl"


class ElementNotFoundSemantically(Exception):
    """Raised when no element matches the query with sufficient confidence (triggers L4 Vision Grounding fallback)."""

    pass


class SemanticDOM:
    def __init__(self, page: Any = None):
        self.page = page
        self.engine = EmbeddingEngine.get_instance()
        self._vectors: list[tuple[list[float], dict[str, Any]]] = []

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2, strict=True))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 <= 0 or norm2 <= 0:
            return 0.0
        return dot / (norm1 * norm2)

    async def build_index(self, elements_snapshot: list[dict[str, Any]] | None = None) -> int:
        """Embed all interactive elements of the current page state."""
        self._vectors = []
        elements: list[dict[str, Any]] = []

        if elements_snapshot is not None:
            elements = elements_snapshot
        elif self.page is not None and hasattr(self.page, "evaluate"):
            try:
                # ISSUE-1570: page হতে পারে sync Playwright Page অথবা async Page —
                # sync page-এ evaluate() সরাসরি value দেয়, async page-এ coroutine.
                # isawaitable guard দুই ধরনের page-কেই সাপোর্ট করে।
                result = self.page.evaluate("""() => {
                    const results = [];
                    
                    const getXPath = (el) => {
                        if (el.id) return `//*[@id="${el.id}"]`;
                        if (el.name) return `//*[@name="${el.name}"]`;
                        return `//${el.tagName.toLowerCase()}[contains(text(), "${(el.innerText||'').slice(0,20).replace(/"/g, "'")}")]`;
                    };
                    
                    // Regular DOM elements
                    document.querySelectorAll('button, a, input, select, textarea, [role], [onclick]')
                        .forEach(el => results.push({
                            tag: (el.tagName || '').toLowerCase(),
                            text: (el.innerText || el.value || el.ariaLabel || el.title || el.placeholder || '').trim().slice(0, 120),
                            role: el.getAttribute('role') || '',
                            placeholder: el.placeholder || '',
                            xpath: getXPath(el),
                            is_shadow: false
                        }));
                    
                    // ✅ NEW: Shadow DOM support
                    document.querySelectorAll('*').forEach(host => {
                        if (host.shadowRoot) {
                            host.shadowRoot.querySelectorAll('button, a, input, [role]')
                                .forEach(el => results.push({
                                    tag: `shadow:${(el.tagName || '').toLowerCase()}`,
                                    text: (el.innerText || el.value || el.ariaLabel || el.title || el.placeholder || '').trim().slice(0, 120),
                                    role: el.getAttribute('role') || '',
                                    placeholder: el.placeholder || '',
                                    xpath: `[shadow-host] >> ${getXPath(el)}`,
                                    is_shadow: true
                                }));
                        }
                    });
                    
                    return results;
                }""")
                if inspect.isawaitable(result):
                    result = await result
                # ISSUE-1570: non-list result (যেমন mock page-এর string) গ্রহণ করা যাবে না —
                # একে mock-fallback path-এ পাঠানো হয় যাতে build_index কখনো ক্র্যাশ না করে।
                elements = result if isinstance(result, list) else []
            except Exception as exc:
                logger.debug(f"[SemanticDOM] Page evaluation fallback: {exc}")

        if not elements:
            # Fallback mock elements for headless or decoupled mode
            elements = [
                {
                    "tag": "button",
                    "text": "Submit Checkout",
                    "role": "button",
                    "xpath": "//button[@type='submit']",
                    "is_shadow": False,
                },
                {
                    "tag": "a",
                    "text": "View Cart",
                    "role": "link",
                    "xpath": "//a[@href='/cart']",
                    "is_shadow": False,
                },
                {
                    "tag": "input",
                    "text": "Search Products",
                    "role": "searchbox",
                    "xpath": "//input[@name='q']",
                    "is_shadow": False,
                },
                {
                    "tag": "button",
                    "text": "Login",
                    "role": "button",
                    "xpath": "//button[@id='login']",
                    "is_shadow": False,
                },
            ]

        # ✅ NEW: Enforce Token Budget (~500 tokens / 4 tokens per item avg = max 125 elements)
        # Prioritize important interactive elements
        priority = {"button": 5, "a": 4, "input": 3, "select": 2, "textarea": 2}
        elements.sort(
            key=lambda e: priority.get(e.get("tag", "").replace("shadow:", ""), 1), reverse=True
        )
        elements = elements[:125]

        for el in elements:
            desc = f"{el.get('tag', '')} | {el.get('role', '')} | {el.get('text', '')} | {el.get('placeholder', '')}"
            vec = await self.engine.embed(desc)
            self._vectors.append((vec, el))

        return len(self._vectors)

    async def query(
        self,
        natural_language: str,
        top_k: int = 3,
        threshold: float = CONFIDENCE_VERIFY,
    ) -> dict[str, Any]:
        """Resolve a natural language intent ('the checkout button') to an element match.

        ISSUE-1570: default threshold এখন CONFIDENCE_VERIFY (0.65) — 0.45-এর নিচের
        দুর্বল ম্যাচ আর নীলচোখে execute হয় না। রেজাল্টে ``confidence_band`` ও
        ``guardrail_action`` যুক্ত থাকে যাতে caller guardrail মানতে বাধ্য হয়।
        """
        if not self._vectors:
            await self.build_index()

        q_vec = await self.engine.embed(natural_language)
        q_tokens = set(w.lower() for w in natural_language.split() if len(w) > 2)
        scored: list[tuple[float, dict[str, Any]]] = []

        for vec, el in self._vectors:
            cos_score = self.cosine_similarity(q_vec, vec)
            # Compute token overlap bonus
            el_text = f"{el.get('text', '')} {el.get('role', '')} {el.get('tag', '')}".lower()
            el_tokens = set(el_text.split())
            overlap = len(q_tokens & el_tokens) / max(len(q_tokens), 1) if q_tokens else 0.0

            # Composite match score: strong match if either semantic vector or keyword overlap matches
            composite_score = max(cos_score, overlap, 0.50 * cos_score + 0.50 * overlap)
            scored.append((composite_score, el))

        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored or scored[0][0] < threshold:
            raise ElementNotFoundSemantically(
                f"No element matching '{natural_language}' found (best score: {scored[0][0] if scored else 0:.2f})"
            )

        best_match = scored[0][1].copy()
        best_match["semantic_confidence"] = scored[0][0]

        # ISSUE-1570: guardrail metadata — caller এই band মেনে চলবে:
        #   execute → সরাসরি act; verify → secondary verification; hitl → escalate.
        band = confidence_band(scored[0][0])
        best_match["confidence_band"] = band
        best_match["guardrail_action"] = (
            "execute"
            if band == "execute"
            else "secondary_verify"
            if band == "verify"
            else "escalate_hitl"
        )

        # ✅ NEW: Add token and shadow DOM metadata
        best_match["is_shadow"] = best_match.get("is_shadow", False)

        return best_match
