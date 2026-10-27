"""TOML validity gate (audit finding F-T1 / gate G-T3, 2026-10-28).

Every tracked ``*.toml`` file must parse with the Python stdlib reference
parser ``tomllib``. This tier did not exist anywhere in the 8-tier verify
chain, the contract-parity byte-hygiene guard (mirrored contract files
only), or ruff itself (ruff silently strips a leading UTF-8 BOM) — which is
exactly how ``ruff.toml`` landed with a BOM (blob from #1465 lineage) and
stayed unparseable by stdlib tooling while every ruff-based check stayed
green. The gate closes that parser-tolerance split-brain: a config file is
only "valid" when the stdlib parser of record accepts it.

Design notes:
- stdlib-only, offline, no fixture files: walks ``git ls-files '*.toml'``
  so the gate automatically covers future TOML files.
- BOM gets an explicit, actionable assertion (tomllib's own error for a
  BOM — "Invalid statement (at line 1, column 1)" — names neither the
  cause nor the cure, which is how this defect survived landing).
- Shrink-only spirit of the ratchet family: any new tracked TOML is
  automatically covered; a file can only leave the gate by leaving the
  tree (or being renamed), never by allowlisting.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"


def _tracked_toml_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.toml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(REPO_ROOT / line for line in out.splitlines() if line.strip())


def test_repo_tracks_at_least_one_toml() -> None:
    files = _tracked_toml_files()
    assert files, "git ls-files '*.toml' returned nothing — gate broken?"
    assert any(p.name == "ruff.toml" for p in files), (
        "root ruff.toml missing from git ls-files — F-T1 regression watch lost its target"
    )


def test_every_tracked_toml_parses_with_stdlib_tomllib() -> None:
    failures: list[str] = []
    for path in _tracked_toml_files():
        raw = path.read_bytes()
        if raw.startswith(BOM):
            failures.append(
                f"{path.relative_to(REPO_ROOT)}: UTF-8 BOM present — strip the "
                "leading 3 bytes (EF BB BF); stdlib tomllib (and several other "
                "TOML consumers) reject BOM'd TOML outright"
            )
            continue
        try:
            tomllib.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            failures.append(
                f"{path.relative_to(REPO_ROOT)}: tomllib cannot parse ({exc})"
            )
    assert not failures, "TOML validity gate failures:\n" + "\n".join(failures)
