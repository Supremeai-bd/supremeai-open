"""tests/test_sdk_foundation.py — 3-tier verification (tier 3, unit).

Imports and executes the SupremeAI multi-language client SDK test battery
at sdk/tests/test_py_client.py against an in-process threaded mock gateway.
Covers: bearer signing, run submission, transient retry recovery (HTTP 503),
terminal GatewayError surfacing, SSE chunk re-assembly, and async iterator.
"""

from __future__ import annotations

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "sdk", "python"))

from sdk.tests.test_py_client import (
    MockGateway,
    MockGatewayServer,
    TestSupremeAISDK,
)

__all__ = ["MockGateway", "MockGatewayServer", "TestSupremeAISDK"]

if __name__ == "__main__":
    unittest.main()
