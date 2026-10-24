#!/usr/bin/env python3
"""
PR Helper — Phase 3: LaunchDarkly Feature Flag Integration (issue #1034)
========================================================================
LaunchDarkly feature flags-এর মাধ্যমে AI Auto-Fix-এর সব আচরণ runtime-এ
control করা যায় — kill switch, model routing, retry limit, confidence
threshold — কোনো redeploy ছাড়াই।

Flags (issue #1034 অনুযায়ী):
  - ai-auto-fix-enabled                  bool    default: false   (kill switch)
  - ai-auto-fix-model                   string  default: "auto"  (gemini|openai|mistral|auto)
  - ai-auto-fix-max-retries              int     default: 2       (per PR)
  - ai-auto-fix-confidence-threshold    float   default: 0.8

Fallback strategy (যদি LD SDK অনুপস্থিত বা LD unreachable):
  - env vars (AI_AUTO_FIX_ENABLED, AI_AUTO_FIX_MODEL, AI_AUTO_FIX_MAX_RETRIES,
    AI_AUTO_FIX_CONFIDENCE_THRESHOLD) override-able
  - সব না পেলে fail-closed defaults (enabled=False, model="auto", retries=2, conf=0.8)

Usage:
  from ai_autofix_flags import get_ai_autofix_config
  cfg = get_ai_autofix_config()
  if not cfg["enabled"]:
      return "AI auto-fix disabled by LaunchDarkly"
  result = generate_fixes(..., model_choice=cfg["model"],
                           max_attempts=cfg["max_retries"],
                           confidence_threshold=cfg["confidence_threshold"])

CLI mode:
  python ai_autofix_flags.py --output-json ai_autofix_flags.json
  # Writes GITHUB_OUTPUT: ai_autofix_enabled, ai_autofix_model, ai_autofix_max_retries, ai_autofix_confidence_threshold
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# --- Defaults (fail-closed) -------------------------------------------------

DEFAULT_ENABLED = False  # kill switch — feature ডিফল্টে off
DEFAULT_MODEL = "auto"  # auto = Gemini → OpenAI → Mistral
DEFAULT_MAX_RETRIES = 2  # issue safety: 2 attempts per PR
DEFAULT_CONFIDENCE_THRESHOLD = 0.8  # 80% confidence minimum

VALID_MODELS = ("auto", "gemini", "openai", "mistral")

FLAG_ENABLED = "ai-auto-fix-enabled"
FLAG_MODEL = "ai-auto-fix-model"
FLAG_MAX_RETRIES = "ai-auto-fix-max-retries"
FLAG_CONFIDENCE_THRESHOLD = "ai-auto-fix-confidence-threshold"

# Context kind for LD evaluation — service-level context
LD_CONTEXT_KIND = "service"
LD_CONTEXT_KEY = "pr-helper-ai-autofix"


# --- LD client loader (lazy) -----------------------------------------------


def _build_ld_context() -> Any:
    """LaunchDarkly service context তৈরি করে (LD unavailable হলে None)."""
    try:
        # backend/core/ld_client.py-এর get_ld_ai_components ব্যবহার করি
        # (script-এর জন্য backend/ path-এ থাকা দরকার)
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
        from core.ld_client import get_ld_ai_components  # type: ignore

        _, _, _, _, Context = get_ld_ai_components()
        if Context is None:
            return None
        return Context.builder(LD_CONTEXT_KEY).kind(LD_CONTEXT_KIND).build()
    except Exception:
        return None


def _ld_variation_bool(flag_key: str, default: bool, context: Any) -> bool:
    """LaunchDarkly bool variation. SDK না থাকলে default ফেরত দেয়।"""
    try:
        import ldclient

        client = ldclient.get()
        if client is None or context is None:
            return default
        return bool(client.variation(flag_key, context, default))
    except Exception:
        return default


def _ld_variation_string(flag_key: str, default: str, context: Any) -> str:
    try:
        import ldclient

        client = ldclient.get()
        if client is None or context is None:
            return default
        val = client.variation(flag_key, context, default)
        return str(val) if val is not None else default
    except Exception:
        return default


def _ld_variation_int(flag_key: str, default: int, context: Any) -> int:
    try:
        import ldclient

        client = ldclient.get()
        if client is None or context is None:
            return default
        val = client.variation(flag_key, context, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default
    except Exception:
        return default


def _ld_variation_float(flag_key: str, default: float, context: Any) -> float:
    try:
        import ldclient

        client = ldclient.get()
        if client is None or context is None:
            return default
        val = client.variation(flag_key, context, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default
    except Exception:
        return default


# --- Env override helper ----------------------------------------------------


def _env_override(env_key: str, val_type: type, default: Any) -> Any:
    """Env var দিয়ে flag override — LD unavailable হলেও CI চলে।"""
    raw = os.getenv(env_key)
    if raw is None or raw == "":
        return default
    try:
        if val_type is bool:
            return raw.lower() in ("1", "true", "yes", "on")
        if val_type is int:
            return int(raw)
        if val_type is float:
            return float(raw)
        return str(raw)
    except (TypeError, ValueError):
        return default


# --- Public API -------------------------------------------------------------


def get_ai_autofix_config() -> dict:
    """LaunchDarkly + env override দিয়ে AI Auto-Fix config তৈরি করে।

    Resolution order (per flag):
      1. Env var (highest — local dev / CI override)
      2. LaunchDarkly flag (production runtime)
      3. Hard-coded default (fail-closed)

    Returns:
      {
        "enabled": bool,
        "model": "auto" | "gemini" | "openai" | "mistral",
        "max_retries": int,
        "confidence_threshold": float,
        "source": "env" | "launchdarkly" | "default"
      }
    """
    context = _build_ld_context()

    # Flag 1: enabled (kill switch)
    enabled = _ld_variation_bool(FLAG_ENABLED, DEFAULT_ENABLED, context)
    enabled = _env_override("AI_AUTO_FIX_ENABLED", bool, enabled)

    # Flag 2: model choice
    model = _ld_variation_string(FLAG_MODEL, DEFAULT_MODEL, context)
    model = _env_override("AI_AUTO_FIX_MODEL", str, model)
    if model not in VALID_MODELS:
        model = DEFAULT_MODEL

    # Flag 3: max retries
    max_retries = _ld_variation_int(FLAG_MAX_RETRIES, DEFAULT_MAX_RETRIES, context)
    max_retries = _env_override("AI_AUTO_FIX_MAX_RETRIES", int, max_retries)
    # Safety clamp: 0-5 range (issue allows 2 default; protect against misconfig)
    max_retries = max(0, min(5, int(max_retries)))

    # Flag 4: confidence threshold
    threshold = _ld_variation_float(
        FLAG_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE_THRESHOLD, context
    )
    threshold = _env_override("AI_AUTO_FIX_CONFIDENCE_THRESHOLD", float, threshold)
    # Safety clamp: 0.0-1.0 range
    threshold = max(0.0, min(1.0, float(threshold)))

    # Determine source — env var set হলে "env", LD available হলে "launchdarkly", নয়তো "default"
    source = "default"
    env_keys = (
        "AI_AUTO_FIX_ENABLED",
        "AI_AUTO_FIX_MODEL",
        "AI_AUTO_FIX_MAX_RETRIES",
        "AI_AUTO_FIX_CONFIDENCE_THRESHOLD",
    )
    if any(os.getenv(k) not in (None, "") for k in env_keys):
        source = "env"
    elif context is not None:
        source = "launchdarkly"

    return {
        "enabled": enabled,
        "model": model,
        "max_retries": max_retries,
        "confidence_threshold": threshold,
        "source": source,
        "flags": {
            FLAG_ENABLED: enabled,
            FLAG_MODEL: model,
            FLAG_MAX_RETRIES: max_retries,
            FLAG_CONFIDENCE_THRESHOLD: threshold,
        },
    }


def is_ai_autofix_enabled() -> bool:
    """শুধু enabled flag check করে (kill switch quick check)."""
    return bool(get_ai_autofix_config()["enabled"])


# --- CLI --------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper — AI Auto-Fix LD Flag Resolver (#1034)")
    parser.add_argument("--output-json", default="ai_autofix_flags.json", help="Output JSON path")
    args = parser.parse_args()

    cfg = get_ai_autofix_config()

    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"AI Auto-Fix Config (source: {cfg['source']}):")
    print(f"  enabled:              {cfg['enabled']}")
    print(f"  model:                {cfg['model']}")
    print(f"  max_retries:          {cfg['max_retries']}")
    print(f"  confidence_threshold: {cfg['confidence_threshold']}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"ai_autofix_enabled={str(cfg['enabled']).lower()}\n")
            f.write(f"ai_autofix_model={cfg['model']}\n")
            f.write(f"ai_autofix_max_retries={cfg['max_retries']}\n")
            f.write(f"ai_autofix_confidence_threshold={cfg['confidence_threshold']}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
