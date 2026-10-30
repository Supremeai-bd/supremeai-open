"""Born-red tests for the #3527 implicit-persist-true census class.

The checkout action's `persist-credentials` input DEFAULTS TO TRUE: a site
with no explicit key persists the job GITHUB_TOKEN into the runner git config
exactly like an explicit true. #3527 (audit, GLM Agent 08) decoded the
monorepo's ops-maintenance.yml: 23 checkout sites, only 5 explicit-false,
18 implicit-true — and asked (remedy 2) for the class to be machine-tracked
with a frozen baseline. These tests pin the window classifier, the
per-census invariant, and the shrink-only baseline tripwire.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / "scripts" / "ci" / "workflow_hardening_census_guard.py"
BASELINE_PATH = REPO_ROOT / "scripts" / "ci" / "workflow_hardening_baseline.json"

spec = importlib.util.spec_from_file_location("workflow_hardening_census_guard", GUARD_PATH)
whg = importlib.util.module_from_spec(spec)
sys.modules.setdefault("workflow_hardening_census_guard", whg)
spec.loader.exec_module(whg)


HARDENED = """
jobs:
  build:
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v5
        with:
          persist-credentials: false
"""


def test_implicit_site_is_counted_not_silent():
    """A checkout with no persist-credentials key lands in implicit_persist_true."""
    text = """
jobs:
  maintain:
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
"""
    p = whg.census_text(text)
    assert p["checkout_sites"] == 1
    assert p["implicit_persist_true"] == 1
    assert p["checkout_explicit_false"] == 0
    assert p["persist_explicit_true"] == 0


def test_explicit_true_is_its_own_class():
    """persist-credentials: true must not be silently folded into implicit."""
    text = """
jobs:
  maintain:
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: true
"""
    p = whg.census_text(text)
    assert p["persist_explicit_true"] == 1
    assert p["implicit_persist_true"] == 0


def test_window_boundary_no_sibling_leak():
    """A sibling step at the same indent must not poison the checkout window."""
    text = """
jobs:
  maintain:
    steps:
      - uses: actions/checkout@v5
      - run: echo 'persist-credentials: false'
"""
    p = whg.census_text(text)
    assert p["checkout_explicit_false"] == 0, "sibling run text leaked into checkout window"
    assert p["implicit_persist_true"] == 1


def test_commented_key_does_not_count():
    """A commented-out persist-credentials line is not an explicit setting."""
    text = """
jobs:
  maintain:
    steps:
      - uses: actions/checkout@v5
        # persist-credentials: false
"""
    p = whg.census_text(text)
    assert p["implicit_persist_true"] == 1
    assert p["checkout_explicit_false"] == 0


def test_flow_style_with_block_counts():
    """`with: { persist-credentials: false }` on one line counts as explicit."""
    text = """
jobs:
  build:
    steps:
      - uses: actions/checkout@v5
        with: { persist-credentials: false }
"""
    p = whg.census_text(text)
    assert p["checkout_explicit_false"] == 1
    assert p["implicit_persist_true"] == 0


def test_persist_invariant_holds_on_mixed_surface():
    """checkout_sites == explicit_false + explicit_true + implicit (exactly once)."""
    text = """
jobs:
  a:
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false
  b:
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: true
  c:
    steps:
      - uses: actions/checkout@v5
"""
    p = whg.census_text(text)
    assert p["checkout_sites"] == 3
    assert p["checkout_sites"] == p["checkout_explicit_false"] + p["persist_explicit_true"] + p["implicit_persist_true"]
    assert (p["checkout_explicit_false"], p["persist_explicit_true"], p["implicit_persist_true"]) == (1, 1, 1)


def test_legacy_profile_keys_unchanged():
    """The seven pre-#3527 keys keep their exact semantics (no verdict flips)."""
    p = whg.census_text(HARDENED)
    assert p["uses_total"] == 1
    assert p["sha_pinned"] == 1
    assert p["tag_pinned"] == 0
    assert p["checkout_sites"] == 1
    assert p["persist_false"] == 1
    assert p["template_injection"] == 0
    assert whg.classify(p, 1) == (whg.REMEDIATED, 0)


def test_baseline_tripwire_drifts_on_implicit_increase():
    """One NEW unpersisted checkout site must drift (fail-loud direction)."""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    drifted = {**baseline, "implicit_persist_true": baseline["implicit_persist_true"] + 1}
    diff = whg.baseline_drift(baseline, drifted)
    assert "implicit_persist_true" in diff
    assert diff["implicit_persist_true"] == (baseline["implicit_persist_true"], baseline["implicit_persist_true"] + 1)


def test_baseline_tripwire_quiet_on_exact_match():
    """The frozen baseline must match a re-census of the unchanged surface."""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    profile, files = whg.census_surface(REPO_ROOT)
    assert len(files) >= 1
    assert whg.baseline_drift(baseline, profile) == {}, "live surface drifted from the frozen baseline — re-baseline with dated evidence in the same PR"


def test_baseline_carries_all_profile_keys():
    """A baseline missing any profile key would drift forever (config defect)."""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    missing = [k for k in whg.PROFILE_KEYS if k not in baseline]
    assert missing == [], f"baseline lacks profile keys: {missing}"


def test_classify_treats_implicit_as_unpersisted():
    """classify() must not hand REMEDIATED to a surface with implicit sites."""
    p = whg.census_text(
        """
jobs:
  build:
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
"""
    )
    # sha pins ok, no injection — but the implicit site keeps persist_ok False.
    assert p["implicit_persist_true"] == 1
    assert whg.classify(p, 1) == (whg.RESIDUAL, 2)
