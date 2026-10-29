#!/usr/bin/env python3
"""bump_candidate_probe.py — dependency freshness probe, report-only (issue #2106 R50 option C).

Mission (issue #2106, scout radar lane R50, option C — the agent-safe lane):
    The repo now carries a 6-guard dependency-safety family (R37 py-CVE,
    R41 js-CVE, R45/R46 npm-CVE, R47 FROM-pin, bandit SAST, dead-import
    ratchet) that DETECTS vulnerable/drifted pins with dated shrink-only
    baselines — but nothing in the repo automates the FIX side, and every
    bump/absorb/re-arm observed on 2026-10-28 was a hand-landed commit.
    This probe is the deliberate complement: it reads the SAME surfaces
    the guard family already owns, both via SSOT import — never a private
    copy (R51/#2122): the npm plane from npm_dep_cve_guard.LOCK_PATHS,
    and the full py plane from py_dep_cve_guard (its MANIFEST_SURFACE
    string plus its poetry synthesizer: requirements*.txt at any tracked
    depth AND pyproject.toml [tool.poetry.dependencies] main group, with
    caret/tilde/exact constraint synthesis, groups/extras/local/wildcard
    skip notes, malformed-TOML fail-close — semantics owned by the guard,
    not reinvented here). It diffs every locked (name, version) pair
    against the LIVE latest version on the public registries, and prints
    a dated candidate list for a human/agent to act on. It decides
    nothing and changes nothing.

Report-only contract (the #2106 section-4 never-do list, verbatim):
    - NO auto-merge / auto-push / auto-PR of any kind; bump decisions are
      always human-reviewed (bump PRs go through the normal review lane).
    - NO unpinning: what R44/R47 pinned is never loosened here.
    - NO access to the protected workflow-config directory at all
      (protected-path law; option A stays admin-lane).
    - NO guard-baseline writes: the shrink-only ratchets' internal truth
      is read-only from this lane's perspective — this probe sits ABOVE
      it, never edits it.
    - NO duplication: R37/R41/R45/R46/R47 detect CVEs; this probe reports
      freshness only (locked vs latest), complementing, never replacing.

Exit contract:
    --self-test  hermetic offline unit pass (roster mode)          -> 0/1
    --plan       offline snapshot: surfaces + locked-pair counts   -> 0/3
    --live       network diff vs PyPI/npm latest, dated report     -> 0 (report-only:
                 per-package probe failures are honest "unknown" rows, never red;
                 2 = usage, 3 = wiring/SSOT error)

Zero-write doctrine: the live code paths never open a file for writing and
never spawn child processes; the only file reads are the tracked lock/manifest
surfaces. Network probes are zero-credential GETs with a browser UA and a
20s timeout (house sentry precedent), sequential, no retries storms.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_TAG = "[bump-candidate-probe]"

EXIT_OK = 0
EXIT_SELFTEST_FAIL = 1
EXIT_USAGE = 2
EXIT_WIRING = 3

PROBE_TIMEOUT_S = 20
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"  # house sentry precedent: browser UA, zero credentials
)

# --- SSOT surfaces (never a private copy) --------------------------------
# npm: import the guard's own LOCK_PATHS tuple; py: import the guard's own
# MANIFEST_SURFACE string + poetry synthesizer. If a sibling module ever
# moves/renames, --plan/--live fail loudly rather than silently probing a
# stale surface list (the R51/#2122 drift class: the py side WAS a private
# copy here and the SSOT widened one commit before this probe landed).
GUARD_REL = Path("scripts/ci/npm_dep_cve_guard.py")
PY_GUARD_REL = Path("scripts/ci/py_dep_cve_guard.py")

_REQ_PIN_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==(?P<ver>[^\s;]+)"
)
_REQ_SKIP_PREFIXES = ("-", "#")
_VER_PART_RE = re.compile(r"^\d+")


def _load_npm_guard():
    guard_path = REPO_ROOT / GUARD_REL
    if not guard_path.is_file():
        raise FileNotFoundError(f"SSOT guard module missing: {GUARD_REL}")
    spec = importlib.util.spec_from_file_location("_npm_dep_cve_guard_ssot", guard_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load SSOT guard module: {GUARD_REL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not getattr(mod, "LOCK_PATHS", None):
        raise AttributeError("SSOT guard module exposes no LOCK_PATHS")
    return mod


def _load_py_guard():
    guard_path = REPO_ROOT / PY_GUARD_REL
    if not guard_path.is_file():
        raise FileNotFoundError(f"SSOT py guard module missing: {PY_GUARD_REL}")
    spec = importlib.util.spec_from_file_location("_py_dep_cve_guard_ssot", guard_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load SSOT py guard module: {PY_GUARD_REL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not getattr(mod, "MANIFEST_SURFACE", None) or not hasattr(
        mod, "synthesize_poetry_requirements"
    ):
        raise AttributeError(
            "SSOT py guard module exposes no MANIFEST_SURFACE/synthesize_poetry_requirements"
        )
    return mod


# --- parsers --------------------------------------------------------------
def parse_npm_lock(path: Path) -> list[dict]:
    """Extract (name, version, dev) pairs from a package-lock.json.

    Semantics mirror npm_dep_cve_guard's parser (v2/v3 `packages` block,
    nested node_modules keys reduced to the real package name, non-registry
    entries without a version skipped); dev entries are KEPT but tagged,
    because freshness is informational here while the CVE guard scopes to
    production only.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs: dict[str, dict] = {}
    packages = data.get("packages")
    if isinstance(packages, dict):
        for key, meta in packages.items():
            if not isinstance(meta, dict) or "node_modules/" not in key:
                continue  # root "", workspace paths, foreign keys
            version = meta.get("version")
            if not version or not isinstance(version, str):
                continue  # link/workspace entries — nothing to diff
            # nested node_modules/a/node_modules/b reduced to the real
            # package name (the LAST segment), mirroring the guard parser
            name = key.rsplit("node_modules/", 1)[1]
            if not name:
                continue
            pairs[f"{name}@{version}"] = {
                "name": name,
                "version": version,
                "dev": bool(meta.get("dev", False)),
            }
    else:
        deps = data.get("dependencies")
        if isinstance(deps, dict):
            stack = [(name, meta, False) for name, meta in sorted(deps.items())]
            while stack:
                name, meta, nested = stack.pop()
                version = meta.get("version") if isinstance(meta, dict) else None
                if version and isinstance(version, str):
                    pairs[f"{name}@{version}"] = {
                        "name": name,
                        "version": version,
                        "dev": bool(meta.get("dev", False)) if isinstance(meta, dict) else False,
                    }
                inner = meta.get("dependencies") if isinstance(meta, dict) else None
                if isinstance(inner, dict):
                    stack.extend((n, m2, True) for n, m2 in sorted(inner.items()))
    return sorted(pairs.values(), key=lambda p: (p["name"], p["version"]))


