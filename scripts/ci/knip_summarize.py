#!/usr/bin/env python3
"""knip JSON → পাঠযোগ্য summary (weekly hygiene issue-র জন্য)।

বাংলা মন্তব্য: knip-এর json reporter schema ভার্সনে বদলাতে পারে — তাই পার্সার
defensive: যে কোনো অপ্রত্যাশিত structure-এ সৎ fallback বার্তা দেয়, কখনো crash
করে না (report-only টুল; CI ভাঙার অধিকার নেই)। সংখ্যা সব প্রকৃত ডেটা থেকে।
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def summarize(data: object) -> str:
    lines: list[str] = []
    if isinstance(data, dict):
        files = data.get("files")
        issues = data.get("issues") or {}
        # বাংলা: knip schema ভার্সনে files list বা dict দুটোই হতে পারে — দুটোই ধরি
        if isinstance(files, list) and files:
            lines.append(f"unused files: {len(files)}")
            for path in files[:15]:
                lines.append(
                    f"  - {path if isinstance(path, str) else path.get('file', '?')}"
                )
            if len(files) > 15:
                lines.append(f"  … আরও {len(files) - 15}টি")
        elif isinstance(files, dict) and files:
            lines.append(f"unused files: {len(files)}")
            for path in list(files)[:15]:
                lines.append(f"  - {path}")
            if len(files) > 15:
                lines.append(f"  … আরও {len(files) - 15}টি")
        if isinstance(issues, dict) and issues:
            total_issues = 0
            for entry in issues.values():
                if isinstance(entry, dict):
                    total_issues += sum(
                        len(v) for v in entry.values() if isinstance(v, list)
                    )
            lines.append(f"total symbol/export issues: {total_issues}")
        if not lines:
            lines.append(
                "(knip json-এ পরিচিত কোনো counter পাওয়া যায়নি — raw artifact দেখুন)"
            )
    elif isinstance(data, list):
        lines.append(f"knip findings (list form): {len(data)}")
        for item in data[:15]:
            file_ref = item.get("file", "?") if isinstance(item, dict) else str(item)
            lines.append(f"  - {file_ref}")
    else:
        lines.append("(অপ্রত্যাশিত knip output — সৎ fallback, অনুমান নয়)")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: knip_summarize.py <knip.json> <out.txt>", file=sys.stderr)
        return 1
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        summary = f"(knip output unreadable: {exc} — এই সপ্তাহে সৎ অনুপস্থিতি)"
    else:
        summary = summarize(data)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(summary + "\n", encoding="utf-8")
    print(f"[knip-summarize] wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
