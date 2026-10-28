#!/usr/bin/env python3
"""QLoRA fine-tuning recipe for the SupremeAI Tiny Core Brain.

This script prepares and (optionally) runs a LoRA/QLoRA training job using
Unsloth/PEFT. In environments without GPU/torch it performs a dry-run that
validates the dataset and writes a training manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_manifest(train_path: Path, val_path: Path, base_model: str, r: int, alpha: int) -> dict[str, Any]:
    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path) if val_path.exists() else []
    return {
        "base_model": base_model,
        "lora": {"r": r, "alpha": alpha, "target_modules": TARGET_MODULES},
        "quantization": "4bit",
        "scheduler": "cosine",
        "train_samples": len(train_rows),
        "val_samples": len(val_rows),
        "export": ["gguf:Q4_K_M", "gguf:Q8_0", "onnx"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Tiny Core Brain (QLoRA)")
    parser.add_argument("--train", default="data/brain/train.jsonl")
    parser.add_argument("--val", default="data/brain/val.jsonl")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--r", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--output-dir", default="models/tiny-core-brain")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    train_path = Path(args.train)
    val_path = Path(args.val)
    if not train_path.exists():
        for cand in ("data/brain/train.jsonl", "data/brain/augmented/train.jsonl"):
            if Path(cand).exists():
                train_path = Path(cand)
                val_path = Path(cand).with_name("val.jsonl")
                break

    manifest = build_manifest(train_path, val_path, args.base_model, args.r, args.alpha)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "training_manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    if not args.dry_run:
        try:
            import torch  # type: ignore
            from unsloth import FastLanguageModel  # type: ignore
        except Exception as exc:
            raise SystemExit(f"Training dependencies unavailable: {exc}")
        # Full training left to deployment environment; manifest is the contract.


if __name__ == "__main__":
    main()
