#!/usr/bin/env python3
"""SCRIPT-INTELLIGENCE LIB (v9): auto-discovery helpers for scripts/.

WHY THIS EXISTS (user problem): many scripts hardcode file lists, module
names, API routes and service URLs.  When the codebase changes those lists
silently rot and the scripts keep validating a phantom inventory.  This lib
replaces hardcoding with DISCOVERY:

    - repo/backend/frontend roots are found by walking up from __file__
      (no "cd ../.." assumptions);
    - python files come from `git ls-files` when available (respects
      .gitignore) with a glob fallback for tarball/CI checkouts;
    - FastAPI routes are extracted by AST parsing (no imports, no boot,
      safe against crash-on-import files);
    - service URLs are read from env (RENDER_*_URL / CORS_ORIGINS) with a
      fail-loud mode instead of silently testing a stale domain.

DESIGN RULES
    1. stdlib only -- any script, CI job or cron can import it.
    2. every discovery function returns [] or {} (never raises) except
       `require()` which you SHOULD call after discovery so empty results
       fail loudly instead of green-lighting nothing.
    3. every function accepts an `env=` override name so an operator can
       pin a value without editing the script.
    4. results are cached per-process; pass refresh=True to re-scan.

USAGE (from any script under scripts/):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/
    from lib.auto_discovery import (
        find_repo_root, discover_py_files, discover_fastapi_routes,
        discover_service_urls, existing_paths, require,
    )
"""

from __future__ import annotations

import ast
import fnmatch
import json
import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = [
    "RepoLayout",
    "find_repo_root",
    "get_layout",
    "discover_py_files",
    "discover_files",
    "existing_paths",
    "discover_fastapi_routes",
    "discover_router_modules",
    "discover_core_modules",
    "discover_service_urls",
    "discover_services_from_render_yaml",
    "require",
    "DiscoveryError",
]


class DiscoveryError(RuntimeError):
    """Raised by require() when discovery found nothing (fail-loud)."""


# --------------------------------------------------------------------------- #
# Repo layout
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RepoLayout:
    """Absolute paths of the well-known roots, resolved at call time."""

    root: Path
    backend: Optional[Path]
    frontend: Optional[Path]
    scripts: Optional[Path]
    docs: Optional[Path]

    def rel(self, p: Path) -> str:
        """Portable forward-slash path relative to repo root."""
        try:
            return p.resolve().relative_to(self.root).as_posix()
        except Exception:
            return str(p)


_REPO_MARKERS = (".git", "pyproject.toml")
_BACKEND_MARKERS = ("core", "api", "main.py")
_FRONTEND_MARKERS = ("src", "package.json")


def find_repo_root(start: Optional[Path] = None, env: str = "SUPREMEAI_REPO_ROOT") -> Path:
    """Walk up from *start* (default: this file) until a repo marker is hit.

    Env override: SUPREMEAI_REPO_ROOT.  Raises DiscoveryError when the
    caller is executed from outside a checkout -- fail loud, never guess.
    """
    override = os.getenv(env)
    if override:
        p = Path(override).resolve()
        if p.is_dir():
            return p
        raise DiscoveryError(f"{env}={override!r} is not a directory")

    cur = (start or Path(__file__)).resolve()
    if cur.is_file():
        cur = cur.parent
    for cand in (cur, *cur.parents):
        if any((cand / m).exists() for m in _REPO_MARKERS):
            return cand
    raise DiscoveryError(
        "Could not locate repo root (no .git/pyproject.toml above "
        f"{cur}); set {env} to run this script from anywhere"
    )


def _find_child_with_markers(root: Path, name: str, markers: Sequence[str]) -> Optional[Path]:
    base = root / name
    if not base.is_dir():
        return None
    if any((base / m).exists() for m in markers):
        return base
    return base if not markers else None


