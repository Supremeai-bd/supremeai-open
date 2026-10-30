#!/usr/bin/env python3
"""Renamed to tests/test_tower_read_file_artifact_probe.py (#3665).

The parity guard pins test file names to module stems: the probe module is
tower_read_file_artifact_probe.py, so the full 12-case hermetic suite now
lives at test_tower_read_file_artifact_probe.py. This stub keeps the old
name a live, honest smoke (no duplicated cases): it re-runs the module's
own self-test so any suite still collecting this path stays green.
"""

from scripts.ci.tower_read_file_artifact_probe import run_self_test


def test_module_self_test_smoke():
    assert run_self_test() == 0
