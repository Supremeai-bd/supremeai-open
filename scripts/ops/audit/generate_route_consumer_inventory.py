#!/usr/bin/env python3
"""Generate the route → frontend-consumer inventory (issue #480, required-fix steps 1-2+5).

Maps EVERY backend route to its frontend consumer, authorization surface and
disposition, then classifies each route:

    user-facing | admin-only | internal | deprecated | api-only | orphaned

* ``user-facing``  — a frontend consumer (literal ``/api/...`` reference in
  ``frontend/src/**.{ts,tsx}``) was matched.
* ``admin-only``   — path contains ``/admin`` / ``/admin-api``, the router file
  lives in an admin package, or the ALL_ROUTERS registry marks it ``is_admin``.
* ``internal``     — path segment is one of the internal namespaces
  (``internal``, ``ops``, ``health``, ``metrics``, ``webhook(s)``, ``cdc``,
  ``kernel``, ``system``, ``service-topology``).
* ``deprecated``   — marked deprecated in the endpoint docstring, decorator
  (``deprecated=True``) or route name/path (``legacy``/``deprecated``/``/v0/``).
* ``api-only``     — path family is allowlisted in
  ``scripts/audit/api_only_routes.txt`` (seeded with the currently-orphaned
  families; owner to prune as wiring lands — issue #480 steps 3-4).
* ``orphaned``     — no frontend consumer AND no classification above. This is
  the actionable output; the CI contract test
  (``tests/test_route_consumer_contract.py``) fails when a NEW orphan appears.

Static and dependency-free: the backend is scanned with :mod:`ast` (the app is
never imported), the frontend with a path-literal regex — the same heuristics as
the older ``scripts/ci/generate_route_client_inventory.py``, upgraded with the
ALL_ROUTERS registry (``backend/api/routers.py``) so resolved paths include the
include-time prefix and the ``is_admin`` flag, and with package-layout support
(``api/routes/admin_dashboard/``, ``browser/``, ``commandcenter/`` share the
package ``__init__.py`` router).

Usage:
    python scripts/audit/generate_route_consumer_inventory.py   # write docs/generated artifacts
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTERS_REGISTRY = REPO_ROOT / "backend" / "api" / "routers.py"
ROUTES_DIR = REPO_ROOT / "backend" / "api" / "routes"
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend" / "src"
ALLOWLIST_FILE = REPO_ROOT / "scripts" / "audit" / "api_only_routes.txt"
OUT_JSON = REPO_ROOT / "docs" / "generated" / "route_consumer_inventory.json"
OUT_MD = REPO_ROOT / "docs" / "generated" / "route_consumer_inventory.md"

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
CLASSIFICATIONS = (
    "user-facing",
    "admin-only",
    "internal",
    "deprecated",
    "api-only",
    "orphaned",
)

_FE_PATH = re.compile(r"['\"`](/api/[A-Za-z0-9/_\-\.]+(?:\$\{[^}]+\})*)['\"`]")
_TMPL_PARAM = re.compile(r"\$\{[^}]+\}")
_BRACE_PARAM = re.compile(r"\{[^}]+\}")
_COLON_PARAM_TYPED = re.compile(r"/:param<[^>]*>")

# Path segments that mark an internal namespace (issue #480 fix #2).
_INTERNAL_SEGMENTS = {
    "internal",
    "ops",
    "health",
    "healthz",
    "metrics",
    "webhook",
    "webhooks",
    "cdc",
    "kernel",
    "system",
    "service-topology",
}
_DEPRECATED_PATH = re.compile(r"/legacy(/|$)|/deprecated|/v0(/|$)", re.IGNORECASE)
_DEPRECATED_NAME = re.compile(r"legacy|deprecated|_v0", re.IGNORECASE)


def _normalize(path: str) -> str:
    """Canonicalize a backend or frontend path for matching."""
    path = _TMPL_PARAM.sub(":param", path)
    path = _BRACE_PARAM.sub(":param", path)
    path = _COLON_PARAM_TYPED.sub("/:param", path)
    path = re.sub(r"/+", "/", path)
    return path.rstrip("/") or "/"


def route_family(path: str) -> str:
    """Family key for a resolved route path (allowlist granularity).

    ``/api/v1/users/{id}`` → ``/api/v1/users`` · ``/api/admin/users`` →
    ``/api/admin/users`` · ``/admin-api/agents`` → ``/admin-api/agents``.
    """
    if path == "/":
        return "/"
    segments = [s for s in _normalize(path).split("/") if s]
    if segments and segments[0] == "api":
        return "/" + "/".join(segments[:3])
    return "/" + "/".join(segments[:2])


# ---------------------------------------------------------------------------
# Backend enumeration (AST only — the app is never imported)
# ---------------------------------------------------------------------------


def parse_router_registry() -> list[dict]:
    """Parse the ALL_ROUTERS registry from backend/api/routers.py (AST).

    Direct ``register_router(app, "module", ...)`` calls in the same file
    (e.g. the conditional ``api.routes.byoc_api`` mount) count as registered
    modules too — they are mounted at runtime, just not via the registry list.
    """
    tree = ast.parse(ROUTERS_REGISTRY.read_text(encoding="utf-8"))
    entries: list[dict] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "ALL_ROUTERS" for t in node.targets
        ):
            try:
                registry = ast.literal_eval(node.value)
            except ValueError as exc:  # pragma: no cover — registry is literal
                raise SystemExit(f"ALL_ROUTERS registry is not literal: {exc}") from exc
            for entry in registry:
                if isinstance(entry, dict) and "path" in entry:
                    entries.append(
                        {
                            "module": entry["path"],
                            "prefix": entry.get("prefix", ""),
                            "is_admin": bool(entry.get("is_admin", False)),
                        }
                    )
                    seen.add(entry["path"])
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Name)
                and func.id == "register_router"
                and node.args
            ):
                callee_ok = (
                    isinstance(node.args[0], ast.Name) and node.args[0].id == "app"
                )
                module_ok = (
                    len(node.args) > 1
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                )
                if callee_ok and module_ok and node.args[1].value not in seen:
                    prefix = ""
                    if len(node.args) > 2 and isinstance(node.args[2], ast.Constant):
                        prefix = str(node.args[2].value or "")
                    for kw in node.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            prefix = str(kw.value.value or "")
                    entries.append(
                        {
                            "module": node.args[1].value,
                            "prefix": prefix,
                            "is_admin": False,
                        }
                    )
                    seen.add(node.args[1].value)
    if not entries:
        raise SystemExit("ALL_ROUTERS registry not found in backend/api/routers.py")
    return entries


def _registry_module_files(module: str) -> list[Path]:
    """Resolve a dotted module path to concrete file(s) under backend/."""
    base = BACKEND_DIR / module.replace(".", "/")
    if base.is_dir():
        return sorted(p for p in base.rglob("*.py") if p.is_file())
    if base.with_suffix(".py").is_file():
        return [base.with_suffix(".py")]
    return []


def _module_name_for_file(file: Path) -> str | None:
    """Best-effort dotted module name for a backend file (for reporting)."""
    try:
        rel = file.resolve().relative_to(BACKEND_DIR.resolve())
    except ValueError:
        return None
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _router_prefixes_in_file(tree: ast.AST) -> dict[str, str]:
    """Map local variable name → APIRouter prefix declared in this file."""
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        call = None
        if isinstance(node, ast.Assign):
            targets, call = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, call = [node.target], node.value
        if call is None or not isinstance(call, ast.Call):
            continue
        func = call.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "APIRouter":
            continue
        prefix = ""
        for kw in call.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                prefix = str(kw.value.value) if kw.value.value else ""
                break
        else:
            # FastAPI's APIRouter(prefix) is also accepted positionally.
            if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
                prefix = str(call.args[1].value) if call.args[1].value else ""
        for target in targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _package_router_prefix(file: Path) -> dict[str, str]:
    """Fallback prefix map from a sibling package ``__init__.py``.

    Package layout (admin_dashboard/, browser/, commandcenter/) declares the
    shared ``router = APIRouter(prefix=...)`` in ``__init__.py``; submodule
    files then decorate that imported name directly.
    """
    init = file.parent / "__init__.py"
    if init.is_file() and init != file:
        try:
            tree = ast.parse(init.read_text(encoding="utf-8"))
        except SyntaxError:
            return {}
        return _router_prefixes_in_file(tree)
    return {}


def _decorator_route(dec: ast.AST) -> tuple[str, str] | None:
    """Extract (method, declared path) from a ``@router.<method>(...)`` node."""
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute):
        return None
    method = func.attr.lower()
    if method not in HTTP_METHODS:
        return None
    path: str | None = None
    if (
        dec.args
        and isinstance(dec.args[0], ast.Constant)
        and isinstance(dec.args[0].value, str)
    ):
        path = dec.args[0].value
    else:
        for kw in dec.keywords:
            if (
                kw.arg == "path"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                path = kw.value.value
                break
    if path is None:  # f-string / dynamic path — best effort, recorded empty
        path = ""
    return method.upper(), path


def _is_deprecated(node: ast.AST, method: str, path: str) -> bool:
    doc = ast.get_docstring(node) or ""
    if "deprecated" in doc.lower():
        return True
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "deprecated" and getattr(kw.value, "value", None) is True:
                    return True
    if _DEPRECATED_PATH.search(path):
        return True
    return bool(_DEPRECATED_NAME.search(getattr(node, "name", "")))


def extract_routes_from_file(
    file: Path, *, registry_prefix: str | None, is_admin: bool, mounted: bool
) -> list[dict]:
    """AST-extract every HTTP route declared in one backend file."""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    prefixes = _router_prefixes_in_file(tree)
    package_prefixes = _package_router_prefix(file) if not prefixes else {}
    module = _module_name_for_file(file)
    rel = file.relative_to(REPO_ROOT).as_posix()

    routes: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            extracted = _decorator_route(dec)
            if extracted is None:
                continue
            method, declared_path = extracted
            var = dec.func.value.id if isinstance(dec.func.value, ast.Name) else ""
            router_prefix = prefixes.get(var)
            if router_prefix is None:
                router_prefix = package_prefixes.get(var, "")
            include_prefix = registry_prefix or ""
            full = _normalize(include_prefix + router_prefix + declared_path)
            routes.append(
                {
                    "method": method,
                    "path": full,
                    "declared": include_prefix + router_prefix + declared_path,
                    "deprecated": _is_deprecated(node, method, declared_path),
                    "router_file": rel,
                    "module": module,
                    "registry_prefix": registry_prefix or "",
                    "mounted": mounted,
                    "is_admin": is_admin,
                    "operation": node.name,
                }
            )
    return routes


def scan_backend() -> tuple[list[dict], int]:
    """Enumerate all routes: registry modules first, then unregistered files."""
    registry = parse_router_registry()
    routes: list[dict] = []
    covered: set[Path] = set()
    for entry in registry:
        files = _registry_module_files(entry["module"])
        covered.update(f.resolve() for f in files)
        for file in files:
            routes.extend(
                extract_routes_from_file(
                    file,
                    registry_prefix=entry["prefix"],
                    is_admin=entry["is_admin"],
                    mounted=True,
                )
            )
    unregistered = 0
    if ROUTES_DIR.is_dir():
        for file in sorted(ROUTES_DIR.rglob("*.py")):
            if file.resolve() in covered:
                continue
            unregistered += 1
            routes.extend(
                extract_routes_from_file(
                    file, registry_prefix=None, is_admin=False, mounted=False
                )
            )
    routes.sort(
        key=lambda r: (r["path"], r["method"], r["router_file"], r["operation"])
    )
    return routes, unregistered


# ---------------------------------------------------------------------------
# Frontend enumeration (same heuristic as the existing generators)
# ---------------------------------------------------------------------------


def scan_frontend() -> dict[str, list[str]]:
    """Literal ``/api/...`` path references in frontend/src/**.{ts,tsx}."""
    refs: dict[str, list[str]] = {}
    if not FRONTEND_DIR.is_dir():
        return refs
    for file in sorted(FRONTEND_DIR.rglob("*")):
        if file.suffix not in {".ts", ".tsx"} or not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(REPO_ROOT).as_posix()
        for match in _FE_PATH.finditer(text):
            refs.setdefault(_normalize(match.group(1)), []).append(rel)
    return {k: sorted(set(v)) for k, v in sorted(refs.items())}


def _segment_match(a: str, b: str) -> bool:
    sa, sb = a.split("/"), b.split("/")
    return len(sa) == len(sb) and all(
        x == ":param" or x == y for x, y in zip(sa, sb, strict=True)
    )


def find_consumers(route_path: str, fe_index: dict) -> list[str]:
    """Match a backend route against the frontend reference index.

    Resolution order: exact → param-normalized → frontend references a base
    path of this route (e.g. frontend calls ``/api/admin`` while the backend
    exposes ``/api/admin/users``). ``/api/v1/x`` and ``/api/x`` are aliases.
    """
    exact: dict[str, list[str]] = {}
    param: list[tuple[str, list[str]]] = []
    for fe_path, files in fe_index.items():
        exact[fe_path] = files
        if fe_path.startswith("/api/v1/"):
            alias = "/api/" + fe_path[len("/api/v1/") :]
            exact.setdefault(alias, files)
        param.append((fe_path, files))

    candidates = [route_path]
    if route_path.startswith("/api/v1/"):
        candidates.append("/api/" + route_path[len("/api/v1/") :])

    for cand in candidates:
        if cand in exact:
            return exact[cand]
    for cand in candidates:
        for fe_path, files in param:
            if _segment_match(fe_path, cand):
                return files
    for cand in candidates:
        for fe_path, files in param:
            if cand.startswith(fe_path + "/") and fe_path.count("/") >= 2:
                return files
    return []


# ---------------------------------------------------------------------------
# Classification + allowlist
# ---------------------------------------------------------------------------


def load_allowlist(path: Path = ALLOWLIST_FILE) -> list[str]:
    """Load api-only family prefixes (``#`` comments, blank lines skipped)."""
    if not path.is_file():
        return []
    families: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        families.append(_normalize(line))
    return sorted(set(families), key=len, reverse=True)


def _is_admin_route(route: dict) -> bool:
    if route["is_admin"]:
        return True
    path = route["path"]
    if "/admin" in path:
        return True
    router_file = route["router_file"]
    return "admin_dashboard/" in router_file or "/admin_" in router_file


def _is_internal_route(path: str) -> bool:
    segments = {s.lower() for s in path.split("/") if s}
    return bool(segments & _INTERNAL_SEGMENTS)


def classify(route: dict, allowlist: list[str]) -> str:
    """Single-label disposition (issue #480 fix #2). Priority order documented
    in the module docstring; a route with a frontend consumer is user-facing
    regardless of the allowlist (owner to prune the stale line as wiring lands)."""
    path = _normalize(route["path"])
    if route.get("deprecated"):
        return "deprecated"
    if _is_admin_route(route):
        return "admin-only"
    if _is_internal_route(path):
        return "internal"
    if route["frontend_consumers"]:
        return "user-facing"
    if any(path == fam or path.startswith(fam + "/") for fam in allowlist):
        return "api-only"
    return "orphaned"


# ---------------------------------------------------------------------------
# Inventory assembly + outputs
# ---------------------------------------------------------------------------


def build_inventory(
    routes: list[dict] | None = None,
    fe_index: dict[str, list[str]] | None = None,
    allowlist: list[str] | None = None,
) -> dict:
    """Build the full inventory payload (deterministic — no timestamps)."""
    if routes is None or fe_index is None:
        routes, unregistered_files = scan_backend()
        fe_index = scan_frontend()
    else:
        unregistered_files = 0
    if allowlist is None:
        allowlist = load_allowlist()

    for route in routes:
        route["frontend_consumers"] = find_consumers(route["path"], fe_index)

    for route in routes:
        route["classification"] = classify(route, allowlist)

    by_classification: dict[str, int] = {c: 0 for c in CLASSIFICATIONS}
    for route in routes:
        by_classification[route["classification"]] += 1

    orphan_families: dict[str, int] = {}
    api_only_families: dict[str, int] = {}
    for route in routes:
        fam = route_family(route["path"])
        if route["classification"] == "orphaned":
            orphan_families[fam] = orphan_families.get(fam, 0) + 1
        elif route["classification"] == "api-only":
            api_only_families[fam] = api_only_families.get(fam, 0) + 1

    return {
        "schema_version": "1.0",
        "generated_by": (
            "scripts/audit/generate_route_consumer_inventory.py "
            "(issue #480 required-fix steps 1-2+5)"
        ),
        "issue": "https://github.com/SaifulHaqueNiloy/supremeai/issues/480",
        "allowlist_file": "scripts/audit/api_only_routes.txt",
        "assumptions": [
            "resolved path = ALL_ROUTERS include-time prefix + file's APIRouter(prefix) + decorator path",
            "package routers (admin_dashboard/, browser/, commandcenter/) take their prefix from the package __init__.py",
            "routes in backend/api/routes/ not present in ALL_ROUTERS are marked mounted=false (unregistered files: "
            + str(unregistered_files)
            + ")",
            "websocket routes are out of scope (no HTTP method, no openapi entry)",
            "frontend consumers are literal /api/... strings in frontend/src/**.{ts,tsx}; ${...} template params normalize to :param",
            "matching: exact → param-normalized → frontend base-path reference; /api/v1/x and /api/x are aliases",
            "family = first 3 path segments for /api/... paths, first 2 otherwise (allowlist granularity)",
            "classification priority: deprecated > admin-only > internal > user-facing > api-only > orphaned",
        ],
        "totals": {
            "backend_routes": len(routes),
            "frontend_unique_refs": len(fe_index),
            "routes_with_frontend_consumer": sum(
                1 for r in routes if r["frontend_consumers"]
            ),
            "unmounted_routes": sum(1 for r in routes if not r["mounted"]),
            "orphan_routes": by_classification["orphaned"],
            "orphan_families": len(orphan_families),
            "api_only_routes": by_classification["api-only"],
            "api_only_families": len(api_only_families),
            "by_classification": by_classification,
        },
        "orphan_families": dict(sorted(orphan_families.items())),
        "api_only_families": dict(sorted(api_only_families.items())),
        "routes": routes,
    }


def write_markdown(payload: dict) -> str:
    totals = payload["totals"]
    by_class = totals["by_classification"]
    lines = [
        "# Route → Frontend-Consumer Inventory (generated)",
        "",
        (
            "> Generator: `scripts/audit/generate_route_consumer_inventory.py` — "
            "issue #480 required-fix steps 1-2+5. Do not edit by hand; regenerate with "
            "`python scripts/audit/generate_route_consumer_inventory.py`. "
            "CI gate: `tests/test_route_consumer_contract.py` (drift + new-orphan)."
        ),
        "",
        "| metric | value |",
        "|---|---|",
        f"| backend routes | {totals['backend_routes']} |",
        f"| routes with frontend consumer | {totals['routes_with_frontend_consumer']} |",
        f"| unique frontend `/api/...` refs | {totals['frontend_unique_refs']} |",
        f"| unmounted routes (not in ALL_ROUTERS) | {totals['unmounted_routes']} |",
        f"| orphan routes (unclassified) | {totals['orphan_routes']} |",
        f"| orphan families | {totals['orphan_families']} |",
        f"| api-only routes (allowlisted) | {totals['api_only_routes']} |",
        f"| api-only families | {totals['api_only_families']} |",
        "",
        "## Classification legend",
        "",
        "| classification | count | meaning |",
        "|---|---|---|",
        "| `user-facing` | "
        + str(by_class["user-facing"])
        + " | frontend consumer matched |",
        "| `admin-only` | "
        + str(by_class["admin-only"])
        + " | /admin path, admin router file or ALL_ROUTERS is_admin |",
        "| `internal` | "
        + str(by_class["internal"])
        + " | internal namespace (internal/ops/health/metrics/webhook/cdc/kernel/system) |",
        "| `deprecated` | "
        + str(by_class["deprecated"])
        + " | marked deprecated (docstring/decorator/name/path) |",
        "| `api-only` | "
        + str(by_class["api-only"])
        + " | family allowlisted in `scripts/audit/api_only_routes.txt` — "
        "owner to prune as wiring lands (#480 steps 3-4) |",
        "| `orphaned` | "
        + str(by_class["orphaned"])
        + " | no consumer and no classification — CI fails on NEW orphans |",
        "",
    ]
    if payload["orphan_families"]:
        lines += [
            "## Orphan families (actionable — wire, classify or deprecate)",
            "",
            "| family | orphan routes |",
            "|---|---|",
            *(f"| `{fam}` | {n} |" for fam, n in payload["orphan_families"].items()),
            "",
        ]
    else:
        lines += [
            "## Orphan families",
            "",
            (
                "None — every route is classified or allowlisted. New orphans fail "
                "`tests/test_route_consumer_contract.py`."
            ),
            "",
        ]
    if payload["api_only_families"]:
        lines += [
            "## Intentionally API-only families (allowlisted — owner to prune as wiring lands)",
            "",
            "| family | routes |",
            "|---|---|",
            *(f"| `{fam}` | {n} |" for fam, n in payload["api_only_families"].items()),
            "",
        ]
    lines += [
        "## Full route table",
        "",
        "| Method | Path | Router file | Classification | Frontend consumers |",
        "|---|---|---|---|---|",
    ]
    for route in payload["routes"]:
        consumers = route["frontend_consumers"]
        consumer_cell = (
            ", ".join(f"`{c}`" for c in consumers[:3])
            + (f" (+{len(consumers) - 3} more)" if len(consumers) > 3 else "")
            if consumers
            else "NONE"
        )
        mounted = "" if route["mounted"] else " *(unmounted)*"
        lines.append(
            f"| {route['method']} | `{route['path']}` | "
            f"`{route['router_file']}` | {route['classification']}{mounted} | "
            f"{consumer_cell} |"
        )
    lines.append("")
    return "\n".join(lines)


def detect_new_orphans(
    fresh: dict, committed: dict | None, allowlist: list[str]
) -> list[dict]:
    """Return orphaned routes that are NEW relative to the committed baseline.

    A route is a *new orphan* when it is classified ``orphaned`` in the fresh
    scan and is neither recorded as an orphan in the committed inventory nor
    covered by the api-only allowlist. This is the issue #480 step-5 contract:
    the pre-existing (allowlisted) debt never fails the gate; a newly orphaned
    route always does.
    """
    committed_orphans = {
        (route["method"], route["path"])
        for route in (committed or {}).get("routes", [])
        if route.get("classification") == "orphaned"
    }
    new: list[dict] = []
    for route in fresh.get("routes", []):
        if route.get("classification") != "orphaned":
            continue
        if (route["method"], route["path"]) in committed_orphans:
            continue
        path = _normalize(route["path"])
        if any(path == fam or path.startswith(fam + "/") for fam in allowlist):
            continue
        new.append(route)
    return new


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the route → frontend-consumer inventory (issue #480)"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="suppress the summary printout"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when a NEW orphaned route (not in the committed baseline "
        "and not allowlisted) is detected — issue #480 step 5",
    )
    args = parser.parse_args()

    committed_payload: dict | None = None
    if args.check and OUT_JSON.is_file():
        committed_payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))

    payload = build_inventory()
    totals = payload["totals"]

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(write_markdown(payload), encoding="utf-8")

    if not args.quiet:
        print(
            "routes={backend_routes} consumers={routes_with_frontend_consumer} "
            "fe_refs={frontend_unique_refs} orphan={orphan_routes} "
            "(families={orphan_families}) api_only={api_only_routes} "
            "(families={api_only_families})".format(**totals)
        )
        print(
            f"wrote {OUT_JSON.relative_to(REPO_ROOT)}, {OUT_MD.relative_to(REPO_ROOT)}"
        )

    if args.check:
        new_orphans = detect_new_orphans(payload, committed_payload, load_allowlist())
        if new_orphans:
            print(
                f"::error::{len(new_orphans)} NEW orphaned route(s) — wire a frontend "
                "consumer, classify, or allowlist (scripts/audit/api_only_routes.txt): "
                + "; ".join(f"{r['method']} {r['path']}" for r in new_orphans[:10]),
                file=sys.stderr,
            )
            return 1
        if not args.quiet:
            print("check: no new orphaned routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
