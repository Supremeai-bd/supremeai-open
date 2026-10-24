"""Intent Router — legacy shim module.

This module historically defined PromptAction and ACTION_PATTERNS, but those
were moved to core/intent_router_v2.py (canonical location) during the
Router Consolidation refactor. They are re-exported here for backwards
compatibility with any code that still imports from core.intent_router.

বাংলা মন্তব্য (ROOT-CAUSE FIX, consolidation regression): "Phase 1 Duplicate
Consolidation" রিফ্যাক্টর (commit 4c5bae29ed) এই ফাইলের IntentRouter ক্লাস থেকে
আসল sync `route()` keyword-matching এলগরিদম (ACTION_PATTERNS scoring,
language/filename detection, _extract_operations, _extract_setting_changes)
সম্পূর্ণ মুছে ফেলে শুধু একটা নতুন async `route_by_intent()` (UnifiedRouter-এ
delegate করা) দিয়ে বদলে দিয়েছিল -- backward-compatible facade না রেখেই।
tests/core/test_core_language_router.py-এর TestIntentRouter ক্লাস তখনো পুরোনো
sync API (`route`, `_extract_operations`, `_extract_setting_changes`) এক্সপেক্ট
করত, ফলে সব টেস্ট AttributeError দিত। কোনো production caller সরাসরি
`IntentRouter().route()` ব্যবহার করে না (repo-wide grep-এ শুধু PromptAction
ইম্পোর্ট পাওয়া গেছে) -- তাই এটা runtime bug না, কিন্তু পুরোনো এলগরিদমটা
হারিয়ে যাওয়া উচিত না (ইউজারের consolidation নীতি: delete না করে merge/facade
রাখা)। এখানে পুরোনো sync এলগরিদম হুবহু পুনরুদ্ধার করা হলো, নতুন async
route_by_intent()-এর পাশাপাশি -- দুটোই এখন একসাথে থাকে।
"""

import re
import warnings
from typing import Any

# Re-export PromptAction and ACTION_PATTERNS from the canonical v2 location
# so legacy imports like `from core.intent_router import PromptAction` keep working.
from core.intent_router_v2 import ACTION_PATTERNS, PromptAction  # noqa: F401

# UnifiedRouter (new canonical async router) is optional at import time so this
# module still loads even if unified_router isn't wired up yet.
try:
    from core.unified_router import RoutingCriteria, RoutingStrategy, get_unified_router

    _UNIFIED_ROUTER_AVAILABLE = True
except ImportError:
    _UNIFIED_ROUTER_AVAILABLE = False


class IntentRouter:
    """
    Legacy synchronous keyword-based intent router (restored, see module
    docstring), plus an async `route_by_intent()` facade delegating to the
    new UnifiedRouter when available.
    """

    def __init__(self):
        self._real = get_unified_router() if _UNIFIED_ROUTER_AVAILABLE else None
        if self._real is not None:
            warnings.warn(
                "IntentRouter.route_by_intent() is deprecated, use UnifiedRouter directly. "
                "IntentRouter.route() (sync, keyword-based) remains supported.",
                DeprecationWarning,
                stacklevel=2,
            )

    # ------------------------------------------------------------------
    # New API — delegates to UnifiedRouter
    # ------------------------------------------------------------------
    async def route_by_intent(self, user_intent, **kwargs):
        if self._real is None:
            raise RuntimeError("UnifiedRouter is not available in this environment")
        decision = await self._real.route(
            RoutingCriteria(prompt=user_intent, **kwargs),
            strategy=RoutingStrategy.INTENT_BASED,
        )
        return decision.to_dict()

    # ------------------------------------------------------------------
    # Legacy API — restored sync keyword-based routing
    # ------------------------------------------------------------------
    def route(self, prompt: str) -> PromptAction:
        text = prompt.lower()
        scores: dict[str, int] = {}
        for action_name, cfg in ACTION_PATTERNS.items():
            score = sum(
                1
                for kw in cfg["keywords"]
                if re.search(r"(^|\W)" + re.escape(kw) + r"(\W|$)", text)
            )
            if score > 0:
                scores[action_name] = score

        if not scores:
            return PromptAction(
                action_type="chat",
                target_module=None,
                confidence=0.5,
                label=None,
                icon=None,
            )

        best = max(scores, key=lambda k: scores[k])
        total = sum(scores.values())
        confidence = round(scores[best] / total, 3)
        cfg = ACTION_PATTERNS[best]

        payload: dict[str, Any] = {"original_prompt": prompt}

        if best == "code_generate":
            payload["language"] = self._detect_language(text)
            payload["filename"] = self._guess_filename(payload["language"])
        elif best == "video_edit":
            payload["operations"] = self._extract_operations(text)
        elif best == "research":
            payload["query"] = prompt.strip()
        elif best == "deploy":
            payload["target"] = (
                "firebase" if "firebase" in text else "vercel" if "vercel" in text else "cloud_run"
            )
        elif best == "settings_change":
            payload["changes"] = self._extract_setting_changes(text)

        return PromptAction(
            action_type=best,
            target_module=cfg["target"],
            payload=payload,
            confidence=confidence,
            requires_confirmation=cfg["requires_confirmation"],
            label=cfg["label"],
            icon=cfg["icon"],
        )

    def _detect_language(self, text: str) -> str:
        lang_map = {
            "python": "python",
            "javascript": "javascript",
            "typescript": "typescript",
            "react": "jsx",
            "node": "javascript",
            "java": "java",
            "c++": "cpp",
            "cpp": "cpp",
            "rust": "rust",
            "go": "go",
            "html": "html",
            "css": "css",
            "sql": "sql",
            "shell": "bash",
            "bash": "bash",
        }
        for lang, code in lang_map.items():
            if re.search(r"(^|\W)" + re.escape(lang) + r"(\W|$)", text):
                return code
        return "javascript"

    def _guess_filename(self, language: str) -> str:
        defaults = {
            "python": "main.py",
            "javascript": "index.js",
            "typescript": "index.ts",
            "jsx": "App.jsx",
            "tsx": "App.tsx",
            "html": "index.html",
            "java": "Main.java",
            "rust": "main.rs",
            "go": "main.go",
        }
        return defaults.get(language, "component.tsx")

    def _extract_operations(self, text: str) -> list[str]:
        ops = []
        for op in [
            "trim",
            "cut",
            "merge",
            "transition",
            "filter",
            "overlay",
            "caption",
        ]:
            if op in text:
                ops.append(op)
        return ops or ["edit"]

    def _extract_setting_changes(self, text: str) -> list[str]:
        changes = []
        for kw in [
            "theme",
            "model",
            "provider",
            "temperature",
            "max tokens",
            "compact",
        ]:
            if kw in text:
                changes.append(kw)
        return changes


__all__ = ["ACTION_PATTERNS", "PromptAction", "IntentRouter"]
