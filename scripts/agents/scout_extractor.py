#!/usr/bin/env python3
"""S11 — Surgical Code & Pattern Extraction Engine (issue #498).

The extraction arm of the Ecosystem Scout. Companion of #489 (S09 dispatch
matrix), #497 (S10 scout agent) — advances both.

Workflow ("কতটুকু দরকার, কীভাবে দরকার — সার্জিক্যাল এক্সট্রাকশন ইঞ্জিন"):

    DIMENSION 1 "কতটুকু দরকার"  — need-driven scope slicing:
        isolate the 1% Gold Algorithm (20-100 lines of pure logic),
        discard the 99% bloat (GUI, CLI, heavy engines).
    DIMENSION 2 "কীভাবে দরকার" — native zero-bloat fitting:
        strip foreign dependencies, re-write in native TS/Python,
        enforce fail-closed error contracts.

Deterministic, fail-closed contract:

  * `extract_python_slice` / `extract_typescript_slice` locate a target
    function/class and return the exact source segment with its imports —
    missing targets, ambiguous targets and over-budget slices all raise;
  * `generate_adaptation_stub` emits a self-contained, provenance-attributed
    stub whose only imports are a stdlib allowlist (zero foreign
    network/binary dependencies — machine-verified by
    `verify_stub_standalone`);
  * `generate_transplant_patch` produces a minimal atomic single-new-file
    patch routed to a canonical federation satellite;
  * the two live benchmark patterns (REA evidence ledger, Moli semantic
    tree) ship as structured zero-bloat blueprints (`BENCHMARK_BLUEPRINTS`).

Pure stdlib. Run: python3 scripts/agents/scout_extractor.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------
# Doctrine constants (extraction SSOT — the CI guard imports these)
# ---------------------------------------------------------------------------

GOLD_PEARL_MIN_LINES: Final = 20
GOLD_PEARL_MAX_LINES: Final = 100

CANONICAL_SATELLITES: Final = (
    "supremeai-open",
    "supremeai-browser",
    "supremeai-agents",
    "supremeai-mcp-control-plane",
    "supremeai-studio",
    "supremeai-sdk",
    "supremeai-infra",
)

#: The only imports a transplanted stub may carry: Python stdlib.
STDLIB_ALLOWLIST: Final = frozenset(
    {
        "hashlib",
        "json",
        "math",
        "re",
        "dataclasses",
        "typing",
        "itertools",
        "functools",
        "collections",
        "enum",
        "abc",
        "io",
        "os.path",
        "pathlib",
        "struct",
        "time",
        "unicodedata",
        "zlib",
        "base64",
        "binascii",
        "bisect",
        "heapq",
        "random",
        "secrets",
        "shutil",
        "textwrap",
        "uuid",
    }
)

#: Foreign-dependency red flags inside a stub (zero-bloat fitting).
FOREIGN_DEPENDENCY_MARKERS: Final = (
    "import requests",
    "import numpy",
    "import pandas",
    "import torch",
    "import flask",
    "import django",
    "from playwright",
    "require(",
    "from 'playwright",
    'from "playwright',
)

PROVENANCE_HEADER_TEMPLATE: Final = (
    "/**\n"
    " * Concept / algorithm adapted from: github.com/{repository}\n"
    " * Upstream License: {license}\n"
    " * Adapted for SupremeAI Federation lightweight satellite runtime.\n"
    " * Surgical extraction: {component} ({lines} lines, zero-dependency).\n"
    " */"
)

PROVENANCE_HEADER_PY: Final = (
    "# Concept / algorithm adapted from: github.com/{repository}\n"
    "# Upstream License: {license}\n"
    "# Adapted for SupremeAI Federation lightweight satellite runtime.\n"
    "# Surgical extraction: {component} ({lines} lines, zero-dependency)."
)


class ExtractionError(ValueError):
    """Raised when a Gold Pearl slice cannot be isolated (fail-closed)."""


# ---------------------------------------------------------------------------
# DIMENSION 1 — "কতটুকু দরকার" (need-driven scope slicing)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedSlice:
    language: str  # "python" | "typescript"
    target_name: str
    source_segment: str
    line_start: int
    line_count: int
    imports_needed: tuple[str, ...]

    @property
    def budget_ok(self) -> bool:
        return GOLD_PEARL_MIN_LINES <= self.line_count <= GOLD_PEARL_MAX_LINES


def _check_budget(slice_: ExtractedSlice) -> ExtractedSlice:
    if not slice_.budget_ok:
        raise ExtractionError(
            f"Gold Pearl budget is {GOLD_PEARL_MIN_LINES}-"
            f"{GOLD_PEARL_MAX_LINES} lines; {slice_.target_name!r} spans "
            f"{slice_.line_count} lines — slice smaller, never vendor"
        )
    return slice_


def extract_python_slice(source: str, target_name: str) -> ExtractedSlice:
    """Isolate a function/class by exact name via the stdlib AST."""
    if not source.strip():
        raise ExtractionError("empty source")
    tree = ast.parse(source)
    lines = source.splitlines()
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == target_name
    ]
    if not matches:
        raise ExtractionError(f"target {target_name!r} not found at module level")
    if len(matches) > 1:
        raise ExtractionError(
            f"target {target_name!r} is ambiguous ({len(matches)} module-level "
            "definitions) — extraction requires an exact, unique slice"
        )
    node = matches[0]
    segment = "\n".join(lines[node.lineno - 1 : node.end_lineno])
    # Imports needed = module-level import bindings actually referenced by
    # name inside the slice (deterministic usage analysis).
    bindings: dict[str, str] = {}
    for stmt in ast.walk(tree):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                bindings[alias.asname or alias.name.split(".")[0]] = alias.name.split(
                    "."
                )[0]
        elif isinstance(stmt, ast.ImportFrom) and stmt.module:
            for alias in stmt.names:
                if alias.name == "*":
                    continue
                bindings[alias.asname or alias.name] = stmt.module.split(".")[0]
    used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    imports_needed = sorted({mod for name, mod in bindings.items() if name in used})
    return _check_budget(
        ExtractedSlice(
            language="python",
            target_name=target_name,
            source_segment=segment,
            line_start=node.lineno,
            line_count=node.end_lineno - node.lineno + 1,
            imports_needed=tuple(imports_needed),
        )
    )


_TS_DECL_RE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function\*?|class|const|let|var)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)",
)


def extract_typescript_slice(source: str, target_name: str) -> ExtractedSlice:
    """Isolate a TS function/class/const by brace-balanced scanning.

    Deterministic stdlib heuristic (no tree-sitter): match the declaration
    line exactly, then balance braces/brackets/parens from the first `{`
    (or the end of a single-expression arrow/const declaration).
    """
    if not source.strip():
        raise ExtractionError("empty source")
    lines = source.splitlines()
    decl_idx = [
        i
        for i, line in enumerate(lines)
        if (m := _TS_DECL_RE.match(line)) and m.group("name") == target_name
    ]
    if not decl_idx:
        raise ExtractionError(f"target {target_name!r} not found")
    if len(decl_idx) > 1:
        raise ExtractionError(
            f"target {target_name!r} is ambiguous ({len(decl_idx)} declarations)"
        )
    start = decl_idx[0]
    depth = 0
    seen_open = False
    end = start
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch in "{[":
                depth += 1
                seen_open = True
            elif ch in "}]":
                depth -= 1
        if seen_open and depth <= 0:
            end = i
            break
        if not seen_open and (
            lines[i].rstrip().endswith(";") or lines[i].rstrip().endswith(",")
        ):
            end = i
            break
    else:
        raise ExtractionError(f"unbalanced braces for {target_name!r}")
    segment = "\n".join(lines[start : end + 1])
    (
        tuple(
            sorted(
                {
                    m.group(1)
                    for line in lines[:start] + lines[end + 1 :]
                    if (
                        m := re.match(
                            r"\s*import\s+(?:.*\s+from\s+)?['\"]([^'\"]+)['\"]", line
                        )
                    )
                }
            )
        )
        if False
        else ()
    )  # slice-internal imports only; header imports excluded
    slice_imports = tuple(
        sorted(
            {
                m.group(1)
                for line in segment.splitlines()
                if (
                    m := re.match(
                        r"\s*import\s+(?:.*\s+from\s+)?['\"]([^'\"]+)['\"]", line
                    )
                )
            }
        )
    )
    return _check_budget(
        ExtractedSlice(
            language="typescript",
            target_name=target_name,
            source_segment=segment,
            line_start=start + 1,
            line_count=len(segment.splitlines()),
            imports_needed=slice_imports,
        )
    )


# ---------------------------------------------------------------------------
# DIMENSION 2 — "কীভাবে দরকার" (native zero-bloat fitting)
# ---------------------------------------------------------------------------


def provenance_header(
    repository: str,
    license_name: str,
    component: str,
    lines: int,
    language: str = "typescript",
) -> str:
    if not repository or not license_name or not component:
        raise ExtractionError(
            "provenance header requires repository, license and component"
        )
    template = (
        PROVENANCE_HEADER_PY if language == "python" else PROVENANCE_HEADER_TEMPLATE
    )
    return template.format(
        repository=repository, license=license_name, component=component, lines=lines
    )


def generate_adaptation_stub(
    slice_: ExtractedSlice, repository: str, license_name: str
) -> str:
    """Emit a self-contained native stub with provenance attribution."""
    if slice_.language != "python":
        raise ExtractionError(
            "native zero-bloat fitting transcribes to python for "
            "scripts/agents|ci payloads; typescript stubs are routed via "
            "generate_transplant_patch (control-plane/studio/sdk)"
        )
    foreign = [imp for imp in slice_.imports_needed if imp not in STDLIB_ALLOWLIST]
    if foreign:
        raise ExtractionError(
            f"slice needs non-stdlib imports {foreign} — strip or re-write "
            "them natively before transplant (zero-bloat doctrine)"
        )
    header = provenance_header(
        repository,
        license_name,
        slice_.target_name,
        slice_.line_count,
        language="python",
    )
    import_block = "\n".join(f"import {imp}" for imp in slice_.imports_needed)
    body = slice_.source_segment
    if "raise NotImplementedError" not in body and "def " in body:
        pass  # fail-closed contracts stay as authored upstream
    return f"{header}\n\n{import_block}\n\n\n{body}\n"


def verify_stub_standalone(stub: str, language: str = "python") -> None:
    """Machine-verify the stub runs standalone.

    python: stdlib-only imports (AST), no foreign network/binary markers,
    compiles. typescript: no foreign markers, no dynamic network calls,
    balanced braces (stdlib heuristic — no external parser).
    """
    lowered = stub.lower()
    for marker in FOREIGN_DEPENDENCY_MARKERS:
        if marker in lowered:
            raise ExtractionError(
                f"foreign dependency marker {marker!r} in stub — zero-bloat "
                "doctrine violated"
            )
    if language == "python":
        try:
            tree = ast.parse(stub)
        except SyntaxError as exc:
            raise ExtractionError(
                f"broken transcription (stub does not compile): {exc}"
            ) from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in STDLIB_ALLOWLIST:
                        raise ExtractionError(
                            f"stub imports non-allowlisted module {alias.name!r}"
                        )
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] not in STDLIB_ALLOWLIST
            ):
                raise ExtractionError(
                    f"stub imports non-allowlisted module {node.module!r}"
                )
        return
    if language == "typescript":
        for line in stub.splitlines():
            if re.search(r"\b(fetch|XMLHttpRequest|require\()\s*\(", line):
                raise ExtractionError(
                    f"network/dynamic loader call in stub: {line.strip()!r}"
                )
        depth = 0
        for line in stub.splitlines():
            code = line.split("//", 1)[0]  # strip line comments (heuristic)
            for ch in code:
                if ch in "{[":
                    depth += 1
                elif ch in "}]":
                    depth -= 1
        if depth != 0:
            raise ExtractionError("unbalanced braces in typescript stub")
        return
    raise ExtractionError(f"unknown stub language {language!r}")


# ---------------------------------------------------------------------------
# Transplant generator — minimal atomic single-new-file patch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransplantPatch:
    satellite: str
    path: str
    new_file: bool
    content: str
    byte_size: int


def generate_transplant_patch(satellite: str, path: str, stub: str) -> TransplantPatch:
    """Atomic patch: exactly one NEW file in a canonical satellite."""
    if satellite not in CANONICAL_SATELLITES:
        raise ExtractionError(
            f"satellite {satellite!r} is not canonical — "
            f"route into {CANONICAL_SATELLITES}"
        )
    if not path or path.startswith("/") or ".." in path.split("/"):
        raise ExtractionError(f"unsafe transplant path {path!r}")
    language = "python" if path.endswith(".py") else "typescript"
    verify_stub_standalone(stub, language=language)
    return TransplantPatch(
        satellite=satellite,
        path=path,
        new_file=True,  # single source of discipline: no edits to
        content=stub,  # existing files — atomic pure-new-file patch
        byte_size=len(stub.encode()),
    )


# ---------------------------------------------------------------------------
# Live benchmark blueprints (issue #498 acceptance criterion)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdoptionBlueprint:
    benchmark: str
    upstream_repository: str
    license: str
    gold_pearl: str
    what_is_needed: str  # "কতটুকু দরকার"
    how_needed: str  # "কীভাবে দরকার"
    native_target: str
    zero_bloat_plan: tuple[str, ...]
    prohibited: tuple[str, ...]


BENCHMARK_BLUEPRINTS: Final = (
    AdoptionBlueprint(
        benchmark="REA Evidence Ledger",
        upstream_repository="morluto/rea",
        license="MIT",
        gold_pearl="EvidenceRecord interface + SHA-256 evidence fingerprint",
        what_is_needed=(
            "the ~30-line Evidence Record interface with its SHA-256 "
            "fingerprinting routine — not the Ghidra/Java analysis engine"
        ),
        how_needed=(
            "transcribe as a frozen python dataclass with hashlib-based "
            "fail-closed fingerprint verification; stdlib only"
        ),
        native_target="python",
        zero_bloat_plan=(
            "single new file scripts/tower/evidence_ledger_reference.py",
            "hashlib + dataclasses imports only (stdlib allowlist)",
            "fail-closed: fingerprint mismatch raises, never warns",
            "no JVM, no Ghidra runtime, no subprocess bridges",
        ),
        prohibited=(
            "vendoring the full reverse-engineering engine",
            "JVM/Java runtime prerequisites",
            "witness GUI or CLI baggage",
        ),
    ),
    AdoptionBlueprint(
        benchmark="Moli Semantic Tree",
        upstream_repository="lexmount/moli",
        license="Apache-2.0",
        gold_pearl="DOM-to-semantic-tree filtering algorithm",
        what_is_needed=(
            "the DOM node semantic filter that yields an on-demand tree "
            "for ~80% prompt-token reduction — not the Rust browser runtime"
        ),
        how_needed=(
            "re-express the filter over a parsed DOM snapshot in "
            "typescript for the browser satellite; deterministic, "
            "fail-closed on unknown node types"
        ),
        native_target="typescript",
        zero_bloat_plan=(
            "single new file under supremeai-browser src/semantic/",
            "no cargo tree, no headless-browser binary bundling",
            "input is a structured DOM snapshot — never a live browser",
            "unknown node types fail closed instead of best-effort",
        ),
        prohibited=(
            "shipping the custom Rust headless engine",
            "fingerprint-anomalous stealth runtimes",
            "vendoring the full Cargo build matrix",
        ),
    ),
)


def validate_blueprint(blueprint: AdoptionBlueprint) -> None:
    """Every ecosystem report carries the কতটুকু দরকার / কীভাবে দরকার pair."""
    for field_name in (
        "benchmark",
        "upstream_repository",
        "license",
        "gold_pearl",
        "what_is_needed",
        "how_needed",
    ):
        if not getattr(blueprint, field_name):
            raise ExtractionError(f"blueprint field {field_name!r} is empty")
    if blueprint.native_target not in ("python", "typescript"):
        raise ExtractionError("blueprint must fit natively (python|typescript)")
    if not blueprint.zero_bloat_plan or not blueprint.prohibited:
        raise ExtractionError("blueprint needs zero_bloat_plan and prohibited lists")


def self_test() -> bool:
    # Build a deterministic in-budget slice (20-100 lines).
    lines = ["import hashlib", "", ""]
    lines.append("def evidence_fingerprint(payload: bytes) -> str:")
    lines.append('    """SHA-256 fingerprint, fail-closed."""')
    lines.append("    if not payload:")
    lines.append("        raise ValueError('empty payload')")
    for i in range(30):
        lines.append(
            f"    stage_{i} = hashlib.sha256(payload + str({i}).encode()).hexdigest()"
        )
    lines.append("    return stage_29")
    lines.append("")
    lines.append("def unrelated():")
    lines.append("    return 'noise'")
    source = "\n".join(lines)

    slice_ = extract_python_slice(source, "evidence_fingerprint")
    assert slice_.language == "python"
    assert slice_.line_count == 35, slice_.line_count
    assert slice_.budget_ok
    assert slice_.imports_needed == ("hashlib",)

    # Fail-closed extraction.
    for breaker, exc in (
        (lambda: extract_python_slice(source, "ghost"), ExtractionError),
        (lambda: extract_python_slice("", "x"), ExtractionError),
        (
            lambda: extract_python_slice(
                source + "\n" + source, "evidence_fingerprint"
            ),
            ExtractionError,
        ),  # duplicate definition across docs — ambiguous
        (
            lambda: _check_budget(
                ExtractedSlice("python", "big", "x\n" * 500, 1, 500, ())
            ),
            ExtractionError,
        ),
        (
            lambda: _check_budget(ExtractedSlice("python", "tiny", "x", 1, 1, ())),
            ExtractionError,
        ),
    ):
        try:
            breaker()
            raise SystemExit(f"extractor gate failed open: {exc}")
        except exc:  # type: ignore[misc]
            pass

    # TS brace balancing.
    ts_source = "\n".join(
        [
            "import { Node } from './dom';",
            "",
            "export function semanticFilter(nodes: Node[]): Node[] {",
            "  const out: Node[] = [];",
        ]
        + [f"  if (!nodes[{i}]) throw new Error('unknown node');" for i in range(20)]
        + ["  return out;", "}", "", "export const noise = 1;"]
    )
    ts_slice = extract_typescript_slice(ts_source, "semanticFilter")
    assert ts_slice.language == "typescript"
    assert ts_slice.line_count == 24, ts_slice.line_count
    assert ts_slice.source_segment.startswith("export function semanticFilter")
    assert ts_slice.source_segment.rstrip().endswith("}")

    # Stub generation + standalone verification.
    stub = generate_adaptation_stub(slice_, "morluto/rea", "MIT")
    assert "github.com/morluto/rea" in stub and "MIT" in stub
    verify_stub_standalone(stub)
    ns: dict = {}
    exec(compile(stub, "<stub>", "exec"), ns)  # noqa: S102  # runs 100% standalone
    assert ns["evidence_fingerprint"](b"abc").startswith("0x") is False
    assert len(ns["evidence_fingerprint"](b"abc")) == 64

    # Foreign dependency rejection.
    try:
        verify_stub_standalone("import requests\nx = 1\n")
        raise SystemExit("foreign import gate failed open")
    except ExtractionError:
        pass
    try:
        generate_adaptation_stub(
            ExtractedSlice(
                "python",
                "needs_pandas",
                "import pandas as pd\ndef f():\n    return 1\n",
                1,
                3,
                ("pandas",),
            ),
            "x/y",
            "MIT",
        )
        raise SystemExit("non-stdlib slice gate failed open")
    except ExtractionError:
        pass
    try:
        generate_adaptation_stub(
            ExtractedSlice("typescript", "ts_fn", "const x = 1", 1, 1, ()), "x/y", "MIT"
        )
        raise SystemExit("ts-to-python gate failed open")
    except ExtractionError:
        pass

    # Transplant patches: atomic, canonical, new-file only.
    patch = generate_transplant_patch(
        "supremeai-mcp-control-plane",
        "src/ledger/evidence_record.ts",
        "// standalone ts stub with no imports\nconst ok = true;\n",
    )
    assert patch.new_file is True and patch.byte_size > 0
    for bad in (
        ("unknown-sat", "a.ts", "x"),
        ("supremeai-open", "/abs/path.ts", "x"),
        ("supremeai-open", "../escape.ts", "x"),
        ("supremeai-open", "ok.ts", "import requests\n"),
    ):
        try:
            generate_transplant_patch(*bad)
            raise SystemExit(f"transplant gate failed open: {bad}")
        except ExtractionError:
            pass

    # Blueprints: both live benchmarks present and valid.
    names = {b.benchmark for b in BENCHMARK_BLUEPRINTS}
    assert names == {"REA Evidence Ledger", "Moli Semantic Tree"}, names
    for blueprint in BENCHMARK_BLUEPRINTS:
        validate_blueprint(blueprint)
        assert True
    try:
        validate_blueprint(
            AdoptionBlueprint("", "r", "MIT", "g", "w", "h", "python", ("z",), ("p",))
        )
        raise SystemExit("blueprint gate failed open")
    except ExtractionError:
        pass

    return True


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--extract",
        nargs=2,
        metavar=("FILE", "TARGET"),
        help="extract a Gold Pearl slice from a source file",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF-TEST OK: scout_extractor")
        return 0
    if args.extract:
        path, target = args.extract
        with open(path, encoding="utf-8") as _f:
            source = _f.read()
        slice_ = (
            extract_python_slice(source, target)
            if path.endswith(".py")
            else extract_typescript_slice(source, target)
        )
        print(
            slice_.source_segment
            if not args.json
            else json.dumps(
                {
                    "language": slice_.language,
                    "target": slice_.target_name,
                    "lines": slice_.line_count,
                    "start": slice_.line_start,
                    "imports": list(slice_.imports_needed),
                    "budget_ok": slice_.budget_ok,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
