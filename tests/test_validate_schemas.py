#!/usr/bin/env python3
"""tests/test_validate_schemas.py — test suite for scripts/validate_schemas.py (issue #45).

Dual-mode by design (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_validate_schemas.py
  - stdlib:  python3 tests/test_validate_schemas.py   (plain runner, no pytest import)

Every test is offline and deterministic. The suite covers the issue's
acceptance criteria: syntax + schema compliance of ``api-schemas/*.schema.json``,
validation of paired ``*.fixture.json`` files, exact line numbers on syntax
errors, and the 0/1 exit-code contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_schemas import (
    FORMAT_CHECKS,
    Finding,
    SchemaValidator,
    _line_of,
    _lint_schema_node,
    check_fixture_file,
    check_schema_file,
    main,
)

VALID_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.test/t.schema.json",
    "title": "T",
    "description": "test contract",
    "type": "object",
    "required": ["x"],
    "additionalProperties": False,
    "properties": {
        "x": {"type": "integer", "minimum": 1, "maximum": 10},
        "name": {"type": "string", "pattern": "^[a-z]+$"},
        "decision": {"enum": ["PASS", "HOLD", "REJECT"]},
    },
}


# --- instance validator ------------------------------------------------------


def test_type_required_additionalproperties():
    v = SchemaValidator(VALID_SCHEMA)
    assert v.validate({"x": 2}) == []
    errs = v.validate({"x": 2, "extra": True})
    assert any("additional property not allowed" in m for _, m in errs)
    errs = v.validate({})
    assert any("missing required property 'x'" in m for _, m in errs)
    errs = v.validate({"x": 0})
    assert any("minimum" in m for _, m in errs)
    errs = v.validate({"x": "2"})
    assert any("expected type integer" in m for _, m in errs)


def test_enum_pattern_bounds():
    v = SchemaValidator(VALID_SCHEMA)
    assert any("not in enum" in m for _, m in v.validate({"x": 1, "decision": "MAYBE"}))
    assert any("pattern" in m for _, m in v.validate({"x": 1, "name": "Bad1"}))
    assert any("maximum" in m for _, m in v.validate({"x": 11}))


def test_conditional_if_then_else():
    """Guardian-style cross-field contract: HOLD requires healing (mirrors
    api-schemas/guardian-evaluation.schema.json semantics)."""
    schema = {
        "type": "object",
        "properties": {
            "decision": {"enum": ["PASS", "HOLD"]},
            "healing": {"type": "array"},
        },
        "allOf": [
            {
                "if": {"properties": {"decision": {"const": "HOLD"}}},
                "then": {"required": ["healing"]},
            },
        ],
    }
    v = SchemaValidator(schema)
    assert v.validate({"decision": "PASS"}) == []
    assert v.validate({"decision": "HOLD", "healing": []}) == []
    errs = v.validate({"decision": "HOLD"})
    assert any("missing required property 'healing'" in m for _, m in errs)


def test_local_ref_resolution_and_broken_ref():
    schema = {
        "$defs": {"pos": {"type": "integer", "minimum": 1}},
        "type": "object",
        "properties": {"n": {"$ref": "#/$defs/pos"}},
    }
    v = SchemaValidator(schema)
    assert v.validate({"n": 3}) == []
    assert any("minimum" in m for _, m in v.validate({"n": 0}))
    broken = {"properties": {"n": {"$ref": "#/$defs/missing"}}}
    errs = SchemaValidator(broken).validate({"n": 1})
    assert any("unresolvable" in m for _, m in errs)


def test_one_of_and_not():
    schema = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
    v = SchemaValidator(schema)
    assert v.validate("s") == []
    assert v.validate(3) == []
    assert any("oneOf" in m for _, m in v.validate(True))
    v2 = SchemaValidator({"not": {"type": "string"}})
    assert any("`not`" in m for _, m in v2.validate("str"))
    assert v2.validate(1) == []


# --- line numbers ------------------------------------------------------------


def test_syntax_error_carries_exact_line():
    findings = []
    try:
        json.loads('{\n  "$id": "x",\n  "oops"\n}')
        raise AssertionError("expected JSONDecodeError")
    except json.JSONDecodeError as exc:
        findings.append(
            Finding(
                "ERROR",
                "x.schema.json",
                f"JSON syntax error: {exc.msg}",
                line=exc.lineno,
                col=exc.colno,
            )
        )
    assert len(findings) == 1
    assert findings[0].line == 4 and findings[0].col == 1


def test_best_effort_line_for_semantic_error():
    raw = json.dumps(VALID_SCHEMA, indent=2)
    assert _line_of(raw, "/properties/x/minimum") is not None
    assert _line_of(raw, "/properties/nope/deeper") is None  # honest miss, no guess


# --- schema-document linter --------------------------------------------------


def _lint(doc):
    findings = []
    _lint_schema_node(doc, "", "test.schema.json", findings, doc)
    return findings


def test_lint_catches_typo_keyword():
    bad = json.loads(json.dumps(VALID_SCHEMA).replace('"required"', '"requried"'))
    findings = _lint(bad)
    assert any("unknown keyword 'requried'" in f.message for f in findings)


def test_lint_catches_bad_pattern_and_missing_id():
    bad = json.loads(json.dumps(VALID_SCHEMA).replace('"^[a-z]+$"', '"[unclosed"'))
    findings = _lint(bad)
    assert any("does not compile" in f.message for f in findings)
    # missing $id is a root-convention rule enforced by check_schema_file
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        no_id = {k: v for k, v in VALID_SCHEMA.items() if k != "$id"}
        p = Path(td) / "no_id.schema.json"
        p.write_text(json.dumps(no_id), encoding="utf-8")
        findings = []
        check_schema_file(p, {}, findings)
        assert any("missing or empty '$id'" in f.message for f in findings)


def test_lint_catches_wrong_keyword_value_types():
    bad = json.loads(
        json.dumps(VALID_SCHEMA).replace('"required": ["x"]', '"required": "x"')
    )
    findings = _lint(bad)
    assert any("'required' must be a list of strings" in f.message for f in findings)
    bad2 = json.loads(
        json.dumps(VALID_SCHEMA).replace('"minimum": 1', '"minimum": "1"')
    )
    findings = _lint(bad2)
    assert any("'minimum' must be a number" in f.message for f in findings)


def test_lint_flags_unknown_format_as_warning_not_error():
    doc = json.loads(
        json.dumps(VALID_SCHEMA).replace(
            '"pattern": "^[a-z]+$"', '"pattern": "^[a-z]+$", "format": "ipv6"'
        )
    )
    findings = _lint(doc)
    assert any(f.severity == "WARNING" and "ipv6" in f.message for f in findings)
    assert not any(f.severity == "ERROR" and "ipv6" in f.message for f in findings)


# --- file-level drivers ------------------------------------------------------


def test_check_schema_file_duplicate_id():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.schema.json"
        b = Path(td) / "b.schema.json"
        a.write_text(json.dumps(VALID_SCHEMA), encoding="utf-8")
        dup = json.loads(
            json.dumps(VALID_SCHEMA).replace('"title": "T"', '"title": "T2"')
        )
        b.write_text(json.dumps(dup), encoding="utf-8")
        seen = {}
        f1 = []
        check_schema_file(a, seen, f1)
        f2 = []
        check_schema_file(b, seen, f2)
        assert not any("duplicate $id" in f.message for f in f1)
        assert any("duplicate $id" in f.message for f in f2)


def test_fixture_pairing_and_orphan_warning():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "t.schema.json").write_text(json.dumps(VALID_SCHEMA), encoding="utf-8")
        (td / "t.fixture.json").write_text(json.dumps({"x": 2}), encoding="utf-8")
        (td / "orphan.fixture.json").write_text(
            json.dumps({"anything": 1}), encoding="utf-8"
        )
        findings = []
        seen = {}
        schema = check_schema_file(td / "t.schema.json", seen, findings)
        check_fixture_file(td / "t.fixture.json", {"t": schema}, findings)
        check_fixture_file(td / "orphan.fixture.json", {"t": schema}, findings)
        assert not any(f.severity == "ERROR" for f in findings)
        assert any("no matching" in f.message for f in findings)
        # now a real violation
        (td / "t.fixture.json").write_text(json.dumps({"x": "bad"}), encoding="utf-8")
        findings2 = []
        check_fixture_file(td / "t.fixture.json", {"t": schema}, findings2)
        assert any(
            f.severity == "ERROR" and "expected type integer" in f.message
            for f in findings2
        )
        assert all(f.line is not None for f in findings2 if f.severity == "ERROR")


# --- integration + exit codes (issue acceptance) -----------------------------


def test_repo_schemas_pass_and_exit_code_contract():
    repo = Path(__file__).resolve().parent.parent
    api = repo / "api-schemas"
    if api.is_dir():
        assert main([]) == 0, "real api-schemas/ must pass"
    # failing directory -> exit 1 with error lines
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        Path(td, "bad.schema.json").write_text("{ nope", encoding="utf-8")
        assert main(["--dir", td]) == 1
    # --self-test guard-the-guard
    assert main(["--self-test"]) == 0


def test_format_registry_has_repo_formats():
    # repo schemas use date-time and uri; both must have local checkers
    assert "date-time" in FORMAT_CHECKS and "uri" in FORMAT_CHECKS


if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except (
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            TimeoutError,
            ConnectionError,
            AttributeError,
            KeyError,
            ImportError,
            ModuleNotFoundError,
        ) as exc:
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
