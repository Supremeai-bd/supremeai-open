"""Tests for scripts/ci/no_versioned_duplicate_files.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "no_versioned_duplicate_files.py"


def test_no_versioned_duplicate_files_passes():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"Script failed: {proc.stdout}\n{proc.stderr}"
    assert "OK:" in proc.stdout

