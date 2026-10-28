"""tests/test_brain_curriculum.py — verification for curriculum conversion.

Revival of the suite landed by #1928 (dc9e8b9), which had failed 2/2 on every
tree since landing because it invoked `scripts/brain/` (a path that never
existed) with `knowledge/sonet.json` (a file that was never committed) —
invisible to CI, which does not run the full pytest suite (#1952).

Honest-revival contract (#1760 house pattern, option (a)):
- invokes the REAL landed scripts under `scripts/knowledge/` (#1935 layout);
- consumes a REAL committed fixture (`tests/fixtures/brain_curriculum_fixture.json`,
  schema-faithful sonet.json slice) — no fabricated PASS, no skip-on-missing-input;
- asserts deterministic outputs (exact row counts and payload shapes) of the
  converter and the augmentor, end-to-end through their CLIs;
- writes outputs to tempfile dirs — zero worktree pollution (the legacy test
  created untracked `data/brain_test/` dirs; `data/` is not gitignored).

The intended production input `knowledge/sonet.json` remains the data owner's
call (#1952 option (c)); these tests deliberately do not depend on it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CONVERTER = REPO_ROOT / "scripts" / "knowledge" / "convert_curriculum_to_jsonl.py"
AUGMENTOR = REPO_ROOT / "scripts" / "knowledge" / "augment_curriculum_data.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "brain_curriculum_fixture.json"

FIXTURE_INPUTS = sorted(
    ex["input"]
    for phase in json.loads(FIXTURE.read_text(encoding="utf-8"))["phases"]
    for skill in phase["skills"]
    for ex in skill["examples"]
)
N_EXAMPLES = len(FIXTURE_INPUTS)  # 8 in the committed fixture


def _assert_sharegpt_row(row: dict) -> None:
    """Every pipeline row is a sharegpt conversation: system -> user -> assistant payload."""
    assert "messages" in row
    assert len(row["messages"]) == 3
    assert row["messages"][0]["role"] == "system"
    assert row["messages"][1]["role"] == "user"
    assert row["messages"][2]["role"] == "assistant"
    payload = json.loads(row["messages"][2]["content"])
    assert "skill" in payload and "phase" in payload
    assert isinstance(payload["confidence"], (int, float))
    assert 0.0 <= payload["confidence"] <= 1.0


def _run(script: Path, args: list[str]) -> None:
    proc = subprocess.run(
        [sys.executable, str(script.relative_to(REPO_ROOT)), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"{script.name} exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_converter_produces_valid_jsonl():
    with tempfile.TemporaryDirectory(prefix="brain-convert-") as td:
        _run(
            CONVERTER,
            ["--input", str(FIXTURE), "--output-dir", td, "--format", "sharegpt"],
        )
        out = Path(td)
        train = out / "train.jsonl"
        val = out / "val.jsonl"
        all_rows_path = out / "all.jsonl"
        assert train.exists() and val.exists() and all_rows_path.exists()

        all_rows = [
            json.loads(line)
            for line in all_rows_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        train_rows = [
            json.loads(line)
            for line in train.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        val_rows = [
            json.loads(line)
            for line in val.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        # Deterministic 80/20 split over the committed fixture (val_ratio 0.2).
        assert len(all_rows) == N_EXAMPLES
        split = int(N_EXAMPLES * 0.8)
        assert len(train_rows) == split
        assert len(val_rows) == N_EXAMPLES - split

        for row in all_rows:
            _assert_sharegpt_row(row)

        # Every fixture example reaches the dataset, with its injected skill/phase
        # metadata (iter_examples setdefault contract) and nothing else.
        user_contents = sorted(row["messages"][1]["content"] for row in all_rows)
        assert user_contents == FIXTURE_INPUTS


def test_converter_alpaca_format():
    """The alpaca branch (to_alpaca) is exported but was never exercised by any test."""
    with tempfile.TemporaryDirectory(prefix="brain-alpaca-") as td:
        _run(
            CONVERTER,
            ["--input", str(FIXTURE), "--output-dir", td, "--format", "alpaca"],
        )
        rows = [
            json.loads(line)
            for line in (Path(td) / "all.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == N_EXAMPLES
        for row in rows:
            assert set(row) == {"instruction", "input", "output"}
            payload = json.loads(row["output"])
            assert "normalized_text" in payload and "intents" in payload


def test_augmented_dataset_size():
    # per-skill 3 x 8 fixture examples = 24 rows, deterministic (seeded templates).
    per_skill = 3
    with tempfile.TemporaryDirectory(prefix="brain-aug-") as td:
        _run(
            AUGMENTOR,
            [
                "--input",
                str(FIXTURE),
                "--output-dir",
                td,
                "--per-skill",
                str(per_skill),
            ],
        )
        all_rows = [
            json.loads(line)
            for line in (Path(td) / "all.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(all_rows) == N_EXAMPLES * per_skill
        for row in all_rows:
            _assert_sharegpt_row(row)

        # Every original example survives augmentation; every synthetic wrap
        # template contains the base text, so each fixture input appears
        # exactly per_skill times across the dataset.
        user_contents = [row["messages"][1]["content"] for row in all_rows]
        for base_input in FIXTURE_INPUTS:
            hits = sum(1 for text in user_contents if base_input in text)
            assert hits == per_skill, f"{base_input!r} appeared {hits}x, want {per_skill}x"
