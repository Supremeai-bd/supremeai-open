#!/usr/bin/env python3
"""
SupremeAI - Auto Checkpoint Updater (Phase B)
=============================================
প্রতিটি git commit-এর আগে বা ম্যানুয়ালি রান করলে CHECKPOINT.md আপডেট করে।

Usage:
  python scripts/checkpoint_update.py
  python scripts/checkpoint_update.py --message "Fixed CI pipeline"

Setup as git pre-commit hook:
  cp scripts/checkpoint_update.py .git/hooks/pre-commit
  chmod +x .git/hooks/pre-commit
"""

import argparse
import os
import subprocess
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKPOINT_FILE = os.path.join(ROOT_DIR, "CHECKPOINT.md")
LESSONS_FILE = os.path.join(ROOT_DIR, "LESSONS_LEARNED.md")


def get_git_changed_files() -> list[str]:
    """সর্বশেষ staged বা unstaged পরিবর্তিত ফাইলের তালিকা বের করে।"""
    try:
        # Staged files (about to be committed)
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=ROOT_DIR
        )
        staged = [f for f in result.stdout.strip().split("\n") if f]

        # Recently modified files (last commit)
        result2 = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-only"],
            capture_output=True, text=True, cwd=ROOT_DIR
        )
        recent = [f for f in result2.stdout.strip().split("\n") if f]

        files = list(set(staged + recent))
        return [f for f in files if f]  # Remove empty strings
    except Exception:
        return []


def get_last_lessons(n: int = 3) -> str:
    """LESSONS_LEARNED.md থেকে শেষ N টি lesson বের করে (সংক্ষিপ্ত)।"""
    try:
        with open(LESSONS_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        # Find last N "##" sections
        sections = content.split("\n## ")
        last_sections = sections[-n:] if len(sections) >= n else sections
        summaries = []
        for sec in last_sections:
            first_line = sec.strip().split("\n")[0].strip("# ").strip()
            if first_line:
                summaries.append(f"  - {first_line}")
        return "\n".join(summaries) if summaries else "  - (no recent lessons)"
    except Exception:
        return "  - (LESSONS_LEARNED.md not found)"


def read_current_checkpoint() -> dict:
    """বর্তমান CHECKPOINT.md পড়ে Pending সেকশন বের করে।"""
    pending = []
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        in_pending = False
        for line in content.split("\n"):
            if line.startswith("## ") and "Pending" in line:
                in_pending = True
                continue
            if line.startswith("## ") and in_pending:
                break
            if in_pending and line.strip().startswith("-"):
                pending.append(line.strip())
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Silenced error: {e}")

    return {"pending": pending}


def update_checkpoint(completed: str, message: str = "") -> None:
    """CHECKPOINT.md আপডেট করে — পুরানো pending → completed হিসেবে move করে।"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    changed_files = get_git_changed_files()
    last_lessons = get_last_lessons(3)
    current = read_current_checkpoint()

    # Build new pending from old pending (carry forward incomplete items)
    old_pending = "\n".join(current["pending"]) if current["pending"] else "  - (none)"

    files_str = "\n".join([f"  - `{f}`" for f in changed_files]) if changed_files else "  - (none detected)"

    new_content = f"""# SupremeAI Session Checkpoint
> Auto-updated by AI agents after each major session. Next agent must read this first.

## Last Session
- **Date:** {now}
- **Agent:** Auto-updated (checkpoint_update.py)
- **Summary:** {message or completed or "Session update"}

## Completed This Session
{completed if completed else "  - (see git log for details)"}

## Files Changed
{files_str}

## Pending (Carry Forward)
{old_pending}

## Recent Lessons Learned
{last_lessons}

## Key Architecture Reminders
- Extension = 100% Thin Client. No third-party API keys from user.
- `SupremeAIService.ts` lines 350-424: OpenRouter fetch logic → MUST be removed.
- Only local Ollama permitted as offline fallback.
- Supabase `ai_memory` table setup pending (Phase C).

## Next Agent Start Point
1. Read `AGENTS.md` + this file (done ✅)
2. Check task type → read relevant files per Context Matrix in `AGENTS.md`
3. Continue from Pending list above
"""

    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[OK] CHECKPOINT.md updated at {now}")
    print(f"[INFO] Files tracked: {len(changed_files)}")


def main():
    parser = argparse.ArgumentParser(description="SupremeAI Checkpoint Updater")
    parser.add_argument("--message", "-m", type=str, default="", help="Session summary message")
    parser.add_argument("--completed", "-c", type=str, default="", help="What was completed")
    args = parser.parse_args()

    print("[INFO] Updating CHECKPOINT.md...")
    update_checkpoint(completed=args.completed, message=args.message)


if __name__ == "__main__":
    main()
