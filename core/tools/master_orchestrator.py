#!/usr/bin/env python3
"""
SupremeAI Master Cognitive Orchestrator CLI
============================================
Dispatches and chains Crown Jewel cognitive tools dynamically.

Usage:
    python tools/master_orchestrator.py --intent repair --error "SyntaxError in task_executor.py"
    python tools/master_orchestrator.py --intent synthesis --demand "Build high-throughput rate limiter"
    python tools/master_orchestrator.py --intent audit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Windows CP1252 stdout safety
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        print('Silenced error in except block')

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from core.orchestration.master_cognitive_orchestrator import (
    CognitiveIntent,
    get_master_orchestrator,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SupremeAI Master Cognitive Orchestrator")
    parser.add_argument(
        "--intent",
        choices=("repair", "synthesis", "audit", "evolution"),
        default="audit",
        help="Cognitive intent to execute",
    )
    parser.add_argument("--error", help="Error message for self-healing repair")
    parser.add_argument("--target", help="Target module/file path for repair or evolution")
    parser.add_argument("--demand", help="User demand or feature request for deep synthesis")
    parser.add_argument("--json", action="store_true", help="Output pure JSON")
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    orchestrator = get_master_orchestrator()

    intent_map = {
        "repair": CognitiveIntent.REPAIR,
        "synthesis": CognitiveIntent.FEATURE_SYNTHESIS,
        "audit": CognitiveIntent.AUDIT_RADAR,
        "evolution": CognitiveIntent.EVOLUTION,
    }
    intent = intent_map[args.intent]

    payload = {
        "error": args.error or "General runtime failure",
        "target_file": args.target or "adapters/task_executor.py",
        "demand": args.demand or "Optimal async task worker",
        "target_module": args.target or "skills/custom_skill.py",
    }

    result = await orchestrator.dispatch(intent, payload)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print("👑 SUPREMEAI MASTER COGNITIVE ORCHESTRATOR")
        print("=" * 70)
        print(f"Intent:     {result.intent.value.upper()}")
        print(f"Status:     {result.status}")
        print(f"Summary:    {result.summary}")
        print(f"Confidence: {result.confidence * 100:.1f}%")
        print("-" * 70)
        print("Stages Completed:")
        for stage in result.stages_completed:
            print(f"  ✓ {stage}")
        if result.error:
            print(f"🚨 Error: {result.error}")
        print("=" * 70)

    return 0 if result.status == "SUCCESS" else 1


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
