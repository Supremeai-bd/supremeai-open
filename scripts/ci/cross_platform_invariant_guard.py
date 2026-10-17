#!/usr/bin/env python3
"""S14 — Cross-Platform Invariant Guard (issue #515).

Machine-enforces the 6 Cross-Platform Silent Landmines as fail-closed
pre-merge gates. Linux CI masks locale/encoding bugs because its system
locale defaults to UTF-8; these guards make the whole class of defects
impossible to land (Windows cp1252 crashes, hanging CI jobs, CRLF
breakage, POSIX path parity, missing CLI dependencies, silent exceptions).

Deterministic rules (AST where possible, bytes where required):

  R1  MANDATORY UTF-8 ENCODING — the open family (open / io.open /
      codecs.open) and pathlib text methods (.read_text / .write_text)
      MUST pass an explicit encoding='utf-8' (utf-8 family accepted);
      binary mode is exempt. Subprocess calls with text=True or
      universal_newlines=True MUST pass encoding='utf-8'.
  R2  MANDATORY SUBPROCESS TIMEOUT — subprocess.run/call/check_output/
      check_call MUST pass timeout=<seconds> (timeout=None is a
      violation). Popen chains must timeout their .communicate()/.wait().
  R3  LF LINE-ENDING & CRLF PURGE — bytes-level scan: .py/.sh/.ts/.md
      (+ .tsx/.js/.mjs/.cjs) files must not contain CRLF.
  R4  PATHLIB & POSIX COMPATIBILITY — no hardcoded path-separator string
      concatenation ('dir/' + name, backslash joins), no '/'.join, no
      .split('/'), no mixed-separator literals. pathlib.Path or
      os.path.join() required. URL-scheme operands are exempt.
  R5  CLI PRESENCE & GRACEFUL 127 — subprocess calls naming an external
      tool (gh, git, docker, ...) require a shutil.which('<tool>')
      check in the same module OR a FileNotFoundError handler wrapping
      the call.
  R6  BARE EXCEPTION & SILENT SWALLOW — except handlers whose body is
      only pass / Ellipsis are rejected; errors must be logged, returned,
      or re-raised honestly.

Exit codes: 0 = clean; 2 = violation (fail-closed — CI must reject);
3 = malformed input (unparseable Python is itself reported as a
fail-closed PARSE-FAIL-CLOSED violation inside exit 2).

Auto-fixer (--fix, dev tool): retrofits R1 with encoding='utf-8', R2
with timeout=<DEFAULT_TIMEOUT>, R3 by rewriting CRLF to LF. Every
rewritten .py is re-validated with ast.parse before it is accepted;
R4/R5/R6 need semantic decisions and are never auto-fixed.

Known V1 limitations (documented, deterministic): dynamic (non-literal)
mode/encoding arguments are treated as text-mode by R1; .open() called
as an attribute on arbitrary receivers is out of scope (use read_text
or module-level open); URL building without a visible scheme literal in
the same expression is still flagged by R4.

Pure stdlib. Run: python3 scripts/ci/cross_platform_invariant_guard.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from typing import Final, Iterable, Mapping, Sequence

EXIT_CLEAN: Final = 0
EXIT_VIOLATION: Final = 2
EXIT_MALFORMED: Final = 3

DEFAULT_TIMEOUT: Final = 30          # seconds; auto-fixer retrofit value
UTF8_FAMILY: Final = frozenset({
    "utf-8", "utf8", "utf_8", "u8", "utf", "utf-8//",
})
CRLF_SUFFIXES: Final = frozenset({
    ".py", ".sh", ".ts", ".md", ".tsx", ".js", ".mjs", ".cjs",
})
SUBPROCESS_FUNCS: Final = frozenset({
    "run", "call", "check_output", "check_call", "Popen",
})
TIMEOUT_REQUIRED_FUNCS: Final = frozenset({
    "run", "call", "check_output", "check_call",
})
EXTERNAL_TOOLS: Final = frozenset({
    "gh", "git", "docker", "curl", "jq", "node", "npm", "npx", "bun",
    "pip", "python3", "python", "shellcheck", "gitleaks", "tar",
    "rsync", "ssh", "gcloud", "aws", "kubectl", "make",
})
SEPARATOR_CHARS: Final = ("/", "\\")


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str

    def format(self) -> str:
        return f"[FAIL] {self.path}:{self.line} - {self.rule}: {self.message}"


@dataclass(frozen=True)
class SourceRecord:
    path: str
    content: str


def _is_utf8_literal(value: str) -> bool:
    return value.strip().lower() in UTF8_FAMILY


def _kwarg(node: ast.Call, name: str) -> ast.keyword | None:
    for kw in node.keywords:
        if kw.arg == name:
            return kw
    return None


def _const_str(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _open_family(call: ast.Call) -> str | None:
    """Return canonical name when the call is open/io.open/codecs.open."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        return "open"
    if (isinstance(func, ast.Attribute) and func.attr == "open"
            and isinstance(func.value, ast.Name)
            and func.value.id in ("io", "codecs")):
        return f"{func.value.id}.open"
    return None


