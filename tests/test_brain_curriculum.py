"""tests/test_brain_curriculum.py — verification for curriculum conversion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_converter_produces_valid_jsonl():
    subprocess.run(
        [sys.executable, "scripts/brain/convert_curriculum_to_jsonl.py", "--input", "knowledge/sonet.json", "--output-dir", str(REPO_ROOT / "data" / "brain_test")],
        cwd=REPO_ROOT,
        check=True,
    )
    train = REPO_ROOT / "data" / "brain_test" / "train.jsonl"
    assert train.exists()
    rows = [json.loads(line) for line in train.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    for row in rows:
        assert "messages" in row
        assert len(row["messages"]) == 3
        assert row["messages"][0]["role"] == "system"


def test_augmented_dataset_size():
    subprocess.run(
        [sys.executable, "scripts/brain/augment_curriculum_data.py", "--input", "knowledge/sonet.json", "--output-dir", str(REPO_ROOT / "data" / "brain_aug_test"), "--per-skill", "5"],
        cwd=REPO_ROOT,
        check=True,
    )
    all_rows = (REPO_ROOT / "data" / "brain_aug_test" / "all.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(all_rows) >= 19  # at least original count
