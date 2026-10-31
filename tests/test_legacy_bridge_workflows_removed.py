from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY = ["auto-bridge-order.yml", "merge-gate.yml"]


def test_legacy_bridge_workflows_removed():
    wf = REPO_ROOT / ".github" / "workflows"
    for name in LEGACY:
        assert not (wf / name).exists(), f"legacy workflow must stay removed: {name}"
