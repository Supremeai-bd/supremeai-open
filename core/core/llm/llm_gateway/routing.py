# backend/core/llm/llm_gateway/routing.py
"""Routing policy, task→model map and fallback-chain builder.

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py into
the RoutingMixin used by LLMGateway (core/llm/llm_gateway/gateway.py).
"""

import json
import os
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

from ...config import settings  # Fixed import path - using relative import
from ...messaging.event_bus import (  # Fixed import path - using relative import
    ErrorContext,
    ErrorEvent,
    error_event_bus,
)

# বাংলা মন্তব্ব: POLICY_PATH এখন os.path দিয়ে বিল্ড হয় — hardcode নেই
# Package-split note (task 4-a): one extra os.path.dirname because this file
# lives one level deeper than the old core/llm/llm_gateway.py module — the
# resolved absolute path is unchanged (backend/core/config/routing_policy.json).
_POLICY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "routing_policy.json",
)

# বাংলা মন্তব্ব: Default fallback models — routing_policy.json না থাকলে এগুলো ব্যবহার হবে।
# Updated 2026-09-13: gemini-2.0-flash was retired by Google (404 on every
# call) and openrouter had no key configured, so the default chain was dead.
_DEFAULT_FALLBACK_MODELS: list[str] = list(
    getattr(
        settings,
        "fallback_models",
        ["gemini/gemini-2.5-flash", "bynara/agnes-2.5-flash", "bai/qwen3.8-flash"],
    )
)

# OpenAI-style Task-to-Model mapping
# Runtime overrides come from the central settings registry; defaults remain backwards compatible.
TASK_MODEL_MAP: dict[str, str] = settings.task_models


# Runtime provider/model override (admin API controlled).
# When set, the override model/provider is prepended to EVERY built call chain
# until the remaining-request budget is exhausted (remaining_requests=0/None
# means unlimited). This is real routing behavior — _build_call_chain feeds the
# gateway's actual request path — not a UI-only flag.
_RUNTIME_OVERRIDE: dict[str, str | None] = {"provider": None, "model": None}
_OVERRIDE_REMAINING: int = 0


def set_runtime_override(
    provider: str, model: str | None = None, remaining_requests: int | None = None
) -> None:
    """Activate a runtime routing override (admin action)."""
    global _OVERRIDE_REMAINING
    _RUNTIME_OVERRIDE["provider"] = provider
    _RUNTIME_OVERRIDE["model"] = model
    _OVERRIDE_REMAINING = max(0, int(remaining_requests)) if remaining_requests else 0


def get_runtime_override() -> dict[str, str | int | None]:
    """Current override state, or None values when inactive."""
    return {
        "provider": _RUNTIME_OVERRIDE["provider"],
        "model": _RUNTIME_OVERRIDE["model"],
        "remaining_requests": _OVERRIDE_REMAINING,
    }


def clear_runtime_override() -> None:
    """Deactivate the runtime override."""
    global _OVERRIDE_REMAINING
    _RUNTIME_OVERRIDE["provider"] = None
    _RUNTIME_OVERRIDE["model"] = None
    _OVERRIDE_REMAINING = 0