def parse_requirements(path: Path) -> list[dict]:
    """Extract pinned (name, version) pairs from a requirements*.txt.

    Skips option/nested-file/editable/hash/comment/blank lines; strips
    extras and environment markers; PEP 503 name normalization.
    """
    pairs: dict[str, dict] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(_REQ_SKIP_PREFIXES):
            continue
        line = line.split(";", 1)[0].strip()  # drop env markers
        line = line.split("#", 1)[0].strip()  # drop trailing comments
        m = _REQ_PIN_RE.match(line)
        if not m:
            continue  # unpinned or non-== specifiers are not freshness candidates
        name = re.sub(r"[-_.]+", "-", m.group("name")).lower()
        pairs[f"{name}@{m.group('ver')}"] = {"name": name, "version": m.group("ver"), "dev": False}
    return sorted(pairs.values(), key=lambda p: (p["name"], p["version"]))


def _pip_spec_bounds(spec: str):
    """One synthesized pip spec -> ((base_name, floor), upper, open_floor) | None.

    Recognises ONLY the forms the guard's poetry synthesizer emits and
    this probe can honestly freshness-check:
      name==V            exact pin           -> floor V, no upper
      name>=F,<U         caret/tilde range   -> floor F, upper U
      name~=F.F(.F)?     PEP 440 compatible  -> floor F, PEP-440 upper
      name>=F            open floor          -> floor F, unbounded above
    Extras brackets are stripped from the reported name (PyPI indexes the
    base distribution). Anything else (bare comparators, `!=` composites,
    pre-release floors the tuple logic cannot compare) returns None — the
    caller records an honest skip instead of guessing a floor.
    """
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?(.+)$", spec)
    if not m:
        return None
    name = re.sub(r"[-_.]+", "-", m.group(1)).lower()
    rest = m.group(2).strip()
    if rest.startswith("=="):
        v = rest[2:].strip()
        return ((name, v), None, False) if _ver_tuple(v) is not None else None
    if rest.startswith("~="):
        vm = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$", rest[2:].strip())
        if not vm or vm.group(2) is None:
            return None
        floor = rest[2:].strip().lstrip("v")
        maj, mino, patch = vm.group(1), vm.group(2), vm.group(3)
        upper = f"{maj}.{int(mino) + 1}.0" if patch is not None else f"{int(maj) + 1}.0"
        return ((name, floor), upper, False)
    parts = [p.strip() for p in rest.split(",")]
    if len(parts) == 2 and parts[0].startswith(">=") and parts[1].startswith("<"):
        floor, upper = parts[0][2:].strip(), parts[1][1:].strip()
        if _ver_tuple(floor) is not None and _ver_tuple(upper) is not None:
            return ((name, floor), upper, False)
    if rest.startswith(">="):
        floor = rest[2:].strip()
        if _ver_tuple(floor) is not None:
            return ((name, floor), None, True)  # unbounded above: latest already admitted
    return None


