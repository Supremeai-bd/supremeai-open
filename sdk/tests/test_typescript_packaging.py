"""sdk/tests/test_typescript_packaging.py — packaging contract for @supremeai/sdk.

Pure static analysis (JSON / regex over source): NO npm build required, so
`pytest sdk/tests` stays green in environments without node. The dual-build
artifacts themselves are verified by `npm test` inside sdk/typescript (AC2/AC3).

Verifies issue #338 AC2: dual CJS/ESM configuration, complete declaration-map
flags, publishable metadata, and the faithful port markers from the validated
reference implementation (examples/sdk-client-ts, PR #318).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TS_DIR = Path(__file__).resolve().parent.parent / "typescript"


def _package_json() -> dict:
    return json.loads((TS_DIR / "package.json").read_text(encoding="utf-8"))


def test_package_identity_and_metadata():
    pkg = _package_json()
    assert pkg["name"] == "@supremeai/sdk"
    assert pkg["version"] == "0.1.0"
    assert pkg["license"] == "MIT"
    assert pkg["engines"]["node"] == ">=18"
    # publishable: only dist + docs in the tarball
    assert set(pkg["files"]) == {"dist", "README.md", "LICENSE"}


def test_zero_runtime_dependencies():
    pkg = _package_json()
    assert pkg.get("dependencies", {}) == {}
    # devDeps limited to the toolchain (typescript); nothing shipped at runtime
    assert set(pkg.get("devDependencies", {})) == {"typescript"}


def test_dual_cjs_esm_exports_map():
    pkg = _package_json()
    entry = pkg["exports"]["."]
    # order matters for resolvers: types first, then import/require
    assert list(entry) == ["types", "import", "require", "default"]
    assert entry["types"] == "./dist/esm/index.d.ts"
    assert entry["import"] == "./dist/esm/index.js"
    assert entry["require"] == "./dist/cjs/index.js"
    assert pkg["main"] == "./dist/cjs/index.js"
    assert pkg["module"] == "./dist/esm/index.js"
    assert pkg["types"] == "./dist/esm/index.d.ts"


def test_declaration_maps_configured_in_both_tsconfigs():
    for cfg_name in ("tsconfig.esm.json", "tsconfig.cjs.json"):
        cfg = json.loads((TS_DIR / cfg_name).read_text(encoding="utf-8"))
        opts = cfg["compilerOptions"]
        assert opts["declaration"] is True, f"{cfg_name}: declarations required"
        assert opts["declarationMap"] is True, f"{cfg_name}: declaration maps required (AC2)"
        # build configs extend the shared base — strict typing comes from there
        assert "extends" in cfg and cfg["extends"] == "./tsconfig.json"
    base = json.loads((TS_DIR / "tsconfig.json").read_text(encoding="utf-8"))
    assert base["compilerOptions"]["strict"] is True, "strict typing (package contract)"
    esm = json.loads((TS_DIR / "tsconfig.esm.json").read_text(encoding="utf-8"))
    cjs = json.loads((TS_DIR / "tsconfig.cjs.json").read_text(encoding="utf-8"))
    assert esm["compilerOptions"]["module"] == "ES2022"
    assert cjs["compilerOptions"]["module"] == "CommonJS"
    assert esm["compilerOptions"]["outDir"] == "dist/esm"
    assert cjs["compilerOptions"]["outDir"] == "dist/cjs"


def test_build_scripts_present_and_fail_closed_marker():
    pkg = _package_json()
    assert "tsc -p tsconfig.esm.json" in pkg["scripts"]["build"]
    assert "tsc -p tsconfig.cjs.json" in pkg["scripts"]["build"]
    assert "mark-outputs.mjs" in pkg["scripts"]["build"]
    marker = (TS_DIR / "scripts" / "mark-outputs.mjs").read_text(encoding="utf-8")
    # fail-closed stamping: refuses incomplete builds
    assert "fail-closed" in marker.lower()
    assert "type: kind" in marker  # each output tree stamped with its module type
    assert "index.d.ts.map" in marker  # declaration maps verified at build time


def test_source_is_faithful_port_of_validated_reference():
    """Contract markers from the validated #318 implementation survive the port."""
    src = (TS_DIR / "src" / "index.ts").read_text(encoding="utf-8")
    for marker in (
        "class SdkError",
        "class SdkRateLimited",
        "class SdkForbidden",
        "class SupremeAIClient",
        "class AsyncQueue",
        "streamStatusFetch",
        "invocation_id",
        "Retry-After",
        "agent:done",
        "agent:error",
        "text/event-stream",
        # port-parity fixes surfaced by the #338 harness (both behaviors were
        # already validated in the Python client; the TS port lacked them):
        "transport_error",          # OSError-equivalent → retryable envelope
        '"jsonrpc" in (envelope as object)',  # JSON-RPC 2.0 unwrap
    ):
        assert marker in src, f"port fidelity: {marker} missing"
    # zero @types/node: platform reached via globalThis casts only (docstring
    # MAY document the absence — assert no actual import/require of it)
    assert re.search(r"(from\s+['\"]@types|require\(\s*['\"]@types)", src) is None
    # auto-run smoke is env-gated (offline-safe module load)
    assert 'SUPREMEAI_SDK_SMOKE' in src
    assert re.search(r"argvRef\[1\] !== undefined && /", src) is None  # no argv auto-run


def test_mock_server_surface_matches_python_harness():
    """Both SDK harnesses exercise the same mock tower routes (parity)."""
    ts_test = (TS_DIR / "tests" / "sdk.test.mjs").read_text(encoding="utf-8")
    for route in ("/health", "/sse", "/mcp", "/private", "/gated", "/throttled"):
        assert route in ts_test, f"mock route {route} missing from TS harness"
    py_test = Path(__file__).resolve().parent / "test_python_sdk.py"
    py_src = py_test.read_text(encoding="utf-8")
    for route in ("/health", "/sse", "/mcp", "/private", "/gated", "/gone", "/throttled"):
        assert route in py_src, f"mock route {route} missing from Python harness"
