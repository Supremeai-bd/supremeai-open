from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_core_browser_not_present():
    assert not (REPO_ROOT / "core" / "browser").exists(), "core/browser duplicate must not reappear (#1396)"