def parse_poetry_pyproject(path: Path, synth=None) -> tuple[list[dict], list[str]]:
    """[tool.poetry.dependencies] main group -> freshness pairs + skip notes.

    Synthesis is the guard's OWN function (SSOT import — the R51/#2122
    lesson: poetry semantics are owned by py_dep_cve_guard, never copied).
    Each synthesized pip spec is reduced to an honest (floor, upper)
    freshness pair; specs without one land in the skip notes. Malformed
    TOML propagates tomllib.TOMLDecodeError — the guard fails closed on
    it and so does this probe (never silently skipped).
    """
    if synth is None:
        synth = _load_py_guard().synthesize_poetry_requirements
    text, skips, _stats = synth(path)
    pairs: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        bounds = _pip_spec_bounds(line)
        if bounds is None:
            skips.append(f"{line}: no honest freshness floor (unrecognised spec)")
            continue
        (name, floor), upper, open_floor = bounds
        pairs[f"{name}@{floor}"] = {
            "name": name,
            "version": floor,
            "dev": False,
            "upper": upper,
            "open_floor": open_floor,
        }
    return sorted(pairs.values(), key=lambda p: (p["name"], p["version"])), skips


def discover_py_manifests(root: Path, skip_dirs=None) -> list[Path]:
    """requirements*.txt at any tracked depth (py_dep_cve_guard surface)."""
    if not root.is_dir():
        return []
    if skip_dirs is None:
        skip_dirs = getattr(_load_py_guard(), "SKIP_DIRS", frozenset({".git", "node_modules"}))
    out = []
    for p in sorted(root.rglob("requirements*.txt")):
        rel = p.relative_to(root)
        if any(part in skip_dirs for part in rel.parts[:-1]):
            continue
        out.append(p)
    return out


def discover_pyprojects(root: Path, skip_dirs=None) -> list[Path]:
    """pyproject.toml at any tracked depth (py_dep_cve_guard surface).

    Pruned by the guard's own SKIP_DIRS (SSOT) so vendored and virtual
    trees are excluded exactly where the guard excludes them; poetry-plane
    membership is decided at parse time — a PEP-621-only pyproject becomes
    an honest skip row, mirroring the guard's discovery contract.
    """
    if not root.is_dir():
        return []
    if skip_dirs is None:
        skip_dirs = getattr(_load_py_guard(), "SKIP_DIRS", frozenset({".git", "node_modules"}))
    out = []
    for p in sorted(root.rglob("pyproject.toml")):
        rel = p.relative_to(root)
        if any(part in skip_dirs for part in rel.parts[:-1]):
            continue
        out.append(p)
    return out


# --- freshness verdict ----------------------------------------------------
def _ver_tuple(v: str):
    parts = []
    for chunk in re.split(r"[.+\-]", str(v)):
        m = _VER_PART_RE.match(chunk)
        if not m:
            return None  # non-numeric chunk (rc, sha, local) -> unparseable
        parts.append(int(m.group(0)))
    return tuple(parts) if parts else None


