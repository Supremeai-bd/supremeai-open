"""Zero-Issue Satellite Doctrine enforcement battery (#425).

Offline, stdlib-only, fail-closed with HONEST SKIPS: a check that cannot
run in a given tree (file absent, layout drifted) skips with an explicit
reason instead of failing — the doctrine document itself (T1) is the only
strictly-required artifact because it ships in the same payload.

Run: python3 -m pytest tests/test_zero_issue_doctrine.py -q
Codifies: docs/ZERO_ISSUE_SATELLITE_DOCTRINE.md
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "ZERO_ISSUE_SATELLITE_DOCTRINE.md"
LANDING_PATH = REPO_ROOT / ".github" / "workflows" / "landing.yml"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
LOOP_PATH = REPO_ROOT / "scripts" / "agents" / "continuous_agent_loop.py"

HUB = "Supremeai-bd/supremeai-open"

# The 12 satellite repositories a landed patch may stream to (landing.yml
# TARGET_REPOS entries). repo:monorepo is the always-sync central target;
# repo:open is the hub itself (never a patch destination); repo:archive is
# a historical stream label, not a task target.
SATELLITE_REPOS = [
    "Supremeai-bd/supremeai-studio",
    "Supremeai-bd/supremeai-api",
    "Supremeai-bd/supremeai-core",
    "Supremeai-bd/supremeai-command",
    "Supremeai-bd/supremeai-skills",
    "Supremeai-bd/supremeai-vscode",
    "Supremeai-bd/supremeai-agents",
    "Supremeai-bd/supremeai-browser",
    "Supremeai-bd/supremeai-sdk",
    "Supremeai-bd/supremeai-mcp-control-plane",
    "Supremeai-bd/supremeai-infrastructure",
    "Supremeai-bd/supremeai",  # central monorepo (always-sync)
]

CANONICAL_LABELS = [
    "repo:monorepo", "repo:studio", "repo:core", "repo:api", "repo:mcp",
    "repo:agents", "repo:skills", "repo:command", "repo:browser",
    "repo:vscode", "repo:infra", "repo:sdk", "repo:open",
]


def _skip_if_missing(path: Path, what: str):
    if not path.is_file():
        pytest.skip(f"{what} not present in this tree ({path.name}); check is target-layout dependent")


# ---------------------------------------------------------------------------
# T1 — doctrine document is present and complete (strict: ships in payload)
# ---------------------------------------------------------------------------

def test_t1_doctrine_doc_exists_with_label_map_and_invariants():
    assert DOC_PATH.is_file(), f"doctrine doc missing: {DOC_PATH}"
    raw = DOC_PATH.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", raw)  # whitespace-tolerant clause matching
    for label in CANONICAL_LABELS:
        assert label in text, f"doctrine doc lacks canonical label {label}"
    for marker in (
        "SOLE canonical issue and task tracking hub",
        "Zero-Issue Satellite Invariant",
        "Intake Zero-Residue Guarantee",
        "Cross-Repo CI Failure Telemetry",
        "Architectural Blueprint",
    ):
        assert marker in text, f"doctrine doc lacks invariant clause: {marker}"
    # The satellite lockdown snippet must be embedded verbatim for Phase 1.
    assert "blank_issues_enabled: false" in text
    assert "issues/new/choose" in text


# ---------------------------------------------------------------------------
# T2 — landing.yml dispatch table streams to all 12 satellites
# ---------------------------------------------------------------------------

def test_t2_landing_routes_cover_all_satellites():
    _skip_if_missing(LANDING_PATH, "landing.yml")
    text = LANDING_PATH.read_text(encoding="utf-8")
    missing = [r for r in SATELLITE_REPOS if f'TARGET_REPOS+=("{r}")' not in text]
    assert not missing, f"landing.yml lacks streaming routes for: {missing}"
    # Central monorepo is the always-sync target.
    assert "Central monorepo Supremeai-bd/supremeai always receives synchronization" in text


# ---------------------------------------------------------------------------
# T3 — agent loop declares the hub as the sole issue source
# ---------------------------------------------------------------------------

def _loop_text() -> str:
    _skip_if_missing(LOOP_PATH, "continuous_agent_loop.py")
    return LOOP_PATH.read_text(encoding="utf-8")


def test_t3_loop_upstream_repo_is_the_hub():
    text = _loop_text()
    m = re.search(r'^UPSTREAM_REPO\s*=\s*"([^"]+)"', text, re.M)
    assert m, "loop does not declare UPSTREAM_REPO"
    assert m.group(1) == HUB, f"loop UPSTREAM_REPO drifted from the hub: {m.group(1)}"


# ---------------------------------------------------------------------------
# T4 — AGENTS.md carries the predecessor Ephemeral Transit doctrine
# ---------------------------------------------------------------------------

def test_t4_agents_md_has_ephemeral_transit_section():
    _skip_if_missing(AGENTS_PATH, "AGENTS.md")
    text = AGENTS_PATH.read_text(encoding="utf-8")
    assert "Ephemeral Transit" in text, "AGENTS.md lost the Ephemeral Transit doctrine section"


# ---------------------------------------------------------------------------
# T5 — the loop never queries any non-hub repository for issues
# ---------------------------------------------------------------------------

def test_t5_loop_has_no_satellite_issue_sources():
    text = _loop_text()
    # Every federation repo reference in the loop must be the hub itself.
    # (supremeai-open is the hub; any other Supremeai-bd/supremeai-* literal
    # would be a satellite issue/PR source — forbidden by invariant 1.)
    refs = set(re.findall(r"Supremeai-bd/supremeai[-\w]*", text))
    offenders = sorted(r for r in refs if r not in (HUB, "Supremeai-bd/supremeai"))
    assert not offenders, f"loop references non-hub repositories: {offenders}"
    # And every gh issue/pr invocation must carry an explicit --repo flag.
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r'"gh",\s*"(issue|pr)",\s*"(list|view)"', line):
            window = " ".join(text.splitlines()[i - 1:i + 3])
            assert "--repo" in window, f"gh invocation without --repo near line {i}: {line.strip()}"
