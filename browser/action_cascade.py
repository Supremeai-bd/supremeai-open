"""
backend/browser/action_cascade.py
=================================
ISSUE-1570 (Part 1): the canonical 5-step ``click_target`` execution cascade,
shared by ``PlaywrightBrowserAgent`` (tools/browser) and
``AutonomousBrowserAgent`` (browser/) so both obey the same guardrails.

Cascade order (strict):
  1. SemanticDOM           — embed & resolve the target by meaning
  2. Accessible role/name  — Playwright ``get_by_role`` probing
  3. Known locator         — treat target as an explicit CSS/XPath selector
  4. Vision grounding      — VLM coordinates under confidence guardrails
  5. HITL escalation       — ``PAUSED_HITL`` (a blind fallback click is FORBIDDEN)

Confidence guardrails (SemanticDOM & VisionGrounding):
  score >= 0.85            → execute immediately
  score 0.65 – 0.85        → secondary verification, act only if verified
  score <  0.65            → escalate to HITL — never blind-act
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from browser.semantic_dom import CONFIDENCE_EXECUTE, CONFIDENCE_VERIFY, confidence_band
from browser.vision_grounding import LowConfidenceGrounding, VisionGrounding
from core.logging_config import logger

__all__ = [
    "CONFIDENCE_EXECUTE",
    "CONFIDENCE_VERIFY",
    "confidence_band",
    "execute_click_cascade",
]

HumanClick = Callable[[Any, str], Any]

# Roles probed in step 2 (accessible name matching).
_ACCESSIBLE_ROLES: tuple[str, ...] = (
    "button",
    "link",
    "tab",
    "menuitem",
    "checkbox",
    "radio",
    "option",
    "treeitem",
)
_ACCESSIBLE_CLICK_TIMEOUT_MS = 3000


def _to_xpath_selector(xpath: str) -> str:
    """Normalise an element xpath into a Playwright selector string."""
    xpath = (xpath or "").strip()
    if not xpath:
        return ""
    if xpath.startswith("xpath=") or xpath.startswith("["):
        return xpath
    return f"xpath={xpath}"


def _findable(page: Any, selector: str, timeout_ms: int = 2000) -> bool:
    """Secondary verification: does the selector actually resolve on the page?"""
    if page is None or not hasattr(page, "wait_for_selector"):
        return False
    try:
        element = page.wait_for_selector(selector, timeout=timeout_ms)
        return element is not None
    except Exception:
        return False


def _dispatch_click(page: Any, selector: str, human_click: HumanClick | None) -> None:
    """Execute a REAL click dispatch — never a no-op success."""
    if human_click is not None:
        result = human_click(page, selector)
        if inspect.isawaitable(result):
            raise RuntimeError("human_click must be a sync callable for cascade dispatch")
        return
    if page is not None and hasattr(page, "locator"):
        page.locator(selector).first.click()
        return
    raise RuntimeError(f"No click mechanism available for selector '{selector}'")


async def _try_accessible_role_click(page: Any, target: str) -> dict[str, Any] | None:
    """Step 2 — probe accessible roles by name; returns success dict or None."""
    get_by_role = getattr(page, "get_by_role", None)
    if not callable(get_by_role):
        return None
    for role in _ACCESSIBLE_ROLES:
        try:
            locator = get_by_role(role, name=target)
            if locator is None:
                continue
            click = locator.click(timeout=_ACCESSIBLE_CLICK_TIMEOUT_MS)
            if inspect.isawaitable(click):
                await click
            return {
                "success": True,
                "method": "accessible_role",
                "role": role,
                "target": target,
                "band": "execute",
                "status": "success",
            }
        except asyncio.CancelledError:
            raise
        except Exception:
            # Role probe miss — try the next accessible role.
            continue
    return None


async def execute_click_cascade(
    page: Any,
    target: str,
    *,
    human_click: HumanClick | None = None,
    vision: VisionGrounding | None = None,
) -> dict[str, Any]:
    """Run the full 5-step cascade for ``target`` on ``page``.

    Returns a dict that ALWAYS tells the truth:
      * ``{"success": True, "method": <semantic_dom|accessible_role|known_locator|vision_grounding>, ...}``
      * ``{"success": False, "status": "PAUSED_HITL", ...}`` — escalated to a human,
        never silently "succeeded" without a real click.
    """
    # ── Step 1: SemanticDOM ────────────────────────────────────────────
    try:
        from browser.semantic_dom import ElementNotFoundSemantically, SemanticDOM

        sdom = SemanticDOM(page)
        element = await sdom.query(target, threshold=CONFIDENCE_VERIFY)
        score = float(element.get("semantic_confidence", 0.0))
        band = confidence_band(score)
        selector = _to_xpath_selector(str(element.get("xpath", "")))

        if selector:
            if band == "execute":
                _dispatch_click(page, selector, human_click)
                return {
                    "success": True,
                    "status": "success",
                    "method": "semantic_dom",
                    "confidence": score,
                    "band": band,
                    "selector": selector,
                    "element": element,
                }
            if band == "verify" and _findable(page, selector):
                # Secondary verification passed — the element truly exists.
                _dispatch_click(page, selector, human_click)
                return {
                    "success": True,
                    "status": "success",
                    "method": "semantic_dom",
                    "confidence": score,
                    "band": band,
                    "verified": True,
                    "selector": selector,
                    "element": element,
                }
            # verify-band element not found on page, or hitl band → cascade on.
            logger.warning(
                "[ClickCascade] Semantic match '%s' band=%s failed secondary verification — escalating",
                target,
                band,
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # ISSUE-1570: failures are logged honestly, never silenced into fake success.
        logger.warning(f"[ClickCascade] Step 1 (SemanticDOM) miss for '{target}': {exc}")

    # ── Step 2: Accessible role/name ───────────────────────────────────
    try:
        accessible = await _try_accessible_role_click(page, target)
        if accessible is not None:
            return accessible
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(f"[ClickCascade] Step 2 (accessible role) miss for '{target}': {exc}")

    # ── Step 3: Known locator (explicit CSS/XPath) ─────────────────────
    try:
        if _findable(page, target, timeout_ms=2000):
            _dispatch_click(page, target, human_click)
            return {
                "success": True,
                "status": "success",
                "method": "known_locator",
                "selector": target,
                "band": "execute",
            }
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(f"[ClickCascade] Step 3 (known locator) miss for '{target}': {exc}")

    # ── Step 4: Vision grounding (confidence-guarded) ──────────────────
    try:
        vg = vision if vision is not None else VisionGrounding(page)
        loc = await vg.locate(target)
        coords = {"x": loc["x"], "y": loc["y"], "confidence": loc["confidence"]}
        if page is not None and hasattr(page, "mouse") and hasattr(page.mouse, "click"):
            click = page.mouse.click(loc["x"], loc["y"])
            if inspect.isawaitable(click):
                await click
        else:
            raise LowConfidenceGrounding("no clickable mouse surface bound to page")
        return {
            "success": True,
            "status": "success",
            "method": "vision_grounding",
            "coordinates": coords,
            "band": loc.get("band", "execute"),
            "verified": loc.get("verified", False),
            "target": target,
        }
    except asyncio.CancelledError:
        raise
    except LowConfidenceGrounding as exc:
        logger.warning(f"[ClickCascade] Step 4 (vision) below threshold for '{target}': {exc}")
    except Exception as exc:
        logger.warning(f"[ClickCascade] Step 4 (vision) miss for '{target}': {exc}")

    # ── Step 5: HITL escalation — the ONLY honest terminal state ───────
    return {
        "success": False,
        "status": "PAUSED_HITL",
        "method": "hitl",
        "target": target,
        "reason": (
            "All 4 automated resolution steps failed or fell below confidence guardrails; "
            "human-in-the-loop confirmation required before any click is dispatched."
        ),
    }
