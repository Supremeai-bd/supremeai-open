"""Intent Router v2 — Real LLM Gatekeeper with regex fallback.

R1 FIX: Replace the regex-only ``backend/core/intent_router.py`` with a real
LLM-based classifier that calls the LLM gateway (Gemini 2.0 Flash or Groq
Llama-3.3-70b — both free-tier eligible) with a strict JSON-output prompt.

Architecture::

    user_prompt → LLM Gatekeeper (2s timeout) → JSON {action, confidence}
                ↓ on failure / disabled → Regex fallback (legacy ACTION_PATTERNS)
                ↓ on no match            → "chat" (default safe route)

Rollback: set env ``INTENT_ROUTER_MODE=regex`` to use legacy behavior only.
         Default: ``llm`` (uses LLM with regex fallback).

This file is kept SEPARATE from the original ``intent_router.py`` so that the
existing call sites are not broken. Callers should migrate to::

    from core.intent_router_v2 import intent_router_v2 as intent_router

    action = await intent_router.route(prompt)  # now async

A thin sync wrapper ``route_sync(prompt)`` is provided for legacy non-async
call sites.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from core.logging_config import logger

# ──────────────────────────────────────────────────────────────────────────
# PromptAction dataclass + ACTION_PATTERNS dict (canonical location)
#
# These were originally defined in core/intent_router.py but were removed
# during Phase 1 Router Consolidation. To preserve backwards compatibility:
#   - Define them here (in the canonical v2 module)
#   - core/intent_router.py re-exports them for legacy callers
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class PromptAction:
    """Result of intent classification."""

    action_type: str
    target_module: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    requires_confirmation: bool = False
    label: str | None = None
    icon: str | None = None


ACTION_PATTERNS: dict[str, dict[str, Any]] = {
    "code_generate": {
        "keywords": [
            "write",
            "create",
            "generate",
            "build",
            "make",
            "implement",
            "function",
            "component",
            "script",
            "program",
            "code",
            "api",
            "class",
            "method",
            "algorithm",
            "cli",
            "tool",
            "bot",
            "python",
            "javascript",
            "typescript",
            "react",
            "node",
        ],
        "target": "ide",
        "icon": "💻",
        "label": "Generate Code",
        "requires_confirmation": False,
    },
    "ide_open": {
        "keywords": [
            "open ide",
            "switch to code",
            "show editor",
            "full editor",
            "open editor",
            "edit code",
            "start coding",
            "write code",
            "new file",
            "open project",
        ],
        "target": "ide",
        "icon": "🖥️",
        "label": "Open IDE",
        "requires_confirmation": False,
    },
    "video_edit": {
        "keywords": [
            "video",
            "edit",
            "trim",
            "cut",
            "merge",
            "timeline",
            "clip",
            "frame",
            "audio",
            "background music",
            "transition",
        ],
        "target": "video_editor",
        "icon": "🎬",
        "label": "Edit Video",
        "requires_confirmation": True,
    },
    "research": {
        "keywords": [
            "search",
            "research",
            "find",
            "look up",
            "google",
            "investigate",
            "explain",
            "what is",
            "who is",
            "summarize",
            "analyze data",
            "report",
        ],
        "target": "research",
        "icon": "🔍",
        "label": "Research",
        "requires_confirmation": False,
    },
    "deploy": {
        "keywords": [
            "deploy",
            "publish",
            "push to production",
            "go live",
            "release",
            "host",
            "ship it",
        ],
        "target": "deploy",
        "icon": "🚀",
        "label": "Deploy",
        "requires_confirmation": True,
    },
    "settings_change": {
        "keywords": [
            "settings",
            "preferences",
            "config",
            "theme",
            "model",
            "provider",
            "temperature",
            "max tokens",
        ],
        "target": "settings",
        "icon": "⚙️",
        "label": "Settings",
        "requires_confirmation": False,
    },
}

# ──────────────────────────────────────────────────────────────────────────
# LLM Gatekeeper prompt — strict JSON output, Bengali-aware
# ──────────────────────────────────────────────────────────────────────────
GATEKEEPER_SYSTEM_PROMPT = """You are the Intent Gatekeeper for SupremeAI.
Given a user prompt, classify it into ONE of these actions:
  - code_generate   (write/create/build code, components, scripts)
  - ide_open        (open editor / switch to code view)
  - video_edit      (edit/trim/merge video)
  - research        (search/research/explain/summarize)
  - deploy          (deploy/publish/release)
  - settings_change (change settings/preferences/config)
  - chat            (default: general conversation, greetings, small talk)

ALSO understand Bengali (বাংলা) and Banglish prompts.

Respond ONLY with a JSON object: {"action": "<action>", "confidence": <0.0-1.0>, "target_hint": "<optional>"}