class RoutingMixin:
    """Routing-policy + fallback-chain methods for LLMGateway (verbatim move)."""

    @with_error_bus("_load_routing_policy")
    def _load_routing_policy(self) -> dict[str, Any]:
        """বাংলা মন্তব্ব: Routing policy JSON load — file not found = safe default।"""
        try:
            if os.path.exists(_POLICY_PATH):
                with open(_POLICY_PATH, encoding="utf-8") as f:
                    policy = json.load(f)
                self._warn_retired_policy_models(policy)
                return policy
            logger.warning(
                f"[LLMGateway] Routing policy not found at '{_POLICY_PATH}'. Using default fallback config."
            )
        except Exception as exc:
            logger.opt(exception=True).error(f"[LLMGateway] Error loading routing policy: {exc}")
            error_event_bus.emit(
                ErrorEvent(
                    module="llm_gateway",
                    error_type="ROUTING_POLICY_LOAD_FAILED",
                    message=str(exc)[:500],
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"policy_path": _POLICY_PATH},
                )
            )
        return {
            "complexity_rules": {},
            "fallback_chain": list(_DEFAULT_FALLBACK_MODELS),
        }

    # Issue #1442: routing_policy.json is the documented source of truth for
    # routing, but registry._RETIRED_MODELS silently skips retired models at
    # request time — a stale entry made the *configured* chain head differ
    # from the *effective* one ("easy" effectively had no working head).
    # Validate at load time and warn loudly instead of failing silently.
    _POLICY_MODEL_KEYS = ("complexity_rules", "task_overrides", "fallback_chain")

    def _warn_retired_policy_models(self, policy: dict[str, Any]) -> None:
        """Warn when routing_policy.json references models retired at their provider."""
        try:
            from core.llm.llm_gateway.registry import _RETIRED_MODELS
        except Exception:  # pragma: no cover — registry import must never break boot
            return
        retired: list[str] = []

        def _scan(path: str, value: Any) -> None:
            if isinstance(value, str):
                if value.lower() in _RETIRED_MODELS:
                    retired.append(f"{path}={value}")
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    _scan(f"{path}[{i}]", item)
            elif isinstance(value, dict):
                for k, v in value.items():
                    _scan(f"{path}.{k}", v)

        for key in self._POLICY_MODEL_KEYS:
            if key in policy:
                _scan(key, policy[key])
        if retired:
            logger.warning(
                "[LLMGateway] routing_policy.json references RETIRED models "
                f"(skipped at request time by registry._RETIRED_MODELS): {', '.join(retired)}. "
                "Update backend/config/routing_policy.json to served equivalents."
            )

    def _build_call_chain(
        self,
        model: str | None,
        provider: str | None,
        task_type: str,
    ) -> list[str]:
        """বাংলা মন্তব্ব: Task type অনুযায়ী fallback chain তৈরি।"""

        difficulty = "easy"
        if any(kw in task_type.lower() for kw in ("reasoning", "math", "code", "coding")):
            difficulty = "hard"
        elif any(kw in task_type.lower() for kw in ("agent", "analysis")):
            difficulty = "medium"

        # Consume the runtime override (if any) for this chain build.
        global _OVERRIDE_REMAINING
        override_provider: str | None = None
        override_model: str | None = None
        if _RUNTIME_OVERRIDE["provider"]:
            override_provider = _RUNTIME_OVERRIDE["provider"]
            override_model = _RUNTIME_OVERRIDE["model"]
            if _OVERRIDE_REMAINING > 0:
                _OVERRIDE_REMAINING -= 1
                if _OVERRIDE_REMAINING == 0:
                    clear_runtime_override()

        effective_model = model or override_model
        effective_provider = provider or override_provider

        model_candidates: list[str] = self.routing_policy.get("complexity_rules", {}).get(
            difficulty, []
        )
        fallbacks: list[str] = self.routing_policy.get(
            "fallback_chain", list(_DEFAULT_FALLBACK_MODELS)
        )

        call_chain: list[str] = []
        if effective_model:
            call_chain.append(effective_model)

        task_specific_model = TASK_MODEL_MAP.get(task_type.lower())
        if task_specific_model and task_specific_model not in call_chain:
            call_chain.append(task_specific_model)

        all_models = model_candidates + fallbacks
        for m in all_models:
            if m not in call_chain:
                call_chain.append(m)

        # বাংলা মন্তব্ব: যদি নির্দিষ্ট কোনো প্রোভাইডার (যেমন 'groq') প্রোভাইড করা হয়, তবে কল চেইনের মডেলগুলো রী-অর্ডার করা হবে
        # যাতে সেই প্রোভাইডারের মডেলগুলো সবার আগে স্থান পায়।
        if effective_provider:
            provider_models = [m for m in call_chain if m.startswith(f"{effective_provider}/")]
            other_models = [m for m in call_chain if not m.startswith(f"{effective_provider}/")]
            call_chain = provider_models + other_models

        if not call_chain:
            call_chain = list(_DEFAULT_FALLBACK_MODELS)
            logger.warning("[LLMGateway] Empty call chain — using default fallback models.")

        return call_chain
