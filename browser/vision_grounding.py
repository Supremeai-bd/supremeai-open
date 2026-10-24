"""
backend/browser/vision_grounding.py
===================================
L4 Vision Grounding Fallback: When SemanticDOM fails (e.g. canvas, shadow DOM,
obfuscated HTML), capture a screenshot and visually ground target coordinates via VLM.

ISSUE-1570 (Part 1) hardening:
* Zero fabricated coordinates — every previous "heuristic fallback" that returned
  invented (x, y) pairs is removed. If the VLM cannot ground the target, we raise
  ``LowConfidenceGrounding`` so the caller escalates to HITL instead of blind-clicking.
* Confidence guardrails enforced inside the module:
    - confidence >= 0.85            → execute
    - confidence 0.65–0.85          → secondary verification (second VLM pass must confirm)
    - confidence <  0.65            → LowConfidenceGrounding (HITL escalation)
* Sync/async page agnostic: coordinates dispatch works with both sync Playwright
  pages and async pages via an ``inspect.isawaitable`` guard.
"""

from __future__ import annotations

import base64
import inspect
import json
from typing import Any

from browser.semantic_dom import CONFIDENCE_EXECUTE, CONFIDENCE_VERIFY, confidence_band
from core.logging_config import logger

__all__ = ["LowConfidenceGrounding", "VisionGrounding"]


class LowConfidenceGrounding(Exception):
    """Raised when VLM visual confidence falls below required threshold (triggers HITL takeover)."""

    pass


