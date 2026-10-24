#!/usr/bin/env python3
"""SupremeAI deep audit scanner (read-only, evidence generator).

Produces:
  .audit_out/backend_routes.txt    - reconstructed backend route table
  .audit_out/frontend_calls.txt    - frontend API string literals
  .audit_out/missing_calls.txt     - frontend calls with NO backend match
  .audit_out/orphan_routes.txt     - backend route families never used by FE
  .audit_out/stubs_backend.txt     - stub/mock/hardcode hits in backend (non-test)
  .audit_out/stubs_frontend.txt    - stub/mock/hardcode hits in frontend/src
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def _find_root() -> str:
    """Walk up from this script until the repository root (.git) is found."""
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        if os.path.isdir(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return os.getcwd()


ROOT = _find_root()
OUT = os.environ.get("AUDIT_OUT", os.path.join(ROOT, ".audit_out"))
os.makedirs(OUT, exist_ok=True)


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _git_tracked() -> list[str]:
    """Tracked files, relative to ROOT. Falls back to a filesystem walk."""
    try:
        res = subprocess.run(
            ["git", "-C", ROOT, "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        files = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
        if files:
            return files
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        print(f"[warn] git ls-files unavailable ({exc}); falling back to os.walk", flush=True)

    skip = {".git", "node_modules", "__pycache__", ".venv", "htmlcov", ".ruff_cache"}
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), ROOT))
    return out


tracked = [p.replace("/", os.sep) for p in _git_tracked()]
py_files = [p for p in tracked if p.endswith(".py")]
fe_files = [p for p in tracked if p.endswith((".ts", ".tsx"))]

# ---------------------------------------------------------------- mounts
mounts = {}
routers_src = read(os.path.join(ROOT, "backend", "api", "routers.py"))
for m in re.finditer(r'"path"\s*:\s*"([^"]+)"', routers_src):
    tail = routers_src[m.end() : m.end() + 260]
    pm = re.search(r'"prefix"\s*:\s*"([^"]*)"', tail)
    am = re.search(r'"is_admin"\s*:\s*(True|False)', tail)
    mounts.setdefault(
        m.group(1), (pm.group(1) if pm else "", am.group(1) if am else "False")
    )

DECOR = re.compile(
    r"@(?:router|app)\.(get|post|put|patch|delete|websocket|api_route)\(\s*[rf]?[\"']([^\"']*)[\"']",
    re.I,
)
PREFIX_DEF = re.compile(r"APIRouter\(\s*(?:[^)]*?)prefix\s*=\s*[\"']([^\"']*)[\"']", re.S)
INCLUDE = re.compile(r"include_router\(\s*([A-Za-z_][\w\.]*)\s*(?:,[^)]*?prefix\s*=\s*[\"']([^\"']*)[\"'])?", re.S)


def module_candidates(mod: str) -> list[str]:
    rel = mod.replace(".", os.sep)
    return [os.path.join("backend", rel + ".py"), os.path.join("backend", rel, "__init__.py")]


def resolve(mod: str) -> str | None:
    for cand in module_candidates(mod):
        if os.path.exists(os.path.join(ROOT, cand)):
            return cand
    return None


def apirouter_prefixes(src: str) -> list[str]:
    """Prefixes of every APIRouter(...) call, scanning balanced parens (multiline-safe)."""
    out: list[str] = []
    for m in re.finditer(r"APIRouter\(", src):
        i = m.end()
        depth = 1
        while i < len(src) and depth > 0:
            ch = src[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        span = src[m.end() : i - 1]
        pm = re.search(r"prefix\s*=\s*[\"']([^\"']*)[\"']", span)
        if pm:
            out.append(pm.group(1))
    return list(dict.fromkeys(out))


def own_prefixes(file_rel: str) -> list[str]:
    """APIRouter prefixes declared in the mounted module itself (no package fallback)."""
    return apirouter_prefixes(read(os.path.join(ROOT, file_rel))) or [""]


def package_sources(file_rel: str) -> list[str]:
    """A package router registers routes from its sibling submodules (e.g. browser/)."""
    if file_rel.endswith("__init__.py"):
        d = os.path.dirname(file_rel)
        extra = [p for p in tracked if p.endswith(".py") and os.path.dirname(p) == d]
        return list(dict.fromkeys([file_rel, *extra]))
    return [file_rel]


route_rows: list[tuple[str, str, str, str, str]] = []  # module, mount, prefix, method, path
unresolved: list[str] = []
print(f"[stage] mounts parsed: {len(mounts)}", flush=True)

for mod, (mprefix, is_admin) in mounts.items():
    f = resolve(mod)
    if not f:
        unresolved.append(f"{mod} | mount={mprefix!r} unresolved module file")
        continue
    src = read(os.path.join(ROOT, f))
    decorators = []
    for sub in package_sources(f):
        decorators += DECOR.findall(read(os.path.join(ROOT, sub)))
    if not decorators:
        continue
    for oprefix in own_prefixes(f):
        for method, dpath in decorators:
            full = mprefix + oprefix + dpath
            route_rows.append((mod, mprefix, oprefix, method.upper(), full))
print(f"[stage] route rows: {len(route_rows)}", flush=True)

with open(os.path.join(OUT, "backend_routes.txt"), "w", encoding="utf-8") as fh:
    fh.write(f"# registered modules: {len(mounts)}  route rows: {len(route_rows)}\n")
    fh.write(f"# UNRESOLVED MODULES ({len(unresolved)})\n")
    for u in unresolved:
        fh.write(f"  !! {u}\n")
    fh.write("#\n")
    for mod, mprefix, oprefix, method, full in sorted(route_rows, key=lambda r: r[4]):
        fh.write(f"{method:9} {full:70} <- {mod} (mount={mprefix!r} own={oprefix!r})\n")

# ------------------------------------------------------- frontend API calls
CALL_RE = re.compile(r"""['"`](/api[^'"`\s]{0,160})['"`]""")
call_rows: list[tuple[str, int, str]] = []
for rel in fe_files:
    src = read(os.path.join(ROOT, rel))
    for i, line in enumerate(src.splitlines(), 1):
        for m in CALL_RE.finditer(line):
            raw = m.group(1)
            if raw.rstrip("/") in ("/api", "/api/v1"):
                continue
            call_rows.append((rel.replace(os.sep, "/"), i, raw))

with open(os.path.join(OUT, "frontend_calls.txt"), "w", encoding="utf-8") as fh:
    fh.write(f"# frontend /api literals: {len(call_rows)}\n")
    for rel, i, raw in sorted(call_rows):
        fh.write(f"{rel}:{i}  {raw}\n")


def segs(path: str) -> list[str]:
    p = path.split("?")[0].split("#")[0]
    p = re.sub(r"https?://[^/]+", "", p)
    p = re.sub(r"\$\{[^}]*\}", "{p}", p)          # template holes
    p = re.sub(r"\{[^}]*\}", "{p}", p)            # already-parametrised
    return [s for s in p.split("/") if s]


def match(fe: list[str], be: list[str]) -> bool:
    if len(fe) != len(be):
        return False
    for a, b in zip(fe, be):
        if b in ("{p}",) or a == "{p}":
            continue
        if a.lower() != b.lower():
            return False
    return True


be_segs = [segs(r[4]) for r in route_rows]
missing: list[tuple[str, int, str]] = []
for rel, i, raw in call_rows:
    fs = segs(raw)
    if not any(match(fs, bs) for bs in be_segs):
        missing.append((rel, i, raw))

with open(os.path.join(OUT, "missing_calls.txt"), "w", encoding="utf-8") as fh:
    fh.write(f"# frontend calls with NO reconstructed backend match: {len(missing)}\n")
    fh.write("# NOTE: candidates - verify each manually.\n")
    for rel, i, raw in sorted(set(missing)):
        fh.write(f"{rel}:{i}  {raw}\n")

# ------------------------------------------------------- orphan route families
fe_blob = "\n".join(read(os.path.join(ROOT, p)) for p in fe_files).lower()
print(f"[stage] frontend blob: {len(fe_blob)} chars", flush=True)
families: dict[str, list[str]] = {}
for _mod, _mp, _op, method, full in route_rows:
    s = segs(full)
    if not s:
        continue
    fam = "/" + "/".join(s[:3])
    families.setdefault(fam, []).append(f"{method} {full}")

orphans = []
for fam, rows in sorted(families.items()):
    leaf = fam.split("/")[-1].lower()
    if len(leaf) < 3:
        continue
    if leaf in fe_blob:
        continue
    orphans.append((fam, rows))

with open(os.path.join(OUT, "orphan_routes.txt"), "w", encoding="utf-8") as fh:
    fh.write(f"# backend route families whose leaf segment never appears in frontend/src: {len(orphans)}\n")
    fh.write("# NOTE: candidates - a family may be used via a different naming or by admin tooling.\n")
    for fam, rows in orphans:
        fh.write(f"\n== {fam}  ({len(rows)} routes)\n")
        for r in sorted(set(rows)):
            fh.write(f"     {r}\n")

# ------------------------------------------------------------- stub scanning
TEST_HINT = re.compile(r"(^|[\\/])(tests?|__tests__)[\\/]|(^|[\\/])test_[^\\/]*\.py$|\.test\.(ts|tsx)$|\.spec\.(ts|tsx)$|conftest\.py$")

BE_PATTERNS = [
    ("mock_literal", re.compile(r"(?i)\bmock\b|MOCK_|mock_png|This is a mock"), "HIGH"),
    ("simulation", re.compile(r"(?i)\bsimulat(e|ed|ing)\b"), "HIGH"),
    ("placeholder", re.compile(r"(?i)\bplaceholder\b"), "MEDIUM"),
    ("todo_fixme", re.compile(r"\b(TODO|FIXME|HACK|XXX)\b"), "MEDIUM"),
    ("not_implemented", re.compile(r"(?i)not implemented|NotImplementedError"), "HIGH"),
    ("hardcoded", re.compile(r"(?i)\bhardcod(e|ed)\b"), "MEDIUM"),
    ("dummy_fake", re.compile(r"(?i)\b(dummy|fake)\b"), "MEDIUM"),
    ("random_metric", re.compile(r"Math\.random|random\.(random|randint|uniform)\("), "MEDIUM"),
    ("for_now", re.compile(r"(?i)\bfor now\b|\btemporar(y|ily)\b"), "LOW"),
]

FE_PATTERNS = [
    ("mock_literal", re.compile(r"(?i)\bmock\b|MOCK_"), "HIGH"),
    ("random_value", re.compile(r"Math\.random"), "HIGH"),
    ("fake_timer", re.compile(r"setTimeout\(\s*\(\)\s*=>"), "MEDIUM"),
    ("dummy_fake", re.compile(r"(?i)\b(dummy|fake|lorem)\b"), "MEDIUM"),
    ("todo_fixme", re.compile(r"\b(TODO|FIXME|HACK)\b"), "MEDIUM"),
    ("hardcoded", re.compile(r"(?i)\bhardcod(e|ed)\b"), "MEDIUM"),
    ("placeholder", re.compile(r"(?i)\bplaceholder\b"), "LOW"),
]


def scan(files: list[str], patterns, out_name: str, kind: str) -> int:
    hits: dict[str, list[tuple[int, str, str]]] = {}
    total = 0
    for rel in files:
        if TEST_HINT.search(rel):
            continue
        src = read(os.path.join(ROOT, rel))
        for i, line in enumerate(src.splitlines(), 1):
            if len(line) > 400:
                continue
            for name, rx, sev in patterns:
                if rx.search(line):
                    hits.setdefault(rel.replace(os.sep, "/"), []).append(
                        (i, name, line.strip()[:190])
                    )
                    total += 1
                    break
    with open(os.path.join(OUT, out_name), "w", encoding="utf-8") as fh:
        fh.write(f"# {kind}: {total} hits in {len(hits)} files (tests excluded)\n")
        for rel in sorted(hits, key=lambda r: -len(hits[r])):
            fh.write(f"\n== {rel}  ({len(hits[rel])} hits)\n")
            for i, name, text in hits[rel]:
                fh.write(f"  {i:5}  [{name}]  {text}\n")
    return total


be_total = scan(py_files, BE_PATTERNS, "stubs_backend.txt", "backend stub/mock/hardcode hits")
fe_total = scan(fe_files, FE_PATTERNS, "stubs_frontend.txt", "frontend stub/mock/hardcode hits")

print("[done]")
print(f"  backend route rows : {len(route_rows)}")
print(f"  unresolved modules : {len(unresolved)}")
print(f"  frontend api calls : {len(call_rows)}")
print(f"  missing calls      : {len(missing)}")
print(f"  orphan families    : {len(orphans)}")
print(f"  backend stub hits  : {be_total}")
print(f"  frontend stub hits : {fe_total}")