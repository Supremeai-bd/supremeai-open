#!/usr/bin/env python3
"""S14 tests — Cross-Platform Invariant Guard (issue #515).

Dual-mode: runs under stdlib unittest AND pytest.
Constants and rules are imported from the reference module (SSOT) —
never duplicated. Sample sources are assembled at runtime via chr()/
repr() so this suite stays clean under the guard's own scan.
"""
from __future__ import annotations

import json
import os
import subprocess  # noqa: F401  (imported to prove import-parity; never called)
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))

import cross_platform_invariant_guard as guard  # noqa: E402

BS = chr(92)   # backslash
FS = chr(47)   # forward slash
CRLF = chr(13) + chr(10)


def scan(src: str, path: str = "sample.py"):
    violations, bad = guard.scan_source(path, src)
    assert bad is None, (src, bad)
    return violations


def rules(src: str, path: str = "sample.py") -> set[str]:
    return {v.rule for v in scan(src, path)}


class TestR1Utf8Encoding(unittest.TestCase):
    def test_open_without_encoding_flagged(self):
        self.assertEqual(rules("open('f.txt')\n"), {"R1-utf8-encoding"})

    def test_open_binary_mode_exempt(self):
        self.assertEqual(rules("open('f.bin', 'wb')\n"), set())
        self.assertEqual(rules("open('f.bin', mode='rb')\n"), set())

    def test_open_utf8_family_accepted(self):
        for enc in ("utf-8", "utf8", "utf_8", "UTF-8"):
            src = "open('f.txt', encoding=" + repr(enc) + ")\n"
            self.assertEqual(rules(src), set(), enc)

    def test_open_non_utf8_flagged(self):
        self.assertEqual(rules("open('f.txt', encoding='cp1252')\n"),
                         {"R1-utf8-encoding"})

    def test_io_and_codecs_open_covered(self):
        self.assertEqual(
            rules("import io\nio.open('f.txt')\n"), {"R1-utf8-encoding"})
        self.assertEqual(
            rules("import codecs\ncodecs.open('f.txt', 'r')\n"),
            {"R1-utf8-encoding"})
        self.assertEqual(
            rules("import codecs\ncodecs.open('f.txt', 'r', 'utf-8')\n"), set())

    def test_read_text_write_text_flagged_without_encoding(self):
        self.assertEqual(rules("p.read_text()\n"), {"R1-utf8-encoding"})
        self.assertEqual(rules("p.write_text(data)\n"), {"R1-utf8-encoding"})
        self.assertEqual(
            rules("p.write_text(data, encoding='utf-8')\n"), set())

    def test_subprocess_text_mode_requires_encoding(self):
        self.assertEqual(rules("subprocess.run(cmd, text=True)\n"),
                         {"R1-utf8-encoding", "R2-subprocess-timeout"})
        self.assertEqual(
            rules("subprocess.run(cmd, universal_newlines=True)\n"),
            {"R1-utf8-encoding", "R2-subprocess-timeout"})
        self.assertEqual(
            rules("subprocess.run(cmd, text=True, encoding='utf-8')\n"),
            {"R2-subprocess-timeout"})
        self.assertEqual(rules("subprocess.run(cmd)\n"),
                         {"R2-subprocess-timeout"})

    def test_dynamic_mode_is_treated_as_text(self):
        self.assertEqual(rules("open(name, mode)\n"), {"R1-utf8-encoding"})


class TestR2SubprocessTimeout(unittest.TestCase):
    def test_run_without_timeout_flagged(self):
        self.assertEqual(rules("subprocess.run(cmd)\n"),
                         {"R2-subprocess-timeout"})

    def test_timeout_none_flagged(self):
        self.assertEqual(rules("subprocess.run(cmd, timeout=None)\n"),
                         {"R2-subprocess-timeout"})

    def test_all_timeout_required_funcs_covered(self):
        for name in ("run", "call", "check_output", "check_call"):
            src = "subprocess." + name + "(cmd)\n"
            self.assertIn("R2-subprocess-timeout", rules(src), name)

    def test_timeout_number_clean(self):
        self.assertEqual(rules("subprocess.run(cmd, timeout=60)\n"), set())

    def test_popen_communicate_chain_tracked(self):
        src = ("import subprocess\n"
               "p = subprocess.Popen(cmd)\n"
               "out = p.communicate()\n")
        self.assertEqual(rules(src), {"R2-subprocess-timeout"})
        fixed = ("import subprocess\n"
                 "p = subprocess.Popen(cmd)\n"
                 "out = p.communicate(timeout=10)\n")
        self.assertEqual(rules(fixed), set())

    def test_popen_wait_chain_tracked(self):
        src = ("import subprocess\n"
               "p = subprocess.Popen(cmd)\n"
               "code = p.wait()\n")
        self.assertIn("R2-subprocess-timeout", rules(src))


