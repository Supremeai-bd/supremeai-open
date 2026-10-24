#!/usr/bin/env python3
"""Generate the route→client inventory (issue #480 / GAP-001).

বাংলা: ৫৭টি orphan backend route-family হাতে ধরে না মেপে — জেনারেট করা
ইনভেন্টরি: প্রতিটি FastAPI route (file, method, path, prefix) বনাম frontend-এর
আসল `/api/...` রেফারেন্স (file list সহ)। রেজাল্ট JSON + markdown সামারিতে
orphans, matched, param-normalized কাউন্ট। এটাই GAP-001-এর "generated
route-to-client inventory rather than manual assumptions"।

English: static, dependency-free AST-lite scanner.
  * Backend: every `@router.<method>("...")` in backend/api/routes/*.py with
    the file's `APIRouter(prefix=...)` declaration (include-time prefixes are
    noted in routers.py comments; the resolved path is a best-effort join —
    assumptions documented in the output header).
  * Frontend: every literal `/api/...` string in frontend/src/**.{ts,tsx} with
    referencing files. `${...}` template params normalize to `:param`.
  * Matching: exact → param-normalized → frontend-prefix-of-backend → orphan.

Usage:
  python scripts/ci/generate_route_client_inventory.py                 # write docs + summary
  python scripts/ci/generate_route_client_inventory.py --check N       # exit 1 if orphans > N
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_DIR = REPO_ROOT / "backend" / "api" / "routes"
FRONTEND_DIR = REPO_ROOT / "frontend" / "src"
OUT_JSON = REPO_ROOT / "docs" / "audit_reports" / "route_client_inventory.json"
OUT_MD = REPO_ROOT / "docs" / "audit_reports" / "route_client_inventory.md"

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
_DEC = re.compile(
    r"@(?P<var>[A-Za-z_][\w]*)\.(?P<method>get|post|put|patch|delete|head|options)\(\s*"
    r"['\"](?P<path>/[^'\"]*)['\"]",
)
_ROUTER_DEF = re.compile(
    r"(?P<var>[A-Za-z_][\w]*)\s*=\s*APIRouter\((?P<args>[^)]*)\)", re.DOTALL
)
_PREFIX = re.compile(r"prefix\s*=\s*['\"]([^'\"]*)['\"]")
_PARAM = re.compile(r"\$\{[^}]+\}")
_FE_PATH = re.compile(r"['\"`](/api/[A-Za-z0-9/_\-\.]+(?:\$\{[^}]+\})*)['\"`]")


def _normalize(path: str) -> str:
    path = _PARAM.sub(":param", path)
    path = re.sub(r"/:param<[^>]*>", "/:param", path)
    path = re.sub(r"\{[^}]+\}", ":param", path)
    return path.rstrip("/")


def scan_backend() -> list[dict]:
    routes: list[dict] = []
    for file in sorted(ROUTES_DIR.glob("*.py")):
        text = file.read_text(encoding="utf-8", errors="replace")
        prefixes: dict[str, str] = {}
        for m in _ROUTER_DEF.finditer(text):
            var = m.group("var")
            p = _PREFIX.search(m.group("args"))
            prefixes[var] = p.group(1) if p else ""
        for m in _DEC.finditer(text):
            var, method, path = (
                m.group("var"),
                m.group("method").upper(),
                m.group("path"),
            )
            prefix = prefixes.get(var, "")
            full = _normalize(
                (prefix + path) if not path.startswith(prefix or "") else path
            )
            if not full.startswith("/api"):
                full = "/api/v1" + full if full.startswith("/") else "/api/v1/" + full
            routes.append(
                {
                    "file": f"backend/api/routes/{file.name}",
                    "method": method,
                    "declared": prefix + path,
                    "resolved": full,
                }
            )
    return routes


def scan_frontend() -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    if not FRONTEND_DIR.exists():
        return refs
    for file in sorted(FRONTEND_DIR.rglob("*")):
        if file.suffix not in {".ts", ".tsx"} or not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001, S112
            continue
        rel = file.relative_to(REPO_ROOT).as_posix()
        for m in _FE_PATH.finditer(text):
            refs.setdefault(_normalize(m.group(1)), []).append(rel)
    return refs


def match(routes: list[dict], fe_refs: dict[str, list[str]]) -> dict[str, list[dict]]:
    # /api/v1/... and /api/... are treated as aliases (frontend uses /api/...,
    # backend routers declare /api/v1/...) — documented in assumptions.
    fe_alias: dict[str, str] = {}
    for k in fe_refs:
        fe_alias[k] = k
        if k.startswith("/api/v1/"):
            fe_alias.setdefault("/api/" + k[len("/api/v1/") :], k)
    fe_keys = list(fe_alias)
    matched, orphan, shared = [], [], []
    for r in routes:
        rp = r["resolved"]
        candidates = [rp]
        if rp.startswith("/api/v1/"):
            candidates.append("/api/" + rp[len("/api/v1/") :])
        hit = None
        for cand in candidates:
            if cand in fe_alias:
                hit = fe_alias[cand]
                break
        if hit is None:
            for fk in fe_keys:
                fcand = fe_alias[fk]
                for cand in candidates:
                    seg_f, seg_b = fcand.split("/"), cand.split("/")
                    if seg_f == seg_b or (
                        len(seg_f) == len(seg_b)
                        and all(
                            b == ":param" or a == b
                            for a, b in zip(seg_f, seg_b, strict=True)
                        )
                    ):
                        hit = fk
                        break
                    # frontend references a base path (e.g. /api/admin) of this route
                    if cand.startswith(fcand + "/") and fcand.count("/") >= 2:
                        hit = fk
                        break
                if hit:
                    break
        if hit:
            matched.append({**r, "frontend": fe_refs[hit][:4]})
        elif r["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            orphan.append(r)
    return {"matched": matched, "orphan": orphan, "shared": shared}


def _classify(route: dict) -> str:
    """Heuristic disposition (issue #480 fix #2) — intent still needs owners
    for the unclassified bucket; admin/internal/legacy are safe auto-labels."""
    path = route["resolved"]
    file = route["file"]
    if re.search(r"/legacy/|/deprecated|/v0/", path):
        return "deprecated-pattern"
    if "admin_dashboard" in file or re.search(r"/admin(/|$)", path):
        return "admin-only"
    if re.search(r"/(internal|system|mcp|ops|metrics|kernel|health|webhook)", path):
        return "internal"
    return "unclassified-orphan"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check",
        type=int,
        default=None,
        metavar="N",
        help="exit 1 if orphan route count exceeds N",
    )
    args = ap.parse_args()

    routes = scan_backend()
    for r in routes:
        r["classification"] = _classify(r)
    fe_refs = scan_frontend()
    result = match(routes, fe_refs)

    by_family: dict[str, int] = {}
    for o in result["orphan"]:
        fam = "/".join(o["resolved"].split("/")[:4])
        by_family[fam] = by_family.get(fam, 0) + 1

    class_counts: dict[str, int] = {}
    for o in result["orphan"]:
        class_counts[o["classification"]] = class_counts.get(o["classification"], 0) + 1

    payload = {
        "generated_by": "scripts/ci/generate_route_client_inventory.py (issue #480 / GAP-001)",
        "assumptions": [
            "resolved = file's APIRouter(prefix) + decorator path; /api/v1 prepended when the join lacks it",
            "include-time prefixes (see backend/api/routers.py) are NOT re-applied — cross-check routers.py for exceptions",
            "frontend refs are literal /api/... strings in frontend/src/**.{ts,tsx}",
        ],
        "totals": {
            "backend_routes": len(routes),
            "frontend_unique_refs": len(fe_refs),
            "matched": len(result["matched"]),
            "orphan_routes": len(result["orphan"]),
        },
        "orphan_by_family": dict(sorted(by_family.items(), key=lambda kv: -kv[1])),
        "orphan_by_classification": dict(
            sorted(class_counts.items(), key=lambda kv: -kv[1])
        ),
        "orphans": result["orphan"],
        "matched": result["matched"],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md = [
        "# Route → Client Inventory (generated)",
        "",
        (
            "> Generator: `scripts/ci/generate_route_client_inventory.py` — issue #480 / GAP-001. "
            "Do not edit by hand; assumptions live inside the JSON header."
        ),
        "",
        f"- backend routes scanned: **{len(routes)}**",
        f"- unique frontend `/api/...` refs: **{len(fe_refs)}**",
        f"- matched (frontend-reachable): **{len(result['matched'])}**",
        f"- orphan backend routes: **{len(result['orphan'])}** ({len(by_family)} route families)",
        "",
        "## Orphan classifications (heuristic — owners must ratify)",
        "",
        "| classification | count | next action |",
        "|---|---|---|",
        *(
            "| `"
            + k
            + "` | "
            + str(v)
            + " | "
            + {
                "admin-only": "wire into admin UI or document as admin-API",
                "internal": "document as internal; verify not publicly reachable",
                "deprecated-pattern": "deprecate formally (#480 fix #4)",
                "unclassified-orphan": "triage: user-facing wiring vs intentional API-only",
            }.get(k, "triage")
            + " |"
            for k, v in class_counts.items()
        ),
        "",
        "## Top orphan families",
        "",
        "| family | orphan routes |",
        "|---|---|",
        *("| `" + k + "` | " + str(v) + " |" for k, v in list(by_family.items())[:20]),
        "",
        "Full detail: `docs/audit_reports/route_client_inventory.json`.",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(
        f"routes={len(routes)} fe_refs={len(fe_refs)} matched={len(result['matched'])} "
        f"orphan={len(result['orphan'])} (families={len(by_family)})"
    )
    print(f"wrote {OUT_JSON.name}, {OUT_MD.name}")
    if args.check is not None and len(result["orphan"]) > args.check:
        print(
            f"::error::orphan routes {len(result['orphan'])} > baseline {args.check} — new unwired backend surface (issue #480)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
