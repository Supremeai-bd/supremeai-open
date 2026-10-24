"""SupremeAI Toolkit — Unified CLI dispatcher (#2403 seq:1 + seq:3).

# বাংলা মন্তব্য: ৩৯০+ বিচ্ছিন্ন স্ক্রিপ্টের বুদ্ধিমান সেন্ট্রাল টুলের প্রবেশদ্বার।
# সাবকমান্ড রেজিস্ট্রি মডুলার — ভবিষ্যৎ seq-এ নতুন ক্ষমতা এখানেই যুক্ত হবে।
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import harvest
    import plan_guard
    import reusability_audit
    import standalone_check
else:
    from . import harvest, plan_guard, reusability_audit, standalone_check


def _cmd_audit(args: argparse.Namespace) -> int:
    """`audit` — Reusability Audit চালায় (read-only; --out দিলে রিপোর্ট লেখে)।"""
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    out_md = Path(args.out_md) if args.out_md else None
    out_json = Path(args.out_json) if args.out_json else None
    total, report = reusability_audit.run_audit(REPO_ROOT, roots, out_md, out_json)
    if not out_md:
        # বাংলা মন্তব্য: --out ছাড়া চালালে সারসংক্ষেপ stdout-এ — কোনো ফাইল-লেখা নয়।
        summary = [ln for ln in report.splitlines() if ln.startswith("**মোট") or ln.startswith("| keep") or ln.startswith("| prune") or ln.startswith("| review")]
        print("\n".join(summary))
    print(f"[OK] audit complete — {total} files scanned across roots: {', '.join(roots)}")
    return 0


def _cmd_harvest(args: argparse.Namespace) -> int:
    """`harvest` — Golden-Rule harvest-check: প্রার্থীদের গভীর রায়-ম্যানিফেস্ট (read-only)।"""
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    out_md = Path(args.out_md) if args.out_md else None
    out_json = Path(args.out_json) if args.out_json else None
    total, manifest = harvest.run_harvest(REPO_ROOT, roots, out_md, out_json)
    if not out_md:
        # বাংলা মন্তব্য: সারসংক্ষেপ টেবিল stdout-এ।
        for ln in manifest.splitlines():
            if ln.startswith("|") and ("keep" in ln or "prune" in ln or "absorb" in ln) and "---" not in ln:
                print(ln)
    print(f"[OK] harvest complete — {total} ruling(s) on prune-candidates across roots: {', '.join(roots)}")
    return 0


def _cmd_plan_guard(args: argparse.Namespace) -> int:
    """`plan-guard` — duplicate-plan স্ক্যান (scan_duplicate_plans.py-এর উত্তরাধিকার)।"""
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[ERROR] রুট ডিরেক্টরি নেই: {root}")
        return 2
    scanned, problems, summary = plan_guard.run_scan(
        root,
        Path(args.out_json) if args.out_json else None,
        Path(args.out_txt) if args.out_txt else None,
    )
    print(summary)
    return 0 if problems == 0 else min(problems, 2)


def _cmd_standalone(args: argparse.Namespace) -> int:
    """`standalone` — review-standalone বাকেটের রান-ভ্যালু যাচাই (read-only, seq:3)।"""
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    out_md = Path(args.out_md) if args.out_md else None
    out_json = Path(args.out_json) if args.out_json else None
    total, report = standalone_check.run_standalone_check(REPO_ROOT, roots, out_md, out_json)
    if not out_md:
        # বাংলা মন্তব্য: সারসংক্ষেপ টেবিল stdout-এ — ফাইল-লেখা শুধু --out দিলে।
        for ln in report.splitlines():
            if ln.startswith("|") and ("operational" in ln or "absorb" in ln or "stale" in ln) and "---" not in ln:
                print(ln)
    print(f"[OK] standalone-check complete — {total} review-standalone file(s) verified across roots: {', '.join(roots)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="supremeai_toolkit", description="SupremeAI Unified Toolkit (#2403)")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit", help="Reusability Audit — প্রমাণ-ভিত্তিক verdict (read-only)")
    a.add_argument("--roots", default="scripts", help="কমা-সেপারেটেড স্ক্যান-রুট (default: scripts)")
    a.add_argument("--out-md", dest="out_md", default=None, help="মার্কডাউন রিপোর্ট আউটপুট পাথ")
    a.add_argument("--out-json", dest="out_json", default=None, help="JSON প্রমাণ আউটপুট পাথ")
    a.set_defaults(func=_cmd_audit)
    h = sub.add_parser("harvest", help="Harvest-check — ছাঁটাই-প্রার্থীদের গভীর রায় (read-only)")
    h.add_argument("--roots", default="scripts", help="কমা-সেপারেটেড স্ক্যান-রুট (default: scripts)")
    h.add_argument("--out-md", dest="out_md", default=None, help="ম্যানিফেস্ট মার্কডাউন আউটপুট পাথ")
    h.add_argument("--out-json", dest="out_json", default=None, help="JSON প্রমাণ আউটপুট পাথ")
    h.set_defaults(func=_cmd_harvest)
    g = sub.add_parser("plan-guard", help="Duplicate-plan স্ক্যান — docs/plans হাইজিন (read-only)")
    g.add_argument("--root", default=str(REPO_ROOT / "docs" / "plans"), help="স্ক্যান-রুট (default: docs/plans)")
    g.add_argument("--out-json", dest="out_json", default=None, help="JSON রিপোর্ট পাথ")
    g.add_argument("--out-txt", dest="out_txt", default=None, help="TXT রিপোর্ট পাথ")
    g.set_defaults(func=_cmd_plan_guard)
    s = sub.add_parser("standalone", help="Run-Value Check — review-standalone বাকেট যাচাই (read-only, seq:3)")
    s.add_argument("--roots", default="scripts", help="কমা-সেপারেটেড স্ক্যান-রুট (default: scripts)")
    s.add_argument("--out-md", dest="out_md", default=None, help="মার্কডাউন রিপোর্ট আউটপুট পাথ")
    s.add_argument("--out-json", dest="out_json", default=None, help="JSON প্রমাণ আউটপুট পাথ")
    s.set_defaults(func=_cmd_standalone)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