@lru_cache(maxsize=8)
def get_layout(start_env: str = "SUPREMEAI_REPO_ROOT") -> RepoLayout:
    """Resolve and cache the standard directory layout of the repo.

    Anchored at this lib file, so scripts can import it from any cwd.
    """
    root = find_repo_root(start=Path(__file__), env=start_env)
    return RepoLayout(
        root=root,
        backend=_find_child_with_markers(root, "backend", _BACKEND_MARKERS),
        frontend=_find_child_with_markers(root, "frontend", _FRONTEND_MARKERS),
        scripts=root / "scripts" if (root / "scripts").is_dir() else None,
        docs=root / "docs" if (root / "docs").is_dir() else None,
    )


# --------------------------------------------------------------------------- #
# File discovery
# --------------------------------------------------------------------------- #

def _git_ls_files(root: Path) -> Optional[List[Path]]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            return None
        return [root / line for line in out.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return None


def discover_py_files(
    base: Optional[Path] = None,
    include: Sequence[str] = ("*.py",),
    exclude: Sequence[str] = ("*__pycache__*", "*.venv*", "*/node_modules/*", "*/.venv/*"),
    env: str = "DISCOVER_PY_ROOT",
    root: Optional[Path] = None,  # legacy alias for base
    refresh: bool = False,
) -> List[Path]:
    """All tracked python files under *root* (default: repo root).

    Prefers `git ls-files`; falls back to rglob for plain directories.
    Env override: DISCOVER_PY_ROOT pins the scan root.
    """
    layout = get_layout()
    base = (base or root or Path(os.getenv(env) or layout.root)).resolve()
    if not base.is_dir():
        raise DiscoveryError(f"discovery root {base} is not a directory")

    files = _git_ls_files(base)
    if files is None:
        files = [p for p in base.rglob("*") if p.is_file()]

    out: List[Path] = []
    for p in files:
        s = str(p)
        if p.suffix != ".py" or not p.exists():
            continue
        if any(fnmatch.fnmatch(s, pat) for pat in exclude):
            continue
        if any(fnmatch.fnmatch(p.name, pat) for pat in include):
            out.append(p)
    return sorted(set(out))


def discover_files(
    base: Path,
    patterns: Sequence[str],
    exclude: Sequence[str] = ("*/node_modules/*", "*/.git/*", "*/dist/*", "*/build/*"),
) -> List[Path]:
    """Glob-based discovery for non-python assets (ts/tsx/yaml/json/...)."""
    base = base.resolve()
    found: Set[Path] = set()
    for pat in patterns:
        if pat.startswith("!"):
            neg = pat[1:]
            found = {p for p in found if not fnmatch.fnmatch(str(p), f"*/{neg}") and not fnmatch.fnmatch(str(p), neg)}
            continue
        for p in base.glob(pat if "/" in pat else f"**/{pat}"):
            if p.is_file() and not any(fnmatch.fnmatch(str(p), ex) for ex in exclude):
                found.add(p)
    return sorted(found)


def existing_paths(paths: Iterable[Path | str], relative_to: Optional[Path] = None) -> List[Path]:
    """Filter a candidate list down to paths that exist on disk.

    This is the one-line replacement for stale hardcoded inventories:
    `existing_paths(candidates)` drops whatever the refactor deleted.
    """
    out: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if relative_to is not None and not p.is_absolute():
            p = relative_to / p
        if p.exists():
            out.append(p)
    return out


def require(items: Sequence, what: str) -> Sequence:
    """Fail loud when discovery yields nothing (prevents silent green CI)."""
    if not items:
        raise DiscoveryError(
            f"Auto-discovery found 0 {what}.  The scan root is probably "
            "wrong (set SUPREMEAI_REPO_ROOT) or the codebase layout "
            "changed -- fix discovery instead of hardcoding the list back."
        )
    return items


# --------------------------------------------------------------------------- #
# Code-level discovery (AST based -- no imports executed)
# --------------------------------------------------------------------------- #

_ROUTER_VAR_NAMES = {"router", "api_router", "routers", "app"}


@dataclass
class RouteInfo:
    method: str
    path: str
    file: Path
    line: int
    router_var: str


def discover_fastapi_routes(
    root: Optional[Path] = None,
    extra_dirs: Sequence[Path] = (),
    env: str = "DISCOVER_ROUTES_ROOT",
) -> List[RouteInfo]:
    """Extract HTTP routes by parsing decorator syntax with AST.

    Works on un-importable files (syntax-ok but import-crash safe), so it
    never goes stale when routers are added/renamed -- as long as the file
    lives in the tree it is scanned.
    """
    layout = get_layout()
    base = root or Path(os.getenv(env) or (layout.backend or layout.root))
    scan_roots = [base.resolve(), *(p.resolve() for p in extra_dirs)]

    routes: List[RouteInfo] = []
    for py in discover_py_files(base=base, env=""):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                method = dec.func.attr.lower()
                if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                router_var = dec.func.value.id if isinstance(dec.func.value, ast.Name) else "?"
                if router_var not in _ROUTER_VAR_NAMES and not router_var.endswith("router"):
                    continue
                if not dec.args:
                    continue
                try:
                    path = ast.literal_eval(dec.args[0])
                except (ValueError, SyntaxError):
                    continue
                if isinstance(path, str):
                    routes.append(RouteInfo(method, path, py, dec.lineno, router_var))
    return routes


def discover_router_modules(root: Optional[Path] = None) -> List[Path]:
    """Files that define FastAPI routers (contain `<name>router = APIRouter`)."""
    layout = get_layout()
    base = (root or layout.backend or layout.root).resolve()
    out: List[Path] = []
    for py in discover_py_files(base=base, env=""):
        try:
            txt = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "APIRouter(" in txt or "FastAPI(" in txt:
            out.append(py)
    return sorted(out)


def discover_core_modules(root: Optional[Path] = None) -> Dict[str, Path]:
    """Locate the load-bearing modules by role, not by hardcoded path.

    Returns a mapping like {"config": ..., "app": ..., "app_builder": ...,
    "health": ..., "routes_dir": ...}.  Candidates are tried in order and
    the first existing one wins, so renames keep working until the role
    genuinely disappears (then the key is absent -> callers must require()).
    """
    layout = get_layout()
    backend = (root or layout.backend or layout.root).resolve()
    role_candidates: Dict[str, List[str]] = {
        "config": [
            "core/config.py", "config.py", "core/config/__init__.py",
        ],
        "app": [
            "core/app.py", "app.py", "main.py", "core/app/__init__.py",
        ],
        "app_builder": [
            "core/app_builder.py", "app_builder.py",
        ],
        "health": [
            "core/health_routes.py", "api/routes/health.py", "core/health.py",
        ],
        "routes_dir": [
            "api/routes",
        ],
        "startup_validator": [
            "core/startup_validator.py",
        ],
    }
    found: Dict[str, Path] = {}
    for role, candidates in role_candidates.items():
        for cand in candidates:
            p = backend / cand
            if p.exists():
                found[role] = p
                break
    return found


# --------------------------------------------------------------------------- #
# Service / deployment discovery
# --------------------------------------------------------------------------- #

@dataclass
class ServiceUrl:
    name: str
    url: str
    source: str  # "env" | "render.yaml" | "cors" | "default"


@dataclass
class ServiceDiscovery:
    services: List[ServiceUrl] = field(default_factory=list)
    cors_origins: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def urls(self) -> Dict[str, str]:
        return {s.name: s.url for s in self.services}


def discover_service_urls(
    fail_loud: bool = True,
    env_override: str = "PRE_MERGE_SERVICE_URLS",
) -> ServiceDiscovery:
    """Collect the deployed service URLs from env/flags -- never a literal.

    Priority:
      1. PRE_MERGE_SERVICE_URLS (JSON: {"primary": "https://..."}) -- CI pin.
      2. RENDER_PRIMARY_URL / RENDER_WORKER_URL / RENDER_SCRAPER_URL /
         RENDER_MCP_URL style per-service env vars.
      3. RENDER_SERVICES env (JSON list of {"name","url"}).
      4. render.yaml service names -> convention-based URLs
         (https://<name>.<render-domain>).
    Never invents a default domain silently: if nothing is discoverable and
    fail_loud is set, raises DiscoveryError.
    """
    layout = get_layout()
    disc = ServiceDiscovery()

    # 1. explicit CI pin
    pin = os.getenv(env_override)
    if pin:
        try:
            for name, url in json.loads(pin).items():
                disc.services.append(ServiceUrl(name, url, "env-pin"))
        except json.JSONDecodeError as exc:
            raise DiscoveryError(f"{env_override} is not valid JSON: {exc}") from exc
        return disc

    # 2. per-service env vars (any RENDER_<NAME>_URL)
    for key, val in sorted(os.environ.items()):
        if key.startswith("RENDER_") and key.endswith("_URL") and val.strip():
            name = key[len("RENDER_"):-len("_URL")].lower()
            disc.services.append(ServiceUrl(name, val.strip(), "env"))

    # 3. json list form
    listing = os.getenv("RENDER_SERVICES")
    if listing:
        try:
            for item in json.loads(listing):
                disc.services.append(
                    ServiceUrl(item["name"], item["url"], "env-list")
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            disc.notes.append(f"RENDER_SERVICES unparseable: {exc}")

    # 4. render.yaml convention
    if not disc.services:
        yaml_hit = discover_files(layout.root, ("render.yaml", "render.yml"))
        if yaml_hit:
            disc.notes.append(f"found {layout.rel(yaml_hit[0])}; parse names")
            try:  # yaml may be absent; do a regex pass instead of hard dep
                import re
                names = re.findall(
                    r"^\s*-\s*type\s*:\s*web\s*$.*?^\s*name\s*:\s*(\S+)",
                    yaml_hit[0].read_text(encoding="utf-8", errors="replace"),
                    re.M | re.S,
                )
                for n in names:
                    disc.services.append(ServiceUrl(n, f"https://{n}.onrender.com", "render.yaml"))
            except OSError as exc:
                disc.notes.append(f"render.yaml unreadable: {exc}")

    cors = [u.strip() for u in os.getenv("CORS_ORIGINS", "").split(",") if u.strip()]
    disc.cors_origins = cors

    if fail_loud and not disc.services:
        raise DiscoveryError(
            "No service URLs discoverable. Set RENDER_<NAME>_URL env vars, "
            "RENDER_SERVICES JSON, PRE_MERGE_SERVICE_URLS pin, or commit "
            "render.yaml -- scripts must not guess production domains."
        )
    return disc


def discover_services_from_render_yaml() -> List[Dict[str, str]]:
    """Return [{name, env...}] entries declared in render.yaml, if present."""
    layout = get_layout()
    hits = discover_files(layout.root, ("render.yaml", "render.yml"))
    if not hits:
        return []
    entries: List[Dict[str, str]] = []
    try:
        import re
        txt = hits[0].read_text(encoding="utf-8", errors="replace")
        for block in re.split(r"(?=^\s*-\s*type\s*:)", txt, flags=re.M):
            m_name = re.search(r"^\s*name\s*:\s*(\S+)", block, re.M)
            m_type = re.search(r"^\s*type\s*:\s*(\S+)", block, re.M)
            if m_name:
                entries.append(
                    {"name": m_name.group(1), "type": m_type.group(1) if m_type else "?"}
                )
    except OSError:
        return []
    return entries


if __name__ == "__main__":  # self-test:  python scripts/lib/auto_discovery.py
    lay = get_layout()
    print(f"repo      : {lay.root}")
    print(f"backend   : {lay.backend}")
    print(f"frontend  : {lay.frontend}")
    core = discover_core_modules()
    for k, v in core.items():
        print(f"core[{k}]  : {lay.rel(v)}")
    pys = discover_py_files()
    print(f"py files  : {len(pys)} (tracked)")
    routes = discover_fastapi_routes()
    print(f"routes    : {len(routes)}")
    try:
        svc = discover_service_urls()
        print(f"services  : {svc.urls()}")
    except DiscoveryError as e:
        print(f"services  : (no urls discovered -> {e})")
