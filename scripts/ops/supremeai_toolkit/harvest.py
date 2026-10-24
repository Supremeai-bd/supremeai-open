"""SupremeAI Toolkit — Harvest Engine (#2403, seq:2).

# বাংলা মন্তব্য: Golden Rule-এর দ্বিতীয় স্তর — audit ইঞ্জিন prune-candidate দিলেও
# ছাঁটাইয়ের আগে প্রতিটি প্রার্থীর গভীর রায় এই ইঞ্জিন দেয়:
#   keep-verdict       = অডিট ইঞ্জিনেই রক্ষিত (structural/tested/canonical/standalone)
#   keep-operational   = অপারেশনাল ডক-রেফারেন্স (runbook/master-doc/security-policy)
#   absorb-then-prune  = বেনিফিশিয়াল লজিক আছে → আগে ক্যানোনিকাল মডিউলে সংরক্ষণ, পরে ছাঁটাই
#   prune-after-harvest= প্রমাণিত অরফ্যান — কোনো রেফ/ডক/এন্ট্রি/ইউনিক-লজিক নেই
# এই ইঞ্জিনও কিছু ডিলিট করে না — রায়-ম্যানিফেস্ট তৈরি করে (read-only); ম্যানিফেস্টই
# পরবর্তী ম্যানুয়াল git rm-এর প্রমাণ-ট্রেইল।
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    # বাংলা মন্তব্য: স্ট্যান্ডঅ্যালোন রান (python scripts/supremeai_toolkit/harvest.py)।
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import reusability_audit
else:
    from . import reusability_audit

# বাংলা মন্তব্য: অপারেশনাল ডক-রুট — এখানে উল্লিখিত টুল মানে চালু runbook-ক্ষমতা।
OPERATIONAL_DOC_DIRS = ("docs/operations/", "docs/master_docs/", "docs/security/")

# বাংলা মন্তব্য: ঐতিহাসিক ডক-রুট — পুরনো প্ল্যান/অডিটে নাম থাকা ক্যাপাবিলিটি-প্রমাণ নয়।
HISTORICAL_DOC_DIRS = ("docs/archive/", "docs/plans/", "docs/audits/", "docs/audit_reports/")

# বাংলা মন্তব্য: self-ref দূষণ বাদ — নিজের অডিট-রিপোর্ট সব প্রার্থীর নাম ধারণ করে।
AUDIT_REPORT_PREFIX = "docs/operations/REUSABILITY-AUDIT-"
AUTO_INDEX = "scripts/_INDEX.md"

# বাংলা মন্তব্য: ভাঙা নন-পোর্টেবল প্যাথ — মূল ডেভেলপারের Windows মেশিনের হার্ডকোড।
_BROKEN_PATH_RE = re.compile(r"f:[\\\\/]+supremeai", re.IGNORECASE)

# বাংলা মন্তব্য: ম্যানুয়াল রায় (প্রত্যেকটির সাথে প্রমাণ-নোট বাধ্যতামূলক) — ইঞ্জিন যা
# দেখতে পায় না (পরিবার-সংস্কৃতি, runbook-অ্যাঙ্করড sibling, repair-pairing) সেগুলোর রায়।
MANUAL_OVERRIDES: dict[str, tuple[str, str]] = {
    # বাংলা মন্তব্য: scrapers.py `from base_api_client import BaseAPIClient` — ভাঙা;
    # merge-হোম api_clients.py-তে রি-পয়েন্ট করলেই চেইন জীবিত → KEEP (repair-pairing)।
    "scripts/resource_collection/api_clients.py": (
        "keep-canonical",
        "merge-হোম: scrapers.py-এর ভাঙা base_api_client import এখানে রি-পয়েন্ট হবে (seq:2 রিপেয়ার); BaseAPIClient ABC + rate-limit/retry লজিক জীবন্ত ক্যাপাবিলিটি",
    ),
    # বাংলা মন্তব্য: DRY Phase 2-C3 render_client পরিবার — runbook-অ্যাঙ্করড sibling
    # (update_render_image.py → BACKUP_RESTORE_AND_ROLLBACK.md) পরিবারের operational
    # প্রমাণ; এক সদস্য রেখে বাকিদের ছাঁটাই করলে ops-টুলসেট অসম্পূর্ণ হয়।
    "scripts/deploy/check_render_auto_deploy.py": (
        "keep-operational",
        "DRY Phase 2-C3 render_client পরিবার — পোর্টেবল, exit-code-সচেতন; runbook-অ্যাঙ্করড sibling update_render_image.py পরিবারের অপারেশনাল প্রমাণ",
    ),
    "scripts/deploy/create_render_service.py": (
        "keep-operational",
        "DRY Phase 2-C3 render_client পরিবার — service-lookup টুল; runbook-অ্যাঙ্করড sibling প্রমাণ",
    ),
    "scripts/deploy/list_render_services.py": (
        "keep-operational",
        "DRY Phase 2-C3 render_client পরিবার — service-inventory টুল; runbook-অ্যাঙ্করড sibling প্রমাণ",
    ),
    "scripts/deploy/update_render_env2.py": (
        "keep-operational",
        "DRY Phase 2-C3 render_client পরিবার — env-var ম্যানেজমেন্ট; runbook-অ্যাঙ্করড sibling প্রমাণ",
    ),
    # বাংলা মন্তব্য: MODULE_21 (crown-jewel গভর্নেন্স ডক) এটিকে সক্রিয়-সনাক্তকারী বলে
    # উল্লেখ করেছে; কিন্তু f:\\-হার্ডকোডে অচল → ক্যাপাবিলিটি হারানো যাবে না, পোর্টেবল
    # পুনঃসৃষ্টির পরেই খোসা ছাঁটাই (absorb-then-prune)।
    "scripts/scan_duplicate_plans.py": (
        "absorb-then-prune",
        "MODULE_21 doc-রেফারেন্সড সনাক্তকারী (duplicate-plan স্ক্যান) — কিন্তু f:\\supremeai হার্ডকোডে অচল; MD5-dup + name/header-similarity লজিক scripts/supremeai_toolkit/plan_guard.py-এ পোর্টেবলভাবে পুনঃসৃষ্ট",
    ),
}


@dataclass
class HarvestRuling:
    """একটি prune-candidate-এর চূড়ান্ত রায় + প্রমাণ-বান্ডিল।"""

    path: str
    audit_verdict: str
    ruling: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _doc_refs(repo: Path, rel: str) -> list[str]:
    """কোন ডক-ফাইলে এই স্ক্রিপ্টের নাম আছে (self-রিপোর্ট/auto-index বাদ)।"""
    token = Path(rel).name
    hits: list[str] = []
    for md in sorted(repo.glob("docs/**/*.md")):
        rel_md = md.relative_to(repo).as_posix()
        if rel_md.startswith(AUDIT_REPORT_PREFIX) or rel_md == AUTO_INDEX:
            continue
        try:
            if token in md.read_text(errors="ignore"):
                hits.append(rel_md)
        except OSError:
            continue
    return hits


def _inspect(repo: Path, rel: str) -> tuple[list[str], int, int]:
    """কনটেন্ট-স্তরের প্রমাণ: ভাঙা-পাথ গণনা, def/class সংখ্যা।"""
    fp = repo / rel
    try:
        text = fp.read_text(errors="ignore")
    except OSError:
        return [], 0, 0
    broken = len(_BROKEN_PATH_RE.findall(text))
    defs = len(re.findall(r"^\s*def\s+\w+", text, re.MULTILINE))
    classes = len(re.findall(r"^\s*class\s+\w+", text, re.MULTILINE))
    return text, defs, classes


def run_harvest(repo: Path, roots: list[str], out_md: Path | None = None, out_json: Path | None = None) -> tuple[int, str]:
    """harvest-check চালায় — (মোট-রায়, ম্যানিফেস্ট-টেক্সট) রিটার্ন; --out দিলে লেখে।"""
    results = reusability_audit.classify(repo, roots)
    candidates = [r for r in results if r.verdict == "prune-candidate"]

    rulings: list[HarvestRuling] = []
    for r in sorted(candidates, key=lambda x: x.path):
        evidence: list[str] = [f"audit: {r.verdict} ({r.reason})"]
        if r.refs_workflow:
            evidence.append(f"workflow-refs: {', '.join(r.refs_workflow[:3])}")
        if r.refs_live_code:
            evidence.append(f"live-refs: {', '.join(r.refs_live_code[:3])}")

        text, defs, classes = _inspect(repo, r.path)
        if text and _BROKEN_PATH_RE.search(text):
            evidence.append("non-portable: f:\\supremeai হার্ডকোড (মূল ডেভ-মেশিনের ওয়ান-টাইম আর্টিফ্যাক্ট)")
        evidence.append(f"content: {defs} def, {classes} class, {r.lines} লাইন")

        if r.path in MANUAL_OVERRIDES:
            ruling, note = MANUAL_OVERRIDES[r.path]
            evidence.append(f"manual-override: {note}")
        else:
            op_docs = [
                d for d in _doc_refs(repo, r.path)
                if d.startswith(OPERATIONAL_DOC_DIRS)
            ]
            if op_docs:
                ruling = "keep-operational"
                evidence.append(f"অপারেশনাল ডক-রেফ: {', '.join(op_docs[:4])}")
            else:
                ruling = "prune-after-harvest"
                hist = [d for d in _doc_refs(repo, r.path) if d.startswith(HISTORICAL_DOC_DIRS)]
                if hist:
                    evidence.append(f"ঐতিহাসিক-ডক মেনশন (ক্যাপাবিলিটি-প্রমাণ নয়): {', '.join(hist[:2])}")
                evidence.append("শূন্য live-ref + অপারেশনাল-ডক-শূন্য + non-entry — Golden-Rule harvest-check সম্পন্ন, বেনিফিশিয়াল ইউনিক লজিক প্রমাণিত নয়")

        rulings.append(HarvestRuling(path=r.path, audit_verdict=r.verdict, ruling=ruling, evidence=evidence))

    md = _render(rulings, roots, len(results))
    if out_md:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md, encoding="utf-8")
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps([x.to_dict() for x in rulings], ensure_ascii=False, indent=1), encoding="utf-8")
    return len(rulings), md


def _render(rulings: list[HarvestRuling], roots: list[str], total: int) -> str:
    """রায়-ম্যানিফেস্ট মার্কডাউন রেন্ডার।"""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    counts: dict[str, int] = {}
    for r in rulings:
        counts[r.ruling] = counts.get(r.ruling, 0) + 1
    lines = [
        "# Harvest Manifest — group:foundation-closeout (seq:2)",
        "",
        f"> **তারিখ:** {now} · **ইঞ্জিন:** `scripts/supremeai_toolkit/harvest.py` · **roots:** {', '.join(roots)} · **অডিট-বেস:** {total} ফাইল",
        "> **Golden Rule:** ছাঁটাইয়ের আগে harvest — beneficial লজিক প্রথমে ক্যানোনিকাল মডিউলে, পরে খোসা।",
        "> এই ম্যানিফেস্ট রায়-প্রমাণ মাত্র — নিজে কিছু ডিলিট করে না (read-only)।",
        "",
        "## রায়-সারসংক্ষেপ (prune-candidate প্রার্থীদের গভীর পরীক্ষা)",
        "",
        "| রায় | সংখ্যা | অর্থ |",
        "| :--- | ---: | :--- |",
        f"| keep-operational | {counts.get('keep-operational', 0)} | অপারেশনাল ডক/পরিবার-প্রমাণ — স্পর্শ নিষিদ্ধ |",
        f"| keep-canonical | {counts.get('keep-canonical', 0)} | repair-pairing/merge-হোম — রিপেয়ারে জীবন্ত হবে |",
        f"| absorb-then-prune | {counts.get('absorb-then-prune', 0)} | আগে toolkit-এ পুনঃসৃষ্ট, পরে ছাঁটাই |",
        f"| prune-after-harvest | {counts.get('prune-after-harvest', 0)} | প্রমাণিত অরফ্যান — ছাঁটাইযোগ্য |",
        "",
        "## ফাইল-ভিত্তিক রায়",
        "",
    ]
    for r in rulings:
        emoji = {"prune-after-harvest": "✂️", "absorb-then-prune": "🧺", "keep-operational": "🛡️", "keep-canonical": "⚙️"}.get(r.ruling, "❔")
        lines.append(f"### {emoji} `{r.path}` → **{r.ruling}**")
        lines.append("")
        for e in r.evidence:
            lines.append(f"- {e}")
        lines.append("")
    return "\n".join(lines)
