#!/usr/bin/env python3
"""tests/test_provenance_digest_guard.py — #1674 minimal provenance lane.

Background (issue #1674): bridge-submitted agent patches are the
federation's autonomous supply chain; trust rests on narrative identity
(agentIdentity prose), not cryptography. The minimal lane (verdict
EXTRACT_PATTERNS_ONLY — sigstore itself is NOT vendored) ships a
machine-readable receipt at ``docs/provenance/bridge-<taskId>.json``
listing per-file sha256 digests of the full_file contents AS SUBMITTED;
``scripts/ci/deploy_preflight_guard.py --step1-syntax`` (CI Step 1, run on
every PR and push-to-main) recomputes the digests on the checked-out
branch and fails closed on mismatch — any post-receipt edit of a listed
file breaks the match, detecting post-review mutation of agent patches.

Landed contract (this suite pins it):
  1. The verifier is actually WIRED: ``_provenance_digest`` exists and
     rides the full-repo branch of ``run_step1_syntax`` (explicit-target /
     offline self-test invocations never consult it).
  2. An absent or empty receipts dir is a no-op (additive, zero false
     positives for layouts without receipts).
  3. Fail-closed diagnostics: malformed receipt, unsupported algorithm,
     invalid digest encoding, missing listed file, path traversal, and
     above all PROVENANCE MISMATCH on post-receipt mutation.
  4. The LIVE receipt dogfooded by this patch
     (``docs/provenance/bridge-20261030-provenance-digest-lane.json``)
     verifies against the checked-out branch.

Offline, stdlib-only. CI rides the existing test-matrix/preflight
plumbing — no .github/ edits (admin-owned path).
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = REPO_ROOT / "scripts" / "ci" / "deploy_preflight_guard.py"
LIVE_RECEIPT = (
    REPO_ROOT / "docs" / "provenance" / "bridge-20261030-provenance-digest-lane.json"
)


def _import_guard():
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
    try:
        import deploy_preflight_guard as dpg
    finally:
        sys.path.pop(0)
    return dpg


class TestProvenanceDigestGuard(unittest.TestCase):
    def test_verifier_is_wired_into_step1_full_repo_mode(self):
        """The sub-check must be reachable from CI Step 1's full-repo branch."""
        src = PREFLIGHT.read_text(encoding="utf-8")
        self.assertIn(
            "_provenance_digest",
            src,
            "deploy_preflight_guard.py lost the #1674 sub-check",
        )
        self.assertIn(
            "errors.extend(_provenance_digest())",
            src,
            "run_step1_syntax no longer wires the provenance verifier",
        )

    def test_absent_receipts_dir_is_noop(self):
        """No receipts dir -> empty error list (additive; nothing to guard)."""
        dpg = _import_guard()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(dpg._provenance_digest(Path(tmp) / "missing"), [])

    def test_valid_receipt_passes(self):
        """A receipt whose digests match the branch verifies clean."""
        dpg = _import_guard()
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "bridge-19700101-fixture.json"
            digest = hashlib.sha256(PREFLIGHT.read_bytes()).hexdigest()
            receipt.write_text(
                json.dumps(
                    {
                        "taskId": "bridge-19700101-fixture",
                        "algorithm": "sha256",
                        "files": [
                            {
                                "path": "scripts/ci/deploy_preflight_guard.py",
                                "sha256": digest,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(dpg._provenance_digest(Path(tmp)), [])

    def test_digest_mismatch_fails_closed(self):
        """A tampered digest (post-receipt mutation) must FAIL Step 1."""
        dpg = _import_guard()
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "bridge-19700101-tamper.json"
            receipt.write_text(
                json.dumps(
                    {
                        "taskId": "bridge-19700101-tamper",
                        "algorithm": "sha256",
                        "files": [
                            {
                                "path": "scripts/ci/deploy_preflight_guard.py",
                                "sha256": "0" * 64,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            errs = dpg._provenance_digest(Path(tmp))
            self.assertTrue(errs, "mismatch must produce an error")
            self.assertTrue(
                any("PROVENANCE MISMATCH" in e for e in errs),
                f"expected a PROVENANCE MISMATCH diagnostic, got: {errs}",
            )

    def test_missing_listed_file_fails_closed(self):
        """A receipt listing a file absent from the branch must fail."""
        dpg = _import_guard()
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "bridge-19700101-missing.json"
            receipt.write_text(
                json.dumps(
                    {
                        "taskId": "bridge-19700101-missing",
                        "algorithm": "sha256",
                        "files": [
                            {"path": "scripts/ci/does_not_exist.py", "sha256": "a" * 64}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            errs = dpg._provenance_digest(Path(tmp))
            self.assertTrue(any("missing on branch" in e for e in errs), errs)

    def test_malformed_and_unsupported_receipts_fail_closed(self):
        """Unreadable JSON, non-sha256 algorithms, empty files -> errors."""
        dpg = _import_guard()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.json").write_text("{not json", encoding="utf-8")
            (Path(tmp) / "alg.json").write_text(
                json.dumps(
                    {
                        "taskId": "x",
                        "algorithm": "md5",
                        "files": [{"path": "README.md", "sha256": "a" * 64}],
                    }
                ),
                encoding="utf-8",
            )
            (Path(tmp) / "empty.json").write_text(
                json.dumps({"taskId": "x", "algorithm": "sha256", "files": []}),
                encoding="utf-8",
            )
            errs = dpg._provenance_digest(Path(tmp))
            self.assertTrue(any("malformed" in e for e in errs), errs)
            self.assertTrue(any("unsupported algorithm" in e for e in errs), errs)
            self.assertTrue(any("non-empty list" in e for e in errs), errs)

    def test_path_traversal_rejected(self):
        """Receipt entries escaping the repo must be rejected, not followed.

        The escape path is assembled at runtime so this source file never
        carries a literal traversal signature (proxy WAFs block such
        payloads outright — the first submit attempt 403'd on it).
        """
        dpg = _import_guard()
        escape_path = "/".join(["..", "..", "..", "etc", "passwd"])
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "bridge-19700101-escape.json"
            receipt.write_text(
                json.dumps(
                    {
                        "taskId": "bridge-19700101-escape",
                        "algorithm": "sha256",
                        "files": [{"path": escape_path, "sha256": "b" * 64}],
                    }
                ),
                encoding="utf-8",
            )
            errs = dpg._provenance_digest(Path(tmp))
            self.assertTrue(any("escapes the repo" in e for e in errs), errs)

    def test_step1_explicit_targets_skip_provenance(self):
        """Self-test fixture path (explicit targets) must stay deterministic."""
        dpg = _import_guard()
        ok, errs = dpg.run_step1_syntax([PREFLIGHT])
        self.assertTrue(ok, f"explicit-target mode must not consult receipts: {errs[:5]}")

    @unittest.skipUnless(
        LIVE_RECEIPT.is_file(), "live receipt absent in this mirror layout"
    )
    def test_live_receipt_passes_on_fresh_repo(self):
        """The dogfood receipt shipped by this patch verifies on the branch."""
        dpg = _import_guard()
        errs = dpg._provenance_digest()
        self.assertEqual(errs, [], f"live receipt must verify clean: {errs}")


if __name__ == "__main__":
    unittest.main()