def _explicit_encoding(call: ast.Call) -> str | None:
    """Extract an explicit encoding from kwargs or codecs positional slot 2."""
    kw = _kwarg(call, "encoding")
    if kw is not None:
        return _const_str(kw.value)
    if call.func and isinstance(call.func, ast.Attribute) \
            and isinstance(call.func.value, ast.Name) \
            and call.func.value.id == "codecs" and len(call.args) >= 3:
        return _const_str(call.args[2])
    return None


def _mode_is_binary(call: ast.Call) -> bool:
    mode_kw = _kwarg(call, "mode")
    if mode_kw is not None:
        val = _const_str(mode_kw.value)
        return val is not None and "b" in val.lower()
    if len(call.args) >= 2:
        val = _const_str(call.args[1])
        return val is not None and "b" in val.lower()
    return False


def _check_encoding_call(call: ast.Call, path: str, violations: list[Violation]) -> None:
    """R1 for the open family and pathlib .read_text/.write_text."""
    func = call.func
    family = _open_family(call)
    if family is not None:
        if _mode_is_binary(call):
            return
        encoding = _explicit_encoding(call)
        if encoding is None:
            violations.append(Violation(
                path, call.lineno, "R1-utf8-encoding",
                f"{family}(...) missing explicit encoding='utf-8'; Windows "
                "default cp1252 will crash on Unicode/emojis"))
        elif not _is_utf8_literal(encoding):
            violations.append(Violation(
                path, call.lineno, "R1-utf8-encoding",
                f"{family}(... encoding={encoding!r}) is not utf-8 family"))
        return
    if isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
        encoding = _explicit_encoding(call)
        if encoding is None:
            violations.append(Violation(
                path, call.lineno, "R1-utf8-encoding",
                f".{func.attr}(...) missing explicit encoding='utf-8'; "
                "locale-dependent decoding breaks Windows runners"))
        elif not _is_utf8_literal(encoding):
            violations.append(Violation(
                path, call.lineno, "R1-utf8-encoding",
                f".{func.attr}(... encoding={encoding!r}) is not utf-8 family"))


