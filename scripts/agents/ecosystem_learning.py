#!/usr/bin/env python3
"""
Ecosystem Learning Loop (#3187).

Captures structured traces for agent runs, scores selected traces,
and persists evidence/decision rationale for future improvement.

Design (AGENT_RULES.md P1 — Simple + Effective):
  - Trace format: JSONL in docs/master_docs/AGENT_TRACES.jsonl
  - Each trace = agent_run, decision, tool_call, outcome
  - Evaluation: simple rubric (success/fail/partial + reason)
  - Learning: pattern extraction from traces (most common failure modes)
  - No external ML — deterministic pattern matching

Usage:
    python scripts/agents/ecosystem_learning.py --record --agent coder-1 --issue 1234 --action "fixed bug" --result success
    python scripts/agents/ecosystem_learning.py --evaluate
    python scripts/agents/ecosystem_learning.py --patterns
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict

ROOT_DIR = Path(__file__).resolve().parents[1]
TRACE_FILE = ROOT_DIR / "docs" / "master_docs" / "AGENT_TRACES.jsonl"
PATTERN_FILE = ROOT_DIR / "docs" / "master_docs" / "AGENT_LEARNING_PATTERNS.json"


def record_trace(agent: str, issue: str, action: str, result: str,
                 details: str = "", tools: list[str] | None = None) -> str:
    """Record an agent run trace."""
    trace = {
        "trace_id": f"{agent}-{int(time.time())}",
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": agent,
        "issue": issue,
        "action": action,
        "result": result,  # success | fail | partial
        "details": details,
        "tools": tools or [],
    }
    
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace) + "\n")
    
    return trace["trace_id"]


def evaluate_traces() -> dict:
    """Evaluate all traces — compute success rates + failure patterns."""
    if not TRACE_FILE.exists():
        return {"total": 0, "success_rate": 0, "failure_patterns": []}
    
    traces = []
    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    traces.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    
    total = len(traces)
    if total == 0:
        return {"total": 0, "success_rate": 0, "failure_patterns": []}
    
    results = Counter(t.get("result", "unknown") for t in traces)
    success_rate = results.get("success", 0) / total
    
    # Extract failure patterns
    failures = [t for t in traces if t.get("result") == "fail"]
    failure_actions = Counter(t.get("action", "unknown") for t in failures)
    
    return {
        "total": total,
        "success": results.get("success", 0),
        "fail": results.get("fail", 0),
        "partial": results.get("partial", 0),
        "success_rate": round(success_rate, 3),
        "failure_patterns": failure_actions.most_common(5),
    }


def extract_patterns() -> list[dict]:
    """Extract common patterns from traces for learning."""
    if not TRACE_FILE.exists():
        return []
    
    traces = []
    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    traces.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    
    # Group by action → compute success rate
    by_action = defaultdict(lambda: {"success": 0, "fail": 0, "total": 0})
    for t in traces:
        action = t.get("action", "unknown")
        by_action[action]["total"] += 1
        if t.get("result") == "success":
            by_action[action]["success"] += 1
        elif t.get("result") == "fail":
            by_action[action]["fail"] += 1
    
    patterns = []
    for action, counts in sorted(by_action.items(), key=lambda x: -x[1]["total"]):
        patterns.append({
            "action": action,
            "total": counts["total"],
            "success_rate": round(counts["success"] / counts["total"], 3) if counts["total"] > 0 else 0,
            "recommendation": "keep" if counts["success"] / max(counts["total"], 1) > 0.7 else "investigate",
        })
    
    # Persist patterns
    PATTERN_FILE.parent.mkdir(parents=True, exist_ok=True)
    PATTERN_FILE.write_text(json.dumps({"patterns": patterns, "updated_at": time.time()}, indent=2), encoding="utf-8")
    
    return patterns


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ecosystem Learning Loop (#3187)")
    parser.add_argument("--record", action="store_true", help="Record a trace")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate traces")
    parser.add_argument("--patterns", action="store_true", help="Extract patterns")
    parser.add_argument("--agent", default="unknown")
    parser.add_argument("--issue", default="")
    parser.add_argument("--action", default="")
    parser.add_argument("--result", default="unknown", choices=["success", "fail", "partial"])
    parser.add_argument("--details", default="")
    args = parser.parse_args()
    
    if args.record:
        tid = record_trace(args.agent, args.issue, args.action, args.result, args.details)
        print(f"Recorded trace: {tid}")
    elif args.evaluate:
        eval_result = evaluate_traces()
        print(json.dumps(eval_result, indent=2))
    elif args.patterns:
        patterns = extract_patterns()
        print(json.dumps(patterns, indent=2))
    else:
        parser.print_help()
