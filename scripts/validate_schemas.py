#!/usr/bin/env python3
"""validate_schemas.py — lightweight, zero-dependency validation CLI for api-schemas/.

Issue #45 (feat(quality), infra-ops group): "Develop a lightweight validation
CLI script to verify all schemas in ``api-schemas/``."

What it checks
==============
1. ``*.schema.json`` files:
   - JSON syntax (errors report exact ``line:col`` from the stdlib parser).
   - Schema compliance via a structural linter over the Draft 2020-12 keyword
     subset this repository actually uses: keyword-value types are checked
     (``required`` must be a list of strings, ``properties`` an object of
     schema nodes, ``pattern`` must compile, ...), UNKNOWN keywords are
     errors (a typo such as ``requried`` silently weakens a schema — that is
     the docs-drift class of defect, applied to schemas), local ``$ref``
     pointers must resolve, ``$id`` must exist and be unique across files,
     and ``$schema`` must name a known JSON Schema draft.
   - House conventions: ``title``/``description`` presence (warning when
     missing — every schema in the repo carries both).
2. ``*.fixture.json`` files:
   - JSON syntax with exact ``line:col``.
   - ``X.fixture.json`` is validated against ``X.schema.json`` (same stem)
     when the pair exists, using an instance validator implementing the
     same Draft 2020-12 subset: ``type``, ``enum``, ``const``, string and
     numeric bounds, object/array keywords, ``allOf``/``anyOf``/``oneOf``/
     ``not``, ``if``/``then``/``else``, ``contains`` and local ``$ref``.
   - A fixture without a schema pair is a warning (pairing is a convention,
     not yet a registry); a schema without fixtures is fine.
3. Exit codes (issue acceptance): 0 = all pass; 1 = at least one error,
   with every error line reporting file, best-effort line number, and the
   JSON Pointer of the offending location.

Integration note (acceptance criterion 2)
=========================================
DELIVERED: ``scripts/agents/continuous_agent_loop.py`` step 6 tier-2
("JSON Schema Parse") now fail-closed-delegates api-schemas/ deep
validation to this CLI whenever both the script and the ``api-schemas/``
directory are present, running alongside the existing JSON syntax parse.
The CLI remains an intentional drop-in: zero dependencies, stdlib only,
deterministic exit codes, no network. (The integration originally shipped
as a follow-up because the Touching-Files scope gate for issue #45 listed
only this file plus its test suite; the loop-file change landed under the
same governing issue #45.)

Usage
=====
    python scripts/validate_schemas.py                # validate api-schemas/
    python scripts/validate_schemas.py --dir DIR      # other directory
    python scripts/validate_schemas.py --file A B     # specific files
    python scripts/validate_schemas.py --self-test    # guard-the-guard

Fail-closed doctrine: unknown keyword -> error, unresolved $ref -> error,
unknown $schema draft -> error. Skipped checks do not exist — a file that
cannot be read is an error, never a silent pass (AGENT_RULES.md §13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KNOWN_DRAFTS = {
    "https://json-schema.org/draft/2020-12/schema",
    "https://json-schema.org/draft/2019-09/schema",
    "http://json-schema.org/draft-07/schema#",
    "http://json-schema.org/draft-04/schema#",
}

# Keywords the validator understands. Anything else that is not an annotation
# is reported as an unknown-keyword error (closed-set, typo guard).
ANNOTATION_KEYWORDS = {
    "title", "description", "default", "examples", "$comment",
    "deprecated", "readOnly", "writeOnly", "$schema", "$id", "$anchor",
}
VALIDATION_KEYWORDS = {
    "type", "enum", "const", "format",
    "required", "properties", "additionalProperties", "propertyNames",
    "patternProperties", "minProperties", "maxProperties",
    "items", "prefixItems", "additionalItems", "minItems", "maxItems",
    "uniqueItems", "contains", "minContains", "maxContains",
    "minLength", "maxLength", "pattern",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
    "$ref", "$defs", "definitions",  # legacy draft-07 container: tolerated
}
FORMAT_CHECKS = {
    "date-time": re.compile(
        r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"),
    "uri": re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$"),
    "uri-reference": re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$|^[/#?][^\s]*$"),
    "regex": None,  # compiled via re.compile at check time
}

MAX_DEPTH = 64  # recursion guard: schema trees deeper than this refuse to walk


class Finding:
    """One validation finding. `line` is exact for syntax errors and
    best-effort (token search) for semantic errors — reported honestly."""

    __slots__ = ("severity", "file", "line", "col", "pointer", "message")

    def __init__(self, severity: str, file: str, message: str,
                 line: Optional[int] = None, col: Optional[int] = None,
                 pointer: str = "") -> None:
        self.severity, self.file, self.message = severity, file, message
        self.line, self.col, self.pointer = line, col, pointer

    def render(self) -> str:
        where = f"{self.file}"
        if self.line is not None:
            where += f":{self.line}"
            if self.col is not None:
                where += f":{self.col}"
        if self.pointer:
            where += f" (pointer: {self.pointer})"
        return f"{self.severity} {where}: {self.message}"


def _line_of(raw: str, pointer: str) -> Optional[int]:
    """Best-effort line number for a JSON Pointer: walk the raw text looking
    for each segment as a quoted key in order. Works on the 2-space-indented
    files this repo ships; returns None when a segment cannot be located
    (never guesses silently — callers may omit the line)."""
    if not pointer or pointer == "/":
        return None
    pos = 0
    for seg in [s for s in pointer.split("/") if s != ""]:
        token = '"%s"' % seg.replace("~1", "/").replace("~0", "~")
        found = raw.find(token, pos)
        if found < 0:
            return None
        pos = found + len(token)
    return raw.count("\n", 0, pos) + 1


def _type_ok(value: Any, typ: str) -> bool:
    checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        # JSON "integer" excludes booleans (Python bool is an int subclass)
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    fn = checks.get(typ)
    return fn(value) if fn else False


class SchemaValidator:
    """Instance validator for the repository's Draft 2020-12 keyword subset."""

    def __init__(self, root_schema: Dict[str, Any]) -> None:
        self.root = root_schema
        self.errors: List[Tuple[str, str]] = []  # (pointer, message)

    def validate(self, doc: Any) -> List[Tuple[str, str]]:
        self.errors = []
        self._node(doc, self.root, "", 0)
        return self.errors

    def _node(self, value: Any, schema: Any, pointer: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            self.errors.append((pointer, f"schema nesting exceeds {MAX_DEPTH} levels (recursion guard)"))
            return
        if schema is True:
            return
        if schema is False:
            self.errors.append((pointer, "schema is `false`: no value permitted here"))
            return
        if not isinstance(schema, dict):
            self.errors.append((pointer, f"schema node must be an object, got {type(schema).__name__}"))
            return

        ref = schema.get("$ref")
        if isinstance(ref, str):
            target = self._resolve(ref)
            if target is None:
                self.errors.append((pointer, f"unresolvable $ref '{ref}'"))
                return
            self._node(value, target, pointer, depth + 1)
            # $ref + siblings: 2020-12 allows siblings; validate them too
            siblings = {k: v for k, v in schema.items() if k != "$ref"}
            if siblings:
                self._node(value, siblings, pointer, depth + 1)
            return

        # type
        t = schema.get("type")
        types = t if isinstance(t, list) else ([t] if t else [])
        if types and not any(_type_ok(value, x) for x in types):
            got = type(value).__name__
            self.errors.append((pointer, f"expected type {'/'.join(map(str, types))}, got {got}"))
            return

        # enum / const
        if "enum" in schema and value not in schema["enum"]:
            self.errors.append((pointer, f"value {json.dumps(value)[:60]} not in enum {json.dumps(schema['enum'])[:120]}"))
        if "const" in schema and value != schema["const"]:
            self.errors.append((pointer, f"value does not equal const {json.dumps(schema['const'])[:60]}"))

        # string / numeric bounds
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                self.errors.append((pointer, f"string shorter than minLength {schema['minLength']}"))
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                self.errors.append((pointer, f"string longer than maxLength {schema['maxLength']}"))
            if "pattern" in schema and not re.search(schema["pattern"], value):
                self.errors.append((pointer, f"string does not match pattern {schema['pattern']!r}"))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                self.errors.append((pointer, f"value < minimum {schema['minimum']}"))
            if "maximum" in schema and value > schema["maximum"]:
                self.errors.append((pointer, f"value > maximum {schema['maximum']}"))
            if schema.get("exclusiveMinimum") is not None and value <= schema["exclusiveMinimum"]:
                self.errors.append((pointer, f"value <= exclusiveMinimum {schema['exclusiveMinimum']}"))
            if schema.get("exclusiveMaximum") is not None and value >= schema["exclusiveMaximum"]:
                self.errors.append((pointer, f"value >= exclusiveMaximum {schema['exclusiveMaximum']}"))
            if "multipleOf" in schema and schema["multipleOf"] and value % schema["multipleOf"] != 0:
                self.errors.append((pointer, f"value not a multiple of {schema['multipleOf']}"))

        # format (best-effort assertions)
        fmt = schema.get("format")
        if isinstance(value, str) and isinstance(fmt, str):
            pat = FORMAT_CHECKS.get(fmt)
            if pat is None and fmt == "regex":
                try:
                    re.compile(value)
                except re.error as exc:
                    self.errors.append((pointer, f"format 'regex' does not compile: {exc}"))
            elif pat is not None and not pat.match(value):
                self.errors.append((pointer, f"format '{fmt}' violated"))

        # object keywords
        if isinstance(value, dict):
            for req in schema.get("required", []) or []:
                if req not in value:
                    self.errors.append((pointer, f"missing required property '{req}'"))
            props = schema.get("properties", {}) or {}
            for key, sub in props.items():
                if key in value:
                    self._node(value[key], sub, f"{pointer}/{key}", depth + 1)
            pattern_props = schema.get("patternProperties", {}) or {}
            for key, sub in pattern_props.items():
                try:
                    rx = re.compile(key)
                except re.error as exc:
                    self.errors.append((pointer, f"patternProperties key {key!r} does not compile: {exc}"))
                    continue
                for vk in value:
                    if rx.search(vk):
                        self._node(value[vk], sub, f"{pointer}/{vk}", depth + 1)
            addl = schema.get("additionalProperties", True)
            if addl is not True:
                compiled_pats = []
                for pk in pattern_props:
                    try:
                        compiled_pats.append(re.compile(pk))
                    except re.error:
                        pass  # already reported by the loop above / by the linter
                for key in value:
                    if key in props:
                        continue
                    if any(rx.search(key) for rx in compiled_pats):
                        continue
                    if addl is False:
                        self.errors.append((f"{pointer}/{key}", "additional property not allowed by additionalProperties: false"))
                    else:
                        self._node(value[key], addl, f"{pointer}/{key}", depth + 1)
            pn = schema.get("propertyNames")
            if isinstance(pn, dict) and "pattern" in pn:
                for key in value:
                    if not re.search(pn["pattern"], key):
                        self.errors.append((f"{pointer}/{key}", f"property name violates propertyNames pattern {pn['pattern']!r}"))
            if "minProperties" in schema and len(value) < schema["minProperties"]:
                self.errors.append((pointer, f"fewer than minProperties {schema['minProperties']}"))
            if "maxProperties" in schema and len(value) > schema["maxProperties"]:
                self.errors.append((pointer, f"more than maxProperties {schema['maxProperties']}"))

        # array keywords
        if isinstance(value, list):
            items = schema.get("items")
            prefix = schema.get("prefixItems")
            if prefix:
                for i, sub in enumerate(prefix[:len(value)]):
                    self._node(value[i], sub, f"{pointer}/{i}", depth + 1)
                items = schema.get("items") if len(value) > len(prefix) else None
                start = len(prefix)
            else:
                start = 0
            if isinstance(items, dict):
                for i in range(start, len(value)):
                    self._node(value[i], items, f"{pointer}/{i}", depth + 1)
            elif items is False and len(value) > (len(prefix) if prefix else 0):
                self.errors.append((pointer, "additional array items not allowed"))
            if "minItems" in schema and len(value) < schema["minItems"]:
                self.errors.append((pointer, f"fewer than minItems {schema['minItems']}"))
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                self.errors.append((pointer, f"more than maxItems {schema['maxItems']}"))
            if schema.get("uniqueItems") is True:
                try:
                    seen = [json.dumps(x, sort_keys=True) for x in value]
                except TypeError:
                    seen = None
                if seen and len(seen) != len(set(seen)):
                    self.errors.append((pointer, "array items are not unique (uniqueItems: true)"))
            if "contains" in schema:
                sub = schema["contains"]
                matched = sum(1 for x in value if self._probe(x, sub, depth))
                want = schema.get("minContains", 1)
                if matched < want:
                    self.errors.append((pointer, f"contains matched {matched} items, needs >= {want}"))
                if "maxContains" in schema and matched > schema["maxContains"]:
                    self.errors.append((pointer, f"contains matched {matched} items, needs <= {schema['maxContains']}"))

        # combinators
        for key in ("allOf", "anyOf", "oneOf"):
            if key in schema:
                if key == "allOf":
                    # every branch must hold; per-branch errors are the report
                    for sub in schema[key]:
                        self._node(value, sub, pointer, depth + 1)
                    continue
                # anyOf/oneOf: branch attempts are isolated probes — errors
                # from non-matching branches are diagnostic noise, only the
                # combinator verdict is reported (fail-honest, not fail-noisy)
                results = [self._probe(value, sub, depth) for sub in schema[key]]
                if key == "anyOf" and not any(results):
                    self.errors.append((pointer, f"anyOf: none of {len(results)} branches matched"))
                elif key == "oneOf" and results.count(True) != 1:
                    self.errors.append((pointer, f"oneOf: {results.count(True)} of {len(results)} branches matched, exactly 1 required"))
        if "not" in schema:
            # `not` means: the value must NOT validate against the embedded
            # schema. _probe returns True when it does — that is the violation.
            if self._probe(value, schema["not"], depth):
                self.errors.append((pointer, "value matches `not` schema"))
        if "if" in schema:
            # _probe returns True when the value validates against the `if`
            # schema — i.e. the condition MATCHES (Draft 2020-12 §10.2.4).
            matches = self._probe(value, schema["if"], depth)
            branch = schema.get("then") if matches else schema.get("else")
            if branch is not None:
                self._node(value, branch, pointer, depth + 1)

    def _probe(self, value: Any, schema: Any, depth: int) -> bool:
        """Dry-run: True when the value does NOT produce errors against schema."""
        saved = self.errors
        self.errors = []
        try:
            self._node(value, schema, "", depth + 1)
            return not self.errors
        finally:
            self.errors = saved

    def _resolve(self, ref: str) -> Optional[Any]:
        if not ref.startswith("#"):
            return None  # external refs are lint findings, not fetch targets (offline doctrine)
        node: Any = self.root
        for raw_seg in ref.lstrip("#/").split("/") if ref not in ("#", "") else []:
            seg = raw_seg.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and seg in node:
                node = node[seg]
            else:
                return None
        return node


# ---------------------------------------------------------------------------
# Schema-document linter (meta checks on *.schema.json files)
# ---------------------------------------------------------------------------

def _lint_schema_node(node: Any, path: str, file: str, findings: List[Finding],
                      root: Dict[str, Any], depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        findings.append(Finding("ERROR", file, f"schema nesting exceeds {MAX_DEPTH} at {path}", pointer=path))
        return
    if not isinstance(node, dict):
        findings.append(Finding("ERROR", file, f"schema node at {path} must be an object, got {type(node).__name__}", pointer=path))
        return
    for key, val in node.items():
        loc = f"{path}/{key}"
        if key in ANNOTATION_KEYWORDS or key in VALIDATION_KEYWORDS:
            pass
        else:
            findings.append(Finding(
                "ERROR", file,
                f"unknown keyword '{key}' (typo guard over the repo's Draft 2020-12 subset)",
                line=_line_of(json.dumps(node, ensure_ascii=False), ""), pointer=loc))
            continue
        # keyword value checks
        if key == "type":
            ok = isinstance(val, str) and val in {"object", "array", "string", "integer", "number", "boolean", "null"}
            ok = ok or (isinstance(val, list) and all(isinstance(x, str) and x in {"object", "array", "string", "integer", "number", "boolean", "null"} for x in val))
            if not ok:
                findings.append(Finding("ERROR", file, f"'type' must be a type name or list of type names, got {json.dumps(val)[:60]}", pointer=loc))
        elif key == "required":
            if not (isinstance(val, list) and all(isinstance(x, str) for x in val)):
                findings.append(Finding("ERROR", file, "'required' must be a list of strings", pointer=loc))
        elif key in ("properties", "patternProperties", "$defs", "definitions"):
            if not isinstance(val, dict):
                findings.append(Finding("ERROR", file, f"'{key}' must be an object", pointer=loc))
            else:
                for k2, sub in val.items():
                    _lint_schema_node(sub, f"{loc}/{k2}", file, findings, root, depth + 1)
        elif key in ("items", "additionalProperties", "propertyNames", "contains", "not", "if", "then", "else"):
            if isinstance(val, (dict, bool)):
                if isinstance(val, dict):
                    _lint_schema_node(val, loc, file, findings, root, depth + 1)
            else:
                findings.append(Finding("ERROR", file, f"'{key}' must be a schema object or boolean", pointer=loc))
        elif key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            if not isinstance(val, list) or not val:
                findings.append(Finding("ERROR", file, f"'{key}' must be a non-empty list of schemas", pointer=loc))
            else:
                for i, sub in enumerate(val):
                    _lint_schema_node(sub, f"{loc}/{i}", file, findings, root, depth + 1)
        elif key == "format":
            if not isinstance(val, str):
                findings.append(Finding("ERROR", file, "'format' must be a string", pointer=loc))
            elif val not in FORMAT_CHECKS and val != "regex":
                findings.append(Finding("WARNING", file, f"format '{val}' has no local checker (best-effort only: {sorted(FORMAT_CHECKS)}), not validated", pointer=loc))
        elif key in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties", "minContains", "maxContains"):
            if not (isinstance(val, int) and not isinstance(val, bool) and val >= 0):
                findings.append(Finding("ERROR", file, f"'{key}' must be a non-negative integer", pointer=loc))
        elif key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
            if not (isinstance(val, (int, float)) and not isinstance(val, bool)):
                findings.append(Finding("ERROR", file, f"'{key}' must be a number", pointer=loc))
            if key == "multipleOf" and val == 0:
                findings.append(Finding("ERROR", file, "'multipleOf' must not be 0", pointer=loc))
        elif key in ("pattern", "propertyNames-pattern"):
            if key == "pattern" and not isinstance(val, str):
                findings.append(Finding("ERROR", file, "'pattern' must be a string", pointer=loc))
            else:
                try:
                    re.compile(val)
                except re.error as exc:
                    findings.append(Finding("ERROR", file, f"'pattern' does not compile: {exc}", pointer=loc))
        elif key == "uniqueItems" and not isinstance(val, bool):
            findings.append(Finding("ERROR", file, "'uniqueItems' must be a boolean", pointer=loc))
        elif key == "additionalItems" and not isinstance(val, (dict, bool)):
            findings.append(Finding("ERROR", file, "'additionalItems' must be a schema object or boolean", pointer=loc))
        elif key == "$ref":
            if not isinstance(val, str) or not val:
                findings.append(Finding("ERROR", file, "'$ref' must be a non-empty string", pointer=loc))
            elif val.startswith("#"):
                target = SchemaValidator(root)._resolve(val) if root else None
                if target is None:
                    findings.append(Finding("ERROR", file, f"local $ref '{val}' does not resolve", pointer=loc))
            # external refs: warning (offline doctrine, no fetching)
            else:
                findings.append(Finding("WARNING", file, f"external $ref '{val}' cannot be validated offline", pointer=loc))
        elif key == "enum" and not isinstance(val, list):
            findings.append(Finding("ERROR", file, "'enum' must be a non-empty list", pointer=loc))


def check_schema_file(path: Path, seen_ids: Dict[str, str],
                      findings: List[Finding]) -> Optional[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        findings.append(Finding("ERROR", str(path), f"JSON syntax error: {exc.msg}", line=exc.lineno, col=exc.colno))
        return None
    if not isinstance(doc, dict):
        findings.append(Finding("ERROR", str(path), "schema root must be a JSON object"))
        return doc if isinstance(doc, (dict, list)) else None

    if "$schema" not in doc:
        findings.append(Finding("ERROR", str(path), "missing '$schema' (must declare a JSON Schema draft)", pointer="/$schema"))
    elif doc["$schema"] not in KNOWN_DRAFTS:
        findings.append(Finding("ERROR", str(path), f"unknown $schema draft '{doc['$schema']}' (expected one of the official drafts)", pointer="/$schema"))

    sid = doc.get("$id")
    if not sid or not isinstance(sid, str):
        findings.append(Finding("ERROR", str(path), "missing or empty '$id' (every published schema carries a stable identity)", pointer="/$id"))
    else:
        if sid in seen_ids:
            findings.append(Finding("ERROR", str(path), f"duplicate $id '{sid}' also declared by {seen_ids[sid]} (copy-paste identity bug)", pointer="/$id"))
        seen_ids[sid] = str(path)

    for convention in ("title", "description"):
        if convention not in doc:
            findings.append(Finding("WARNING", str(path), f"missing '{convention}' (house convention: both shipped schemas carry it)", pointer=f"/{convention}"))

    _lint_schema_node(doc, "", str(path), findings, doc)
    return doc


def check_fixture_file(path: Path, schema_by_stem: Dict[str, Dict[str, Any]],
                       findings: List[Finding]) -> None:
    raw = path.read_text(encoding="utf-8")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        findings.append(Finding("ERROR", str(path), f"JSON syntax error: {exc.msg}", line=exc.lineno, col=exc.colno))
        return
    schema = schema_by_stem.get(path.stem.replace(".fixture", ""))
    if schema is None:
        findings.append(Finding("WARNING", str(path), "no matching *.schema.json for this fixture (naming convention: X.fixture.json <-> X.schema.json)"))
        return
    errs = SchemaValidator(schema).validate(doc)
    for pointer, message in errs:
        findings.append(Finding("ERROR", str(path), message, line=_line_of(raw, pointer), pointer=pointer or "/"))


# ---------------------------------------------------------------------------
# Self-test (guard-the-guard, offline, deterministic)
# ---------------------------------------------------------------------------

def _self_test() -> int:
    import tempfile

    def run_files(files: Dict[str, str]) -> Tuple[int, List[str]]:
        with tempfile.TemporaryDirectory() as td:
            tdpath = Path(td)
            for name, content in files.items():
                (tdpath / name).write_text(content, encoding="utf-8")
            code, findings = _validate_dir(tdpath)
            return code, [f.render() for f in findings]

    checks: List[Tuple[str, bool]] = []

    # 1. valid schema + matching valid fixture -> exit 0
    good = {
        "a.schema.json": json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.test/a.schema.json", "title": "A", "description": "d",
            "type": "object", "required": ["x"], "additionalProperties": False,
            "properties": {"x": {"type": "integer", "minimum": 1}},
        }),
        "a.fixture.json": json.dumps({"x": 2}),
    }
    code, out = run_files(good)
    checks.append(("valid pair exits 0", code == 0))

    # 2. fixture violation -> exit 1, pointer recorded
    bad_pair = dict(good)
    bad_pair["a.fixture.json"] = json.dumps({"x": "nope"})
    code, out = run_files(bad_pair)
    checks.append(("fixture type violation exits 1", code == 1 and any("expected type integer" in o for o in out)))

    # 3. syntax error reports exact line (error token is the `}` on line 4)
    syntax = dict(good)
    syntax["a.schema.json"] = '{\n  "$id": "x",\n  "oops"\n}'
    code, out = run_files(syntax)
    checks.append(("syntax error carries line 4", code == 1 and any("a.schema.json:4" in o for o in out)))

    # 4. typo keyword guard
    typo = dict(good)
    typo["a.schema.json"] = good["a.schema.json"].replace('"required"', '"requried"')
    code, out = run_files(typo)
    checks.append(("typo'd keyword flagged", code == 1 and any("unknown keyword 'requried'" in o for o in out)))

    # 5. broken local $ref flagged
    ref = dict(good)
    ref["a.schema.json"] = good["a.schema.json"].replace('"minimum": 1', '"$ref": "#/$defs/nope"')
    code, out = run_files(ref)
    checks.append(("broken $ref flagged", code == 1 and any("does not resolve" in o for o in out)))

    # 6. duplicate $id flagged
    dup = dict(good)
    dup["b.schema.json"] = good["a.schema.json"].replace('"title": "A"', '"title": "B"')
    code, out = run_files(dup)
    checks.append(("duplicate $id flagged", code == 1 and any("duplicate $id" in o for o in out)))

    # 7. unpaired fixture is a warning, still exit 0
    lone = {"orphan.fixture.json": json.dumps({"any": "thing"})}
    code, out = run_files(lone)
    checks.append(("unpaired fixture warns but exits 0", code == 0 and any("no matching" in o for o in out)))

    # 8. if/then/else cross-field works (guardian-style contract)
    cond = {
        "c.schema.json": json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.test/c.schema.json", "title": "C", "description": "d",
            "type": "object",
            "properties": {"decision": {"enum": ["PASS", "HOLD"]}, "healing": {"type": "array"}},
            "allOf": [{"if": {"properties": {"decision": {"const": "HOLD"}}},
                       "then": {"required": ["healing"]}}],
        }),
        "c.fixture.json": json.dumps({"decision": "PASS"}),
    }
    code, out = run_files(cond)
    checks.append(("if/then/else PASS branch ok", code == 0))
    cond["c.fixture.json"] = json.dumps({"decision": "HOLD"})
    code, out = run_files(cond)
    checks.append(("if/then/else missing healing rejected", code == 1 and any("missing required property 'healing'" in o for o in out)))

    # 9. contains/minContains/maxContains verdict (regression guard: the
    #    verdict used to count non-matching items, so a fixture with zero
    #    matching items passed and an all-matching fixture errored)
    contains_base = {
        "k.schema.json": json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.test/k.schema.json", "title": "K", "description": "d",
            "type": "array", "contains": {"const": "x"}, "minContains": 1,
        }),
    }
    code, out = run_files({**contains_base, "k.fixture.json": json.dumps([1, 2, 3])})
    checks.append(("contains zero-match rejected", code == 1 and any("contains matched 0 items" in o for o in out)))
    code, out = run_files({**contains_base, "k.fixture.json": json.dumps(["x", "x", "x"])})
    checks.append(("contains all-match accepted", code == 0))
    maxc_schema = json.loads(contains_base["k.schema.json"])
    maxc_schema["maxContains"] = 1
    code, out = run_files({"k.schema.json": json.dumps(maxc_schema), "k.fixture.json": json.dumps(["x", "x"])})
    checks.append(("maxContains breach rejected", code == 1 and any("needs <= 1" in o for o in out)))

    # 10. real repo schemas pass (integration smoke; skipped when run outside repo)
    repo_dir = Path(__file__).resolve().parent.parent / "api-schemas"
    if repo_dir.is_dir():
        code, out = _validate_dir(repo_dir)
        checks.append(("repo api-schemas/ exits 0", code == 0))

    failed = 0
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} | {name}")
        failed += 0 if ok else 1
    print(f"Self-test: {len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _validate_dir(directory: Path) -> Tuple[int, List[Finding]]:
    findings: List[Finding] = []
    seen_ids: Dict[str, str] = {}
    schemas: Dict[str, Dict[str, Any]] = {}
    schema_files = sorted(directory.glob("*.schema.json"))
    fixture_files = sorted(directory.glob("*.fixture.json"))
    for p in schema_files:
        doc = check_schema_file(p, seen_ids, findings)
        if doc is not None:
            schemas[p.stem.replace(".schema", "")] = doc
    for p in fixture_files:
        check_fixture_file(p, schemas, findings)
    errors = [f for f in findings if f.severity == "ERROR"]
    return (1 if errors else 0), findings


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate api-schemas/ schema and fixture files (issue #45).")
    ap.add_argument("--dir", default=None, help="directory containing *.schema.json / *.fixture.json (default: <repo>/api-schemas)")
    ap.add_argument("--file", nargs="+", default=None, help="validate specific files instead of a directory")
    ap.add_argument("--self-test", action="store_true", help="guard-the-guard: run embedded deterministic fixtures")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.file:
        findings: List[Finding] = []
        seen_ids: Dict[str, str] = {}
        schemas: Dict[str, Dict[str, Any]] = {}
        paths = [Path(x) for x in args.file]
        for p in paths:
            if p.name.endswith(".schema.json"):
                doc = check_schema_file(p, seen_ids, findings)
                if doc is not None:
                    schemas[p.stem.replace(".schema", "")] = doc
        for p in paths:
            if p.name.endswith(".fixture.json"):
                check_fixture_file(p, schemas, findings)
    else:
        d = Path(args.dir) if args.dir else Path(__file__).resolve().parent.parent / "api-schemas"
        if not d.is_dir():
            print(f"ERROR {d}: directory does not exist")
            return 1
        code, findings = _validate_dir(d)

    errors = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARNING"]
    for f in findings:
        print(f.render())
    print(f"Schema validation summary: errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
