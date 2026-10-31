#!/usr/bin/env python3
"""tests/test_scan_secret_logs.py — contract tests for scripts/ci/scan_secret_logs.py.

no-secret-logs: fixture-file — this face quotes detection vectors as string
data (that is its job); the scanner skips files carrying this declaration.

The no-secret-logs pre-commit hook (WO #1361) shipped with no test face and
a false-positive class that kept the fail-closed gate permanently red on its
own tree: `secret` + `\\w*` suffix-gobbling conflated the secret's lookup
key (`secret_id` / `secret_name`) with its value, flagging 18 identifier-only
call-sites in core/security/secret_vault.py and scripts/ops/security/*.
Closed with the same identifier-suffix escape in master_secret_shield.py's
LOG_INTERPOLATION rule (shared root cause, one defect family).

Pins the pure contracts hermetically (no network, no repo mutations):
  - detection: f-string interpolation of value-bearing secret vars inside
    log/print calls — case-insensitive, dotted callers, word-char suffixes;
  - escapes: [REDACTED_*] markers and identifier-suffix forms (`_id`,
    `_name`, plurals) — while value-bearing neighbors still fail;
  - scan_repo(): SKIP_DIRS honored, non-.py ignored, undecodable bytes
    survive via errors="replace", relative path:line and 120-char trim;
  - main(): exit 1 + banner on hits, exit 0 + clean line otherwise, both
    the explicit-root and default-cwd branches;
  - cross-guard: master_secret_shield's LOG_INTERPOLATION shares the
    identifier escape (self-test stays 7/7) and its OTP self-test vector
    stays dynamically constructed so the fixture never trips the scanner.

Fully offline, stdlib-only, dual mode (unittest + pytest).
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import scan_secret_logs as scanner  # noqa: E402
import master_secret_shield as shield  # noqa: E402


def _write(root: Path, rel: str, data) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return p


def _scan_tree(files: dict) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, data in files.items():
            _write(root, rel, data)
        return scanner.scan_repo(root)


class TestScanDetection(unittest.TestCase):
    def test_flags_value_interpolation_in_print(self):
        hits = _scan_tree({"app.py": 'print(f"login otp {current_otp} ok")\n'})
        self.assertEqual(len(hits), 1)
        self.assertIn("app.py:1:", hits[0])
        self.assertIn("current_otp", hits[0])

    def test_flags_caller_flavors_and_case(self):
        src = (
            'LOGGER.info(f"pw={PASSWORD}")\n'
            'logger.debug(f"code {totp_secret} end")\n'
            'console.error(f"key {api_key} bad")\n'
            'print(f"tok {access_token}")\n'
        )
        hits = _scan_tree({"app.py": src})
        self.assertEqual(len(hits), 4)

    def test_word_char_suffix_value_forms_flagged(self):
        src = (
            'print(f"{secret}")\n'
            'print(f"{secret_value}")\n'
            'print(f"{api_key_v2}")\n'
            'print(f"{pwd_hash}")\n'
            'print(f"{otp_code2}")\n'
        )
        hits = _scan_tree({"app.py": src})
        self.assertEqual(len(hits), 5)

    def test_identifier_suffix_forms_escaped(self):
        src = (
            "logger.warning(f\"Secret '{secret_id}' not found.\")\n"
            "print(f\"deleted {secret_name} from vault\")\n"
            "print(f\"rotated {secret_ids} batch\")\n"
            "print(f\"listed {secret_names} batch\")\n"
            "print(f\"entry {password_id} saved\")\n"
            "print(f\"entry {api_key_id} saved\")\n"
            "print(f\"entry {auth_token_name} saved\")\n"
            "print(f\"entry {credential_id} saved\")\n"
        )
        self.assertEqual(_scan_tree({"app.py": src}), [])

    def test_identifier_escape_is_narrow(self):
        hits = _scan_tree(
            {"app.py": 'print(f"{secret_id} -> {secret}")\n'
                       'print(f"{secret_name} value={secret_value}")\n'}
        )
        self.assertEqual(len(hits), 2)
        self.assertIn("{secret}", hits[0])
        self.assertIn("{secret_value}", hits[1])

    def test_non_secret_and_non_log_lines_clean(self):
        src = (
            'print(f"user {username} otp_len {otp_length}")\n'
            'token = f"{access_token}"\n'
            'payload = {"password": password}\n'
        )
        self.assertEqual(_scan_tree({"app.py": src}), [])

    def test_redacted_marker_escaped(self):
        src = 'logger.info(f"otp {current_otp}")  # [REDACTED_IN_PROD]\n'
        self.assertEqual(_scan_tree({"app.py": src}), [])

    def test_fixture_file_declaration_skips_file(self):
        src = "# no-secret-logs: fixture-file\nprint(f'{pwd}')\n"
        self.assertEqual(_scan_tree({"tests/test_x.py": src}), [])

    def test_fixture_declaration_is_author_scoped(self):
        marked = "# no-secret-logs: fixture-file\nprint(f'{pwd}')\n"
        hits = _scan_tree({"tests/test_x.py": marked, "app.py": 'print(f"{pwd}")\n'})
        self.assertEqual(len(hits), 1)
        self.assertIn("app.py", hits[0])

    def test_fixture_declaration_must_live_in_head_window(self):
        pad = "\n" * 2100  # push the declaration past the 2 KB head window
        src = "x = 1\n" + pad + "# no-secret-logs: fixture-file\nprint(f'{pwd}')\n"
        hits = _scan_tree({"app.py": src})
        self.assertEqual(len(hits), 1)

    def test_gap_between_call_and_brace(self):
        hits = _scan_tree({"app.py": 'print(f"user {username} pwd {pwd} done")\n'})
        self.assertEqual(len(hits), 1)
        self.assertIn("{pwd}", hits[0])


class TestScanRepo(unittest.TestCase):
    def test_skip_dirs_ignored(self):
        off = 'print(f"{current_otp}")\n'
        files = {
            "app.py": off,
            "node_modules/pkg/x.py": off,
            "__pycache__/y.py": off,
            ".venv/lib/z.py": off,
            "venv/lib/w.py": off,
            ".mypy_cache/a.py": off,
            ".git/hooks/b.py": off,
        }
        hits = _scan_tree(files)
        self.assertEqual(len(hits), 1)
        self.assertIn("app.py", hits[0])

    def test_non_py_files_ignored(self):
        off = 'print(f"{current_otp}")\n'
        files = {
            "notes.txt": off,
            "cfg.json": off,
            "README.md": off,
            "stub.pyi": off,
        }
        self.assertEqual(_scan_tree(files), [])

    def test_undecodable_bytes_survive(self):
        files = {"app.py": b"\xff\xfe garbage line\nprint(f'pwd {pwd}')\n"}
        hits = _scan_tree(files)
        self.assertEqual(len(hits), 1)

    def test_nested_relative_path_and_lineno(self):
        src = "# header\n# header\nprint(f'{pwd}')\n"
        hits = _scan_tree({"sub/dir/x.py": src})
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].startswith("sub/dir/x.py:3:"))

    def test_hit_line_trimmed_to_120(self):
        pad = "x" * 300
        src = f'print(f"pwd {{pwd}} {pad}")\n'
        hits = _scan_tree({"a.py": src})
        self.assertEqual(len(hits), 1)
        tail = hits[0].split(": ", 1)[1]
        self.assertLessEqual(len(tail), 120)


class TestMainContract(unittest.TestCase):
    def _tree(self, files: dict):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, data in files.items():
            _write(root, rel, data)
        return root

    def test_main_dirty_root_exits_1_with_banner(self):
        root = self._tree({"app.py": 'print(f"{pwd}")\n'})
        buf = io.StringIO()
        with mock_argv([str(root)]), contextlib.redirect_stdout(buf):
            rc = scanner.main()
        self.assertEqual(rc, 1)
        self.assertIn("SECRET-LOG SCAN FAILED", buf.getvalue())

    def test_main_clean_root_exits_0(self):
        root = self._tree({"app.py": 'print(f"{username}")\n'})
        buf = io.StringIO()
        with mock_argv([str(root)]), contextlib.redirect_stdout(buf):
            rc = scanner.main()
        self.assertEqual(rc, 0)
        self.assertIn("secret-log scan: clean", buf.getvalue())

    def test_main_default_root_is_cwd(self):
        root = self._tree({"app.py": 'print(f"{pwd}")\n'})
        buf = io.StringIO()
        with mock_argv([]), \
                mock.patch.object(Path, "cwd", lambda: root), \
                contextlib.redirect_stdout(buf):
            rc = scanner.main()
        self.assertEqual(rc, 1)
        self.assertIn("SECRET-LOG SCAN FAILED", buf.getvalue())


class TestShieldSharedContract(unittest.TestCase):
    """Same defect family, shared root cause: shield's LOG_INTERPOLATION."""

    def _shield_verdict(self, line: str) -> bool:
        finding = shield.scan_line(line, "f.py", 1)
        return finding is not None and finding.rule == "LOG_SECRET_INTERPOLATION"

    def test_identifier_forms_escape_shield_rule(self):
        for line in (
            "logger.warning(f\"Secret '{secret_id}' not found.\")",
            "print(f'deleted {secret_name} from Infisical')",
            "print(f'listed {secret_names} batch')",
        ):
            self.assertFalse(self._shield_verdict(line), line)

    def test_value_forms_still_flagged_by_shield_rule(self):
        for line in (
            "logger.info(f'Logged in with OTP: {current_otp}')",
            "logger.info(f'value={secret_value}')",
            "logger.info(f'key={secret}')",
        ):
            self.assertTrue(self._shield_verdict(line), line)

    def test_shield_selftest_stays_all_pass(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = shield.main(["--self-test"])
        self.assertEqual(rc, 0)
        self.assertIn("ALL PASS (7/7", buf.getvalue())

    def test_shield_source_never_trips_scanner(self):
        """Drift guard: the shield's self-test vectors stay fixture-safe."""
        src = (REPO_ROOT / "scripts" / "ci" / "master_secret_shield.py") \
            .read_text(encoding="utf-8")
        for i, line in enumerate(src.splitlines(), 1):
            self.assertIsNone(
                scanner.LOG_INTERP.search(line),
                f"shield source line {i} trips the no-secret-logs scanner",
            )


class mock_argv:
    """Context manager pinning sys.argv for scanner.main() branches."""

    def __init__(self, argv_tail):
        self.argv_tail = argv_tail

    def __enter__(self):
        self.p = mock.patch.object(
            sys, "argv", ["scan_secret_logs.py"] + self.argv_tail)
        self.p.start()
        return self

    def __exit__(self, *exc):
        self.p.stop()
        return False


if __name__ == "__main__":
    unittest.main()
