#!/usr/bin/env python3
"""Contract pins for the package-true gateway satellite layout (#1772).

Root cause class: the satellite image ran 'uvicorn service.app:app' over a flat
'service/' copy while the app imports its own code as the 'gateway.*' package
namespace (16+ import sites incl. gateway.middleware.correlation_id /
gateway.middleware.security_headers). Every deploy since 09dec15 (2026-10-27)
boot-crashed as Render update_failed and the public edge froze on a stale
pre-09:14Z build (the #1819 drift). These pins keep the Dockerfile contract,
the sync contract and the runtime namespace mutually consistent.

stdlib-only, offline, house dual-mode style.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPO_ROOT = ROOT
DOCKERFILE = REPO_ROOT / "gateway" / "Dockerfile"
SYNC = REPO_ROOT / "scripts" / "ci" / "federation_satellite_sync.py"


def _read(path: Path) -> str:
    assert path.exists(), f"required file missing: {path}"
    return path.read_text(encoding="utf-8")


def test_dockerfile_ships_gateway_package() -> None:
    text = _read(DOCKERFILE)
    assert "COPY gateway/ gateway/" in text, (
        "Dockerfile must ship the gateway/ package (namespace-true layout)"
    )


def test_dockerfile_cmd_runs_package_module() -> None:
    text = _read(DOCKERFILE)
    assert "uvicorn gateway.service.app:app" in text, (
        "CMD must run the package module gateway.service.app:app"
    )
    # The flat module path must be retired from the EXECUTED contract (CMD
    # lines only — comments may describe the retired path historically).
    cmd_lines = [ln for ln in text.splitlines() if ln.strip().startswith("CMD")]
    assert cmd_lines, "Dockerfile must declare a CMD"
    for ln in cmd_lines:
        assert "uvicorn service.app:app" not in ln, (
            "CMD must not reference the flat service.app:app module path"
        )


def test_dockerfile_has_no_flat_service_copy() -> None:
    text = _read(DOCKERFILE)
    assert "COPY service/ service/" not in text, (
        "flat 'service/' copy must not return; the package layout is SSOT"
    )


def test_dockerfile_keeps_liveness_fallbacks() -> None:
    text = _read(DOCKERFILE)
    # Render-safe boot chain: requirements install with bare-deps fallback,
    # bootstrap exec with direct-uvicorn fallback.
    assert "pip install --no-cache-dir -r requirements.txt" in text
    assert "|| pip install --no-cache-dir fastapi" in text
    assert "runtime/infisical_bootstrap.py" in text
    assert "|| (uvicorn gateway.service.app:app" in text


def test_sync_no_longer_creates_flat_service_tree() -> None:
    text = _read(SYNC)
    assert "'gateway/service' -> 'service'" not in text, (
        "sync must not recreate the flat service/ tree it retired for #1772"
    )
    assert 'copy_tree_contents(service_src, tmp_repo / "service")' not in text, (
        "flat service/ re-materialization (incl. push-retry reconcile) must stay retired"
    )
    # The one-time legacy cleanup must stay (satellite trees created before the
    # retirement still carry the stale flat dir until the next sync lands).
    assert "legacy_service" in text and "rmtree" in text
    # Package-true reconcile on concurrent push: gateway/ restored, not service/.
    assert 'copy_tree_contents(gw_src, tmp_repo / "gateway", prune=True)' in text


def test_sync_still_maps_gateway_package_and_dockerfile() -> None:
    text = _read(SYNC)
    # The package block that predates the fix must remain: gateway -> gateway.
    assert '("gateway", "gateway")' in text
    assert 'shutil.copy2(df_src, tmp_repo / "Dockerfile")' in text
    # Root requirements mapping remains (single requirements source).
    assert 'shutil.copy2(req_src, tmp_repo / "requirements.txt")' in text


def test_app_namespace_imports_resolvable_under_package_layout() -> None:
    """The two bare middleware imports that boot-crashed the flat layout must
    resolve as gateway.* modules from the package tree."""
    import importlib.util

    for mod_name in (
        "gateway.middleware.correlation_id",
        "gateway.middleware.security_headers",
    ):
        spec = importlib.util.find_spec(mod_name)
        assert spec is not None, f"package module must be importable: {mod_name}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)
    ):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"{7 - failures}/7 checks passed" if failures else "all checks passed")
    sys.exit(1 if failures else 0)