def freshness_verdict(locked: str, latest, upper: str | None = None, open_floor: bool = False) -> str:
    """BUMP / fresh / unknown — freshness only, zero severity hype.

    Three pin shapes, all produced by the guard's poetry synthesizer:
      exact `==V`       BUMP iff latest > V (legacy 2-arg behavior)
      ranged `>=F,<U`   BUMP iff latest >= U — outside the allowed range,
                        i.e. a constraint edit is the fix-side candidate;
                        a latest inside the range is fresh (the resolver
                        already admits it)
      open floor `>=F`  fresh — unbounded above, the resolver admits the
                        latest release by construction (upper=None alone
                        keeps the legacy exact-pin semantics)
    """
    if latest is None:
        return "unknown"
    lt = _ver_tuple(locked)
    ll = _ver_tuple(str(latest))
    if lt is None or ll is None:
        return "unknown"
    if open_floor:
        return "fresh"
    if upper is not None:
        ut = _ver_tuple(upper)
        if ut is None:
            return "unknown"
        return "BUMP" if ll >= ut else "fresh"
    return "BUMP" if ll > lt else "fresh"


# --- registry probes (zero-credential) ------------------------------------
def _http_get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_S) as resp:  # nosec B310 — pypi.org/registry.npmjs.org https endpoints, zero-credential GET with pinned UA+timeout (report-only design; #2122 audit)
        if getattr(resp, "status", 200) != 200:
            return None
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def latest_pypi(name: str):
    data = _http_get_json(f"https://pypi.org/pypi/{name}/json")
    if not isinstance(data, dict):
        return None
    info = data.get("info")
    return info.get("version") if isinstance(info, dict) else None


def latest_npm(name: str):
    quoted = urllib.request.quote(name, safe="@")
    data = _http_get_json(f"https://registry.npmjs.org/{quoted}/latest")
    if not isinstance(data, dict):
        return None
    return data.get("version")


FETCHERS = {"pip": staticmethod(latest_pypi), "npm": staticmethod(latest_npm)}


# --- report assembly ------------------------------------------------------
def collect_surfaces(repo_root: Path):
    """(kind, path, pairs, skip_reason) rows for every surface, honest-skips included."""
    guard = _load_npm_guard()
    pyg = _load_py_guard()
    skip_dirs = getattr(pyg, "SKIP_DIRS", frozenset({".git", "node_modules"}))
    rows = []
    for rel in guard.LOCK_PATHS:
        p = repo_root / rel
        if not p.is_file():
            rows.append(("npm", rel, [], "absent-surface"))
            continue
        try:
            rows.append(("npm", rel, parse_npm_lock(p), ""))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            rows.append(("npm", rel, [], f"unparseable: {type(exc).__name__}"))
    py_root = repo_root
    for p in discover_py_manifests(py_root, skip_dirs):
        rel = p.relative_to(py_root).as_posix()
        try:
            rows.append(("pip", rel, parse_requirements(p), ""))
        except UnicodeDecodeError as exc:
            rows.append(("pip", rel, [], f"unparseable: {type(exc).__name__}"))
    for p in discover_pyprojects(py_root, skip_dirs):
        rel = p.relative_to(py_root).as_posix()
        try:
            pairs, skips = parse_poetry_pyproject(p, synth=pyg.synthesize_poetry_requirements)
        except UnicodeDecodeError as exc:
            rows.append(("pip", rel, [], f"unparseable: {type(exc).__name__}"))
            continue
        # tomllib.TOMLDecodeError deliberately NOT caught: the guard fails
        # closed on malformed TOML (#2114) and this probe inherits that.
        if not pairs:
            reason = "; ".join(skips[:3]) if skips else (
                "no [tool.poetry.dependencies] (PEP-621-only or absent poetry plane)"
            )
            rows.append(("pip", rel, [], f"poetry plane: {reason}"))
            continue
        rows.append(("pip", rel, pairs, ""))
    return rows