Do not include any other text. If unsure, return {"action": "chat", "confidence": 0.5}.
"""

GATEKEEPER_TIMEOUT_SECONDS = 2.0  # strict SLA — fall back to regex if exceeded
GATEKEEPER_MIN_CONFIDENCE = 0.6  # below this, regex fallback is consulted
GATEKEEPER_MODEL = "gemini/gemini-2.5-flash"  # free-tier fast model (2.0 retired by Google 2026-09)


def _is_llm_mode_enabled() -> bool:
    """Env flag — instant rollback to regex-only mode."""
    return os.getenv("INTENT_ROUTER_MODE", "llm").lower() != "regex"


async def _llm_classify(prompt: str) -> PromptAction | None:
    """Call LLM gateway with a fast/cheap model to classify intent.

    Returns ``None`` on any failure (timeout, JSON decode error, unknown action,
    low confidence) — caller should then fall back to regex.
    """
    try:
        from core.llm.llm_gateway import llm_gateway
    except Exception as e:  # pragma: no cover — defensive
        logger.debug(f"[IntentRouterV2] llm_gateway unavailable: {e}")
        return None

    try:
        response = await asyncio.wait_for(
            llm_gateway.acompletion(
                prompt=prompt,
                task_type="intent_classification",
                model=GATEKEEPER_MODEL,
                stream=False,
            ),
            timeout=GATEKEEPER_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("[IntentRouterV2] LLM gatekeeper timed out — falling back to regex")
        return None
    except Exception as e:
        logger.warning(f"[IntentRouterV2] LLM gatekeeper failed: {e} — falling back to regex")
        return None

    text = (response or {}).get("text", "") if isinstance(response, dict) else str(response)
    text = text.strip()

    # Strip markdown code fences if any
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"[IntentRouterV2] LLM returned non-JSON: {text[:120]!r}")
        return None

    action = str(data.get("action", "chat")).strip().lower()
    confidence = float(data.get("confidence", 0.0))

    if action not in ACTION_PATTERNS and action != "chat":
        logger.warning(f"[IntentRouterV2] LLM returned unknown action: {action!r}")
        return None

    if confidence < GATEKEEPER_MIN_CONFIDENCE:
        logger.debug(
            f"[IntentRouterV2] LLM confidence {confidence:.2f} < {GATEKEEPER_MIN_CONFIDENCE} — falling back to regex"
        )
        return None

    cfg = ACTION_PATTERNS.get(action, {})
    return PromptAction(
        action_type=action,
        target_module=cfg.get("target"),
        payload={
            "original_prompt": prompt,
            "gatekeeper": "llm",
            "target_hint": data.get("target_hint"),
        },
        confidence=confidence,
        requires_confirmation=cfg.get("requires_confirmation", False),
        label=cfg.get("label"),
        icon=cfg.get("icon"),
    )


class IntentRouterV2:
    """LLM-first intent router with regex fallback."""

    async def route(self, prompt: str) -> PromptAction:
        """Classify the user prompt into a PromptAction.

        Strategy:
          1. If ``INTENT_ROUTER_MODE=regex`` (or LLM unavailable) → legacy regex path.
          2. Otherwise → call LLM gatekeeper (2s timeout). On success + high
             confidence, return LLM result. On failure/low confidence, fall back
             to regex and finally to "chat".
        """
        if _is_llm_mode_enabled():
            llm_result = await _llm_classify(prompt)
            if llm_result is not None:
                logger.info(
                    f"[IntentRouterV2] LLM gatekeeper → action={llm_result.action_type} "
                    f"confidence={llm_result.confidence:.2f}"
                )
                return llm_result

        # Fallback: deterministic regex path (legacy logic from intent_router.py)
        return self._route_regex(prompt)

    def _route_regex(self, prompt: str) -> PromptAction:
        """Legacy regex-based intent classification (preserved for fallback)."""
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

        return PromptAction(
            action_type=best,
            target_module=cfg["target"],
            payload={"original_prompt": prompt, "gatekeeper": "regex"},
            confidence=confidence,
            requires_confirmation=cfg["requires_confirmation"],
            label=cfg["label"],
            icon=cfg["icon"],
        )

    def route_sync(self, prompt: str) -> PromptAction:
        """Sync wrapper for callers that cannot ``await``.

        If we're inside a running event loop (typical FastAPI context), this
        falls back to the regex path immediately — do NOT call this from an
        async context. Use ``await route(prompt)`` instead.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an event loop — fall back to regex immediately
                return self._route_regex(prompt)
            return loop.run_until_complete(self.route(prompt))
        except RuntimeError:
            # No event loop at all — sync mode
            return self._route_regex(prompt)


# Module-level singleton — drop-in replacement for the legacy ``intent_router``
intent_router_v2 = IntentRouterV2()
