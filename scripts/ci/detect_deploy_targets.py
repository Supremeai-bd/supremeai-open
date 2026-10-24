#!/usr/bin/env python3
"""Deploy-train changed-path detection (#2901 → #4246 Phase-1 SSOT refactor).

প্রেক্ষাপট (#2901 ফরেনসিক অডিট): deploy-train.yml-এর service-selection
বাইনারি ছিল — core+worker প্রতি eligible push-এ অন্ধ redeploy হতো (ফ্রি-টিয়ার
৪৫০-মিনিট কোটার অপচয়), আর scraper/mcp/cloudflare কখনোই auto-deploy হতো না
(main.yml কলার কোনো input পাস করত না)। এই স্ক্রিপ্ট push-ইভেন্টে বদলানো
পাথ দেখে ঠিক কোন সার্ভিস deploy দরকার তা সিদ্ধান্ত করে।

#4246 ফেজ-১ (declarative service topology): ম্যাপিং if/elif হার্ডকোড থেকে
``config/service_topology.yaml`` SSOT-এ সরানো হলো — ফাউন্ডার নির্দেশনা:
"ভবিষ্যতে আরও ১০০টি টাওয়ার যুক্ত হলেও সিস্টেম নিজেই জানবে তার কী করা
উচিত।" নতুন সার্ভিস = রেজিস্ট্রিতে ব্লক যোগ, Python কোড অস্পৃশ্য। লাইভ
বাগ-ফিক্স সহ: ``infrastructure/mcp-control-plane/**`` আগে cloudflare-কে
ভুল ট্রিগার করত আর আসল MCP টাওয়ার নিরবে স্কিপ হতো (PR #4238, run #392)।

সিদ্ধান্ত-চুক্তি (টেস্ট: tests/test_detect_deploy_targets_2901.py +
tests/test_service_topology_contract.py):
  config/service_topology.yaml-এর services[].watch_paths fnmatch-গ্লোব মিললে
  সেই সার্ভিস deploy; exclude_paths আগে বাদ; noise (docs/tests/scripts/.github/
  **.md ইত্যাদি) কোনো সার্ভিস নয়; অজানা পাথ → conservative fail-open:
  core + worker (স্টেল প্রোডের ঝুঁকি অপচয়ের চেয়ে বড়)। scraper = manual_only
  (backend-গাছেই কোড — পাথ-বিয়োজন অসম্ভব, #2901 সিদ্ধান্ত অপরিবর্তিত)।
  frontend → vercel স্টেশন, firebase rules → firebase স্টেশন (#4246-এ নতুন)।

manual dispatch মোডে (--mode manual) সব সিদ্ধান্ত মানুষের স্পষ্ট input-এ —
ডিটেক্টর শুধু pass-through (মানুষ যা চান তা-ই আইন)।

GITHUB_OUTPUT চুক্তি:
  deploy-core / deploy-worker / deploy-scraper / deploy-mcp /
  deploy-cloudflare / deploy-frontend / deploy-firebase = true|false,
  deploy-needed = true|false,
  summary = মানুষ-পাঠযোগ্য এক-লাইন

মতবাদ (Pipeline Constitution Rule 10): Missing evidence ≠ healthy —
টপোলজি ফাইল অনুপস্থিত/ভাঙা হলে এই স্ক্রিপ্ট exit 2 (পাইপলাইন লাল),
কখনো ফাঁদ-সবুজ নয়।
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

# ── মতবাদ-ধ্রুবক (#4246) ────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOPOLOGY = REPO_ROOT / "config" / "service_topology.yaml"
# conservative fail-open (#2901): অজানা পাথ যে সার্ভিসগুলো ট্রিগার করবে
UNKNOWN_FALLBACK_KEYS = ("core", "worker")
# GITHUB_OUTPUT-এ emit হওয়া কী-গুলোর ক্রম (topology-তে deploy_key-এর সাথে
# সংগতি contract-test দ্বারা যাচাইকৃত — নতুন সার্ভিস যোগ হলে এখানেও যোগ)。
SERVICE_KEYS = (
    "deploy_core",
    "deploy_worker",
    "deploy_scraper",
    "deploy_mcp",
    "deploy_cloudflare",
    "deploy_frontend",
    "deploy_firebase",
)
# deploy_needed-এর হিসাবে কোন কী-গুলো গণ্য (সবই — কোনো স্টেশন মিস হবে না)


def _gha_key(key: str) -> str:
    return key.replace("_", "-")


def load_topology(path: str | os.PathLike[str] | None = None) -> dict:
    """Topology registry পড়ে — ভাঙা/অনুপস্থিত রেজিস্ট্রি = fail-closed (Rule 10)।"""
    topo_path = Path(path) if path else DEFAULT_TOPOLOGY
    if not topo_path.exists():
        raise SystemExit(f"::error::service topology missing: {topo_path} — fail-closed (Rule 10)")
    try:
        topo = yaml.safe_load(topo_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise SystemExit(f"::error::service topology unparsable: {topo_path}: {err}") from err
    services = (topo or {}).get("services") or {}
    if not services:
        raise SystemExit(f"::error::service topology has no services: {topo_path}")
    return topo


def _noise(topo: dict) -> dict:
    n = topo.get("noise") or {}
    return {
        "exact": set(n.get("exact") or ()),
        "prefixes": tuple(n.get("prefixes") or ()),
        "suffixes": tuple(n.get("suffixes") or ()),
    }


def _is_noise(p: str, name: str, noise: dict) -> bool:
    return (
        p in noise["exact"]
        or name in noise["exact"]
        or p.endswith(tuple(noise["suffixes"]))
        or p.startswith(noise["prefixes"])
    )


def _matches(p: str, patterns: list[str]) -> bool:
    # fnmatch এর `*` স্ল্যাশ-পার করে — `backend/**` প্যাটার্নে নেস্টেড পাথ মেলে
    return any(fnmatch.fnmatch(p, pat) for pat in patterns)


def _service_result(topo: dict) -> dict:
    out: dict = {}
    for key in topo["services"]:
        out[f"deploy_{key}"] = False
    return out


def classify_paths(paths: list[str], topology: dict | None = None) -> dict:
    """Pure ম্যাপিং — পরিবর্তিত পাথ তালিকা → প্রতি-সার্ভিস deploy সিদ্ধান্ত।

    topology=None হলে DEFAULT_TOPOLOGY থেকে লোড হয় (একবার — pure প্রদানের
    জন্য টেস্টে সরাসরি topology dict পাস করা যায়)।
    """
    topo = topology if topology is not None else _CLASSIFY_CACHE["topo"]
    if topo is None:
        topo = load_topology()
        _CLASSIFY_CACHE["topo"] = topo
    noise = _noise(topo)
    services = topo["services"]

    result: dict = _service_result(topo)
    # কাউন্টার-ফিল্ড (পুরনো চুক্তি অপরিবর্তিত — summary/step-summary ভোক্তা)
    result.update(
        {
            "backend_files": 0,
            "infra_files": 0,
            "frontend_files": 0,
            "noise_files": 0,
            "unknown_files": 0,
            "unknown_examples": [],
            "total": 0,
        }
    )
    for raw in paths:
        p = _norm(raw)
        if not p:
            continue
        result["total"] += 1
        name = p.rsplit("/", 1)[-1]
        if _is_noise(p, name, noise):
            result["noise_files"] += 1
            continue
        matched_any = False
        for skey, svc in services.items():
            patterns = svc.get("watch_paths") or []
            excludes = svc.get("exclude_paths") or []
            if not patterns:
                continue  # manual_only (যেমন scraper) — পাথ-ডিটেকশনে কখনো নয়
            if _matches(p, patterns) and not _matches(p, excludes):
                result[f"deploy_{skey}"] = True
                matched_any = True
        if not matched_any:
            # কোনো watch_paths-এ মেলেনি → অজানা পাথ = conservative fail-open
            result["unknown_files"] += 1
            if len(result["unknown_examples"]) < 5:
                result["unknown_examples"].append(p)
            for ukey in UNKNOWN_FALLBACK_KEYS:
                if f"deploy_{ukey}" in result:
                    result[f"deploy_{ukey}"] = True
        # কাউন্টার প্রতি-ফাইল একবার (এক পাথ একাধিক সার্ভিস ট্রিগার করলেও দ্বিগুণ নয়)
        if p.startswith("backend"):
            result["backend_files"] += 1
        elif p.startswith("infrastructure"):
            result["infra_files"] += 1
        elif p.startswith(("frontend", "client", "apps")):
            result["frontend_files"] += 1
    result["deploy_needed"] = any(result[k] for k in SERVICE_KEYS if k in result)
    return result


# classify_paths টেস্টে হাজারবার চলে — topology ফাইল একবারই পড়লে যথেষ্ট
_CLASSIFY_CACHE: dict = {"topo": None}


def _norm(path: str) -> str:
    # lstrip("./") নয় — সেটি '.' ও '/' দুটোই বামদিক থেকে খেয়ে ফেলে
    # (.github/ → github/ হয়ে নয়েজ-মিস); removeprefix-ই সঠিক।
    return str(path).strip().replace("\\", "/").removeprefix("./")


def changed_paths(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def emit_github_output(result: dict, manual_summary: str | None = None) -> None:
    dest = os.getenv("GITHUB_OUTPUT")
    if not dest:
        return
    with open(dest, "a", encoding="utf-8") as fh:
        for key in SERVICE_KEYS:
            if key in result:
                fh.write(f"{_gha_key(key)}={'true' if result[key] else 'false'}\n")
        fh.write(f"deploy-needed={'true' if result['deploy_needed'] else 'false'}\n")
        fh.write(f"summary={manual_summary or _summary_line(result)}\n")


def _summary_line(result: dict) -> str:
    on = [k.removeprefix("deploy_") for k in SERVICE_KEYS if result.get(k)]
    targets = ", ".join(on) if on else "শূন্য (deploy স্কিপ — কোটা সাশ্রয়)"
    return (
        f"targets=[{targets}] "
        f"backend={result['backend_files']} infra={result['infra_files']} "
        f"frontend={result['frontend_files']} noise={result['noise_files']} "
        f"unknown={result['unknown_files']}/{result['total']}"
    )


def write_step_summary(result: dict, manual_summary: str | None = None) -> None:
    dest = os.getenv("GITHUB_STEP_SUMMARY")
    if not dest:
        return
    lines = [
        "### 🔬 Deploy-target detection (#2901 → #4246 topology SSOT)",
        "",
        f"- **decision:** {manual_summary or _summary_line(result)}",
    ]
    if result.get("unknown_examples"):
        lines.append(f"- **unknown paths (fail-open → core+worker):** {result['unknown_examples']}")
    with open(dest, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="#2901→#4246 deploy-target detection")
    ap.add_argument("--base", help="git diff base sha/ref (push mode)")
    ap.add_argument("--head", default="HEAD", help="git diff head sha/ref")
    ap.add_argument("--paths-file", help="নিজস্ব পাথ-তালিকা ফাইল (প্রতি লাইনে একটি)")
    ap.add_argument("--topology", help="বিকল্প service_topology.yaml (টেস্ট/dry-run)")
    ap.add_argument(
        "--mode",
        choices=("push", "manual"),
        default="push",
        help="push=diff-ভিত্তিক ডিটেকশন; manual=মানুষের input pass-through",
    )
    ap.add_argument("--scraper", choices=("true", "false"), default="false")
    ap.add_argument("--mcp", choices=("true", "false"), default="false")
    ap.add_argument("--cloudflare", choices=("true", "false"), default="false")
    ap.add_argument("--frontend", choices=("true", "false"), default="false")
    ap.add_argument("--firebase", choices=("true", "false"), default="false")
    args = ap.parse_args()

    topo = load_topology(args.topology)

    if args.mode == "manual":
        # manual dispatch = স্পষ্ট মানুষের অভিপ্রায়: core+worker সবসময়,
        # বাকিগুলো resolve-হওয়া input অনুযায়ী। কোনো diff-বিশ্লেষণ নেই।
        result: dict = {k: False for k in SERVICE_KEYS}
        result["deploy_core"] = True
        result["deploy_worker"] = True
        result["deploy_scraper"] = args.scraper == "true"
        result["deploy_mcp"] = args.mcp == "true"
        result["deploy_cloudflare"] = args.cloudflare == "true"
        result["deploy_frontend"] = args.frontend == "true"
        result["deploy_firebase"] = args.firebase == "true"
        result["deploy_needed"] = True
        result["total"] = 0
        result["backend_files"] = 0
        result["infra_files"] = 0
        result["frontend_files"] = 0
        result["noise_files"] = 0
        result["unknown_files"] = 0
        result["unknown_examples"] = []
        summary = (
            f"manual dispatch → core+worker, scraper={result['deploy_scraper']}, "
            f"mcp={result['deploy_mcp']}, cloudflare={result['deploy_cloudflare']}, "
            f"frontend={result['deploy_frontend']}, firebase={result['deploy_firebase']}"
        )
        emit_github_output(result, summary)
        write_step_summary(result, summary)
        print(json.dumps(result, sort_keys=True))
        return 0

    if args.paths_file:
        paths = [l for l in Path(args.paths_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.base:
        paths = changed_paths(args.base, args.head)
    else:
        # base নেই (যেমন নতুন ব্রাঞ্চে event.before = শূন্য-শা) → fail-open manual-সমতুল্য
        result = {k: False for k in SERVICE_KEYS}
        result["deploy_core"] = True
        result["deploy_worker"] = True
        result["deploy_needed"] = True
        result["total"] = 0
        result["backend_files"] = 0
        result["infra_files"] = 0
        result["frontend_files"] = 0
        result["noise_files"] = 0
        result["unknown_files"] = 0
        result["unknown_examples"] = []
        summary = "no base sha (fresh push) → conservative core+worker"
        emit_github_output(result, summary)
        write_step_summary(result, summary)
        print(json.dumps(result, sort_keys=True))
        return 0

    result = classify_paths(paths, topo)
    emit_github_output(result)
    write_step_summary(result)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
