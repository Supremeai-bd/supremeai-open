"""
tests/test_core_gateway_parity.py — Unit test for Core-Gateway Parity Guard (#761).
"""

from pathlib import Path
from scripts.ci.core_gateway_parity_guard import REPO_ROOT, check_parity, run_self_test


def test_core_gateway_parity_zero_divergence():
    scanned, violations = check_parity(REPO_ROOT)
    assert scanned >= 30, f"Expected at least 30 shared files to be scanned, got {scanned}"
    assert violations == [], f"Detected core-gateway divergence: {violations}"


def test_core_gateway_parity_self_test():
    assert run_self_test() == 0
