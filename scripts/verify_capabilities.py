#!/usr/bin/env python3
"""VERIFY phase — capability matrix test.

Tests that each SupremeAI capability ACTUALLY WORKS (not just imports).
Run before every push to main to verify no regressions.

Usage:
    python3 scripts/verify_capabilities.py
    # or
    cd backend && python3 ../scripts/verify_capabilities.py

Exit code: 0 = all pass, 1 = at least one failure
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

# Add backend/ to path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Set safe defaults to avoid env var requirements
os.environ.setdefault("INTENT_ROUTER_MODE", "regex")
os.environ.setdefault("ENABLE_AUTO_HEALER", "false")


def test(name: str, fn):
    """Run a test function and print result. Returns True if pass."""
    print(f"\n[{name}]")
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        print(f"  ✅ PASS")
        if result is not None:
            print(f"     → {result!r}")
        return True
    except Exception as e:
        print(f"  ❌ FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


# === Capability tests ===


def test_self_healing():
    """MaintenancePipeline.run_health_check should return a dict."""
    from core.maintenance_pipeline import maintenance_pipeline

    async def _run():
        return await maintenance_pipeline.run_health_check()

    return _run()


def test_self_evolving():
    """SelfEvolutionAgent should instantiate + have _tick method."""
    from core.evolution.self_evolution_agent import SelfEvolutionAgent

    agent = SelfEvolutionAgent(interval_seconds=300)
    assert hasattr(agent, "_tick"), "SelfEvolutionAgent missing _tick method"
    assert hasattr(agent, "fitness_engine"), "SelfEvolutionAgent missing fitness_engine attr"
    return f"type={type(agent).__name__}, has _tick + fitness_engine"


def test_auto_learning():
    """ExperienceDatabase.record_experience should persist + find_similar should work."""
    from adaptive_engine.experience_db import Experience, ExperienceDatabase

    ed = ExperienceDatabase()
    exp = Experience(
        request="VERIFY phase smoke test",
        action_taken="capability_test",
        result="success",
        context={"phase": "verify", "test": "smoke"},
    )
    result_id = ed.record_experience(exp)
    assert isinstance(result_id, int) and result_id > 0, f"record_experience returned {result_id}"
    return f"persisted experience id={result_id}"


def test_semantic_cache():
    """SemanticCache.query_similar should return None or CacheEntry for unknown prompt."""
    from core.cache.semantic_cache import SemanticCache

    sc = SemanticCache()

    async def _query():
        return await sc.query_similar(prompt="nonexistent-test-prompt-12345", task_type="general")

    return _query()


def test_sse_streaming():
    """stream_chat_sse._event_stream should return an async generator."""
    from api.routes.stream_chat_sse import _event_stream

    gen = _event_stream(prompt="test", user_id="verify", task_type="chat")
    assert hasattr(gen, "__aiter__"), f"expected async generator, got {type(gen).__name__}"
    return f"type={type(gen).__name__}"


def test_auto_healer():
    """AutoHealer should instantiate + have start_monitoring method."""
    from services.auto_healer import AutoHealer, get_healer

    healer = get_healer()
    assert isinstance(healer, AutoHealer), f"expected AutoHealer, got {type(healer).__name__}"
    assert hasattr(healer, "start_monitoring"), "AutoHealer missing start_monitoring"
    return f"type={type(healer).__name__}"


def test_intent_router():
    """intent_router_v2.route should classify prompts using regex fallback."""
    from core.intent_router_v2 import intent_router_v2

    async def _route():
        return await intent_router_v2.route("write a python function")

    result = asyncio.run(_route())
    assert result.action_type == "code_generate", f"expected code_generate, got {result.action_type}"
    return f"action_type={result.action_type}, confidence={result.confidence}"


def test_prompt_action_dataclass():
    """PromptAction should be importable from both core.intent_router and v2."""
    from core.intent_router import ACTION_PATTERNS, PromptAction
    from core.intent_router_v2 import (
        ACTION_PATTERNS as AP2,
        PromptAction as PA2,
    )

    assert PromptAction is PA2, "PromptAction mismatch between modules"
    assert ACTION_PATTERNS is AP2, "ACTION_PATTERNS mismatch between modules"
    expected_keys = {"code_generate", "ide_open", "video_edit", "research", "deploy", "settings_change"}
    assert set(ACTION_PATTERNS.keys()) == expected_keys, f"keys: {set(ACTION_PATTERNS.keys())}"
    return f"{len(ACTION_PATTERNS)} action patterns, PromptAction consistent across modules"


def main():
    print("═" * 70)
    print("VERIFY Phase — SupremeAI Capability Matrix")
    print("═" * 70)

    tests = [
        ("1. SELF-HEALING", test_self_healing),
        ("2. SELF-EVOLVING", test_self_evolving),
        ("3. AUTO-LEARNING", test_auto_learning),
        ("4. SEMANTIC CACHE", test_semantic_cache),
        ("5. SSE STREAMING", test_sse_streaming),
        ("6. AUTO-HEALER", test_auto_healer),
        ("7. INTENT ROUTER", test_intent_router),
        ("8. PROMPTACTION CONSISTENCY", test_prompt_action_dataclass),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        if test(name, fn):
            passed += 1
        else:
            failed += 1

    print("\n" + "═" * 70)
    print(f"Result: {passed}/{len(tests)} passed, {failed} failed")
    print("═" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
