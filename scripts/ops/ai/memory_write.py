#!/usr/bin/env python3
"""
SupremeAI - AI Memory Write (Phase C)
=====================================
প্রতিটি সেশন শেষে AI-এর key learnings Supabase-এ vector হিসেবে save করে।
এটাই "Eternal Brain"-এর ভিত্তি।

Usage:
  python scripts/ai/memory_write.py --summary "Fixed CI pipeline by..." --task-type "ci"
  python scripts/ai/memory_write.py --from-checkpoint  # CHECKPOINT.md থেকে অটো-read
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from core.config import settings
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root to path
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "backend"))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    print("python-dotenv not installed, continuing with existing environment.")

CHECKPOINT_FILE = ROOT_DIR / "CHECKPOINT.md"
VALID_TASK_TYPES = ["bug-fix", "feature", "refactor", "deploy", "ci", "planning", "debug", "general"]


def get_embedding(text: str) -> list[float]:
    """
    HuggingFace sentence-transformers দিয়ে embedding তৈরি করে ($0 cost, local)।
    Fallback: simple word-frequency vector।
    """
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")  # ছোট, দ্রুত, ফ্রি
        embedding = model.encode(text).tolist()
        return embedding
    except (ImportError, OSError) as e:
        print(f"⚠️  sentence-transformers not available ({e}). Using fallback null embedding.")
        print("   Install/Fix: pip install sentence-transformers (and ensure VC++ redist is installed on Windows)")
        return [0.0] * 384  # MiniLM-L6-v2 dimension


def get_supabase_client():
    """Supabase client তৈরি করে।"""
    try:
        from supabase import create_client
        url = settings.supabase_url
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set in .env")
        return create_client(url, key)
    except ImportError:
        raise ImportError("supabase-py not installed. Run: pip install supabase")


def read_checkpoint_summary() -> tuple[str, str]:
    """CHECKPOINT.md থেকে completed summary এবং task type বের করে।"""
    try:
        content = CHECKPOINT_FILE.read_text(encoding="utf-8")
        summary_lines = []
        task_type = "general"
        in_completed = False

        for line in content.split("\n"):
            if "## Completed This Session" in line:
                in_completed = True
                continue
            if line.startswith("## ") and in_completed:
                break
            if in_completed and line.strip().startswith("-"):
                summary_lines.append(line.strip("- ").strip())

            # Task type detection
            if "ci" in line.lower() or "pipeline" in line.lower():
                task_type = "ci"
            elif "bug" in line.lower() or "fix" in line.lower():
                task_type = "bug-fix"
            elif "feature" in line.lower() or "implement" in line.lower():
                task_type = "feature"
            elif "refactor" in line.lower():
                task_type = "refactor"

        summary = " | ".join(summary_lines[:5]) if summary_lines else "Session memory save"
        return summary, task_type
    except Exception:
        return f"Memory save at {datetime.now().isoformat()}", "general"


def save_memory(summary: str, task_type: str, agent_type: str = "main",
                metadata: dict | None = None) -> bool:
    """Supabase ai_memory টেবিলে একটি memory entry save করে।"""
    print(f"🧠 Generating embedding for: '{summary[:60]}...'")
    embedding = get_embedding(summary)

    supabase = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()

    record = {
        "session_id": f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "agent_type": agent_type,
        "task_type": task_type,
        "summary": summary,
        "embedding": embedding,
        "metadata": json.dumps(metadata or {}),
        "created_at": now,
    }

    result = supabase.table("ai_memory").insert(record).execute()

    if result.data:
        print(f"✅ Memory saved! ID: {result.data[0].get('id', 'unknown')}")
        print(f"   Task: {task_type} | Agent: {agent_type}")
        return True
    else:
        print(f"❌ Failed to save memory: {result}")
        return False


def main():
    parser = argparse.ArgumentParser(description="SupremeAI AI Memory Writer")
    parser.add_argument("--summary", "-s", type=str, default="",
                        help="Summary of what was accomplished this session")
    parser.add_argument("--task-type", "-t", type=str, default="general",
                        choices=VALID_TASK_TYPES,
                        help="Type of task performed")
    parser.add_argument("--agent-type", "-a", type=str, default="main",
                        choices=["main", "subagent", "reviewer"],
                        help="Type of agent performing the task")
    parser.add_argument("--from-checkpoint", action="store_true",
                        help="Auto-read summary from CHECKPOINT.md")
    args = parser.parse_args()

    if args.from_checkpoint:
        print("📖 Reading from CHECKPOINT.md...")
        summary, task_type = read_checkpoint_summary()
        print(f"   Detected task type: {task_type}")
    else:
        summary = args.summary or "Session memory save"
        task_type = args.task_type

    if not summary:
        print("❌ No summary provided. Use --summary or --from-checkpoint")
        sys.exit(1)

    save_memory(
        summary=summary,
        task_type=task_type,
        agent_type=args.agent_type,
        metadata={"source": "cli", "checkpoint_used": args.from_checkpoint}
    )


if __name__ == "__main__":
    main()
