#!/usr/bin/env python3
"""Convert the Banglish/Bangla intent curriculum (sonet.json) into JSONL datasets.

Usage:
    python scripts/knowledge/convert_curriculum_to_jsonl.py \
        --input knowledge/sonet.json \
        --output-dir data/brain \
        --format sharegpt

Produces train.jsonl and val.jsonl (80/20 by default) plus a combined dataset.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Iterable

SYSTEM_PROMPT = (
    "You are SupremeAI Tiny Core Brain. Analyze user inputs for phonetic mistakes, "
    "missing context, emotional urgency, and multi-intents before deciding whether "
    "to act or ask for clarification."
)


def load_curriculum(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def iter_examples(curriculum: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for phase in curriculum.get("phases", []):
        phase_no = phase.get("phase")
        phase_title = phase.get("title")
        for skill in phase.get("skills", []):
            skill_name = skill.get("skill") or skill.get("name")
            for example in skill.get("examples", skill.get("lessons", [])):
                record = dict(example)
                record.setdefault("phase", phase_no)
                record.setdefault("phase_title", phase_title)
                record.setdefault("skill", skill_name)
                yield record


def to_sharegpt(example: dict[str, Any]) -> dict[str, Any]:
    assistant_payload = {
        "normalized_text": example.get("normalized", example.get("normalized_text", "")),
        "confidence": example.get("confidence", 0.5),
        "intents": example.get("intent", example.get("intents", "unknown")),
        "urgency": example.get("urgency", "low"),
        "needs_clarification": bool(example.get("needs_clarification", False)),
        "skill": example.get("skill"),
        "phase": example.get("phase"),
    }
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": str(example.get("input", ""))},
            {"role": "assistant", "content": json.dumps(assistant_payload, ensure_ascii=False)},
        ]
    }


def to_alpaca(example: dict[str, Any]) -> dict[str, Any]:
    assistant_payload = {
        "normalized_text": example.get("normalized", example.get("normalized_text", "")),
        "confidence": example.get("confidence", 0.5),
        "intents": example.get("intent", example.get("intents", "unknown")),
        "urgency": example.get("urgency", "low"),
        "needs_clarification": bool(example.get("needs_clarification", False)),
    }
    return {
        "instruction": SYSTEM_PROMPT,
        "input": str(example.get("input", "")),
        "output": json.dumps(assistant_payload, ensure_ascii=False),
    }


def convert(curriculum: dict[str, Any], fmt: str) -> list[dict[str, Any]]:
    converter = to_sharegpt if fmt == "sharegpt" else to_alpaca
    return [converter(ex) for ex in iter_examples(curriculum)]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert sonet curriculum to JSONL")
    parser.add_argument("--input", default="knowledge/sonet.json", help="Path to sonet.json")
    parser.add_argument("--output-dir", default="data/brain", help="Output directory")
    parser.add_argument("--format", choices=["sharegpt", "alpaca"], default="sharegpt")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        # Fallback search common locations
        for candidate in ("knowledge/sonet.json", "core/knowledge/sonet.json", "data/sonet.json"):
            if Path(candidate).exists():
                input_path = Path(candidate)
                break

    curriculum = load_curriculum(input_path)
    rows = convert(curriculum, args.format)
    random.Random(args.seed).shuffle(rows)  # nosec B311 — seeded determinism is a data-gen feature (reproducible splits), not crypto (#2081 audit)

    split = int(len(rows) * (1 - args.val_ratio))
    train_rows = rows[:split]
    val_rows = rows[split:]

    out_dir = Path(args.output_dir)
    write_jsonl(out_dir / "train.jsonl", train_rows)
    write_jsonl(out_dir / "val.jsonl", val_rows)
    write_jsonl(out_dir / "all.jsonl", rows)

    print(f"Converted {len(rows)} examples -> {len(train_rows)} train / {len(val_rows)} val")


if __name__ == "__main__":
    main()