class TestR3CrlfPurge(unittest.TestCase):
    def test_crlf_in_shell_script_flagged(self):
        found = guard.scan_record(guard.SourceRecord("run.sh", "echo hi" + CRLF))
        self.assertEqual([v.rule for v in found], ["R3-crlf-purge"])
        self.assertEqual(found[0].line, 1)

    def test_lf_clean(self):
        self.assertEqual(
            guard.scan_record(guard.SourceRecord("run.sh", "echo hi\n")), [])

    def test_covered_suffixes(self):
        for ext in (".py", ".sh", ".ts", ".md", ".tsx", ".js", ".mjs", ".cjs"):
            found = guard.scan_record(guard.SourceRecord("f" + ext, "x" + CRLF))
            self.assertEqual([v.rule for v in found], ["R3-crlf-purge"], ext)

    def test_uncovered_suffix_ignored(self):
        found = guard.scan_record(guard.SourceRecord("data.yaml", "x" + CRLF))
        self.assertEqual(found, [])

    def test_every_crlf_line_reported(self):
        found = guard.scan_record(guard.SourceRecord("a.py", "x = 1" + CRLF + "y = 2" + CRLF))
        self.assertEqual(len(found), 2)
        self.assertEqual([v.line for v in found], [1, 2])


class TestR4PosixPath(unittest.TestCase):
    def test_forward_slash_concat_flagged(self):
        src = "p = 'dir' + " + repr(FS) + " + name\n"
        self.assertIn("R4-posix-path", rules(src))

    def test_backslash_concat_flagged(self):
        src = "p = 'dir' + " + repr(BS) + " + name\n"
        self.assertIn("R4-posix-path", rules(src))

    def test_os_path_join_clean(self):
        self.assertEqual(rules("p = os.path.join('dir', name)\n"), set())

    def test_pathlib_div_clean(self):
        src = "p = pathlib.Path('dir') " + chr(47) + " 'x'\n"
        self.assertEqual(rules(src), set())

    def test_separator_join_flagged(self):
        self.assertIn("R4-posix-path",
                      rules("p = " + repr(FS) + ".join(parts)\n"))
        self.assertIn("R4-posix-path",
                      rules("p = " + repr(BS) + ".join(parts)\n"))

    def test_split_separator_flagged(self):
        self.assertIn("R4-posix-path",
                      rules("parts = p.split(" + repr(FS) + ")\n"))

    def test_mixed_separator_literal_flagged(self):
        src = "cmd(" + repr('C:' + BS + 'dir' + FS + 'file') + ")\n"
        self.assertIn("R4-posix-path", rules(src))

    def test_url_scheme_literal_exempt(self):
        src = "u = 'https://x' + " + repr(FS + "api") + "\n"
        self.assertNotIn("R4-posix-path", rules(src))

    def test_url_without_visible_scheme_flagged(self):
        src = "u = base + " + repr(FS + "api") + "\n"
        self.assertIn("R4-posix-path", rules(src))

    def test_fstring_separator_flagged(self):
        src = "p = f\"dir" + FS + "\" + name\n"
        self.assertIn("R4-posix-path", rules(src))


class TestR5CliPresence(unittest.TestCase):
    def test_which_guard_clean(self):
        src = ("import shutil, subprocess\n"
               "if shutil.which('git') is None:\n"
               "    raise SystemExit(127)\n"
               "subprocess.run(['git', 'status'], timeout=30)\n")
        self.assertEqual(rules(src), set())

    def test_missing_which_flagged(self):
        src = ("import subprocess\n"
               "subprocess.run(['git', 'status'], timeout=30)\n")
        self.assertIn("R5-cli-presence", rules(src))

    def test_filenotfound_handler_clean(self):
        src = ("import subprocess\n"
               "def go():\n"
               "    try:\n"
               "        subprocess.run(['gh', 'pr'], timeout=30)\n"
               "    except FileNotFoundError:\n"
               "        return 127\n")
        self.assertEqual(rules(src), set())

    def test_shell_string_command_covered(self):
        src = ("import subprocess\n"
               "subprocess.run('docker ps', timeout=30)\n")
        self.assertIn("R5-cli-presence", rules(src))

    def test_path_prefixed_binary_resolved(self):
        src = ("import subprocess\n"
               "subprocess.run([" + repr('/usr/bin/git') + ", 'status'], timeout=30)\n")
        self.assertIn("R5-cli-presence", rules(src))


class TestR6AntiSwallow(unittest.TestCase):
    def test_bare_except_pass_flagged(self):
        src = "try:\n    a()\nexcept:\n    pass\n"
        self.assertIn("R6-anti-swallow", rules(src))

    def test_except_exception_pass_flagged(self):
        src = "try:\n    a()\nexcept Exception:\n    pass\n"
        self.assertIn("R6-anti-swallow", rules(src))

    def test_ellipsis_body_flagged(self):
        src = "try:\n    a()\nexcept Exception:\n    ...\n"
        self.assertIn("R6-anti-swallow", rules(src))

    def test_raise_clean(self):
        src = "try:\n    a()\nexcept Exception:\n    raise\n"
        self.assertEqual(rules(src), set())

    def test_logging_clean(self):
        src = "try:\n    a()\nexcept Exception:\n    log.error('x')\n"
        self.assertEqual(rules(src), set())

    def test_honest_assignment_clean(self):
        src = "try:\n    a()\nexcept FileNotFoundError:\n    code = 127\n"
        self.assertEqual(rules(src), set())