def build_report(surfaces, fetch=None, clock=None):
    """Assemble the dated candidate report. `fetch(kind, name)` injectable for tests."""
    if fetch is None:
        fetch = lambda kind, name: FETCHERS[kind](name)  # noqa: E731
    when = clock or datetime.now(timezone.utc)
    lines = [
        f"BUMP CANDIDATE PROBE (report-only, #2106 R50 option C) — {when.date().isoformat()}",
        "freshness-only view over the guard family's own surfaces; bump decisions stay human-reviewed",
    ]
    counters = {"BUMP": 0, "fresh": 0, "unknown": 0, "skipped": 0}
    cache: dict = {}  # (kind, name) -> latest | Exception; one probe per package
    for kind, rel, pairs, skip in surfaces:
        if skip:
            counters["skipped"] += 1
            lines.append(f"[skip  ] {kind} {rel} — {skip}")
            continue
        for pair in pairs:
            key = (kind, pair["name"])
            if key not in cache:
                try:
                    cache[key] = fetch(kind, pair["name"])
                except Exception as exc:  # report-only: any probe failure is an honest row
                    cache[key] = exc
            latest = cache[key]
            if isinstance(latest, Exception):
                lines.append(
                    f"[unknwn] {kind} {pair['name']} {pair['version']} (probe-failed: "
                    f"{type(latest).__name__}) — {rel}"
                )
                counters["unknown"] += 1
                continue
            verdict = freshness_verdict(pair["version"], latest, pair.get("upper"), pair.get("open_floor", False))
            counters[verdict] += 1
            if verdict == "BUMP":
                lines.append(f"[BUMP  ] {kind} {pair['name']} {pair['version']} -> {latest} — {rel}")
            elif verdict == "unknown":
                lines.append(f"[unknwn] {kind} {pair['name']} {pair['version']} (unparseable latest) — {rel}")
    lines.append(
        "SUMMARY: {BUMP} bump candidates, {fresh} fresh, {unknown} unknown, "
        "{skipped} skipped surfaces".format(**counters)
    )
    return lines, counters


# --- entrypoints ----------------------------------------------------------
def run_plan(repo_root: Path) -> int:
    surfaces = collect_surfaces(repo_root)
    total = 0
    print(f"{PROBE_TAG} offline surface snapshot (no network, no writes):")
    print(f"{PROBE_TAG} py surface (SSOT import): {_load_py_guard().MANIFEST_SURFACE}")
    for kind, rel, pairs, skip in surfaces:
        if skip:
            print(f"  {kind} {rel} — SKIP {skip}")
            continue
        dev = sum(1 for p in pairs if p["dev"])
        print(f"  {kind} {rel} — {len(pairs)} pinned pairs ({len(pairs) - dev} prod / {dev} dev)")
        total += len(pairs)
    print(f"{PROBE_TAG} {total} locked pairs across {len(surfaces)} surfaces — run --live for the dated diff")
    return EXIT_OK


def run_live(repo_root: Path) -> int:
    surfaces = collect_surfaces(repo_root)
    lines, counters = build_report(surfaces)
    for line in lines:
        print(line)
    return EXIT_OK  # report-only: never red, by contract


