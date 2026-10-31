#!/usr/bin/env python3
"""Offline tests for service_latency_probe (read-only HTTP probe plane).

Parity companion for scripts/ci/service_latency_probe.py (added by #4377
without its parity test — the test_parity_guard real-repo leg went red at
52218ca). Contract pinned offline: urlopen is patched, no live network;
CLI validation (bad --url) exits before any probing.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import service_latency_probe as slp


class _Resp:
    def __init__(self, status: int = 200):
        self.status = status

    def read(self, n: int = -1) -> bytes:
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestServiceLatencyProbe(unittest.TestCase):
    def test_success_samples_and_percentiles(self):
        with patch.object(slp, "urlopen", lambda *a, **k: _Resp(200)):
            r = slp.probe("ok", "https://unit.test/health", attempts=3, timeout=1.0)
        self.assertEqual(len(r["samples_ms"]), 3)
        self.assertEqual(r["errors"], [])
        for key in ("min_ms", "avg_ms", "p95_ms"):
            self.assertIn(key, r)

    def test_http_500_recorded_as_error(self):
        with patch.object(slp, "urlopen", lambda *a, **k: _Resp(503)):
            r = slp.probe("bad", "https://unit.test/health", attempts=2, timeout=1.0)
        self.assertEqual(r["errors"], ["HTTP 503", "HTTP 503"])
        self.assertEqual(len(r["samples_ms"]), 2)

    def test_transport_error_recorded(self):
        def _boom(*a, **k):
            raise urllib.error.URLError("unit-test down")

        with patch.object(slp, "urlopen", _boom):
            r = slp.probe("down", "https://unit.test/health", attempts=2, timeout=1.0)
        self.assertEqual(r["errors"], ["URLError", "URLError"])
        self.assertEqual(r["samples_ms"], [])

    def test_cli_rejects_malformed_url_offline(self):
        """ap.error fires before any probe — no network, exit != 0."""
        r = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "ci" / "service_latency_probe.py"),
             "--url", "not-a-pair", "--attempts", "1"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--url", r.stderr)


if __name__ == "__main__":
    unittest.main()
