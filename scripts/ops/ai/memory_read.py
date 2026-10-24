#!/usr/bin/env python3
"""
SupremeAI - AI Memory Read (Phase C)
=====================================
বড় কাজ শুরুর আগে Supabase থেকে প্রাসঙ্গিক past memory query করে।
Semantic search ব্যবহার করে — task description দিলে সবচেয়ে relevant
past experiences দেখায়।

Usage:
  python scripts/ai/memory_read.py --task "fix github actions failure"
  python scripts/ai/memory_read.py --task "deploy backend" --limit 3
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from core.config import settings
import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "backend"))


def get_embedding(text: str) -> list[float]:
    """Sentence-transformers দিয়ে embedding তৈরি করে।"""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text).tolist()
    except ImportError:
        print("⚠️  sentence-transformers not installed. Install: pip install sentence-transformers")
        return [0.0] * 384


def get_supabase_client():
    """Supabase client তৈরি করে।"""
    try:
        from supabase import create_client
        url = settings.supabase_url
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in environment")
        return create_client(url, key)
    except ImportError:
        raise ImportError("supabase-py not installed. Run: pip install supabase")


def recall_memories(task_description: str, limit: int = 5,
                    threshold: float = 0.7) -> list[dict]:
    """
    Task description থেকে Supabase pgvector-এ semantic search করে
    সবচেয়ে relevant past memories return করে।
    """
    print(f"🔍 Searching memory for: '{task_description}'")
    embedding = get_embedding(task_description)

    supabase = get_supabase_client()

    # pgvector match_memory RPC function call
    result = supabase.rpc("match_ai_memory", {
        "query_embedding": embedding,
        "match_threshold": threshold,
        "match_count": limit,
    }).execute()

    return result.data or []


def display_memories(memories: list[dict]) -> None:
    """Memory results সুন্দরভাবে print করে।"""
    if not memories:
        print("\n💭 No relevant past memories found for this task.")
        print("   (This is normal for first-time tasks or new task types)\n")
        return

    print(f"\n🧠 Found {len(memories)} relevant past memories:\n")
    print("=" * 60)

    for i, mem in enumerate(memories, 1):
        similarity = mem.get("similarity", 0)
        task_type = mem.get("task_type", "unknown")
        summary = mem.get("summary", "")
        created_at = mem.get("created_at", "")[:10]  # Just date

        print(f"\n[{i}] Relevance: {similarity:.0%} | Type: {task_type} | Date: {created_at}")
        print(f"    📝 {summary}")

    print("\n" + "=" * 60)
    print("\n💡 Use these past experiences to avoid repeating mistakes!\n")


def main():
    parser = argparse.ArgumentParser(description="SupremeAI AI Memory Reader")
    parser.add_argument("--task", "-t", type=str, required=True,
                        help="Task description to search for relevant memories")
    parser.add_argument("--limit", "-l", type=int, default=5,
                        help="Max number of memories to return (default: 5)")
    parser.add_argument("--threshold", type=float, default=0.7,
                        help="Similarity threshold 0-1 (default: 0.7)")
    args = parser.parse_args()

    try:
        memories = recall_memories(
            task_description=args.task,
            limit=args.limit,
            threshold=args.threshold
        )
        display_memories(memories)
    except Exception as e:
        print(f"❌ Memory read failed: {e}")
        print("   Tip: Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        print("   Tip: Run the Supabase SQL migration first (see docs/ai_memory_migration.sql)")
        sys.exit(1)


if __name__ == "__main__":
    main()
