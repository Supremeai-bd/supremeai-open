#!/usr/bin/env python3
"""Gateway health contract tests — issue #401 (Phase 0, Seq 0.1).

Fail-closed behavioral suite for the Render gateway deployment contract:

  Tier 1 (reflection)  : /healthz is wired somewhere in backend/
                         (`git grep -n healthz backend/` equivalent, stdlib walk)
  Tier 2 (boot smoke)  : `import backend.main` exits 0 (verbatim issue contract)
  Tier 3 (live check)  : GET /healthz and /health return 200 with
                         {"status": "healthy", ...} unauthenticated
                         (opt-in live probe: RUN_LIVE_HEALTH=1)

Plus two plane-independent guards:

  openapi-parity guard : api-schemas/gateway.openapi.yaml documents /healthz
                         as GET, security: [] (no auth), 200 response
  cors-origins guard   : the four CORS origins and the X-Supreme-Key header
                         required by issue #401 task 3 are declared in backend/

Dual-mode runner (same convention as tests/test_ci_guards.py):

  pytest tests/test_gateway_health.py -v     # rich assertions per test
  python3 tests/test_gateway_health.py       # stdlib summary, exit 0/1

Plane-aware honesty: this file routes to the private monorepo (tests/ is
unlisted in ECOSYSTEM_MAP 3.1 -> monorepo anchor). On the public mirror
(no backend/ directory) the backend-dependent tests SKIP with an explicit
reason; the openapi guard still runs (api-schemas/ is public). A skip is
reported, never silently passed. The live probe is opt-in only — CI never
depends on a network service.

Exit contract: 0 = all runnable checks passed (skips allowed, counted);
1 = at least one runnable check failed. Unreadable repository state fails
closed (never counts as a pass).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Issue #401 task-3 CORS contract (verbatim origins/headers).
CORS_ORIGINS = (
    "https://supremeai-studio.vercel.app",
    "https://supremeai-studio-live.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
)
CORS_HEADERS = ("Authorization", "Content-Type", "X-Supreme-Key", "Accept")

LIVE_BASE_URL = os.environ.get(
    "GATEWAY_HEALTH_URL", "https://supremeai-primary-node-5xso.onrender.com"
).rstrip("/")


# --------------------------------------------------------------------------
# plane resolution — search upward so the suite works from any CWD
# --------------------------------------------------------------------------
def find_root(marker: str) -> Path | None:
    """Nearest ancestor (of this file) containing <marker> as dir or file."""
    for cand in (HERE, *HERE.parents):
        if (cand / marker).exists():
            return cand
    return None


MONO_ROOT = find_root("backend")          # private monorepo plane
SCHEMA_ROOT = find_root("api-schemas")    # public mirror + monorepo both carry it
OPENAPI = (SCHEMA_ROOT / "api-schemas" / "gateway.openapi.yaml") if SCHEMA_ROOT else None

# --------------------------------------------------------------------------
# shared assertion plumbing (stdlib summary + pytest share these predicates)
# --------------------------------------------------------------------------
class Check:
    """One named check with a pass/fail/skip verdict and a detail line."""

    def __init__(self, name: str):
        self.name = name
        self.state = "FAIL"   # fail-closed default: only explicit pass/skip wins
        self.detail = "check did not complete"

    def ok(self, detail: str = "") -> None:
        self.state, self.detail = "PASS", detail

    def skip(self, detail: str) -> None:
        self.state, self.detail = "SKIP", detail

    def fail(self, detail: str) -> None:
        self.state, self.detail = "FAIL", detail


def walk_text_files(root: Path, subdir: str):
    """Yield (path, text) for readable text files under root/subdir.

    Unreadable files are yielded as (path, None) so callers can fail closed
    when NOTHING is readable (UNVERIFIABLE is never a pass).
    """
    base = root / subdir
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        try:
            if p.stat().st_size > 2_000_000:
                yield p, None
                continue
            yield p, p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            yield p, None


# --------------------------------------------------------------------------
# 1. openapi parity guard (both planes)
# --------------------------------------------------------------------------
def check_openapi_healthz() -> Check:
    c = Check("openapi-documents-healthz-noauth")
    if OPENAPI is None or not OPENAPI.is_file():
        c.skip("api-schemas/gateway.openapi.yaml not found on this plane")
        return c
    try:
        raw = OPENAPI.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        c.fail(f"openapi unreadable: {e}")
        return c
    if len(raw.strip()) == 0:
        c.fail("openapi file is empty")
        return c
    # Locate the /healthz path block (text-level: YAML dependency-free).
    idx = raw.find("/healthz:")
    if idx < 0:
        c.fail("openapi has no /healthz path entry")
        return c
    block = raw[idx : idx + 600]
    # Contract per spec: GET, security: [] (unauthenticated), 200 response.
    if "get:" not in block:
        c.fail("/healthz block does not declare a GET operation")
        return c
    if "security: []" not in block:
        c.fail("/healthz is not marked unauthenticated (security: [] missing)")
        return c
    if '"200"' not in block and "200" not in block:
        c.fail("/healthz block does not declare a 200 response")
        return c
    c.ok("/healthz: GET, security: [], 200 documented")
    return c


# --------------------------------------------------------------------------
# 2. tier-1 reflection: healthz wired in backend/
# --------------------------------------------------------------------------
def check_healthz_wired() -> Check:
    c = Check("backend-wires-healthz")
    if MONO_ROOT is None:
        c.skip("backend/ not present on this plane (public mirror)")
        return c
    seen_files = 0
    hits: list[str] = []
    unreadable = 0
    for path, text in walk_text_files(MONO_ROOT, "backend"):
        if text is None:
            unreadable += 1
            continue
        seen_files += 1
        if "healthz" in text.lower():
            rel = path.relative_to(MONO_ROOT)
            hits.append(str(rel))
    if seen_files == 0:
        c.fail(f"backend/ exists but 0 files readable ({unreadable} unreadable)")
        return c
    if not hits:
        c.fail(
            f"tier-1 reflection failed: 'healthz' absent from all {seen_files} "
            "backend files — the route the issue demands is not wired"
        )
        return c
    c.ok(f"healthz referenced in {len(hits)} backend file(s), e.g. {hits[0]}")
    return c


# --------------------------------------------------------------------------
# 3. tier-2 boot smoke: import backend.main (verbatim issue contract)
# --------------------------------------------------------------------------
def check_boot_smoke() -> Check:
    c = Check("backend-main-imports-cleanly")
    if MONO_ROOT is None:
        c.skip("backend/ not present on this plane (public mirror)")
        return c
    main_mod = MONO_ROOT / "backend" / "main.py"
    if not main_mod.is_file():
        c.fail(
            "tier-2 contract is `import backend.main` but backend/main.py does "
            "not exist — see docs/GATEWAY_HEALTH_401_APPENDIX.md §5 "
            "reconciliation (entrypoint shim or contract amendment required)"
        )
        return c
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import backend.main"],
            cwd=str(MONO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": str(MONO_ROOT)},
        )
    except subprocess.TimeoutExpired:
        c.fail("import backend.main timed out after 120s (boot hang, not clean boot)")
        return c
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()
        tail = tail[-3:] if tail else ["(no output)"]
        c.fail(
            "tier-2 boot smoke FAILED — `import backend.main` exited "
            f"{r.returncode}; this is exactly the Render boot failure class "
            "issue #401 exists to fix. stderr tail: " + " | ".join(tail)
        )
        return c
    c.ok("import backend.main exited 0")
    return c


# --------------------------------------------------------------------------
# 4. task-3 CORS origins guard
# --------------------------------------------------------------------------
def check_cors_origins() -> Check:
    c = Check("cors-origins-declared-in-backend")
    if MONO_ROOT is None:
        c.skip("backend/ not present on this plane (public mirror)")
        return c
    blobs: list[tuple[str, str]] = []
    unreadable = 0
    for path, text in walk_text_files(MONO_ROOT, "backend"):
        if text is None:
            unreadable += 1
            continue
        blobs.append((str(path.relative_to(MONO_ROOT)), text))
    if not blobs:
        c.fail(f"backend/ exists but 0 files readable ({unreadable} unreadable)")
        return c
    missing: list[str] = []
    for needle in CORS_ORIGINS + CORS_HEADERS:
        if not any(needle in text for _, text in blobs):
            missing.append(needle)
    if missing:
        c.fail(
            "issue #401 task-3 CORS contract incomplete — not found anywhere in "
            f"backend/: {missing}; required origins {list(CORS_ORIGINS)} and "
            f"headers {list(CORS_HEADERS)} must all be declared"
        )
        return c
    c.ok(
        "all 4 origins + 4 allowed headers declared in backend/ "
        f"({len(blobs)} files scanned)"
    )
    return c


# --------------------------------------------------------------------------
# 5. tier-3 live probe (opt-in; both planes)
# --------------------------------------------------------------------------
def _probe(path: str) -> tuple[int | None, str]:
    url = f"{LIVE_BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")  # no auth header by design
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), resp.read(65536).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, (e.read(65536).decode("utf-8", errors="replace") if e.fp else "")
    except Exception as e:  # transport-level (DNS, TLS, timeout)
        return None, f"{type(e).__name__}: {e}"


def check_live_health() -> Check:
    c = Check("live-healthz-and-health-200-healthy")
    if os.environ.get("RUN_LIVE_HEALTH") != "1":
        c.skip("opt-in live probe not enabled (set RUN_LIVE_HEALTH=1)")
        return c
    verdicts = []
    for path in ("/healthz", "/health"):
        code, body = _probe(path)
        if code is None:
            verdicts.append(f"{path}: transport error ({body})")
            continue
        if code != 200:
            verdicts.append(f"{path}: HTTP {code} — {body[:160]!r}")
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            verdicts.append(f"{path}: 200 but body is not JSON — {body[:120]!r}")
            continue
        status = payload.get("status")
        if status != "healthy":
            verdicts.append(f"{path}: 200 JSON but status={status!r} != 'healthy'")
            continue
        verdicts.append(f"{path}: 200 status=healthy OK")
    bad = [v for v in verdicts if "OK" not in v]
    if bad:
        c.fail("live health contract violated — " + "; ".join(bad))
        return c
    c.ok("; ".join(verdicts))
    return c


# --------------------------------------------------------------------------
# runner plumbing
# --------------------------------------------------------------------------
ALL_CHECKS = (
    check_openapi_healthz,
    check_healthz_wired,
    check_boot_smoke,
    check_cors_origins,
    check_live_health,
)


def run_all() -> list[Check]:
    return [fn() for fn in ALL_CHECKS]


def stdlib_main() -> int:
    results = run_all()
    print("=" * 68)
    print("tests/test_gateway_health.py — issue #401 gateway health contract")
    print("=" * 68)
    fails = skips = passes = 0
    for r in results:
        print(f"  [{r.state}] {r.name}: {r.detail}")
        if r.state == "PASS":
            passes += 1
        elif r.state == "SKIP":
            skips += 1
        else:
            fails += 1
    print("-" * 68)
    print(f"  {passes} passed, {fails} failed, {skips} skipped")
    return 0 if fails == 0 else 1


# --------------------------------------------------------------------------
# pytest surface — one test per check, mapping verdicts to pytest outcomes.
# Conditional import: the file must stay a stdlib-runnable dual-mode suite
# (same convention as tests/test_ci_guards.py) even where pytest is absent.
# --------------------------------------------------------------------------
try:
    import pytest
except ImportError:  # stdlib mode — pytest surface simply not exposed
    pytest = None

if pytest is not None:

    def _expect(check: Check) -> None:
        if check.state == "PASS":
            assert True, check.detail
        elif check.state == "SKIP":
            pytest.skip(check.detail)
        else:
            pytest.fail(check.detail)

    def test_openapi_documents_healthz_noauth():
        _expect(check_openapi_healthz())

    def test_backend_wires_healthz():
        _expect(check_healthz_wired())

    def test_backend_main_imports_cleanly():
        _expect(check_boot_smoke())

    def test_cors_origins_declared_in_backend():
        _expect(check_cors_origins())

    def test_live_healthz_and_health_200_healthy():
        _expect(check_live_health())


if __name__ == "__main__":
    sys.exit(stdlib_main())
