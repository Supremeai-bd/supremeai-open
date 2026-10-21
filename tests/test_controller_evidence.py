#!/usr/bin/env python3
"""Offline tests for controller-side evidence verifier."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import controller_evidence_verify as cev


class TestProtected(unittest.TestCase):
    def test_protected_paths(self):
        self.assertTrue(cev.is_protected(".env"))
        self.assertTrue(cev.is_protected("secrets/x"))
        self.assertTrue(cev.is_protected("foo/credential.txt"))
        self.assertTrue(cev.is_protected("a.pem"))
        self.assertFalse(cev.is_protected("src/main.py"))


class TestScopeViolations(unittest.TestCase):
    def test_in_scope_ok(self):
        self.assertEqual(cev.scope_violations(["src/a.py"], ["src/a.py"]), [])

    def test_out_of_scope(self):
        v = cev.scope_violations(["src/a.py", "other/b.py"], ["src/a.py"])
        self.assertIn("out-of-scope:other/b.py", v)

    def test_protected_always_violation(self):
        v = cev.scope_violations([".env"], [])
        self.assertTrue(any(x.startswith("protected:") for x in v))

    def test_empty_scope_means_no_scope_check(self):
        # when scope empty, any non-protected file is allowed
        self.assertEqual(cev.scope_violations(["src/a.py"], []), [])


class TestDigests(unittest.TestCase):
    def test_matching_digest_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "a.txt"
            f.write_text("hello", encoding="utf-8")
            digest = cev.sha256_file(f)
            mism = cev.verify_digests(root, ["a.txt"], {"a.txt": digest})
            self.assertEqual(mism, [])

    def test_mismatch_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "a.txt"
            f.write_text("hello", encoding="utf-8")
            mism = cev.verify_digests(root, ["a.txt"], {"a.txt": "sha256:" + "0" * 64})
            self.assertTrue(any(x.startswith("digest-mismatch:") for x in mism))

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mism = cev.verify_digests(root, ["nope.txt"], {})
            self.assertTrue(any(x.startswith("missing:") for x in mism))


class TestChangedFilesFailClosed(unittest.TestCase):
    def test_bad_sha_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            # not a git repo -> None
            self.assertIsNone(cev.changed_files("aaa", "bbb", Path(td)))


class TestVerify(unittest.TestCase):
    def test_fail_closed_on_bad_shas(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            res = cev.verify("bad", "bad2", [], {}, [], root)
            self.assertFalse(res["passed"])
            self.assertIn("git-diff-failed", res["errors"])


if __name__ == "__main__":
    unittest.main()