# --- self-test (hermetic, offline) ----------------------------------------
def _selftest() -> int:
    import tempfile

    checks: list[tuple[str, bool]] = []
    tmp = Path(tempfile.mkdtemp(prefix="bump-probe-selftest-"))

    # 1. npm v3 lock parse: prod + dev tags, nested reduction, link skip
    lock = tmp / "package-lock.json"
    lock.write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "root"},
            "node_modules/lodash": {"version": "4.17.20"},
            "node_modules/@org/pkg": {"version": "1.2.3"},
            "node_modules/a/node_modules/b": {"version": "0.0.9"},
            "node_modules/devonly": {"version": "2.0.0", "dev": True},
            "node_modules/linked": {"resolved": "file:../x"},
        },
    }), encoding="utf-8")
    got = {(p["name"], p["version"], p["dev"]) for p in parse_npm_lock(lock)}
    checks.append(("npm v3 parse", got == {
        ("lodash", "4.17.20", False), ("@org/pkg", "1.2.3", False),
        ("b", "0.0.9", False), ("devonly", "2.0.0", True),
    }))

    # 2. npm v1 recursive dependencies fallback
    lock1 = tmp / "package-lock-v1.json"
    lock1.write_text(json.dumps({"lockfileVersion": 1, "dependencies": {
        "left-pad": {"version": "1.3.0"},
        "outer": {"version": "2.0.0", "dependencies": {"inner": {"version": "0.1.0"}}},
    }}), encoding="utf-8")
    got1 = {(p["name"], p["version"]) for p in parse_npm_lock(lock1)}
    checks.append(("npm v1 parse", got1 == {("left-pad", "1.3.0"), ("outer", "2.0.0"), ("inner", "0.1.0")}))

    # 3. requirements parse: extras, markers, comments, options, normalization
    req = tmp / "requirements-test.txt"
    req.write_text("\n".join([
        "# comment",
        "requests==2.31.0",
        "uvicorn[standard]==0.30.1 ; python_version >= '3.9'",
        "-r other.txt",
        "-e ./local",
        "Dask_Utils==3.1.2  # trailing note",
        "flask >= 2.0",
        "",
    ]), encoding="utf-8")
    got3 = {(p["name"], p["version"]) for p in parse_requirements(req)}
    checks.append(("requirements parse", got3 == {("requests", "2.31.0"), ("uvicorn", "0.30.1"), ("dask-utils", "3.1.2")}))

    # 3b. poetry plane parse (R51/#2122): synthesis is the guard's OWN SSOT
    #     function; dict/optional/local/wildcard forms skip with notes;
    #     caret/exact/extras/open-floor give honest (floor, upper) pairs
    pyproject = tmp / "pyproject.toml"
    pyproject.write_text("\n".join([
        "[tool.poetry.dependencies]",
        'python = "^3.11"',
        'fastapi = "^0.136.0"',
        'requests = "2.31.0"',
        'httpx = { version = "^0.28.0", extras = ["http2"] }',
        'pillow = { version = "^11.0", optional = true }',
        'mypkg = { path = "../mypkg" }',
        'starlette = "*"',
        'cachetools = ">=5.0.0"',
        "",
    ]), encoding="utf-8")
    try:
        pyg = _load_py_guard()
        gotp, skipsp = parse_poetry_pyproject(pyproject, synth=pyg.synthesize_poetry_requirements)
        gp = {(p["name"], p["version"], p["upper"], p["open_floor"]) for p in gotp}
        checks.append(("poetry parse", gp == {
            ("fastapi", "0.136.0", "0.137.0", False),
            ("requests", "2.31.0", None, False),
            ("httpx", "0.28.0", "0.29.0", False),
            ("cachetools", "5.0.0", None, True),
        }
            and any("optional" in s for s in skipsp)
            and any("wildcard-any" in s for s in skipsp)
            and any("path" in s for s in skipsp)))
    except Exception:
        checks.append(("poetry parse", False))

    # 3c. PEP-621-only pyproject -> zero pairs, zero notes (collect_surfaces
    #     turns this into an honest skip row, never an error)
    pep = tmp / "pep621-only.toml"
    pep.write_text('[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    try:
        gotq, skipq = parse_poetry_pyproject(pep, synth=_load_py_guard().synthesize_poetry_requirements)
        checks.append(("pep621-only empty", gotq == [] and skipq == []))
    except Exception:
        checks.append(("pep621-only empty", False))

    # 4. verdict matrix
    checks.append(("verdict BUMP", freshness_verdict("1.2.3", "1.3.0") == "BUMP"))
    checks.append(("verdict fresh", freshness_verdict("4.17.21", "4.17.21") == "fresh"))
    checks.append(("verdict None", freshness_verdict("1.0.0", None) == "unknown"))
    checks.append(("verdict garbage", freshness_verdict("1.0.0", "abc-alpha") == "unknown"))
    checks.append(("verdict shorter", freshness_verdict("1.2", "1.2.1") == "BUMP"))
    checks.append(("verdict in-range fresh", freshness_verdict("0.136.0", "0.136.9", "0.137.0") == "fresh"))
    checks.append(("verdict out-range BUMP", freshness_verdict("0.136.0", "0.137.0", "0.137.0") == "BUMP"))
    checks.append(("verdict open-floor fresh", freshness_verdict("5.0.0", "9.9.9", None, True) == "fresh"))
    checks.append(("verdict bad-upper unknown", freshness_verdict("1.0.0", "1.1.0", "garbage") == "unknown"))

    # 5. full pipeline on injected fetcher (zero network)
    surf = [("pip", "requirements-test.txt", parse_requirements(req), ""),
            ("npm", "absent/package-lock.json", [], "absent-surface")]
    fake = {"requests": "2.32.3", "uvicorn": "0.30.1", "dask-utils": None}
    lines, counters = build_report(surf, fetch=lambda kind, name: fake.get(name))
    checks.append(("pipeline counts", counters == {"BUMP": 1, "fresh": 1, "unknown": 1, "skipped": 1}))
    checks.append(("dated header", any("BUMP CANDIDATE PROBE" in l and "option C" in l for l in lines)))
    checks.append(("skip row", any("[skip  ]" in l and "absent-surface" in l for l in lines)))
    checks.append(("bump row", any("[BUMP  ] pip requests 2.31.0 -> 2.32.3" in l for l in lines)))

    # 6. probe failure is an honest unknown row, never an exception
    def boom(kind, name):
        raise TimeoutError("simulated")
    lines6, counters6 = build_report([("pip", "requirements-test.txt", parse_requirements(req), "")], fetch=boom)
    checks.append(("probe-failure honest", counters6["unknown"] == 3 and any("probe-failed" in l for l in lines6)))

    # 7. SSOT wiring pin: the load-bearing control-plane surface comes from
    #    the guard's own LOCK_PATHS tuple (membership, not length — the
    #    tuple may legitimately widen like R46 did)
    try:
        guard = _load_npm_guard()
        checks.append(("SSOT LOCK_PATHS", Path("infrastructure/mcp-control-plane/package-lock.json") in tuple(guard.LOCK_PATHS)))
    except Exception:
        checks.append(("SSOT LOCK_PATHS", False))

    # 7b. py SSOT wiring pin: the guard's own MANIFEST_SURFACE must still
    #     advertise BOTH py planes — if the guard ever drops the poetry
    #     plane, the probe's SSOT import makes that drift loud here
    try:
        pyg2 = _load_py_guard()
        checks.append(("SSOT py MANIFEST_SURFACE", "pyproject.toml" in pyg2.MANIFEST_SURFACE
                       and "requirements" in pyg2.MANIFEST_SURFACE))
    except Exception:
        checks.append(("SSOT py MANIFEST_SURFACE", False))

    # 8. never-write / never-subprocess source pin on the LIVE code (everything
    #    before the self-test section; the self-test's own tmpdir fixture
    #    writes are the sanctioned exception by construction)
    live_src = Path(__file__).read_text(encoding="utf-8").split("def _selftest", 1)[0]
    forbidden = re.search(r"\bsubprocess\b|write_text|write_bytes|(?<![A-Za-z_])open\(", live_src)
    checks.append(("zero-write source pin", forbidden is None))

    # 9. real-repo never-writes proof: guard baselines byte-identical after
    #    a full offline surface collection
    baselines = [REPO_ROOT / "scripts/ci/npm_dep_cve_baseline.json",
                 REPO_ROOT / "scripts/ci/py_dep_cve_baseline.json"]
    before = {b: b.read_bytes() for b in baselines if b.is_file()}
    live_rows = collect_surfaces(REPO_ROOT)
    checks.append(("baselines untouched", all(b.read_bytes() == data for b, data in before.items()) and len(before) == 2))

    # 9b. live poetry plane enumerated (R51/#2122 Finding-3 receipt flipped:
    #     core/pyproject.toml now yields fix-side candidates)
    pyproj_rows = [r for r in live_rows if str(r[1]).endswith("pyproject.toml")]
    checks.append(("poetry plane live-enumerated", bool(pyproj_rows) and any(r[2] for r in pyproj_rows)))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"{PROBE_TAG} self-test {len(checks) - len(failed)}/{len(checks)}")
    return EXIT_SELFTEST_FAIL if failed else EXIT_OK


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _selftest()
    if "--plan" in argv and "--live" in argv:
        print(f"{PROBE_TAG} usage: --plan and --live are mutually exclusive")
        return EXIT_USAGE
    if "--live" in argv:
        return run_live(REPO_ROOT)
    if "--plan" in argv or not argv:
        return run_plan(REPO_ROOT)
    print(f"{PROBE_TAG} usage: [--self-test | --plan | --live]")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
