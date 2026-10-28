"""tests/test_brain_curriculum.py — verification for curriculum conversion.

The converters live in ``scripts/knowledge/`` and read a ``sonet.json``-shaped
curriculum. ``knowledge/sonet.json`` is not committed, so these tests run
against a small committed fixture instead of a path that never existed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "brain_curriculum.json"
CONVERTER = REPO_ROOT / "scripts" / "knowledge" / "convert_curriculum_to_jsonl.py"
AUGMENTER = REPO_ROOT / "scripts" / "knowledge" / "augment_curriculum_data.py"

# The fixture's phases hold 2 + 2 + 2 examples across three skills.
FIXTURE_EXAMPLES = 6


def run_script(script: Path, output_dir: Path, *extra: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--input",
            str(FIXTURE),
            "--output-dir",
            str(output_dir),
            *extra,
        ],
        cwd=REPO_ROOT,
        check=True,
    )


def test_converter_produces_valid_jsonl(tmp_path):
    out = tmp_path / "converted"
    run_script(CONVERTER, out)

    train = out / "train.jsonl"
    assert train.exists()
    rows = [
        json.loads(line)
        for line in train.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert (out / "all.jsonl").exists()
    for row in rows:
        assert "messages" in row
        assert len(row["messages"]) == 3
        assert row["messages"][0]["role"] == "system"


def test_augmented_dataset_size(tmp_path):
    out = tmp_path / "augmented"
    run_script(AUGMENTER, out, "--per-skill", "5")

    all_rows = (out / "all.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(all_rows) == FIXTURE_EXAMPLES * 5  # every example, five times