def _subprocess_name(call: ast.Call) -> str | None:
    func = call.func
    if (isinstance(func, ast.Attribute) and func.attr in SUBPROCESS_FUNCS
            and isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
        return func.attr
    return None


def _check_encoding_subprocess(call: ast.Call, path: str, violations: list[Violation]) -> None:
    """R1 for subprocess calls with text=True / universal_newlines=True."""
    name = _subprocess_name(call)
    if name is None:
        return
    text_mode = False
    for flag in ("text", "universal_newlines"):
        kw = _kwarg(call, flag)
        if kw is not None and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            text_mode = True
    if not text_mode:
        return
    encoding = _explicit_encoding(call)
    if encoding is None:
        violations.append(Violation(
            path, call.lineno, "R1-utf8-encoding",
            f"subprocess.{name}(text=True) without encoding='utf-8'; child "
            "output decodes with cp1252 on Windows"))
    elif not _is_utf8_literal(encoding):
        violations.append(Violation(
            path, call.lineno, "R1-utf8-encoding",
            f"subprocess.{name}(encoding={encoding!r}) is not utf-8 family"))


def _check_timeout(call: ast.Call, path: str, violations: list[Violation]) -> None:
    """R2: subprocess.run/call/check_output/check_call require timeout=<seconds>."""
    name = _subprocess_name(call)
    if name is None or name not in TIMEOUT_REQUIRED_FUNCS:
        return
    kw = _kwarg(call, "timeout")
    if kw is None:
        violations.append(Violation(
            path, call.lineno, "R2-subprocess-timeout",
            f"subprocess.{name}(...) missing explicit timeout=<seconds>; a "
            "hanging job burns up to 360 Actions quota minutes"))
    elif isinstance(kw.value, ast.Constant) and kw.value.value is None:
        violations.append(Violation(
            path, call.lineno, "R2-subprocess-timeout",
            f"subprocess.{name}(timeout=None) is unbounded; pass a number"))


def _popen_wait_chains(tree: ast.AST, path: str, violations: list[Violation]) -> None:
    """R2 for Popen: var.communicate()/var.wait() without timeout where var
    was assigned subprocess.Popen(...) in the same module."""
    popen_vars: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Call):
                func = value.func
                if (isinstance(func, ast.Attribute) and func.attr == "Popen"
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "subprocess"):
                    for target in targets:
                        if isinstance(target, ast.Name):
                            popen_vars.add(target.id)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("communicate", "wait"):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id not in popen_vars:
            continue
        if _kwarg(node, "timeout") is None:
            violations.append(Violation(
                path, node.lineno, "R2-subprocess-timeout",
                f"Popen .{node.func.attr}() without timeout=<seconds>"))


def _url_exempt(texts: Iterable[str | None]) -> bool:
    return any(t and "://" in t for t in texts)


