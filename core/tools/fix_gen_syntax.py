#!/usr/bin/env python3
"""Repair known generated knowledge-seed syntax damage before static auditing."""
from __future__ import annotations

import re

PATH = "tools/gen_knowledge_seed.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

# A generated entry occasionally contains a malformed final string such as
# `"...queries")]`. The intended list element is `"...queries)"`.
content = re.sub(r'"\)\]', ')\"]', content)

keywords = [
    "assumptions=",
    "invariants=",
    "failure_modes=",
    "counterarguments=",
    "evidence=",
]

lines = content.splitlines()
fixed: list[str] = []
for line in lines:
    stripped = line.strip()
    matched_kw = next((kw for kw in keywords if stripped.startswith(kw)), None)

    if matched_kw:
        indent_match = re.match(r"^(\s+)", line)
        indent = indent_match.group(1) if indent_match else ""
        eq_idx = stripped.index("=")
        value_part = stripped[eq_idx + 1 :]
        target = '"]'
        last_close = value_part.rfind(target)
        if last_close >= 0:
            list_value = value_part[: last_close + len(target)]
            fixed.append(f"{indent}{matched_kw}{list_value},")
            continue

    fixed.append(line)

with open(PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(fixed) + "\n")

print(f"Syntax repair applied to {PATH}")
