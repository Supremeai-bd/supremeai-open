#!/usr/bin/env python3
"""SupremeAI Feature Parity Sentinel — Backend ⇄ Frontend drift detector.

Zero-dependency (Python stdlib only) intelligent scanner that continuously
verifies the parity contract between the backend API surface and the frontend
UI surface, so the findings in
``docs/architecture/BACKEND_FRONTEND_FEATURE_PARITY_AUDIT.md`` can never
silently regress (and new drift can never silently appear).

Why this exists
---------------
The 2026-09-11 parity audit proved that mismatches do not arrive as loud
build failures. They arrive as silent 404s: a router defined but never
mounted, a component built but never rendered, a link pointing at a route
that does not exist, a frontend call whose backend path drifted. This
sentinel turns all of them into explicit, baselined, CI-enforced findings.

Detection engines
-----------------
  unmounted-router       backend module defines APIRouter routes but the router
                         is never registered via ``ALL_ROUTERS``,
                         ``app.include_router`` or ``register_routes`` (404 at boot)
  missing-backend-route  frontend apiClient/fetch/WebSocket/EventSource call has
                         no mounted backend route (path or prefix drift)
  dead-nav-link          ``<Link to>`` / ``navigate(...)`` target with no
                         matching ``<Route path>`` (user-visible 404)
  ghost-ui               component/page file never imported and never rendered
                         as JSX anywhere (invisible feature)
  orphan-endpoint        mounted backend endpoint with zero frontend consumers
                         (backend-only capability; medium severity)
  parse-error            source file that could not be parsed (blind spot in
                         the sentinel itself — never allowed to be silent)

Intelligence model (drift, not debt)
------------------------------------
The current audit debt lives in a committed baseline JSON. Every nightly run:
  1. re-scans the whole repo,
  2. classifies findings as KNOWN (in baseline), NEW (not in baseline) or
     RESOLVED (in baseline but no longer present),
  3. exits non-zero only for NEW findings at/above ``--fail-on`` severity,
  4. can refresh the baseline with ``--update-baseline`` after intentional
     remediation or when accepting new debt explicitly.

Usage
-----
    python scripts/feature_parity_sentinel.py                        # human report
    python scripts/feature_parity_sentinel.py --json r.json --markdown r.md
    python scripts/feature_parity_sentinel.py --baseline scripts/feature_parity_baseline.json
    python scripts/feature_parity_sentinel.py --update-baseline      # refresh snapshot
    python scripts/feature_parity_sentinel.py --strict               # fail on new medium too
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_BASELINE = ROOT / "scripts" / "feature_parity_baseline.json"
ROUTERS_REGISTRY = BACKEND_DIR / "api" / "routers.py"

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}
CATEGORY_SEVERITY = {
    "unmounted-router": "high",
    "missing-backend-route": "high",
    "dead-nav-link": "high",
    "parse-error": "medium",
    "ghost-ui": "medium",
    "orphan-endpoint": "medium",
}

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
PY_IGNORE_DIRS = {"__pycache__", ".venv", ".venv_ci", "node_modules", "htmlcov", "tests"}
FE_IGNORE_DIRS = {"node_modules", "dist", "build", "coverage", "__pycache__"}

NON_API_SUFFIXES = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".md",
    ".json",
    ".txt",
    ".mp4",
    ".webm",
    ".tsx",
    ".ts",
)
FE_SRC = FRONTEND_DIR / "src"


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def iter_files(base: Path, suffixes: tuple[str, ...], ignore_dirs: set[str]) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
        for name in filenames:
            if name.endswith(suffixes):
                out.append(Path(dirpath) / name)
    return sorted(out)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def normalize_path(raw: str) -> str:
    """Normalize a URL path: unify JS template params, :params and {params}
    into ``{}`` wildcards; strip query/hash and trailing slash."""
    p = raw.strip().split("#", 1)[0].split("?", 1)[0].strip()
    p = re.sub(r"\$\{[^}]*\}", "{}", p)  # template literal param
    p = re.sub(r"(?<![\w$]):[A-Za-z_][\w-]*", "{}", p)  # :param
    p = re.sub(r"\{[^}/]*\}", "{}", p)  # {param}
    p = re.sub(r"/{2,}", "/", p)
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def paths_match(called: str, mounted: str) -> bool:
    """Wildcard-aware bidirectional path match; ``{}`` matches any segment,
    a mounted trailing ``*``/``{}`` matches everything beyond it."""
    c = [s for s in called.split("/") if s != ""]
    m = [s for s in mounted.split("/") if s != ""]
    for i in range(max(len(c), len(m))):
        cseg = c[i] if i < len(c) else None
        mseg = m[i] if i < len(m) else None
        if mseg is None:
            return False
        if mseg in ("{}", "*") and i == len(m) - 1:
            return True
        if cseg is None:
            return False
        if mseg == "{}" or cseg == "{}" or cseg == mseg:
            continue
        return False
    return True


def looks_like_api_path(raw: str) -> bool:
    p = raw.strip()
    if not p.startswith("/") or " " in p or p in ("", "/"):
        return False
    if any(p.lower().endswith(s) for s in NON_API_SUFFIXES):
        return False
    return len([s for s in p.split("/") if s]) >= 2


# ---------------------------------------------------------------------------
# Backend engine: AST route inventory + mount graph
# ---------------------------------------------------------------------------


def module_name_for(path: Path) -> str:
    rel = path.relative_to(BACKEND_DIR).with_suffix("")
    return ".".join(rel.parts)


def extract_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def scan_backend(files: list[Path]):
    """Return (routes_by_module, router_prefixes, mount_calls, parse_errors).

    routes_by_module: module -> [{method, path, line, mounted}]
    router_prefixes:  module -> declared APIRouter(prefix=...)
    mount_calls:      [{module, prefix, file, line}] mounted via include_router/register_routes
    """
    routes_by_module: dict[str, list[dict[str, Any]]] = {}
    router_prefixes: dict[str, str] = {}
    mount_calls: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for f in files:
        src = read_text(f)
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            parse_errors.append(
                {"file": str(f.relative_to(ROOT)), "line": e.lineno or 0, "error": str(e.msg)}
            )
            continue

        module = module_name_for(f)
        imports: dict[str, str] = {}  # local name -> full dotted path
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name] = alias.name

        router_vars: dict[str, str] = {}  # local var -> owning module
        app_vars: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                if isinstance(fn, ast.Name) and fn.id in ("APIRouter", "FastAPI"):
                    prefix = ""
                    for kw in node.value.keywords:
                        if kw.arg == "prefix":
                            prefix = extract_str(kw.value) or ""
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            if fn.id == "APIRouter":
                                router_vars[tgt.id] = module
                                router_prefixes[module] = prefix
                            else:
                                app_vars.add(tgt.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                        continue
                    attr = dec.func.attr
                    owner = dec.func.value
                    owner_name = owner.id if isinstance(owner, ast.Name) else None
                    if owner_name is None:
                        continue
                    method = (
                        attr.upper()
                        if attr in HTTP_METHODS
                        else ("WEBSOCKET" if attr == "websocket" else None)
                    )
                    if method is None:
                        continue
                    path = ""
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        path = extract_str(dec.args[0]) or ""
                    if owner_name in app_vars:
                        routes_by_module.setdefault(module, []).append(
                            {"method": method, "path": path, "line": node.lineno, "mounted": True}
                        )
                    elif owner_name in router_vars:
                        routes_by_module.setdefault(router_vars[owner_name], []).append(
                            {"method": method, "path": path, "line": node.lineno}
                        )
            elif isinstance(node, ast.Call):
                fname = node.func
                target_module, prefix = None, ""
                if (
                    isinstance(fname, ast.Attribute)
                    and fname.attr == "include_router"
                    and node.args
                ):
                    owner_name = fname.value.id if isinstance(fname.value, ast.Name) else None
                    if owner_name in app_vars:
                        arg = node.args[0]
                        var = arg.id if isinstance(arg, ast.Name) else None
                        for kw in node.keywords:
                            if kw.arg == "prefix":
                                prefix = extract_str(kw.value) or ""
                        if var and var in imports:
                            target_module = imports[var]
                        elif var and var in router_vars:
                            target_module = router_vars[var]
                elif isinstance(fname, ast.Name) and fname.id == "register_routes" and node.args:
                    for full in imports.values():
                        if full.endswith(".register_routes"):
                            target_module = full.rsplit(".", 1)[0]
                            break
                if target_module:
                    mount_calls.append(
                        {
                            "file": str(f.relative_to(ROOT)),
                            "line": node.lineno,
                            "module": target_module,
                            "prefix": prefix,
                        }
                    )

    return routes_by_module, router_prefixes, mount_calls, parse_errors


def parse_all_routers_registry() -> dict[str, str]:
    """Parse ALL_ROUTERS = [{"path": "api.routes.x", "prefix": "..."}]."""
    registry: dict[str, str] = {}
    try:
        tree = ast.parse(read_text(ROUTERS_REGISTRY))
    except SyntaxError:
        return registry
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Name)
                    and tgt.id == "ALL_ROUTERS"
                    and isinstance(node.value, ast.List)
                ):
                    for el in node.value.elts:
                        if not isinstance(el, ast.Dict):
                            continue
                        entry: dict[str, str] = {}
                        for k, v in zip(el.keys, el.values, strict=False):
                            if (
                                isinstance(k, ast.Constant)
                                and isinstance(k.value, str)
                                and isinstance(v, ast.Constant)
                            ):
                                entry[str(k.value)] = str(v.value)
                        mod = entry.get("path")
                        if mod:
                            registry[mod] = entry.get("prefix", "")
    return registry


# ---------------------------------------------------------------------------
# Frontend engine: API calls, nav links, routes, ghost UI
# ---------------------------------------------------------------------------

RE_API_CALL = re.compile(
    r"(?:apiClient|api|axios|http|client)\s*\.\s*"
    r"(?:get|post|put|patch|delete|request|head)\s*(?:<[^>(]*>)?\s*\(\s*[`'\"]([^`'\"]+)[`'\"]"
    r"|fetch\s*\(\s*[`'\"]([^`'\"]+)[`'\"]"
    r"|new\s+(?:WebSocket|EventSource)\s*\(\s*[`'\"]([^`'\"]+)[`'\"]"
)
RE_NAV = re.compile(
    r"<(?:Link|NavLink)\b[^>]*?\bto=\{?[`'\"]([^`'\"]+)[`'\"]"
    r"|navigate\s*\(\s*[`'\"]([^`'\"]+)[`'\"]"
    r"|\bhref\s*:\s*[`'\"](/[^`'\"]*)[`'\"]"
)
RE_ROUTE = re.compile(r"<Route\b[^>]*?\bpath=[\"']([^\"']+)[\"']")
RE_IMPORT = re.compile(
    r"""(?:import|export)\s[^;]*?\bfrom\s+["']([^"']+)["']"""
    r"""|(?:import\s*\(\s*["']([^"']+)["']\s*\))"""
)


def py_files() -> list[Path]:
    return iter_files(BACKEND_DIR, (".py",), PY_IGNORE_DIRS)


def fe_files() -> list[Path]:
    return iter_files(FE_SRC, (".ts", ".tsx"), FE_IGNORE_DIRS)


def scan_frontend(files: list[Path]):
    """Return (api_calls, nav_links, route_paths, import_lines).

    Full-text scanning (not per-line) so multiline JSX attributes are captured.
    """
    api_calls: list[dict[str, Any]] = []
    nav_links: list[dict[str, Any]] = []
    route_paths: list[str] = []
    import_lines: dict[Path, list[str]] = {}

    def line_of(text: str, pos: int) -> int:
        return text.count("\n", 0, pos) + 1

    for f in files:
        text = read_text(f)
        import_lines[f] = text.splitlines()
        for m in RE_ROUTE.finditer(text):
            route_paths.append(normalize_path(m.group(1)))
        for m in RE_API_CALL.finditer(text):
            raw = next((g for g in m.groups() if g), "")
            if looks_like_api_path(raw):
                api_calls.append(
                    {
                        "path": raw,
                        "norm": normalize_path(raw),
                        "file": str(f.relative_to(ROOT)),
                        "line": line_of(text, m.start()),
                    }
                )
        for m in RE_NAV.finditer(text):
            raw = next((g for g in m.groups() if g), "")
            if raw.startswith("/") and not raw.startswith("//"):
                nav_links.append(
                    {
                        "target": raw,
                        "norm": normalize_path(raw),
                        "file": str(f.relative_to(ROOT)),
                        "line": line_of(text, m.start()),
                    }
                )
    return api_calls, nav_links, route_paths, import_lines


def detect_ghost_ui(files: list[Path], import_lines: dict[Path, list[str]]) -> list[dict[str, Any]]:
    """Component/page files never imported anywhere and never used as JSX."""
    ghosts: list[dict[str, Any]] = []
    candidates = [
        f
        for f in files
        if str(f).replace("\\", "/").split("/src/")[-1].startswith(("components/", "pages/"))
        and not f.name.startswith(("index.", "App.", "main."))
        and not f.name.endswith((".test.tsx", ".test.ts", ".d.ts", ".stories.tsx"))
    ]
    import_blob = "\n".join(
        "\n".join(l for l in lines if RE_IMPORT.search(l) or "lazy(" in l)
        for lines in import_lines.values()
    )
    jsx_blob = "\n".join(
        "".join(re.findall(r"<([A-Z][A-Za-z0-9]+)", "\n".join(lines)))
        for lines in import_lines.values()
    )
    for f in candidates:
        name = f.stem
        referenced = re.search(
            r"""["'/]""" + re.escape(name) + """["']""", import_blob
        ) or re.search(r"\b" + re.escape(name) + r"\b", jsx_blob)
        if not referenced:
            ghosts.append({"file": str(f.relative_to(ROOT)), "component": name})
    return ghosts


