#!/usr/bin/env python3
"""AGENTS.md v2 generator — renders the agent constitution from rules.yml.

বাংলা: AGENTS.md এখন GENERATED document — হাতে এডিট করা যাবে না।
Single source of truth: `.github/constitution/rules.yml` (`constitution`,
`bootstrap`, `gates`, `hard_rules`, `freedoms` sections).

Usage:
    python scripts/ci/generate_agents_md.py             # write AGENTS.md
    python scripts/ci/generate_agents_md.py --check     # drift check (CI): exit 1 if drifted

Part of Phase-5 governance flip (Issue #2251): prose → gate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPO_ROOT / ".github" / "constitution" / "rules.yml"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"

HEADER = "<!-- GENERATED FILE — DO NOT EDIT BY HAND -->\n<!-- Source of truth: .github/constitution/rules.yml · Generator: scripts/ci/generate_agents_md.py -->\n<!-- CI drift check: system-gates.yml → agents-md-sync. To change rules, edit rules.yml. -->\n"


def render(rules: dict) -> str:
    """Render AGENTS.md v2 from the machine-readable registry."""
    constitution = rules.get("constitution") or {}
    living_protocols = rules.get("living_protocols") or {}
    bootstrap = rules.get("bootstrap") or []
    gates = rules.get("gates") or {}
    review_protocol = rules.get("review_protocol") or {}
    hard_rules = rules.get("hard_rules") or {}
    freedoms = rules.get("freedoms") or []
    version = constitution.get("rules_version", "2.1")

    lines: list[str] = []
    lines.append(HEADER)
    lines.append("")
    lines.append(f"# {constitution.get('name', 'SupremeAI — AGENTS.md v2 (Universal Operating Constitution & Agent Bootstrap)')}")
    lines.append("")
    lines.append(f"> rules_version: `{version}` · {constitution.get('philosophy_quote', '')}")
    lines.append(">")
    lines.append(f"> {constitution.get('philosophy_line', '')}")

    if constitution.get("benefit_principle"):
        lines.append(">")
        lines.append(f"> 💎 **{constitution.get('benefit_principle')}**")
    if constitution.get("separation_note"):
        lines.append(">")
        lines.append(f"> 🏛️ {constitution.get('separation_note')}")

    lines.append("")
    lines.append("---")
    lines.append("")

    if living_protocols:
        lines.append("## The Living Protocols (Root-Cause Invariants — ১০১% লাভ)")
        lines.append("")
        for pid, proto in living_protocols.items():
            lines.append(f"### {proto.get('title', pid)}")
            lines.append(f"{proto.get('rule', '')}")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Bootstrap Checklist (সেশন শুরু হলে ঠিক এই ক্রমে কাজ করো)")
    lines.append("")
    step_no = 0
    for entry in bootstrap:
        step_no += 1
        # Support both old-style {slot:..., claim:...} and new-style {step:...}
        if "step" in entry:
            command = entry["step"]
        else:
            label, command = next(iter(entry.items()))
        note = entry.get("note", "")
        line = f"{step_no}. `{command}`"
        if note:
            line += f" — {note}"
        lines.append(line)
    lines.append("")
    lines.append("_কাজ শুরুর আগে সর্বদা `git fetch origin --prune && cat AGENTS.md` চালাও।_")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## System যা আটকাবে (মনে রাখার দরকার নেই — শুধু জেনে রাখো কেন আটকালো)")
    lines.append("")
    lines.append("| Gate | কখন আটকাবে | Enforcement |")
    lines.append("| :--- | :--- | :--- |")
    for gid, gate in gates.items():
        title = gate.get("title", gid)
        blocks = (gate.get("blocks_when", "") or "").replace("|", "\\|")
        if gate.get("wired"):
            enforcement = f"CI ({gate.get('workflow', 'workflow')})"
        else:
            enforcement = (gate.get("enforced_by", "follow-up") or "follow-up").split("(")[0].strip()
        lines.append(f"| {title} | {blocks} | {enforcement} |")
    lines.append("")

    if review_protocol and review_protocol.get("rubric"):
        lines.append("---")
        lines.append("")
        lines.append("## Peer Review Protocol (The 4-Pillar Rubric)")
        lines.append("")
        lines.append("| Pillar | প্রশ্ন ও মানদণ্ড |")
        lines.append("| :--- | :--- |")
        for item in review_protocol.get("rubric", []):
            pillar = item.get("pillar", "")
            check = item.get("check", "")
            lines.append(f"| **{pillar}** | {check} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## তোমার স্বাধীনতা (কেউ আটকাবে না)")
    lines.append("")
    for freedom in freedoms:
        lines.append(f"- {freedom}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## একমাত্র কঠিন নিয়ম (মোট ৩টা, বাকি সব system-এর ভার)")
    lines.append("")
    for idx, (_, text) in enumerate(hard_rules.items(), start=1):
        lines.append(f"{idx}. {text}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> সম্পূর্ণ machine-readable rule registry: `.github/constitution/rules.yml` (CI এটা থেকে gate চালায়)।")
    lines.append("> **এই file-টি registry থেকে GENERATED — হাতে এডিট করবে না।**")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AGENTS.md from rules.yml")
    parser.add_argument("--check", action="store_true",
                        help="drift check: exit 1 if AGENTS.md differs from generated output")
    parser.add_argument("--rules", default=str(RULES_PATH))
    parser.add_argument("--out", default=str(AGENTS_PATH))
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:
        print("PyYAML required: pip install pyyaml", file=sys.stderr)
        return 2

    rules = yaml.safe_load(Path(args.rules).read_text(encoding="utf-8")) or {}
    rendered = render(rules)

    if args.check:
        current = Path(args.out).read_text(encoding="utf-8")
        if current == rendered:
            print("[PASSED] AGENTS.md is in sync with rules.yml")
            return 0
        print("[FAILED] AGENTS.md drifted from rules.yml — "
              "run `python scripts/ci/generate_agents_md.py` and commit")
        return 1

    Path(args.out).write_text(rendered, encoding="utf-8")
    print(f"[OK] AGENTS.md generated from {args.rules} ({len(rendered.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
