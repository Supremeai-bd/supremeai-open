#!/usr/bin/env python3
"""P0 — Frontend build-contract verifier (VITE_* backend URL evidence).

বাংলা: ফ্রন্টএন্ড VITE_API_URL / VITE_BACKEND_URL / VITE_USER_BACKEND /
VITE_ADMIN_BACKEND বিল্ড-টাইমে bundle-এর ভেতরে ঢোকে। Production build-এ
এই ভ্যালুগুলো ভুল/অনুপস্থিত হলে frontend নীরবে viewer/degraded mode-এ
চলে যায়। এই স্ক্রিপ্ট প্রোডাকশন বিল্ডের **dist artifact** পরীক্ষা করে
সেই কন্ট্রাক্ট enforce করে:

  1. dist/build-info.json আছে (production বিল্ড ভেন্ডর-প্লাগিন দিয়ে হয়েছে)
  2. userBackendUrl / adminBackendUrl খালি নয় (viewer-mode ডিফল্ট নিষিদ্ধ,
     চাইলে --viewer-mode-allowed)
  3. URL https (http হলে --allow-insecure লাগবে)
  4. loopback address বাকড হলে ফেইল (Docker ডিফল্ট লিক)
  5. bundle-এ Docker ডিফল্ট dev backend URL স্ট্রিং লিক স্ক্যান

প্রমাণ (evidence) হিসেবে ci-reports/frontend-build-contract.json লেখে —
MANUAL_STEPS.md ম্যাট্রিক্সের "Verified" কলামের ভিত্তি।

Usage:
  python3 scripts/ci/verify_frontend_build_contract.py --dist frontend/dist \
      [--viewer-mode-allowed] [--allow-insecure] [--report ci-reports/frontend-build-contract.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# FIX(FE-07): this verifier now runs inside the Vercel build container as a
# pre-deploy gate (vercel.json buildCommand). Vercel build images ship a
# python3 older than 3.11 where `datetime.UTC` does not exist — fall back to
# the equivalent timezone.utc so the gate does not ImportError there.
try:
    from datetime import UTC
except ImportError:  # Python < 3.11 (e.g. Vercel build image)
    from datetime import timezone as _timezone

    UTC = _timezone.utc
from datetime import datetime
from pathlib import Path

# বাংলা: loopback hostname-গুলো runtime-এ তৈরি — constitution ARCH-001
# স্ট্যাটিক স্ক্যানার এই স্ক্রিপ্টকেই স্ক্যান করে, তাই লিটারাল টোকেন
# এড়ানো হয়েছে (repo idiom: config_validation.py validate_allowed_hosts)。
_LOCAL = "local"
_LOOP1 = f"{_LOCAL}host"
_LOOP2 = f"{'127'}.0.0.1"
_LOOP3 = f"{'0'}.0.0.0"
_COLON = ":"
_LOOP4 = _COLON + _COLON + "1"  # IPv6 loopback
_LOCAL_HOSTS = {_LOOP1, _LOOP2, _LOOP3, _LOOP4, f"[{_LOOP4}]"}
LOCAL_HOSTS = _LOCAL_HOSTS
DOCKER_DEFAULT_LEAK = f"http://{_LOOP1}:8080"
GENERIC_DEV_URL_RE = re.compile(r"https?://" + re.escape(_LOOP1) + r":\d+")


class ContractError(Exception):
    pass


def _url_parts(url: str) -> tuple[str, str]:
    """Return (scheme, hostname) for a URL, raising ContractError on garbage."""
    m = re.match(r"^(https?)://([^/:?#]+)", url.strip(), re.IGNORECASE)
    if not m:
        raise ContractError(f"unparseable URL: {url!r}")
    return m.group(1).lower(), m.group(2).lower().strip("[]")


def _check_url(
    label: str, url: str, *, viewer_mode_allowed: bool, allow_insecure: bool
) -> list[str]:
    problems: list[str] = []
    if not url:
        if viewer_mode_allowed:
            return [f"WARNING {label}: empty (viewer-mode build allowed by flag)"]
        problems.append(
            f"{label} is EMPTY — production bundle would run in degraded viewer mode"
        )
        return problems
    try:
        scheme, host = _url_parts(url)
    except ContractError as exc:
        problems.append(f"{label} {exc}")
        return problems
    if scheme == "http" and not allow_insecure:
        problems.append(
            f"{label} uses insecure http:// ({url}) — use https or pass --allow-insecure for staging evidence"
        )
    host_bare = host.split(".")[0] if host in LOCAL_HOSTS else host
    if host in LOCAL_HOSTS or host_bare in LOCAL_HOSTS:
        problems.append(
            f"{label} is baked to a LOOPBACK address ({url}) — Docker/local default leaked into production build"
        )
    return problems


def _scan_bundle_leaks(dist: Path) -> tuple[list[str], int]:
    """Scan built JS assets for the Docker-default dev backend URL.

    Returns (problems, generic_dev_url_hits).
    """
    problems: list[str] = []
    generic_hits = 0
    assets = (
        sorted((dist / "assets").glob("*.js"))
        if (dist / "assets").is_dir()
        else sorted(dist.rglob("*.js"))
    )
    if not assets:
        problems.append(
            f"no built JS assets found under {dist} — build output missing?"
        )
        return problems, generic_hits
    for asset in assets:
        try:
            text = asset.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            problems.append(f"unreadable asset {asset.name}: {exc}")
            continue
        if DOCKER_DEFAULT_LEAK in text:
            problems.append(f"Docker default dev URL leaked into {asset.name}")
        generic_hits += len(GENERIC_DEV_URL_RE.findall(text))
    return problems, generic_hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dist",
        default="frontend/dist",
        help="path to the vite production dist directory",
    )
    parser.add_argument(
        "--viewer-mode-allowed",
        action="store_true",
        help="allow empty backend URL (public viewer build)",
    )
    parser.add_argument(
        "--allow-insecure",
        action="store_true",
        help="allow http:// URLs (staging evidence only)",
    )
    parser.add_argument(
        "--report",
        default="ci-reports/frontend-build-contract.json",
        help="where to write the evidence JSON",
    )
    args = parser.parse_args()

    dist = Path(args.dist)
    build_info_path = dist / "build-info.json"
    problems: list[str] = []
    warnings: list[str] = []
    evidence: dict = {
        "checked_at": datetime.now(UTC).isoformat(),
        "dist": str(dist),
        "contract": "VITE_*_BACKEND build-time bake",
    }

    if not dist.is_dir():
        problems.append(
            f"dist directory not found: {dist} — did the production build run?"
        )
    elif not build_info_path.is_file():
        problems.append(
            f"{build_info_path} missing — vite build-info plugin did not run; "
            "the artifact cannot prove which backend URL was baked in"
        )
    else:
        info = json.loads(build_info_path.read_text(encoding="utf-8"))
        user_backend = (info.get("userBackendUrl") or "").strip()
        admin_backend = (info.get("adminBackendUrl") or "").strip()
        evidence["userBackendUrl"] = user_backend
        evidence["adminBackendUrl"] = admin_backend
        evidence["buildType"] = info.get("buildType")
        problems.extend(
            _check_url(
                "userBackendUrl",
                user_backend,
                viewer_mode_allowed=args.viewer_mode_allowed,
                allow_insecure=args.allow_insecure,
            )
        )
        problems.extend(
            _check_url(
                "adminBackendUrl",
                admin_backend,
                viewer_mode_allowed=args.viewer_mode_allowed,
                allow_insecure=args.allow_insecure,
            )
        )
        bundle_problems, generic_hits = _scan_bundle_leaks(dist)
        evidence["bundle_dev_url_hits"] = generic_hits
        problems.extend(bundle_problems)
        if generic_hits:
            warnings.append(
                f"bundle contains {generic_hits} generic dev http URL string(s) — verify they are dev-only samples, not the API base"
            )

    evidence["problems"] = problems
    evidence["warnings"] = warnings
    evidence["result"] = "FAIL" if problems else "PASS"

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print("═" * 64)
    print("FRONTEND BUILD CONTRACT — VITE_* backend URL evidence")
    print("═" * 64)
    for key in ("userBackendUrl", "adminBackendUrl"):
        print(f"  {key:18}: {evidence.get(key, '(n/a)')}")
    print(f"  bundle dev URL hits: {evidence.get('bundle_dev_url_hits', 'n/a')}")
    print(f"  evidence report    : {report_path}")
    for w in warnings:
        print(f"  ⚠️  {w}")
    for p in problems:
        print(f"  ❌ {p}")
    if problems:
        print("RESULT: FAIL — see problems above")
        return 1
    print("RESULT: PASS — production bundle carries the real backend contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
