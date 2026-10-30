#!/usr/bin/env python3
"""Hermetic tests for scripts/ci/workflow_hardening_census_guard.py (#3665).

Pins the hardening census + four-quadrant verdict on inline workflow YAML —
zero filesystem, zero network: sha-pinning, persist-credentials and template
injection are the countable classes, and classify() must stay fail-closed.
"""

from scripts.ci.workflow_hardening_census_guard import (
    INSUFFICIENT_EVIDENCE,
    REMEDIATED,
    RESIDUAL,
    census_text,
    classify,
)

HARDENED = """\
jobs:
  build:
    steps:
      - uses: actions/checkout@0ad4b8fadaa221de15dcec353f45205ec38ea70b  # v4
        persist-credentials: false
      - uses: ./ ./.github/actions/local-step
      - run: echo "${{ github.sha }}"
"""

RESIDUAL_WF = """\
jobs:
  build:
    steps:
      - uses: actions/checkout@v4
      - run: echo "branch=${{ github.head_ref }}"
"""

EMPTY = """\
jobs:
  build:
    steps:
      - run: echo nothing to census
"""


def test_census_text_counts():
    c = census_text(HARDENED)
    assert c["uses_total"] == 2
    assert c["sha_pinned"] == 1
    assert c["local_actions"] == 1
    assert c["tag_pinned"] == 0
    assert c["checkout_sites"] == 1
    assert c["persist_false"] == 1
    assert c["template_injection"] == 0  # github.sha is not an injection token


def test_census_text_flags_template_injection():
    c = census_text(RESIDUAL_WF)
    assert c["template_injection"] == 1
    assert c["sha_pinned"] == 0
    assert c["tag_pinned"] == 1


def test_classify_remediated():
    profile = {"uses_total": 2, "sha_pinned": 1, "local_actions": 1,
               "checkout_sites": 1, "persist_false": 1, "template_injection": 0}
    assert classify(profile, surface_files=1) == (REMEDIATED, 0)


def test_classify_residual_on_unpinned_or_injection():
    residual_profile = {"uses_total": 1, "sha_pinned": 0, "local_actions": 0,
                        "checkout_sites": 1, "persist_false": 0, "template_injection": 1}
    assert classify(residual_profile, surface_files=1) == (RESIDUAL, 2)
    unpinned_only = {"uses_total": 1, "sha_pinned": 0, "local_actions": 0,
                     "checkout_sites": 0, "persist_false": 0, "template_injection": 0}
    assert classify(unpinned_only, surface_files=1) == (RESIDUAL, 2)


def test_classify_insufficient_evidence_fail_closed():
    assert classify({"uses_total": 0, "sha_pinned": 0, "local_actions": 0,
                     "checkout_sites": 0, "persist_false": 0,
                     "template_injection": 0}, surface_files=0) == (INSUFFICIENT_EVIDENCE, 2)