class TestParseFailClosed(unittest.TestCase):
    def test_syntax_error_is_violation(self):
        violations, bad = guard.scan_source("broken.py", "def broken(:\n")
        self.assertIsNotNone(bad)
        records = [guard.SourceRecord("broken.py", "def broken(:\n")]
        found = guard.scan_records(records)
        self.assertIn("PARSE-FAIL-CLOSED", {v.rule for v in found})


class TestScanRecords(unittest.TestCase):
    def test_mixed_records(self):
        records = [
            guard.SourceRecord("a.py", "open('x')\n"),
            guard.SourceRecord("b.sh", "echo hi" + CRLF),
            guard.SourceRecord("c.md", "clean\n"),
        ]
        found = guard.scan_records(records)
        by_rule = {v.rule for v in found}
        self.assertEqual(by_rule, {"R1-utf8-encoding", "R3-crlf-purge"})
        self.assertEqual(
            [v.path for v in found if v.rule == "R1-utf8-encoding"], ["a.py"])

    def test_empty_input_clean(self):
        self.assertEqual(guard.scan_records([]), [])


class TestAutofix(unittest.TestCase):
    def test_fix_adds_encoding_and_timeout(self):
        dirty = ("with open('a.txt') as fh:\n"
                 "    data = fh.read()\n"
                 "subprocess.run(['git', 'status'])\n")
        fixed, notes = guard.autofix_records([guard.SourceRecord("d.py", dirty)])
        self.assertIn("encoding='utf-8'", fixed[0].content)
        self.assertIn("timeout=30", fixed[0].content)
        self.assertEqual(len(notes), 2)
        clean = scan(fixed[0].content, "d.py")
        self.assertEqual([v.rule for v in clean], ["R5-cli-presence"])

    def test_fix_never_touches_binary_mode(self):
        fixed, notes = guard.autofix_records(
            [guard.SourceRecord("b.py", "open('x', 'wb')\n")])
        self.assertEqual(fixed[0].content, "open('x', 'wb')\n")
        self.assertEqual(notes, [])

    def test_fix_rewrites_crlf(self):
        fixed, notes = guard.autofix_records(
            [guard.SourceRecord("run.sh", "echo hi" + CRLF)])
        self.assertEqual(fixed[0].content, "echo hi\n")
        self.assertEqual(notes, ["run.sh: R3 rewrote CRLF to LF"])

    def test_fix_is_idempotent(self):
        dirty = "open('a.txt')\nsubprocess.run(cmd)\n"
        once, _ = guard.autofix_records([guard.SourceRecord("i.py", dirty)])
        twice, notes2 = guard.autofix_records(once)
        self.assertEqual(once[0].content, twice[0].content)
        self.assertEqual(notes2, [])

    def test_fixer_rejects_invalid_roundtrip(self):
        # A file that does not parse yields no fixes and no crash.
        fixed, notes = guard.autofix_records(
            [guard.SourceRecord("broken.py", "def broken(:\n")])
        self.assertEqual(fixed[0].content, "def broken(:\n")
        self.assertEqual(notes, [])


class TestConstantsSSOT(unittest.TestCase):
    def test_documented_exit_codes(self):
        self.assertEqual(guard.EXIT_CLEAN, 0)
        self.assertEqual(guard.EXIT_VIOLATION, 2)
        self.assertEqual(guard.EXIT_MALFORMED, 3)

    def test_default_timeout_is_bounded_number(self):
        self.assertIsInstance(guard.DEFAULT_TIMEOUT, int)
        self.assertGreater(guard.DEFAULT_TIMEOUT, 0)
        self.assertLessEqual(guard.DEFAULT_TIMEOUT, 300)

    def test_external_tools_include_federation_stack(self):
        for tool in ("gh", "git", "docker", "curl"):
            self.assertIn(tool, guard.EXTERNAL_TOOLS)


class TestSelfTestAndCli(unittest.TestCase):
    def test_module_self_test_passes(self):
        self.assertTrue(guard.self_test())

    def test_cli_clean_exit(self):
        proc = subprocess_run_guard("--self-test")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_cli_flags_violations(self):
        record = {"path": "x.py", "content": "open('f')\n"}
        proc = subprocess_run_guard("--files-json", json.dumps([record]))
        self.assertEqual(proc.returncode, guard.EXIT_VIOLATION)
        self.assertIn("R1-utf8-encoding", proc.stdout)

    def test_cli_malformed_json_fail_closed(self):
        proc = subprocess_run_guard("--files-json", "{not json")
        self.assertEqual(proc.returncode, guard.EXIT_MALFORMED)


def subprocess_run_guard(*cli_args: str):
    import subprocess as sp
    module = Path(guard.__file__).resolve()
    return sp.run(
        [sys.executable, str(module), *cli_args],
        capture_output=True, text=True, encoding="utf-8", timeout=60)


if __name__ == "__main__":
    unittest.main()
