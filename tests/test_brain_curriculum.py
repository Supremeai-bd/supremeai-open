"""tests/test_brain_curriculum.py — verification for curriculum conversion.

History: the original version pinned `scripts/brain/…` and the proprietary
`knowledge/sonet.json` input. #1935 landed the scripts at the
boundary-guard-sanctioned path `scripts/knowledge/` (the constitutional
boundary guard rejected `scripts/brain/`) and deliberately kept the
proprietary curriculum OUT of the public tree. Result: this test was doubly
unrunnable on clean main (missing script path AND missing input fixture) and
redded the suite. Superior replacement (#1908 red-main precedent): pin the
sanctioned path and generate a hermetic synthetic curriculum so the REAL
converter/augmenter scripts are exercised end-to-end with zero proprietary
surface and zero repo-tree side effects (outputs live in tmp_path).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONVERTER = REPO_ROOT / "scripts" / "knowledge" / "convert_curriculum_to_jsonl.py"
AUGMENTER = REPO_ROOT / "scripts" / "knowledge" / "augment_curriculum_data.py"


def _synthetic_curriculum(path: Path) -> Path:
    """Minimal schema-true sonet.json stand-in (phases > skills > examples)."""
    curriculum = {
        "phases": [
            {
                "phase": 1,
                "title": "Phase One — Greetings & Intents",
                "skills": [
                    {
                        "skill": "greeting",
                        "examples": [
                            {"input": "hello bhai", "normalized": "hello",
                             "intent": "greet", "urgency": "low", "needs_clarification": False},
                            {"input": "hi, ki khobor?", "normalized": "hi what's up",
                             "intent": "greet", "urgency": "low", "needs_clarification": False},
                            {"input": "assalamualaikum", "normalized": "greetings",
                             "intent": "greet", "urgency": "low", "needs_clarification": False},
                        ],
                    },
                    {
                        "name": "task_status",
                        "lessons": [
                            {"input": "amar task koi?", "normalized": "where is my task",
                             "intent": "status_query", "urgency": "medium", "needs_clarification": False},
                            {"input": "task done hoyeche?", "normalized": "is the task done",
                             "intent": "status_query", "urgency": "medium", "needs_clarification": False},
                            {"input": "update dao task e", "normalized": "give task update",
                             "intent": "status_query", "urgency": "high", "needs_clarification": False},
                        ],
                    },
                ],
            },
            {
                "phase": 2,
                "title": "Phase Two — Multi-intent",
                "skills": [
                    {
                        "skill": "deploy_and_report",
                        "examples": [
                            {"input": "deploy koro ar report dao", "normalized": "deploy and report",
                             "intent": "deploy+report", "urgency": "high", "needs_clarification": False},
                        ],
                    },
                ],
            },
        ]
    }
    path.write_text(json.dumps(curriculum, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def test_converter_produces_valid_jsonl(tmp_path: Path):
    sonet = _synthetic_curriculum(tmp_path / "sonet.json")
    out_dir = tmp_path / "brain_test"
    subprocess.run(
        [sys.executable, str(CONVERTER), "--input", str(sonet), "--output-dir", str(out_dir)],
        cwd=REPO_ROOT,
        check=True,
    )
    train = out_dir / "train.jsonl"
    assert train.exists(), f"converter produced no train.jsonl in {out_dir}"
    rows = [json.loads(line) for line in train.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "train.jsonl has zero rows"
    for row in rows:
        assert "messages" in row
        assert len(row["messages"]) == 3
        assert row["messages"][0]["role"] == "system"


def test_augmented_dataset_size(tmp_path: Path):
    sonet = _synthetic_curriculum(tmp_path / "sonet.json")
    out_dir = tmp_path / "brain_aug_test"
    subprocess.run(
        [sys.executable, str(AUGMENTER), "--input", str(sonet), "--output-dir", str(out_dir), "--per-skill", "5"],
        cwd=REPO_ROOT,
        check=True,
    )
    all_rows = (out_dir / "all.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(all_rows) >= 7  # at least the original 7-example count
    for line in all_rows:
        row = json.loads(line)
        assert len(row["messages"]) == 3