# ---------------------------------------------------------------------------
# Parity analysis → findings
# ---------------------------------------------------------------------------


def build_findings(
    routes_by_module,
    router_prefixes,
    mount_calls,
    parse_errors,
    api_calls,
    nav_links,
    route_paths,
    ghosts,
):
    findings: list[dict[str, Any]] = []

    # 0) parse errors — never silent
    for pe in parse_errors:
        findings.append(
            {
                "category": "parse-error",
                "severity": "medium",
                "key": "parse-error|" + pe["file"],
                "file": pe["file"],
                "line": pe["line"],
                "detail": "Unparseable source file (sentinel blind spot): " + pe["error"],
            }
        )

    # 1) mounted-route set (ALL_ROUTERS registry + include_router/register_routes)
    registry = parse_all_routers_registry()
    # Package routers are scanned under their package module name, while a
    # registry may explicitly name the package __init__ module. Treat those
    # spellings as the same mounted router so package-split endpoints are not
    # reported as runtime 404s.
    registry = {
        module.removesuffix(".__init__"): prefix
        for module, prefix in registry.items()
    }
    # AST scanning names package __init__.py modules explicitly; retain that
    # alias alongside the canonical package name used by ALL_ROUTERS.
    registry.update({f"{module}.__init__": prefix for module, prefix in registry.items()})
    mounted_prefixes: dict[str, str] = dict(registry)
    # Routes registered on a package router can be declared in imported
    # submodules. In that layout the decorator's AST module is the submodule,
    # but runtime registration happens when the mounted package is imported.
    for mounted_module, prefix in list(mounted_prefixes.items()):
        package_module = mounted_module.removesuffix(".__init__")
        for route_module in routes_by_module:
            if route_module.startswith(package_module + "."):
                mounted_prefixes.setdefault(route_module, prefix)
    for mc in mount_calls:
        mounted_prefixes.setdefault(mc["module"], "")
        if mc["prefix"]:
            mounted_prefixes[mc["module"]] = mc["prefix"]

    # 2) unmounted routers (defined routes but never mounted anywhere)
    for module, routes in sorted(routes_by_module.items()):
        if any(r.get("mounted") for r in routes):
            continue  # mounted directly on app
        if module in mounted_prefixes or module in registry:
            continue
        rel = str((BACKEND_DIR / module.replace(".", "/")).with_suffix(".py").relative_to(ROOT))
        sample = ", ".join(f"{r['method']} {r['path']}" for r in routes[:5])
        findings.append(
            {
                "category": "unmounted-router",
                "severity": "high",
                "key": f"unmounted-router|{module}",
                "file": rel,
                "line": 0,
                "detail": f"Router defines {len(routes)} route(s) but is never mounted "
                f"(missing from ALL_ROUTERS / include_router / register_routes) "
                f"→ endpoints 404 at runtime: {sample}",
            }
        )

    # 3) effective mounted backend route table
    mounted_routes: list[dict[str, Any]] = []
    for module, routes in sorted(routes_by_module.items()):
        eff_prefix = mounted_prefixes.get(module)
        router_own = router_prefixes.get(module, "")
        for r in routes:
            if r.get("mounted"):
                full = "/" + r["path"].strip("/")
                mounted_routes.append({"method": r["method"], "norm": normalize_path(full)})
            elif eff_prefix is not None:
                full = f"{eff_prefix}{router_own}{r['path']}"
                mounted_routes.append(
                    {
                        "method": r["method"],
                        "norm": normalize_path(full),
                        "module": module,
                        "line": r["line"],
                    }
                )

    # 4) missing-backend-route: every frontend call must hit a mounted route
    for call in api_calls:
        if not any(paths_match(call["norm"], mr["norm"]) for mr in mounted_routes):
            findings.append(
                {
                    "category": "missing-backend-route",
                    "severity": "high",
                    "key": "missing-backend-route|" + call["norm"],
                    "file": call["file"],
                    "line": call["line"],
                    "detail": f"Frontend calls `{call['path']}` but no mounted backend route serves "
                    f"this path (path/prefix drift → runtime 404 or mock fallback).",
                }
            )

    # 5) orphan-endpoint: mounted route with zero frontend consumers
    for mr in mounted_routes:
        if not any(paths_match(call["norm"], mr["norm"]) for call in api_calls):
            mod = mr.get("module", "unknown")
            rel = str((BACKEND_DIR / mod.replace(".", "/")).with_suffix(".py").relative_to(ROOT))
            findings.append(
                {
                    "category": "orphan-endpoint",
                    "severity": "medium",
                    "key": f"orphan-endpoint|{mr['method']} {mr['norm']}",
                    "file": rel,
                    "line": mr.get("line", 0),
                    "detail": f"Mounted endpoint `{mr['method']} {mr['norm']}` has no frontend "
                    f"consumer (backend-only capability, no UI to operate it).",
                }
            )

    # 6) dead-nav-link: nav target without a matching route
    real_routes = [rp for rp in route_paths if rp not in ("*", "")]
    for nav in nav_links:
        target = nav["norm"]
        if any(paths_match(target, rp) or paths_match(rp, target) for rp in real_routes):
            continue
        findings.append(
            {
                "category": "dead-nav-link",
                "severity": "high",
                "key": "dead-nav-link|" + target,
                "file": nav["file"],
                "line": nav["line"],
                "detail": f"Navigation to `{nav['target']}` has no matching <Route> → user-facing 404.",
            }
        )

    # 7) ghost-ui
    for g in ghosts:
        findings.append(
            {
                "category": "ghost-ui",
                "severity": "medium",
                "key": "ghost-ui|" + g["file"],
                "file": g["file"],
                "line": 0,
                "detail": f"Component `{g['component']}` is never imported or rendered as JSX — "
                f"fully built feature invisible to users.",
            }
        )

    return findings, mounted_routes