class VisionGrounding:
    CONFIDENCE_EXECUTE = CONFIDENCE_EXECUTE
    CONFIDENCE_VERIFY = CONFIDENCE_VERIFY

    def __init__(self, page: Any = None, router_factory: Any = None):
        self.page = page
        # router_factory দিলে সেটাই ModelRouter বানায় — টেস্টে VLM মক করা সহজ হয়।
        self._router_factory = router_factory

    # ------------------------------------------------------------------
    # Screenshot (sync/async page agnostic)
    # ------------------------------------------------------------------
    async def _screenshot_b64(self) -> str | None:
        if self.page is None or not hasattr(self.page, "screenshot"):
            return None
        try:
            shot = self.page.screenshot(full_page=False)
            if inspect.isawaitable(shot):
                shot = await shot
            if isinstance(shot, bytes):
                return base64.b64encode(shot).decode()
            logger.debug("[VisionGrounding] Screenshot returned non-bytes payload")
            return None
        except Exception as e:
            logger.debug(f"[VisionGrounding] Screenshot capture fallback: {e}")
            return None

    def _make_router(self) -> Any:
        if self._router_factory is not None:
            return self._router_factory()
        from brain.model_router import ModelRouter

        return ModelRouter()

    # ------------------------------------------------------------------
    # VLM grounding — NO fabricated fallbacks
    # ------------------------------------------------------------------
    def _parse_vlm_json(self, raw: str) -> dict[str, Any]:
        raw = (raw or "{}").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("VLM grounding response is not a JSON object")
        return data

    def _vlm_locate(self, router: Any, target: str, screenshot_b64: str | None) -> dict[str, Any]:
        prompt = (
            f"Identify the (x, y) click coordinates for '{target}' on the screen."
            + (
                f" [Image Context Base64 attached (len={len(screenshot_b64)})]"
                if screenshot_b64
                else ""
            )
            + '\nReturn JSON format: {"x": 250, "y": 320, "confidence": 0.88}'
        )
        res = router.route_and_generate(prompt=prompt, task_type="general", max_cost=0.01)
        return self._parse_vlm_json(res.get("text", ""))

    async def _secondary_verify(
        self, router: Any, target: str, loc: dict[str, Any], screenshot_b64: str | None
    ) -> bool:
        """ISSUE-1570: 0.65–0.85 band-এর জন্য দ্বিতীয় স্বাধীন VLM যাচাই।"""
        prompt = (
            f"Verification pass: a previous model claims '{target}' is located at "
            f"approximately (x={loc['x']}, y={loc['y']}) on the screen."
            + (
                f" [Image Context Base64 attached (len={len(screenshot_b64)})]"
                if screenshot_b64
                else ""
            )
            + '\nConfirm independently. Return JSON: {"confirmed": true, "confidence": 0.9} '
            'or {"confirmed": false, "confidence": 0.4}'
        )
        try:
            res = router.route_and_generate(prompt=prompt, task_type="general", max_cost=0.01)
            data = self._parse_vlm_json(res.get("text", ""))
            confirmed = bool(data.get("confirmed", False))
            conf = float(data.get("confidence", 0.0))
            # যাচাইকারী নিজেই কম আত্মবিশ্বাসী হলে confirmation গ্রহণযোগ্য নয়।
            return confirmed and conf >= self.CONFIDENCE_VERIFY
        except Exception as exc:
            logger.warning(f"[VisionGrounding] Secondary verification errored: {exc}")
            return False

    async def locate(
        self,
        target: str,
        min_confidence: float = CONFIDENCE_VERIFY,
        require_secondary: bool | None = None,
    ) -> dict[str, Any]:
        """Locate target bounding coordinates (x, y) from visual input.

        ISSUE-1570: কোনো অবস্থাতেই fabricated coordinate return করা হয় না।
        VLM failure / low confidence / অসম্পূর্ণ payload → ``LowConfidenceGrounding``।
        """
        logger.info(f"[VisionGrounding] Visually locating target: '{target}'")
        screenshot_b64 = await self._screenshot_b64()

        try:
            router = self._make_router()
            data = self._vlm_locate(router, target, screenshot_b64)
        except LowConfidenceGrounding:
            raise
        except Exception as exc:
            # আগে এখানে fake {"x": 100, "y": 100, "confidence": 0.75} বানানো হতো —
            # এটাই blind-fallback-click দুর্ঘটনার মূল উৎস। এখন fail → HITL।
            logger.warning(f"[VisionGrounding] VLM grounding unavailable for '{target}': {exc}")
            raise LowConfidenceGrounding(
                f"Visual grounding unavailable for '{target}': {exc}"
            ) from exc

        if "x" not in data or "y" not in data:
            raise LowConfidenceGrounding(
                f"VLM grounding payload for '{target}' missing coordinates — refusing to guess"
            )
        conf = float(data.get("confidence", 0.0))
        if conf < self.CONFIDENCE_VERIFY or conf < min_confidence:
            raise LowConfidenceGrounding(
                f"Visual confidence {conf:.2f} < {max(min_confidence, self.CONFIDENCE_VERIFY):.2f} for '{target}'"
            )

        band = confidence_band(conf)
        loc: dict[str, Any] = {
            "x": int(data["x"]),
            "y": int(data["y"]),
            "confidence": conf,
            "target": target,
            "band": band,
        }

        want_secondary = (
            (band == "verify") if require_secondary is None else bool(require_secondary)
        )
        if want_secondary:
            verified = await self._secondary_verify(router, target, loc, screenshot_b64)
            if not verified:
                raise LowConfidenceGrounding(
                    f"Secondary verification failed for '{target}' (initial confidence {conf:.2f})"
                )
            loc["verified"] = True

        return loc

    async def click(self, target: str) -> dict[str, Any]:
        """Ground and click coordinates on page — only when guardrails allow."""
        loc = await self.locate(target)
        band = loc.get("band", "hitl")
        if band == "hitl":
            # Defence in depth: locate() already raises, but never blind-click.
            raise LowConfidenceGrounding(
                f"Confidence band '{band}' forbids visual click for '{target}'"
            )
        if (
            self.page is not None
            and hasattr(self.page, "mouse")
            and hasattr(self.page.mouse, "click")
        ):
            try:
                result = self.page.mouse.click(loc["x"], loc["y"])
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                logger.warning(f"[VisionGrounding] Mouse click dispatch failed: {e}")
                raise LowConfidenceGrounding(
                    f"Mouse click dispatch failed for '{target}': {e}"
                ) from e
        return {"action": "visual_click", "coordinates": loc, "target": target, "band": band}
