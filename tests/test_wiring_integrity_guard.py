#!/usr/bin/env python3
"""Hermetic tests for scripts/ci/wiring_integrity_guard.py (#3665).

Pins the roster AST extraction contract — the wired-but-absent class guard
(wiring #3268 merged while carrier PR #3257 still sat in the gate): every
structural failure must be reported, never silently skipped.
"""

from pathlib import Path

from scripts.ci.wiring_integrity_guard import _extract_scripts_from_source, check_tree

GOOD = '''\
GUARDS = [
    ["python", "scripts/ci/alpha_guard.py", "--check"],
    ["bash", "scripts/ci/beta.sh"],
]
'''

NO_GUARDS = 'GUARDZ = ["python", "scripts/ci/alpha_guard.py"]\n'

NON_LIST_ENTRY = 'GUARDS = ["python", "scripts/ci/alpha_guard.py"]\n'  # bare strings, not lists

SYNTAX_ERR = "GUARDS = [\n"


def test_extract_scripts_from_good_roster():
    scripts, errors = _extract_scripts_from_source(GOOD)
    assert scripts == ["scripts/ci/alpha_guard.py", "scripts/ci/beta.sh"]
    assert errors == []


def test_extract_flags_missing_guards_assignment():
    scripts, errors = _extract_scripts_from_source(NO_GUARDS)
    assert scripts == []
    assert any("no module-level GUARDS" in e for e in errors)


def test_extract_flags_syntax_error_fail_closed():
    scripts, errors = _extract_scripts_from_source(SYNTAX_ERR)
    assert scripts == []
    assert any("not parseable" in e for e in errors)


def test_extract_ignores_flags_and_bare_names():
    src = 'GUARDS = [["python", "-m", "pytest", "scripts/ci/g.py", "-x"]]\n'
    scripts, errors = _extract_scripts_from_source(src)
    assert scripts == ["scripts/ci/g.py"]
    assert errors == []


def test_check_tree_reports_missing_scripts(tmp_path: Path):
    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    (tmp_path / "scripts" / "ci" / "alpha_guard.py").write_text("# ok\n")
    missing, errors = check_tree(tmp_path, source=GOOD)
    assert errors == []
    assert missing == ["scripts/ci/beta.sh"]  # beta.sh absent on disk

    (tmp_path / "scripts" / "ci" / "beta.sh").write_text("#!/usr/bin/env bash\n")
    missing, errors = check_tree(tmp_path, source=GOOD)
    assert missing == [] and errors == []


def test_check_tree_missing_roster_file():
    missing, errors = check_tree(Path("/nonexistent-root-for-3665"), source=None)
    assert missing == []
    assert any("roster not found" in e for e in errors)