# ---------------------------------------------------------------------------
# Baseline (drift detection) + reports + CLI
# ---------------------------------------------------------------------------


def _normalize_key(key: str) -> str:
    """Platform-normalize a finding key.

    Baselines authored on Windows carry ``\\`` separators inside path-bearing
    keys (e.g. ``ghost-ui|frontend\\src\\components\\X.tsx``); on the Linux CI
    runner the same finding is keyed with ``/``. Without normalization the
    identical debt flip-flops between "RESOLVED" and "NEW" on every
    platform change (observed 2026-09-15: 35 ghost-ui entries). Keys without
    path separators are returned unchanged.
    """
    return key.replace("\\", "/")


def load_baseline(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {_normalize_key(k) for k in data.get("finding_keys", [])}
    except FileNotFoundError:
        print(f"  ⚠️  Baseline not found ({path}); treating ALL findings as new.", file=sys.stderr)
        return set()
    except (OSError, json.JSONDecodeError) as e:
        print(f"  ⚠️  Could not read baseline {path}: {e}; treating all as new.", file=sys.stderr)
        return set()


def save_baseline(path: Path, findings: list[dict[str, Any]]) -> None:
    slim = sorted({f["key"] for f in findings})
    payload = {
        "schema_version": "1.0",
        "description": "Known/accepted feature-parity debt (Feature Parity Sentinel baseline). "
        "Nightly CI fails only on findings NOT in this list. Refresh intentionally "
        "via: python scripts/feature_parity_sentinel.py --update-baseline",
        "finding_count": len(slim),
        "finding_keys": slim,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  📌 Baseline written to {path} ({len(slim)} findings)")


def human_report(findings, known, new, resolved, mounted_count, api_count) -> str:
    lines = [
        "🔍 Feature Parity Sentinel — Backend ⇄ Frontend",
        "=" * 55,
        f"  Mounted backend routes: {mounted_count}",
        f"  Frontend API calls:     {api_count}",
        f"  Total findings:         {len(findings)}",
        "",
    ]
    if new:
        lines.append(f"🚨 NEW drift (not in baseline) — {len(new)}:")
        for f in new:
            lines.append(f"  [{f['severity'].upper():6}] {f['category']}: {f['key']}")
            lines.append(f"           {f['file']}:{f['line']} — {f['detail'][:140]}")
        lines.append("")
    if resolved:
        lines.append(f"✅ RESOLVED since baseline — {len(resolved)}:")
        lines.extend(f"  {k}" for k in sorted(resolved))
        lines.append("")
    lines.append(f"📜 Known (baselined) debt: {len(known)} — see baseline JSON + parity audit doc.")
    return "\n".join(lines)


def markdown_report(findings, known, new, resolved, baseline_meta) -> str:
    lines = [
        "# Feature Parity Sentinel Report",
        "",
        f"> Drift vs baseline: **{len(new)} new**, {len(known)} known, "
        f"**{len(resolved)} resolved**. Sources: backend AST + routers.py registry + frontend src.",
        "",
    ]
    if new:
        lines += [
            "## 🚨 New Mismatches (must fix or explicitly baseline)",
            "",
            "| Severity | Category | Subject | Location |",
            "|---|---|---|---|",
        ]
        for f in sorted(new, key=lambda x: (-SEVERITY_ORDER[x["severity"]], x["category"])):
            lines.append(
                f"| {f['severity']} | {f['category']} | `{f['key'].split('|', 1)[1]}` | "
                f"`{f['file']}:{f['line']}` |"
            )
        lines.append("")
    if resolved:
        lines += (
            ["## ✅ Resolved Since Baseline", ""]
            + [f"- ~~`{k}`~~" for k in sorted(resolved)]
            + [""]
        )
    lines += [
        f"## 📜 Known Debt ({len(known)})",
        "",
        f"Baseline: `{baseline_meta['path']}` — refresh with `--update-baseline` after "
        "intentional changes. Full context: "
        "`docs/architecture/BACKEND_FRONTEND_FEATURE_PARITY_AUDIT.md`.",
    ]
    return "\n".join(lines)


def force_utf8_streams(stdout=None, stderr=None) -> None:
    """ERR-M03 FIX (2026-09-16): on Windows the console defaults to a legacy
    codepage (e.g. cp1252) that cannot encode the sentinel's status glyphs
    (U+1F50D 🔍 etc.), raising UnicodeEncodeError mid-run. Reconfigure
    stdout/stderr to UTF-8 with replacement so the tool works on any
    terminal; streams without reconfigure (rare wrappers) are left alone.

    Stream parameters are injectable for tests.
    """
    for _stream in (stdout if stdout is not None else sys.stdout, stderr if stderr is not None else sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError) as exc:
            # বাংলা নোট: reconfigure-অসমর্থ স্ট্রিম ইচ্ছাকৃতভাবে skip করা হয় (rare
            # wrappers — crash করা ঠিক নয়), তবে REL-001/REL-002 অনুযায়ী এটা
            # নীরব থাকবে না — stderr-এ দৃশ্যমান warning দেওয়া হয়।
            print(f"[WARN] stream {_stream!r} not reconfigurable: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    p = argparse.ArgumentParser(
        description="SupremeAI Feature Parity Sentinel (backend ⇄ frontend drift)"
    )
    p.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="baseline JSON; CI fails only on findings NOT in the baseline",
    )
    p.add_argument(
        "--update-baseline",
        action="store_true",
        help="write the baseline snapshot of the current scan and exit 0",
    )
    p.add_argument("--json", type=Path, default=None, help="write full JSON report")
    p.add_argument("--markdown", type=Path, default=None, help="write markdown report")
    p.add_argument(
        "--fail-on",
        choices=["never", "medium", "high"],
        default="high",
        help="minimum severity of NEW findings that fails CI (default: high)",
    )
    p.add_argument("--strict", action="store_true", help="alias for --fail-on medium")
    args = p.parse_args(argv)
    fail_on = "medium" if args.strict else args.fail_on

    print("🔍 Scanning backend (AST)...")
    routes_by_module, router_prefixes, mount_calls, parse_errors = scan_backend(py_files())
    print("🔍 Scanning frontend (regex)...")
    fe = fe_files()
    api_calls, nav_links, route_paths, import_lines = scan_frontend(fe)
    ghosts = detect_ghost_ui(fe, import_lines)

    findings, mounted_routes = build_findings(
        routes_by_module,
        router_prefixes,
        mount_calls,
        parse_errors,
        api_calls,
        nav_links,
        route_paths,
        ghosts,
    )

    print(
        f"  Backend modules with routes: {len(routes_by_module)} | mounted routes: "
        f"{len(mounted_routes)} | frontend calls: {len(api_calls)} | nav links: "
        f"{len(nav_links)} | route paths: {len(route_paths)}"
    )

    if args.update_baseline:
        save_baseline(args.baseline, findings)
        return 0

    baseline_keys = load_baseline(args.baseline)
    # Normalize live keys too so a Windows-authored scan matches a Linux-authored
    # baseline (and vice versa) — comparison is separator-agnostic both ways.
    for f in findings:
        f["key"] = _normalize_key(f["key"])
    new = [f for f in findings if f["key"] not in baseline_keys]
    known = [f for f in findings if f["key"] in baseline_keys]
    live_keys = {f["key"] for f in findings}
    resolved = baseline_keys - live_keys

    if fail_on == "never":
        blockers = []
    else:
        blockers = [f for f in new if SEVERITY_ORDER[f["severity"]] >= SEVERITY_ORDER[fail_on]]
    exit_code = 1 if blockers else 0

    print(human_report(findings, known, new, resolved, len(mounted_routes), len(api_calls)))

    # বাংলা নোট: --baseline যখন relative পাথ হিসেবে আসে (যেমন scheduled-deep-audit
    # থেকে "scripts/feature_parity_baseline.json"), তখন absolute ROOT-এর বিপরীতে
    # relative_to() কল করলে ValueError-এ ক্র্যাশ করে — গত ৩ দিনের nightly failure-এর
    # মূল কারণ এটাই। resolve() দিয়ে normalize + নিরাপদ fallback, আউটপুট আগের মতোই
    # repo-relative থাকে।
    try:
        baseline_display = str(args.baseline.resolve().relative_to(ROOT))
    except ValueError:
        baseline_display = str(args.baseline)
    baseline_meta = {"path": baseline_display}
    report = {
        "schema_version": "1.0",
        "stats": {
            "backend_modules_with_routes": len(routes_by_module),
            "mounted_routes": len(mounted_routes),
            "frontend_api_calls": len(api_calls),
            "nav_links": len(nav_links),
            "route_paths": len(route_paths),
            "total_findings": len(findings),
            "new": len(new),
            "known": len(known),
            "resolved": len(resolved),
        },
        "baseline": baseline_meta,
        "exit": {"code": exit_code, "fail_on": fail_on, "blockers": len(blockers)},
        "new_findings": new,
        "resolved_keys": sorted(resolved),
        "all_findings": findings,
    }
    if args.json:
        # বাংলা নোট: scheduled-deep-audit runner-এ ci-reports/ ডিরেক্টরি আগে থেকে
        # থাকে না — write_text সরাসরি FileNotFoundError দিত (Heavy Analysis-এর
        # দ্বিতীয় failure স্তর)। parent mkdir নিশ্চিত করে নিলে যেকোনো cwd থেকে নিরাপদ।
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  📄 JSON report → {args.json}")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(
            markdown_report(findings, known, new, resolved, baseline_meta), encoding="utf-8"
        )
        print(f"  📄 Markdown report → {args.markdown}")

    if exit_code:
        print(
            f"\n🚨 CI gate: {len(blockers)} NEW parity mismatch(es) at severity ≥ {fail_on}. "
            f"Fix them or explicitly extend the baseline.",
            file=sys.stderr,
        )
    else:
        print("\n✅ CI gate passed — no new parity drift beyond the accepted baseline.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
