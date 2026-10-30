#!/usr/bin/env python3
"""satellite_residue_guard.py — Satellite Nested-Anchor Residue Guard (#1676, detection half).

গার্ডের মিশন (বাংলা):
  #1676 প্রমাণ করেছে — bridge intake-এর identity routing-এর দোষে স্যাটেলাইট রিপোর
  root-এ নিজের namespace-এর স্টেল nested কপি জমে ছিল (supremeai-studio-র root-এ
  `studio/` dir, তার ভেতরে root-এরই 15টি ফাইলের পুরনো কপি — ৭টি diverged
  split-brain)। প্রতিরোধ-অর্ধেক landed (bridge_intake.split_brain_duplicates,
  dispatch-কালে আটকায়) — কিন্তু বিদ্যমান অবশিষ্টাংশ (residue) শনাক্তকারী কোনো
  automated gate ছিল না; satellite_parity_gate.py কেবল sentinel-pair drift দেখে,
  অতিরিক্ত ফাইল দেখে না। এই গার্ড সেই শনাক্তকরণ-অর্ধেক: প্রতিটি satellite-এর
  root tree-তে নিজের anchor namespace dir থাকলে তার প্রতিটি ফাইলকে root-twin-এর
  সাথে blob-SHA তুলনায় শ্রেণিবদ্ধ করে — ঠিক সেই deletion worklist দেয় যা
  #1676-র cleanup pass-এর জন্য দরকার (preimage-SHA সহ, fail-closed apply-র পূর্বশর্ত)।

DESIGN PRINCIPLES
  - Fail-closed: API/auth/rate-limit ব্যর্থতা => exit 2, কখনো নীরব "clean" নয়।
  - Stdlib-only: urllib + json; নেটওয়ার্ক স্তর পাতলা ও injectable — সব সিদ্ধান্ত-কোর
    pure function, তাই --self-test সম্পূর্ণ offline (guard-the-guard)।
  - Byte-identity by blob SHA: git blob sha কনটেন্ট-অ্যাড্রেসড — sha সমান = বাইট
    সমান (studio-parity closeout sweep ও parity gate-এর একই পদ্ধতি)।
  - Calibrated: কেবল স্যাটেলাইটের নিজের anchor dir-ই residue; অন্য বৈধ root dir
    (যেমন studio-র `infrastructure/cloudflare-studio-proxy` — closeout-প্রমাণিত
    intended) কখনো পতাকাঙ্কিত হয় না।

MODES
  --check              লাইভ রান (ডিফল্ট): ৫টি satellite root tree স্ক্যান।
  --json               মেশিন-পাঠ্যোগ্য JSON রিপোর্ট stdout-এ (--check অন্তর্ভুক্ত)।
  --repos R[,R...]     নির্দিষ্ট satellite-এ সীমাবদ্ধ (ডিফল্ট: সব)।
  --ref REF            git ref (ডিফল্ট main)।
  --token-env NAME     টোকেন env (ডিফল্ট চেইন: SAT_SYNC_PAT → OPEN_SYNC_PAT →
                       GITHUB_TOKEN; সব খালি হলে unauthenticated — কেবল পাবলিক
                       satellite স্ক্যান হয়; প্রাইভেট টার্গেট সৎ 403 row দেয় ও
                       রান exit 2 হয় — রেকর্ডেড প্লেনে টোকেন চেইন বাধ্যতামূলক)।
  --self-test          Offline ফিক্সচার: ধরা পড়া উচিত এমন সব কেস ধরা পড়ে,
                       বৈধ লেআউট কখনো পতাকাঙ্কিত হয় না।

EXIT CODES
  0  পরিষ্কার (কোনো satellite-এ anchor residue নেই)
  1  residue পাওয়া গেছে (actionable — deletion worklist রিপোর্টে)
  2  infra/যাচাই ত্রুটি (fail-closed: দেখতে না পেয়ে ভোট নেই)

SSOT নোট: (repo, anchor) জোড়া এখানেই — bridge_intake.route_files() ও
bridge.tools.ts SATELLITE_REPO_MAP-এর prefix-routing থেকে প্রমাণিত। পরিবর্তন
রিভিউযোগ্য আলাদা PR-এ হবে (কোনো config ফাইল নয় — boundary guard-এর নিয়ম)।
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

EXIT_CLEAN = 0
EXIT_RESIDUE = 1
EXIT_INFRA = 2

GUARD_NAME = "satellite_residue_guard"
GOVERNING_ISSUE = 1676
DEFAULT_REF = "main"
UA = "supremeai-satellite-residue-guard"
TOKEN_ENV_CHAIN = ["SAT_SYNC_PAT", "OPEN_SYNC_PAT", "GITHUB_TOKEN"]
API_BASE = "https://api.github.com"

# (repo, anchor) SSOT — satellite root-এ এই anchor-নামের dir মানেই #1676-শ্রেণির
# identity-routing residue। anchor নামগুলো open-repo mirror namespace-এর সাথে
# মিলে যায় (route_files()/SATELLITE_REPO_MAP)। monorepo (Supremeai-bd/supremeai)
# ইচ্ছাকৃতভাবে বাদ — সেখানে এই namespace dir-গুলো বৈধ workspace লেআউট।
SATELLITE_ANCHORS: dict[str, str] = {
    "Supremeai-bd/supremeai-studio": "studio",
    "Supremeai-bd/supremeai-api": "gateway",
    "Supremeai-bd/supremeai-core": "core",
    "Supremeai-bd/supremeai-browser": "browser",
    "Supremeai-bd/supremeai-vscode": "vscode",
}


# ---------------------------------------------------------------------------
# Pure decision core (offline-testable; নেটওয়ার্ক এখানে নেই)
# ---------------------------------------------------------------------------

def classify_residue(entries: list[dict], anchor: str) -> dict:
    """Recursive tree entries থেকে anchor-residue শ্রেণিবদ্ধ করা (pure)।

    বাংলা: root twin index = anchor/ ছাড়া সব blob। `<anchor>/<rest>` ফাইলের
    twin `<rest>`; blob-SHA সমান → identical, ভিন্ন → diverged (split-brain),
    twin অনুপস্থিত → nested-only। `anchor/`-এর বাইরের কিছুই স্পর্শ করা হয় না
    (calibration: বৈধ infrastructure/ ইত্যাদি অস্পৃষ্ট)।
    """
    blobs = [e for e in entries if e.get("type") == "blob" and isinstance(e.get("path"), str)]
    prefix = anchor.rstrip("/") + "/"
    root_index = {e["path"]: e.get("sha") for e in blobs if not e["path"].startswith(prefix)}
    residue: list[dict] = []
    for e in blobs:
        path = e["path"]
        if not path.startswith(prefix) or len(path) <= len(prefix):
            continue
        twin = path[len(prefix):]
        twin_sha = root_index.get(twin)
        sat_sha = e.get("sha")
        if twin_sha is None:
            classification = "nested-only"
        elif twin_sha == sat_sha:
            classification = "identical"
        else:
            classification = "diverged"
        residue.append({
            "path": path,
            "twin": twin,
            "twinExists": twin_sha is not None,
            "classification": classification,
            "satelliteSha": (sat_sha or "")[:12] or None,
            "twinSha": (twin_sha or "")[:12] or None,
        })
    residue.sort(key=lambda r: r["path"])
    anchor_dir_present = any(
        e.get("type") == "tree" and e.get("path") == anchor.rstrip("/") for e in entries
    )
    return {
        "anchorDirPresent": anchor_dir_present,
        "residue": residue,
        "residueCount": len(residue),
        "counts": {
            "identical": sum(1 for r in residue if r["classification"] == "identical"),
            "diverged": sum(1 for r in residue if r["classification"] == "diverged"),
            "nested-only": sum(1 for r in residue if r["classification"] == "nested-only"),
        },
    }


def build_report(results: list[dict], ref: str) -> dict:
    """প্রতি-satellite ফলাফল → চূড়ান্ত রিপোর্ট envelope (pure)।"""
    total = sum(r.get("residueCount", 0) for r in results)
    return {
        "guard": GUARD_NAME,
        "issue": GOVERNING_ISSUE,
        "ref": ref,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "satellites": results,
        "totals": {
            "satellitesScanned": len(results),
            "satellitesWithResidue": sum(1 for r in results if r.get("residueCount", 0) > 0),
            "residueFiles": total,
        },
        "verdict": "residue-found" if total > 0 else "clean",
    }


def exit_code_for(report: dict, infra_errors: int) -> int:
    """0 পরিষ্কার / 1 residue / 2 infra — fail-closed র‍্যাঙ্কিং।"""
    if infra_errors:
        return EXIT_INFRA
    if report["totals"]["residueFiles"] > 0:
        return EXIT_RESIDUE
    return EXIT_CLEAN


def render_human(report: dict) -> str:
    """--check মোডের মানুষ-পাঠ্যোগ্য আউটপুট (pure)।"""
    lines: list[str] = []
    t = report["totals"]
    lines.append(
        f"satellite residue scan @ {report['ref']}: {t['satellitesScanned']} satellite(s), "
        f"{t['residueFiles']} residue file(s) in {t['satellitesWithResidue']} satellite(s)"
    )
    for sat in report["satellites"]:
        head = f"- {sat['repo']} (anchor '{sat['anchor']}'): "
        if sat.get("error"):
            lines.append(head + f"INFRA ERROR: {sat['error']}")
            continue
        if not sat["anchorDirPresent"]:
            lines.append(head + "clean — no anchor dir at satellite root")
            continue
        c = sat["counts"]
        lines.append(
            head + f"{sat['residueCount']} stale copy(ies) under '{sat['anchor']}/' "
            f"(identical={c['identical']}, diverged={c['diverged']}, nested-only={c['nested-only']})"
        )
        for r in sat["residue"]:
            lines.append(f"    [{r['classification']:>11}] {r['path']}  (twin: {r['twin']})")
    if report["verdict"] == "residue-found":
        lines.append(
            "verdict: RESIDUE FOUND — deletion worklist above (per-file satellite blob SHAs "
            "pin the fail-closed apply preimage). Cleanup rides the satellite/admin lane "
            f"(governing issue #{GOVERNING_ISSUE}); dispatch-time prevention already lives in "
            "scripts/bridge/bridge_intake.py split_brain_duplicates."
        )
    elif report["verdict"] == "clean":
        lines.append("verdict: CLEAN — no #1676-class residue on any scanned satellite")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Thin network layer (injectable — tests monkeypatch fetch_tree/resolve_token)
# ---------------------------------------------------------------------------

def resolve_token(token_env: str | None) -> str:
    """প্রথম পাওয়া টোকেন; কিছু না পেলে '' (unauthenticated — কেবল পাবলিক টার্গেট)।"""
    chain = [token_env] if token_env else list(TOKEN_ENV_CHAIN)
    for name in chain:
        if name and os.environ.get(name, "").strip():
            return os.environ[name].strip()
    return ""


def fetch_tree(repo: str, token: str, ref: str, timeout_s: float = 20.0) -> list[dict]:
    """GitHub trees API → recursive entry list; HTTP/নেটওয়ার্ক ব্যর্থতায় RuntimeError।"""
    url = f"{API_BASE}/repos/{repo}/git/trees/{ref}?recursive=1"
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching tree of {repo}@{ref}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"network/parse failure fetching tree of {repo}@{ref}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
        raise RuntimeError(f"unexpected tree payload shape for {repo}@{ref}")
    return data["tree"]


def scan_satellite(repo: str, anchor: str, token: str, ref: str) -> dict:
    """এক satellite স্ক্যান → রিপোর্ট row; infra ব্যর্থতা সৎ error row-তে।"""
    row: dict = {"repo": repo, "anchor": anchor, "ref": ref}
    try:
        entries = fetch_tree(repo, token, ref)
    except RuntimeError as exc:
        row["error"] = str(exc)
        row["anchorDirPresent"] = None
        row["residue"] = []
        row["residueCount"] = 0
        row["counts"] = {"identical": 0, "diverged": 0, "nested-only": 0}
        return row
    row.update(classify_residue(entries, anchor))
    return row


# ---------------------------------------------------------------------------
# Self-test (guard-the-guard — সম্পূর্ণ offline ফিক্সচার)
# ---------------------------------------------------------------------------

def self_test() -> int:
    """ফিক্সচার: residue-ধরা কেস + calibration (বৈধ লেআউট অস্পৃষ্ট) + report/exit।"""
    failures: list[str] = []

    def expect(cond: bool, label: str) -> None:
        if not cond:
            failures.append(label)

    def sha(i: int) -> str:
        return f"sha{i:03d}"

    # ফিক্সচার A — studio-শ্রেনির satellite: ১ identical, ১ diverged, ২ nested-only;
    # বৈধ infrastructure/ dir (closeout-প্রমাণিত intended) অবশ্যই অস্পৃষ্ট থাকবে।
    fixture_a = [
        {"path": "package.json", "type": "blob", "sha": sha(1)},
        {"path": "src/utils/api.ts", "type": "blob", "sha": sha(2)},
        {"path": "src/styles/cockpit.css", "type": "blob", "sha": sha(3)},
        {"path": "infrastructure/cloudflare-studio-proxy/wrangler.toml", "type": "blob", "sha": sha(4)},
        {"path": "studio", "type": "tree", "sha": sha(5)},
        {"path": "studio/package.json", "type": "blob", "sha": sha(1)},      # identical twin
        {"path": "studio/src/utils/api.ts", "type": "blob", "sha": sha(9)},  # diverged twin
        {"path": "studio/src/components/auth/ServiceHealthBar.test.ts", "type": "blob", "sha": sha(6)},  # nested-only
        {"path": "studio/src/services/apiClient.ts", "type": "blob", "sha": sha(7)},  # nested-only
        {"path": "studio/infrastructure/cloudflare-studio-proxy/wrangler.toml", "type": "blob", "sha": sha(4)},  # identical
    ]
    got = classify_residue(fixture_a, "studio")
    expect(got["anchorDirPresent"] is True, "A: anchor dir detected")
    expect(got["residueCount"] == 5, f"A: 5 residue files (got {got['residueCount']})")
    by_path = {r["path"]: r for r in got["residue"]}
    expect(by_path["studio/package.json"]["classification"] == "identical", "A: identical class")
    expect(by_path["studio/src/utils/api.ts"]["classification"] == "diverged", "A: diverged class")
    expect(by_path["studio/src/services/apiClient.ts"]["classification"] == "nested-only", "A: nested-only class")
    expect(by_path["studio/infrastructure/cloudflare-studio-proxy/wrangler.toml"]["classification"] == "identical", "A: nested infrastructure twin matched")
    expect(all(not r["path"].startswith("infrastructure/") for r in got["residue"]), "A: legitimate root infrastructure/ untouched")
    expect(by_path["studio/src/utils/api.ts"]["twin"] == "src/utils/api.ts", "A: twin strips exactly one anchor segment")

    # ফিক্সচার B — পরিষ্কার satellite: anchor dir নেই।
    fixture_b = [
        {"path": "package.json", "type": "blob", "sha": sha(1)},
        {"path": "src/main.py", "type": "blob", "sha": sha(2)},
        {"path": "gateway", "type": "tree", "sha": sha(8)},  # ভিন্ন নামের বৈধ dir
    ]
    got_b = classify_residue(fixture_b, "studio")
    expect(got_b["anchorDirPresent"] is False, "B: no anchor dir")
    expect(got_b["residueCount"] == 0, "B: zero residue")

    # ফিক্সচার C — খালি anchor dir: residue শূন্য, presence সত্য।
    fixture_c = [{"path": "studio", "type": "tree", "sha": sha(5)}, {"path": "README.md", "type": "blob", "sha": sha(1)}]
    got_c = classify_residue(fixture_c, "studio")
    expect(got_c["anchorDirPresent"] is True and got_c["residueCount"] == 0, "C: empty anchor dir = present, 0 files")

    # রিপোর্ট + exit-কোড র‍্যাঙ্কিং।
    rep = build_report([
        {"repo": "r/studio-like", "anchor": "studio", **got},
        {"repo": "r/clean", "anchor": "studio", **got_b},
    ], "main")
    expect(rep["totals"]["residueFiles"] == 5, "report totals")
    expect(rep["verdict"] == "residue-found", "report verdict")
    expect(exit_code_for(rep, infra_errors=0) == EXIT_RESIDUE, "exit: residue -> 1")
    expect(exit_code_for(build_report([{"repo": "r", "anchor": "studio", **got_b}], "main"), 0) == EXIT_CLEAN, "exit: clean -> 0")
    expect(exit_code_for(rep, infra_errors=1) == EXIT_INFRA, "exit: infra error outranks residue -> 2")
    text = render_human(rep)
    expect("RESIDUE FOUND" in text and "studio/package.json" in text, "human report carries worklist")

    if failures:
        print(f"self-test FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("self-test PASS: residue detection, calibration, report and exit ranking verified (offline)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Satellite nested-anchor residue guard (#1676 detection half)")
    parser.add_argument("--check", action="store_true", help="live scan (default when no mode given)")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON report on stdout")
    parser.add_argument("--repos", type=str, default="", help="comma-separated repo subset (default: all)")
    parser.add_argument("--ref", type=str, default=DEFAULT_REF, help="git ref for both sides")
    parser.add_argument("--token-env", type=str, default="", help="env var holding a read token (chain fallback applies)")
    parser.add_argument("--self-test", action="store_true", help="offline guard-the-guard fixtures")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    selected = dict(SATELLITE_ANCHORS)
    if args.repos:
        wanted = {r.strip() for r in args.repos.split(",") if r.strip()}
        unknown = wanted - set(selected)
        if unknown:
            print(f"unknown repos: {sorted(unknown)}; known: {sorted(selected)}", file=sys.stderr)
            return EXIT_INFRA
        selected = {k: v for k, v in selected.items() if k in wanted}

    token = resolve_token(args.token_env or None)
    results = [scan_satellite(repo, anchor, token, args.ref) for repo, anchor in selected.items()]
    infra_errors = sum(1 for r in results if r.get("error"))
    report = build_report(results, args.ref)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_human(report))
    return exit_code_for(report, infra_errors)


if __name__ == "__main__":
    sys.exit(main())
