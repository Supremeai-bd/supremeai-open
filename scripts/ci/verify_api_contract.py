#!/usr/bin/env python3
"""Frontend ↔ Backend API Contract Verifier (AUDIT-018 prevention).

এই স্ক্রিপ্ট backend-এর রাউটার রেজিস্ট্রেশন (backend/api/routers.py) ও প্রতিটি
রাউটার মডিউল থেকে পৌঁছানো যায় এমন HTTP রুটের সেট বানায়, তারপর frontend
TypeScript-এ নেটওয়ার্ক কল হিসেবে ব্যবহৃত `/api/...` / `/admin-api/...` স্ট্রিং
লিটারাল স্ক্যান করে — যেগুলো backend-এ নেই সেগুলো রিপোর্ট করে।

ব্যবহার:
    python scripts/ci/verify_api_contract.py
    python scripts/ci/verify_api_contract.py --json   # machine-readable আউটপুট

Exit code: 0 = contract OK, 1 = বিচ্ছিন্ন endpoint পাওয়া গেছে।
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTERS_FILE = ROOT / "backend" / "api" / "routers.py"
BACKEND_SRC = ROOT / "backend"
FRONTEND_SRC = ROOT / "frontend" / "src"

# যেসব prefix ফ্রন্টএন্ড-বেকএন্ড কন্ট্রাক্টের বাইরে (Firebase বিশেষ path ইত্যাদি)
SKIP_FRONTEND_PREFIXES = ("/__/",)

# রাউটার রেজিস্ট্রেশন পার্স: {"path": "module.path", "prefix": "/prefix", ...}
_REG_PATTERN = re.compile(r'"path"\s*:\s*"([^"]+)"\s*,\s*"prefix"\s*:\s*"([^"]*)"')

# রাউটার মডিউলে path ডেকোরেটর: @router.get("/path") / @router.websocket("/x")
_DECORATOR_PATTERN = re.compile(r"@router\.(?:get|post|put|patch|delete|websocket|api_route)\(\s*[\"'](/[^\"']*)[\"']")

# ফ্রন্টএন্ডে API path স্ট্রিং লিটারাল
_FRONTEND_PATH_PATTERN = re.compile(r"""["'`]((?:/api(?:/v\d+)?|/admin-api)[A-Za-z0-9/_.{}-]*)(?:["'`]|\?)""")


def norm(p: str) -> str:
    """Path নরমালাইজ: ট্রেইলিং স্ল্যাশ কাটা + path param একীভূত করা।"""
    p = re.sub(r"\{[^}/]+\}", "{PARAM}", p)
    p = re.sub(r":[A-Za-z_][A-Za-z0-9_]*(?=/|$)", "{PARAM}", p)
    p = p.split("?")[0]
    p = p.rstrip("/") or "/"
    return p


def parse_registered_routers() -> list[tuple[str, str]]:
    """routers.py থেকে (module_path, url_prefix) তালিকা বের করো (core + optional)।"""
    if not ROUTERS_FILE.exists():
        print(f"ERROR: routers file not found: {ROUTERS_FILE}", file=sys.stderr)
        sys.exit(2)
    text = ROUTERS_FILE.read_text(encoding="utf-8", errors="ignore")
    return _REG_PATTERN.findall(text)


def backend_routes() -> set[str]:
    """সমস্ত নিবন্ধিত রাউটার থেকে পূর্ণ HTTP path-এর সেট।"""
    routes: set[str] = set()
    for mod_path, prefix in parse_registered_routers():
        rel = mod_path.replace(".", "/") + ".py"
        mod_file = BACKEND_SRC / rel
        if not mod_file.exists():
            continue  # optional router অনুপস্থিত — optional হিসেবে গৃহীত
        text = mod_file.read_text(encoding="utf-8", errors="ignore")
        for path in _DECORATOR_PATTERN.findall(text):
            if path.startswith("/"):
                combined = prefix.rstrip("/") + path
            else:
                combined = prefix + "/" + path
            routes.add(norm(combined))
    return routes


def frontend_calls() -> set[str]:
    """ফ্রন্টএন্ডে ব্যবহৃত API path-এর সেট।"""
    calls: set[str] = set()
    src_files = [f for f in FRONTEND_SRC.rglob("*.ts") if "node_modules" not in f.parts and ".test." not in f.name and not f.name.endswith(".spec.ts")]
    src_files += [f for f in FRONTEND_SRC.rglob("*.tsx") if "node_modules" not in f.parts and ".test." not in f.name and not f.name.endswith(".spec.tsx")]
    for f in src_files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in _FRONTEND_PATH_PATTERN.finditer(text):
            path = m.group(1)
            if "${" in path:  # template interpolation — skip (dynamic build)
                continue
            if path.startswith(SKIP_FRONTEND_PREFIXES):
                continue
            calls.add(norm(path))
    return calls
def path_to_regex(p: str) -> re.Pattern[str]:
    """নরমালাইজড path থেকে regex — {PARAM} → [^/]+ , টেইল প্যারাম অনুমোদন।"""
    escaped = re.escape(p)
    escaped = escaped.replace(r"\{PARAM\}", r"[^/]+")
    return re.compile("^" + escaped)


def find_missing(backend: set[str], frontend: set[str]) -> list[str]:
    """ফ্রন্টএন্ড কল যেগুলো ডায়নামিক টেইলসহও backend-এ নেই, সেগুলো রিপোর্ট।"""
    backend_regexes = [path_to_regex(b) for b in backend]
    missing: list[str] = []
    for call in sorted(frontend):
        if call in backend:
            continue
        matched = False
        for rx in backend_regexes:
            if rx.fullmatch(call):
                matched = True
                break
            # backend static prefix + ফ্রন্টএন্ডে গভীর path (যেমন /api/files/x/y)
            m = rx.match(call)
            if m and (m.end() == len(call) or call[m.end() : m.end() + 1] == "/"):
                matched = True
                break
        if not matched:
            missing.append(call)
    return missing


def main() -> int:
    backend = backend_routes()
    frontend = frontend_calls()
    missing = find_missing(backend, frontend)

    if "--json" in sys.argv:
        print(json.dumps({
            "ok": not missing,
            "backend_routes": len(backend),
            "frontend_calls": len(frontend),
            "missing": missing,
        }, indent=2))
    else:
        print(f"Backend routes (registered): {len(backend)}")
        print(f"Frontend API calls found:     {len(frontend)}")
        if missing:
            print("\n[BROKEN CONTRACTS] frontend calls backend paths that are NOT registered:")
            for m in missing:
                print(f"   - {m}")
            print("\nFix: রাউটারটি backend/api/routers.py-তে register করুন কিংবা frontend পাথ ঠিক করুন।")
            return 1
        print("OK - all frontend API calls have matching backend routes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
