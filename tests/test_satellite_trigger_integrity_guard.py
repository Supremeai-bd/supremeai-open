#!/usr/bin/env python3
"""Hermetic tests for scripts/ci/satellite_trigger_integrity_guard.py (#3665).

Pins the push-branches census verdict matrix on inline workflow fixtures —
zero filesystem, zero network: the guard exists so a satellite workflow's
on.push filter can never silently drop `main` again.
"""

from scripts.ci.satellite_trigger_integrity_guard import (
    CLOBBERED,
    INTACT,
    UNFILTERED,
    census_file,
    classify_branches,
    extract_push_branch_values,
)

LIST_MAIN = """\
on:
  push:
    branches: [main]
  pull_request:
"""

LIST_CLOBBERED = """\
on:
  push:
    branches: [develop]
"""

BLOCK_MAIN = """\
on:
  push:
    branches:
      - main
      - release/*
"""

NO_FILTER = """\
on:
  push:
  workflow_dispatch:
"""

NO_PUSH = """\
on:
  pull_request:
    branches: [main]
"""


def test_extract_list_filter():
    assert extract_push_branch_values(LIST_MAIN) == ["main"]
    assert extract_push_branch_values(LIST_CLOBBERED) == ["develop"]


def test_extract_block_filter():
    assert extract_push_branch_values(BLOCK_MAIN) == ["main", "release/*"]


def test_extract_unfiltered_and_absent():
    assert extract_push_branch_values(NO_FILTER) == []
    assert extract_push_branch_values(NO_PUSH) is None
    assert extract_push_branch_values("") is None


def test_classify_matrix():
    assert classify_branches(["main"]) == INTACT
    assert classify_branches(["main", "release/*"]) == INTACT
    assert classify_branches(["develop"]) == CLOBBERED
    assert classify_branches([]) == UNFILTERED
    assert classify_branches(None) == UNFILTERED


def test_census_file_rows():
    assert census_file(LIST_MAIN) == {"push_branches": ["main"], "verdict": INTACT}
    assert census_file(LIST_CLOBBERED) == {"push_branches": ["develop"], "verdict": CLOBBERED}
    assert census_file(NO_FILTER) == {"push_branches": [], "verdict": UNFILTERED}