def _separator_concat(tree: ast.AST, path: str, violations: list[Violation]) -> None:
    """R4: hardcoded path-separator concatenation and splits."""
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            operands = [node.left, node.right]
            texts = [_const_str(o) for o in operands]
            if _url_exempt(texts):
                continue
            for text in texts:
                if not text:
                    continue
                if text.endswith(SEPARATOR_CHARS) or text.startswith(SEPARATOR_CHARS):
                    violations.append(Violation(
                        path, node.lineno, "R4-posix-path",
                        f"hardcoded path separator in string concatenation "
                        f"({text!r}); use pathlib.Path or os.path.join()"))
        elif isinstance(node, ast.JoinedStr):
            parts = [_const_str(v) for v in node.values if isinstance(v, ast.Constant)]
            if _url_exempt(parts):
                continue
            for text in parts:
                if text and (text.endswith(SEPARATOR_CHARS) or text.startswith(SEPARATOR_CHARS)):
                    violations.append(Violation(
                        path, node.lineno, "R4-posix-path",
                        f"f-string path separator ({text!r}); use pathlib.Path "
                        "or os.path.join()"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if (attr == "join" and isinstance(node.func.value, ast.Constant)
                    and isinstance(node.func.value.value, str)):
                sep = node.func.value.value
                if sep in SEPARATOR_CHARS and not _url_exempt([sep]):
                    violations.append(Violation(
                        path, node.lineno, "R4-posix-path",
                        f"{sep!r}.join(...) path building; use os.path.join() "
                        "or pathlib"))
            if attr in ("split", "rsplit") and node.args:
                sep = _const_str(node.args[0])
                if sep in SEPARATOR_CHARS:
                    violations.append(Violation(
                        path, node.lineno, "R4-posix-path",
                        f".{attr}({sep!r}) path splitting; use pathlib parts "
                        "or os.path.split"))
        elif isinstance(node, ast.Call):
            for arg in node.args:
                value = _const_str(arg)
                if value and "\\" in value and "/" in value:
                    violations.append(Violation(
                        path, node.lineno, "R4-posix-path",
                        f"mixed-separator path literal {value!r}; normalize "
                        "with pathlib.Path"))


def _which_tool_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "which":
            continue
        base = node.func.value
        if isinstance(base, ast.Name) and base.id != "shutil":
            continue
        if node.args:
            tool = _const_str(node.args[0])
            if tool:
                names.add(tool)
        for kw in node.keywords:
            if kw.arg == "cmd":
                tool = _const_str(kw.value)
                if tool:
                    names.add(tool)
    return names


def _first_tool_token(call: ast.Call) -> str | None:
    def from_str(value: str) -> str | None:
        token = value.split()
        if token:
            head = token[0].rpartition("/")[2] or token[0]
            return head or None
        return None

    if not call.args:
        return None
    first = call.args[0]
    value = _const_str(first)
    if value is not None:
        return from_str(value)
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        head = _const_str(first.elts[0])
        if head is not None:
            head = head.rpartition("/")[2] or head
            return head or None
    return None


def _in_file_notfound_handler(tree: ast.AST, target: ast.Call) -> bool:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    node: ast.AST | None = target
    while node is not None and id(node) in parents:
        node = parents[id(node)]
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                types = ()
                if isinstance(handler.type, ast.Name):
                    types = (handler.type,)
                elif isinstance(handler.type, ast.Tuple):
                    types = tuple(elt for elt in handler.type.elts
                                  if isinstance(elt, ast.Name))
                if any(t.id == "FileNotFoundError" for t in types):
                    return True
    return False


def _check_cli_presence(tree: ast.AST, path: str, violations: list[Violation]) -> None:
    """R5: external tool subprocess calls need shutil.which or FileNotFoundError."""
    which_names = _which_tool_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _subprocess_name(node)
        if name is None:
            continue
        tool = _first_tool_token(node)
        if tool not in EXTERNAL_TOOLS:
            continue
        if tool in which_names:
            continue
        if _in_file_notfound_handler(tree, node):
            continue
        violations.append(Violation(
            path, node.lineno, "R5-cli-presence",
            f"subprocess.{name} calls external tool {tool!r} without a "
            f"shutil.which({tool!r}) guard or FileNotFoundError handling; "
            "containers raise FileNotFoundError (exit 127)"))


def _check_swallow(tree: ast.AST, path: str, violations: list[Violation]) -> None:
    """R6: except handlers that only pass/Ellipsis are silent swallows."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not node.body:
            violations.append(Violation(
                path, node.lineno, "R6-anti-swallow",
                "empty except handler swallows errors"))
            continue
        only_pass = all(
            isinstance(stmt, ast.Pass)
            or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is Ellipsis)
            for stmt in node.body)
        if only_pass:
            label = "bare except:" if node.type is None else "except:"
            violations.append(Violation(
                path, node.lineno, "R6-anti-swallow",
                f"{label} pass silently swallows errors; log, return, or "
                "re-raise honestly"))


def scan_source(path: str, content: str) -> tuple[list[Violation], int | None]:
    """Scan one .py record with all AST rules.

    Returns (violations, syntax_error_line); syntax_error_line is not None
    when the file failed to parse (the caller reports PARSE-FAIL-CLOSED).
    """
    violations: list[Violation] = []
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        return [], exc.lineno if exc.lineno is not None else 0
    _separator_concat(tree, path, violations)
    _check_cli_presence(tree, path, violations)
    _check_swallow(tree, path, violations)
    _popen_wait_chains(tree, path, violations)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _check_encoding_call(node, path, violations)
            _check_encoding_subprocess(node, path, violations)
            _check_timeout(node, path, violations)
    return violations, None


def scan_record(record: SourceRecord) -> list[Violation]:
    """Full scan of one source record (R1-R6). Non-.py files: R3 only."""
    violations: list[Violation] = []
    parts = record.path.rsplit(".", 1)
    ext = ("." + parts[1].lower()) if len(parts) == 2 else ""
    if ext == ".py":
        found, bad_line = scan_source(record.path, record.content)
        violations.extend(found)
        if bad_line is not None:
            violations.append(Violation(
                record.path, bad_line, "PARSE-FAIL-CLOSED",
                "Python file does not parse; guard cannot verify invariants"))
    if ext in CRLF_SUFFIXES:
        raw = record.content.encode("utf-8", errors="surrogateescape")
        for lineno, line in enumerate(raw.split(b"\n"), start=1):
            if line.endswith(b"\r"):
                violations.append(Violation(
                    record.path, lineno, "R3-crlf-purge",
                    "CRLF line ending; causes /bin/bash^M bad-interpreter "
                    "and command-not-found outages on Linux"))
    return violations


def scan_records(records: Sequence[SourceRecord]) -> list[Violation]:
    violations: list[Violation] = []
    for record in records:
        violations.extend(scan_record(record))
    return violations


def _needs_encoding_kwarg(call: ast.Call) -> bool:
    func = call.func
    if _open_family(call) is not None:
        return not _mode_is_binary(call)
    if isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
        return True
    return False


def _insert_kwarg(source: str, call: ast.Call, kw_text: str) -> str | None:
    lines = source.splitlines(keepends=True)
    end_line = call.end_lineno - 1
    if end_line < 0 or end_line >= len(lines):
        return None
    line = lines[end_line]
    col = (call.end_col_offset or 1) - 1
    if col < len(line) and line[col] == ")":
        head, tail = line[:col], line[col:]
        sep = "" if head.endswith("(") else ", "
        lines[end_line] = head + sep + kw_text + tail
        return "".join(lines)
    return None


def _fix_record(record: SourceRecord) -> tuple[str, list[str]]:
    """Auto-retrofit R1/R2 on one .py record. Returns (fixed_source, notes).

    Every rewrite is re-parsed before acceptance; a failed round-trip
    discards the fix and leaves the file untouched (fail-closed fixer).
    """
    if not record.path.endswith(".py"):
        return record.content, []
    notes: list[str] = []
    source = record.content
    for _round in range(64):
        try:
            tree = ast.parse(source, filename=record.path)
        except SyntaxError:
            return (record.content, []) if not notes else (record.content, [])
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _needs_encoding_kwarg(node) and _kwarg(node, "encoding") is None:
                candidate = _insert_kwarg(source, node, "encoding='utf-8'")
                if candidate is None:
                    continue
                try:
                    ast.parse(candidate, filename=record.path)
                except SyntaxError:
                    continue
                source, changed = candidate, True
                notes.append(f"R1 line {node.lineno}: added encoding='utf-8'")
                break
            name = _subprocess_name(node)
            if name in TIMEOUT_REQUIRED_FUNCS and _kwarg(node, "timeout") is None:
                candidate = _insert_kwarg(source, node, f"timeout={DEFAULT_TIMEOUT}")
                if candidate is None:
                    continue
                try:
                    ast.parse(candidate, filename=record.path)
                except SyntaxError:
                    continue
                source, changed = candidate, True
                notes.append(f"R2 line {node.lineno}: added timeout={DEFAULT_TIMEOUT}")
                break
        if not changed:
            break
    return source, notes


def fix_crlf(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")


def autofix_records(
    records: Sequence[SourceRecord],
) -> tuple[list[SourceRecord], list[str]]:
    fixed: list[SourceRecord] = []
    notes: list[str] = []
    for record in records:
        content = record.content
        if record.path.endswith(".py"):
            content, file_notes = _fix_record(record)
            notes.extend(f"{record.path}: {note}" for note in file_notes)
        parts = record.path.rsplit(".", 1)
        ext = ("." + parts[1].lower()) if len(parts) == 2 else ""
        if ext in CRLF_SUFFIXES and "\r\n" in content:
            content = fix_crlf(content)
            notes.append(f"{record.path}: R3 rewrote CRLF to LF")
        fixed.append(SourceRecord(record.path, content))
    return fixed, notes


def _parse_records(raw: str) -> list[SourceRecord]:
    data = json.loads(raw)
    if isinstance(data, Mapping):
        data = data.get("files", [])
    if not isinstance(data, list):
        raise ValueError("expected a JSON list of {path, content}")
    records = []
    for item in data:
        if not isinstance(item, Mapping) or "path" not in item or "content" not in item:
            raise ValueError("record needs 'path' and 'content'")
        records.append(SourceRecord(str(item["path"]), str(item["content"])))
    return records


def self_test() -> bool:
    # Sample sources are assembled at runtime via chr()/repr() so this
    # module stays clean under its own scan (no flaggable literals).
    BS = chr(92)   # backslash
    FS = chr(47)   # forward slash
    CRLF = chr(13) + chr(10)

    def run(src: str) -> list[Violation]:
        found, bad = scan_source("sample.py", src)
        assert bad is None, (src, bad)
        return found

    rules = {v.rule for v in [
        *run("open('f.txt')"),
        *run("open('f.txt', 'rb')"),
        *run("open('f.txt', encoding='utf-8')"),
        *run("open('f.txt', encoding='cp1252')"),
        *run("open('f.txt', 'r', encoding='UTF-8')"),
        *run("path.read_text()"),
        *run("path.write_text(data, encoding='UTF-8')"),
        *run("subprocess.run(cmd, text=True)"),
        *run("subprocess.run(cmd, text=True, encoding='utf-8')"),
        *run("subprocess.run(cmd, timeout=30)"),
        *run("subprocess.run(cmd, timeout=None)"),
        *run("subprocess.check_output(cmd)"),
    ]}
    assert rules == {"R1-utf8-encoding", "R2-subprocess-timeout"}, rules

    # Binary mode and codecs positional encoding are exempt / honored.
    assert run("open('f.bin', 'wb')\n") == []
    assert run("import codecs\ncodecs.open('f.txt', 'r', 'utf-8')\n") == []
    assert run("import io\nio.open('f.txt', encoding='utf8')\n") == []
    assert any(v.rule == "R1-utf8-encoding"
               for v in run("subprocess.run(cmd, universal_newlines=True)\n"))

    # R2 Popen chain tracking.
    popen_src = ("import subprocess\n"
                 "p = subprocess.Popen(cmd)\n"
                 "out = p.communicate()\n")
    assert [v.rule for v in run(popen_src)] == ["R2-subprocess-timeout"]
    ok_popen = ("import subprocess\n"
                "p = subprocess.Popen(cmd)\n"
                "out = p.communicate(timeout=10)\n")
    assert run(ok_popen) == []

    # R3: CRLF (byte-level).
    crlf = SourceRecord("run.sh", "echo hi" + CRLF)
    assert [v.rule for v in scan_record(crlf)] == ["R3-crlf-purge"]
    assert scan_record(SourceRecord("run.sh", "echo hi\n")) == []
    assert len(scan_record(SourceRecord("notes.md", "para" + CRLF))) == 1
    assert scan_record(SourceRecord("notes.md", "para\n")) == []

    # R4: separators (runtime-built samples).
    concat = "p = 'dir' + " + repr(FS) + " + name\n"
    assert any(v.rule == "R4-posix-path" for v in run(concat))
    back = "p = 'dir' + " + repr(BS) + " + name\n"
    assert any(v.rule == "R4-posix-path" for v in run(back))
    join = "p = " + repr(FS) + ".join(parts)\n"
    assert any(v.rule == "R4-posix-path" for v in run(join))
    split = "parts = p.split(" + repr(FS) + ")\n"
    assert any(v.rule == "R4-posix-path" for v in run(split))
    mixed = "cmd(" + repr('C:' + BS + 'dir' + FS + 'file') + ")\n"
    assert any(v.rule == "R4-posix-path" for v in run(mixed))
    assert run("p = os.path.join('dir', name)\n") == []
    assert run("p = pathlib.Path('dir') " + chr(47) + " 'x'\n") == []
    bare_url = "u = base + " + repr(FS + "api") + "\n"
    assert any(v.rule == "R4-posix-path" for v in run(bare_url))
    url_lit = "u = 'https://x' + " + repr(FS + "api") + "\n"
    assert not any(v.rule == "R4-posix-path" for v in run(url_lit))

    # R5: CLI presence.
    which = ("import shutil, subprocess\n"
             "if shutil.which('git') is None:\n"
             "    raise SystemExit(127)\n"
             "subprocess.run(['git', 'status'], timeout=30)\n")
    assert run(which) == []
    no_which = ("import subprocess\n"
                "subprocess.run(['git', 'status'], timeout=30)\n")
    assert any(v.rule == "R5-cli-presence" for v in run(no_which))
    caught = ("import subprocess\n"
              "def go():\n"
              "    try:\n"
              "        subprocess.run(['gh', 'pr'], timeout=30)\n"
              "    except FileNotFoundError:\n"
              "        return 127\n")
    assert run(caught) == []
    unknown_tool = "subprocess.run(['make', 'all'], timeout=5)\n"
    assert any(v.rule == "R5-cli-presence" for v in run(unknown_tool))

    # R6: anti-swallow.
    assert any(v.rule == "R6-anti-swallow"
               for v in run("try:\n    a()\nexcept Exception:\n    pass\n"))
    assert any(v.rule == "R6-anti-swallow"
               for v in run("try:\n    a()\nexcept:\n    pass\n"))
    assert run("try:\n    a()\nexcept Exception:\n    raise\n") == []
    assert run("try:\n    a()\nexcept Exception:\n    log.error('x')\n") == []
    assert run("try:\n    a()\nexcept FileNotFoundError:\n    code = 127\n") == []

    # Parse failure is fail-closed.
    _, bad = scan_source("broken.py", "def broken(:\n")
    assert bad is not None
    broken = [SourceRecord("broken.py", "def broken(:\n")]
    assert any(v.rule == "PARSE-FAIL-CLOSED" for v in scan_records(broken))

    # Fixer: R1 + R2 retrofit with round-trip validation.
    dirty = ("with open('a.txt') as fh:\n"
             "    data = fh.read()\n"
             "subprocess.run(['git', 'status'])\n")
    fixed, notes = autofix_records([SourceRecord("dirty.py", dirty)])
    assert "encoding='utf-8'" in fixed[0].content, fixed
    assert "timeout=30" in fixed[0].content, fixed
    assert len(notes) == 2, notes
    clean, _ = scan_source("dirty.py", fixed[0].content)
    assert [v.rule for v in clean] == ["R5-cli-presence"], clean
    binary = autofix_records([SourceRecord("b.py", "open('x', 'wb')\n")])[0]
    assert binary[0].content == "open('x', 'wb')\n"
    fixed2, notes2 = autofix_records([crlf])
    assert fixed2[0].content == "echo hi\n"
    assert notes2 == ["run.sh: R3 rewrote CRLF to LF"]
    # Idempotence.
    fixed3, _ = autofix_records(fixed)
    assert fixed3[0].content == fixed[0].content
    return True


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--files", nargs="*",
                        help="paths to scan (read from disk with utf-8)")
    parser.add_argument("--files-json",
                        help="inline JSON list of {path, content}; omit to read stdin")
    parser.add_argument("--fix", action="store_true",
                        help="auto-retrofit R1/R2/R3 (in place with --files)")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("SELF-TEST OK: cross_platform_invariant_guard")
        return EXIT_CLEAN
    if args.files:
        records = []
        for rel in args.files:
            with open(rel, "r", encoding="utf-8", errors="surrogateescape") as fh:
                records.append(SourceRecord(rel, fh.read()))
    else:
        raw = args.files_json if args.files_json else sys.stdin.read()
        try:
            records = _parse_records(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"MALFORMED INPUT (fail-closed): {exc}")
            return EXIT_MALFORMED
    if args.fix:
        records, notes = autofix_records(records)
        for note in notes:
            print("FIXED", note)
        if args.files:
            for record in records:
                with open(record.path, "w", encoding="utf-8",
                          errors="surrogateescape", newline="") as fh:
                    fh.write(record.content)
    violations = scan_records(records)
    for violation in violations:
        print(violation.format())
    if violations:
        print("CROSS-PLATFORM GUARD: BLOCKED (fail-closed)")
        return EXIT_VIOLATION
    print("CROSS-PLATFORM GUARD: clean")
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(_cli())
