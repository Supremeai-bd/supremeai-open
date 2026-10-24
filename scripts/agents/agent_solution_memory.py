#!/usr/bin/env python3
r"""SupremeAI — Collective Agent Memory & Problem-Solving Layer CLI.

Implements the "Search Before Solving · Pave Before Leaving · Gap Before Guessing" workflow:
1. Search database & LESSONS_LEARNED.md for how previous agents solved the same issue.
2. Record newly validated solutions into database memory and LESSONS_LEARNED.md.
3. Record Solution Gaps (failed attempts, missing capabilities, future path) when no solution exists.
4. Verify MCP Control Tower connection contract.

Usage:
    # 1. Search for existing solutions:
    python scripts/agents/agent_solution_memory.py search --query "UnicodeEncodeError charmap"

    # 2. Record a validated solution:
    python scripts/agents/agent_solution_memory.py record \
        --task-id "2237" \
        --problem "PowerShell cp1252 stdout fails on UTF-8 emojis" \
        --solution "Prefix command with PYTHONIOENCODING=utf-8" \
        --lesson "Always set PYTHONIOENCODING in windows terminal subprocesses" \
        --status "VERIFIED" \
        --tags "windows,encoding,powershell"

    # 3. Record a Solution Gap (when no solution yet exists):
    python scripts/agents/agent_solution_memory.py gap \
        --task-id "1042" \
        --problem "Authentication token refresh fails inside isolated container" \
        --failed-attempts "OAuth refresh failed; stored token caused security violation" \
        --missing-capability "credential.refresh.scoped" \
        --future-path "Implement scoped credential broker endpoint"

    # 4. Verify MCP connection:
    python scripts/agents/agent_solution_memory.py verify-mcp
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

LESSONS_FILE = REPO_ROOT / "LESSONS_LEARNED.md"
MCP_CONFIG_FILE = REPO_ROOT / "mcp.json"
SQLITE_DB_PATH = REPO_ROOT / "data" / "supremeai.db"


def search_local_lessons(query: str) -> list[dict[str, str]]:
    """Search LESSONS_LEARNED.md for relevant entries matching keywords in query."""
    hits = []
    if not LESSONS_FILE.exists():
        return hits

    terms = [t.lower() for t in re.split(r"[\s,:;\-_]+", query) if len(t) > 2]
    if not terms:
        return hits

    try:
        content = LESSONS_FILE.read_text(encoding="utf-8", errors="replace")
    except Exception as err:
        print(f"[WARN] Failed reading LESSONS_LEARNED.md: {err}", file=sys.stderr)
        return hits

    for line in content.splitlines():
        line_clean = line.strip()
        if not line_clean.startswith("|") or "Date" in line_clean or "---" in line_clean:
            continue
        line_lower = line_clean.lower()
        score = sum(1 for term in terms if term in line_lower)
        if score > 0:
            hits.append({"text": line_clean, "score": score, "source": "LESSONS_LEARNED.md"})

    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits[:5]


def search_database_memory(query: str) -> list[dict[str, Any]]:
    """Search episodic memory or SQLite database for similar past task solutions and gaps."""
    hits = []
    try:
        from memory.episodic_memory import EpisodicMemory

        ep_mem = EpisodicMemory(db_path=str(SQLITE_DB_PATH))
        results = ep_mem.recall_episodes(query=query)
        for ep in results:
            hits.append({
                "task_id": ep.get("task_id", ep.get("id", "unknown")),
                "type": ep.get("event_type", "solution"),
                "problem": ep.get("context", ep.get("input_data", "")),
                "solution": ep.get("outcome", ep.get("output_data", "")),
                "success": ep.get("success", True),
                "source": "EpisodicMemory (Database)",
            })
    except Exception:
        pass
    return hits


def record_solution(
    task_id: str,
    problem: str,
    solution: str,
    lesson: str,
    status: str = "VERIFIED",
    tags: list[str] | None = None,
) -> bool:
    """Record solution into database episodic memory and LESSONS_LEARNED.md."""
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    clean_task = task_id.lstrip("#")

    # 1. Store in Database Episodic Memory
    try:
        from memory.episodic_memory import EpisodicMemory

        ep_mem = EpisodicMemory(db_path=str(SQLITE_DB_PATH))
        ep_mem.store_episode(
            event_type="solution",
            context=problem,
            outcome=solution,
            importance=1.0,
            success=True,
            tags=tags or [],
            metadata={"lesson": lesson, "task_id": clean_task, "status": status},
        )
        print(f"✅ Stored solution [{status}] into Database Episodic Memory for task #{clean_task}.")
    except Exception as err:
        print(f"[INFO] Database storage skipped ({err}), recording to file.")

    # 2. Append to LESSONS_LEARNED.md if not already recorded
    if LESSONS_FILE.exists():
        try:
            content = LESSONS_FILE.read_text(encoding="utf-8", errors="replace")
            new_entry = f"| {now_str} | #{clean_task} | {problem} | {solution} | {lesson} |"
            if clean_task not in content:
                lines = content.splitlines()
                table_idx = -1
                for i, l in enumerate(lines):
                    if l.strip().startswith("| :---"):
                        table_idx = i + 1
                        break
                if table_idx != -1:
                    lines.insert(table_idx, new_entry)
                    LESSONS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    print(f"✅ Appended entry to LESSONS_LEARNED.md (# {clean_task}).")
                else:
                    with open(LESSONS_FILE, "a", encoding="utf-8") as f:
                        f.write(f"\n{new_entry}\n")
                    print(f"✅ Appended entry to end of LESSONS_LEARNED.md (# {clean_task}).")
            else:
                print(f"ℹ️ Issue #{clean_task} already present in LESSONS_LEARNED.md.")
        except Exception as err:
            print(f"[ERROR] Failed writing to LESSONS_LEARNED.md: {err}", file=sys.stderr)
            return False

    return True


def record_solution_gap(
    task_id: str,
    problem: str,
    failed_attempts: str,
    missing_capability: str,
    future_path: str,
) -> bool:
    """Record a Solution Gap when no known solution exists to pave the way for future agents."""
    clean_task = task_id.lstrip("#")
    try:
        from memory.episodic_memory import EpisodicMemory

        ep_mem = EpisodicMemory(db_path=str(SQLITE_DB_PATH))
        ep_mem.store_episode(
            event_type="solution_gap",
            context=problem,
            outcome=f"GAP: missing capability '{missing_capability}'. Path: {future_path}",
            importance=0.9,
            success=False,
            tags=["gap", missing_capability],
            metadata={
                "task_id": clean_task,
                "failed_attempts": failed_attempts,
                "missing_capability": missing_capability,
                "future_path": future_path,
                "status": "GAP",
            },
        )
        print(f"🧭 Solution Gap [GAP-{clean_task}] recorded in Database Memory:")
        print(f"   Missing Capability: {missing_capability}")
        print(f"   Future Recommended Path: {future_path}")
        return True
    except Exception as err:
        print(f"[WARN] Failed storing gap in episodic memory: {err}", file=sys.stderr)
        return False


def verify_mcp() -> bool:
    """Verify MCP Control Tower connection contract."""
    print("🔍 Checking SupremeAI MCP Tower connection contract...")
    
    # 1. Check workspace config (mcp.json)
    if MCP_CONFIG_FILE.exists():
        try:
            cfg = json.loads(MCP_CONFIG_FILE.read_text(encoding="utf-8"))
            servers = cfg.get("mcpServers", {})
            if "supremeai-control-tower" in servers:
                print("✅ Valid MCP Tower contract found in mcp.json.")
                return True
        except Exception:
            pass

    # 2. Check environment variable contract
    mcp_env = os.environ.get("MCP_TOWER_URL", os.environ.get("MCP_SERVER_URL", ""))
    if mcp_env:
        print("✅ Valid MCP Tower contract found in environment (MCP_TOWER_URL).")
        return True

    print("❌ No valid MCP Tower contract found (checked mcp.json and MCP_TOWER_URL).", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Collective Agent Memory & Problem-Solving Layer CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search Command
    search_parser = subparsers.add_parser("search", help="Search past solutions by problem or error query")
    search_parser.add_argument("--query", "-q", required=True, help="Error message, symptom, or task description")

    # Record Command
    record_parser = subparsers.add_parser("record", help="Record newly validated solution for future agents")
    record_parser.add_argument("--task-id", required=True, help="GitHub Issue ID or task identifier")
    record_parser.add_argument("--problem", required=True, help="Problem summary or error signature")
    record_parser.add_argument("--solution", required=True, help="Exact validated solution recipe")
    record_parser.add_argument("--lesson", required=True, help="Prevention rule / lesson learned")
    record_parser.add_argument("--status", default="VERIFIED", choices=["UNVERIFIED", "EXPERIMENTAL", "VERIFIED", "RECOMMENDED"], help="Trust status")
    record_parser.add_argument("--tags", default="", help="Comma-separated tags")

    # Gap Command (Path B)
    gap_parser = subparsers.add_parser("gap", help="Record a Solution Gap when no solution yet exists")
    gap_parser.add_argument("--task-id", required=True, help="GitHub Issue ID or task identifier")
    gap_parser.add_argument("--problem", required=True, help="Problem summary or symptom")
    gap_parser.add_argument("--failed-attempts", required=True, help="What previous approaches were tried and failed")
    gap_parser.add_argument("--missing-capability", required=True, help="Missing system or tool capability")
    gap_parser.add_argument("--future-path", required=True, help="Recommended next path for future agents")

    # Verify MCP Command
    subparsers.add_parser("verify-mcp", help="Verify MCP Control Tower connection contract")

    args = parser.parse_args()

    if args.command == "search":
        print(f"🔍 Searching SupremeAI Collective Memory for: '{args.query}'...\n")
        lessons = search_local_lessons(args.query)
        db_hits = search_database_memory(args.query)

        if not lessons and not db_hits:
            print("⚠️ No exact previous solutions found in system memory.")
            print("👉 Recommendation: Check available capabilities, or record a Solution Gap ('gap') if missing tools!")
            return 0

        print(f"Found {len(lessons) + len(db_hits)} potential reference(s):\n")
        if lessons:
            print("📋 Matches from LESSONS_LEARNED.md:")
            for hit in lessons:
                print(f"  • {hit['text']}")
            print()
        if db_hits:
            print("🧠 Matches from Database Episodic Memory:")
            for hit in db_hits:
                print(f"  • [{hit['type'].upper()} #{hit['task_id']}] {hit['problem']} -> {hit['solution']}")
            print()

        return 0

    elif args.command == "record":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        success = record_solution(
            task_id=args.task_id,
            problem=args.problem,
            solution=args.solution,
            lesson=args.lesson,
            status=args.status,
            tags=tags,
        )
        return 0 if success else 1

    elif args.command == "gap":
        success = record_solution_gap(
            task_id=args.task_id,
            problem=args.problem,
            failed_attempts=args.failed_attempts,
            missing_capability=args.missing_capability,
            future_path=args.future_path,
        )
        return 0 if success else 1

    elif args.command == "verify-mcp":
        return 0 if verify_mcp() else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
