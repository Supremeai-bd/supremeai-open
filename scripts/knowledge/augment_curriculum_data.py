#!/usr/bin/env python3
"""Synthetic data augmentor for the Tiny Core Brain curriculum.

Expands a sonet.json curriculum into >= 500 samples per skill using deterministic
offline templates (no network/LLM dependency). Writes train/val JSONL splits.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import json
import random
from pathlib import Path
from typing import Any

from convert_curriculum_to_jsonl import iter_examples, to_sharegpt

TEMPLATES = [
    "{input}",
    "{input} please",
    "bhai {input}",
    "{input} to",
    "ami chai {input}",
    "ekhon {input}",
    "joldi {input}",
]


def augment_example(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    example = dict(base)
    text = str(base.get("input", ""))
    template = rng.choice(TEMPLATES)
    example["input"] = template.format(input=text).strip()
    # slight confidence jitter while staying in [0,1]
    conf = float(base.get("confidence", 0.5))
    example["confidence"] = round(min(1.0, max(0.0, conf + rng.uniform(-0.05, 0.05))), 3)
    return example


def build_dataset(curriculum: dict[str, Any], per_skill: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)  # nosec B311 — seeded determinism is a data-gen feature (reproducible curriculum builds), not crypto (#2081 audit)
    rows: list[dict[str, Any]] = []
    for base in iter_examples(curriculum):
        rows.append(to_sharegpt(base))
        for _ in range(max(0, per_skill - 1)):
            synth = augment_example(base, rng)
            rows.append(to_sharegpt(synth))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Augment curriculum into 500+ samples/skill")
    parser.add_argument("--input", default="knowledge/sonet.json")
    parser.add_argument("--output-dir", default="data/brain/augmented")
    parser.add_argument("--per-skill", type=int, default=500)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        for candidate in ("knowledge/sonet.json", "core/knowledge/sonet.json", "data/sonet.json"):
            if Path(candidate).exists():
                input_path = Path(candidate)
                break

    with input_path.open("r", encoding="utf-8") as fh:
        curriculum = json.load(fh)

    rows = build_dataset(curriculum, args.per_skill, args.seed)
    rng = random.Random(args.seed)  # nosec B311 — seeded determinism is a data-gen feature (reproducible curriculum builds), not crypto (#2081 audit)
    rng.shuffle(rows)
    split = int(len(rows) * (1 - args.val_ratio))
    train_rows, val_rows = rows[:split], rows[split:]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("train.jsonl", train_rows), ("val.jsonl", val_rows), ("all.jsonl", rows)):
        with (out_dir / name).open("w", encoding="utf-8") as fh:
            for row in data:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Augmented {len(rows)} samples -> {len(train_rows)} train / {len(val_rows)} val")


if __name__ == "__main__":
    main()
