#!/usr/bin/env python3
"""
rotate_lessons.py — LESSONS_LEARNED.md Size Cap Enforcer
Rule: Keep last 30 entries (~12KB). Archive older entries to docs/archive/lessons_YYYY-MM.md
Usage: python scripts/rotate_lessons.py [--dry-run]
"""

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
LESSONS_FILE = ROOT / "LESSONS_LEARNED.md"
ARCHIVE_DIR = ROOT / "docs" / "archive"
MAX_ENTRIES = 30
SIZE_CAP_KB = 12

def split_entries(content: str) -> list[str]:
    """Split file into individual lesson entries (split on ## headers)."""
    parts = re.split(r'(?=^## )', content, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]

def main():
    dry_run = "--dry-run" in sys.argv

    if not LESSONS_FILE.exists():
        print("❌ LESSONS_LEARNED.md not found")
        sys.exit(1)

    content = LESSONS_FILE.read_text(encoding="utf-8")
    size_kb = len(content.encode("utf-8")) / 1024
    print(f"[INFO] Current size: {size_kb:.1f} KB")

    if size_kb <= SIZE_CAP_KB:
        print(f"[OK] Size is within {SIZE_CAP_KB}KB cap. No rotation needed.")
        return

    entries = split_entries(content)
    total = len(entries)
    print(f"[INFO] Total entries: {total}")

    # Remove oldest entries (bottom of list, since newest is at top) until <= SIZE_CAP_KB
    to_keep = list(entries)
    to_archive = []
    while len("\n\n".join(to_keep).encode("utf-8")) / 1024 > SIZE_CAP_KB and len(to_keep) > 5:
        to_archive.append(to_keep.pop())  # pop oldest (last in list = oldest = bottom of file)

    print(f"[INFO] Archiving {len(to_archive)} entries | Keeping {len(to_keep)}")

    # Write archive file
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_filename = f"lessons_{datetime.now().strftime('%Y-%m')}.md"
    archive_path = ARCHIVE_DIR / archive_filename

    archive_header = f"# LESSONS_LEARNED Archive — {datetime.now().strftime('%Y-%m')}\n> Auto-archived by rotate_lessons.py on {datetime.now().isoformat()[:10]}\n> Original entries: {len(to_archive)}\n\n"
    archive_content = archive_header + "\n\n".join(to_archive)

    if dry_run:
        print(f"\n[DRY RUN] Would archive to: {archive_path}")
        print(f"   Entries to archive: {len(to_archive)}")
        print(f"   Entries to keep:    {len(to_keep)}")
        new_size = len(("\n\n".join(to_keep)).encode("utf-8")) / 1024
        print(f"   New size estimate:  {new_size:.1f} KB")
    else:
        # Append if archive for this month already exists
        if archive_path.exists():
            existing = archive_path.read_text(encoding="utf-8")
            archive_path.write_text(existing + "\n\n---\n\n" + "\n\n".join(to_archive), encoding="utf-8")
        else:
            archive_path.write_text(archive_content, encoding="utf-8")

        new_content = "\n\n".join(to_keep) + "\n"
        LESSONS_FILE.write_text(new_content, encoding="utf-8")
        new_size = len(new_content.encode("utf-8")) / 1024

        print("[OK] Rotation complete!")
        print(f"   Archived {len(to_archive)} entries -> {archive_path}")
        print(f"   New LESSONS_LEARNED.md size: {new_size:.1f} KB")

if __name__ == "__main__":
    main()
