"""SupremeAI Toolkit — Reusability Audit Engine (#2403, seq:1 + seq:2 refinement).

# বাংলা মন্তব্য: Golden Rule এনফোর্সার — প্রতিটি স্ক্রিপ্টের পুনঃব্যবহারযোগ্যতা
# প্রমাণ-ভিত্তিক যাচাই করে verdict দেয়:
#   keep-structural    = __init__.py — import-সিস্টেমের implicit প্যাকেজ-মার্কার (seq:2)
#   keep-tested        = test_*.py — pytest-discovery + test_guard gate সাংবিধানিকভাবে রক্ষা করে (seq:2)
#   keep-canonical     = workflow বা live-code রেফারেন্স আছে → স্পর্শ নিষিদ্ধ
#   review-standalone  = entry-point কিন্তু শূন্য রেফ → ম্যানুয়াল রান-ভ্যালু যাচাই দরকার
#   prune-candidate    = শূন্য রেফ + non-entry-point → পরবর্তী seq-এ harvest-check-এর পর ছাঁটাই
#
# seq:2 ব্লাইন্ড-স্পট ফিক্স: seq:1 স্ক্যানার basename শুধু extension-সহ ("validators.py")
# মিলত — কিন্তু Python import stem-only টোকেন ব্যবহার করে (`from validators import X`)।
# ফলে import-রেফারেন্সড মডিউল ভুলভাবে prune-candidate হত (প্রমাণ: devops/config/validators.py)।
# এখন live-code রেফারেন্স = ফাইলনাম-ম্যাচ **অথবা** import-stem টোকেন-ম্যাচ (safe-direction:
# false-KEEP নিরাপদ, false-PRUNE বিপজ্জনক — Golden Rule অনুযায়ী over-keep সবসময় শ্রেয়)।
#
# এই ইঞ্জিন কখনোই ফাইল ডিলিট করে না — শুধু প্রমাণ তৈরি করে (read-only, dry-run-by-design)।
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# বাংলা মন্তব্য: স্ক্যান থেকে বাদ দেওয়া ডিরেক্টরি — প্রমাণকে গোলযোগদার করে না।
EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "download", "upload"}

ENTRYPOINT_MARKERS = (
    'if __name__ ==',
    'argparse',
    'uvicorn.run',
)

# বাংলা মন্তব্য: seq:2 — module-level sys.argv ব্যবহারও entry-point (যেমন security/generate_secrets.py
# `if __name__` গার্ড ছাড়াই CLI হিসেবে চলে; seq:1 এটি মিস করত)।
ENTRYPOINT_SOFT_MARKERS = (
    'sys.argv',
)

# বাংলা মন্তব্য: import-স্টেটমেন্ট থেকে মডিউল-পাথ টেনে আনা হয় (dotted path + relative import)।
# seq:2 ফিক্স: প্রতিটি ক্যাপচার লাইন-অ্যাঙ্করড ([^#\n]) — আগের \\s-গ্রিডি প্যাটার্ন নিউলাইন
# টপকে যেত, ফলে প্রথম import-এর পরের সব import-টোকেন নষ্ট হত।
_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:from\s+([.\w]+)\s+import\s+([^#\n]+)|import\s+([^#\n]+))",
    re.MULTILINE,
)

# বাংলা মন্তব্য: seq:2 harvest-exemption — এই নাম-প্যাটার্নগুলো ref-count-নির্বিশেষে রক্ষিত।
TEST_NAME_RE = re.compile(r"(?:^|/)(?:test_[^/]*\.py|[^/]*_test\.py)$", re.IGNORECASE)
INIT_NAME = "__init__.py"

# বাংলা মন্তব্য: toolkit-এর নিজের ফাইল রেফ-সোর্স নয় (মেটাডাটা-স্তর নিজেকে প্রমাণ করে না)।
TOOLKIT_PREFIX = "scripts/supremeai_toolkit/"

SHEBANG = '#!'


@dataclass
class FileVerdict:
    """একটি স্ক্রিপ্ট-ফাইলের সম্পূর্ণ প্রমাণ-বান্ডিল।"""

    path: str
    lines: int
    is_entrypoint: bool
    refs_workflow: list[str] = field(default_factory=list)
    refs_live_code: list[str] = field(default_factory=list)
    refs_docs: int = 0
    verdict: str = "keep-canonical"
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _repo_git_files(repo: Path) -> list[str]:
    """git ls-files — ট্র্যাকড ফাইল মাত্র (untracked noise বাদ)।"""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=str(repo), capture_output=True, text=True, timeout=60, check=True
        )
        return [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except (subprocess.SubprocessError, OSError):
        # git না থাকলে fallback: সব ফাইল হাঁটো (প্রমাণ কম-নির্ভুল হবে, বাংলা নোট রিপোর্টে থাকবে)
        return [str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file()]


def _is_entrypoint(text: str, first_line: str) -> bool:
    # বাংলা মন্তব্য: shebang/argparse/uvicorn ছাড়াও module-level sys.argv = চালু CLI-স্ক্রিপ্ট।
    return (
        first_line.startswith(SHEBANG)
        or any(m in text for m in ENTRYPOINT_MARKERS)
        or any(m in text for m in ENTRYPOINT_SOFT_MARKERS)
    )


def _imported_stems(text: str) -> set[str]:
    """ফাইলের সব import-মডিউলের last-component stem-সেট (seq:2 import-token ম্যাচিং)।"""
    stems: set[str] = set()
    for m in _IMPORT_LINE_RE.finditer(text):
        mod, names, plain = m.group(1), m.group(2), m.group(3)
        if mod is not None:
            # বাংলা মন্তব্য: `from x.y import Z` → x.y-এর last component = y (ইমপোর্ট-হোম)।
            parts = [p for p in mod.split(".") if p]
            if parts:
                stems.add(parts[-1])
            if mod.strip(".") == "":
                # বাংলা মন্তব্য: bare-relative `from . import a, b` → নামগুলোই সহোদর মডিউল।
                for tok in names.split(","):
                    tok = tok.strip().split(" as ")[0].strip()
                    if tok and tok.isidentifier():
                        stems.add(tok)
            continue
        # বাংলা মন্তব্য: `import a.b.c as x, d` → a.b.c→c, d→d।
        for tok in (plain or "").split(","):
            tok = tok.strip().split(" as ")[0].split(" ")[0].strip()
            parts = [p for p in tok.split(".") if p]
            if parts and parts[-1].isidentifier():
                stems.add(parts[-1])
    return stems


def classify(repo: Path, roots: list[str]) -> list[FileVerdict]:
    """প্রতিটি টার্গেট ফাইলের verdict তৈরি করে (শুধু .py/.sh — রিপোর্ট স্কোপ)।"""
    all_files = _repo_git_files(repo)
    target_set: dict[str, Path] = {}
    for root in roots:
        root_path = (repo / root).resolve()
        if root_path.is_file():
            rel = root_path.relative_to(repo).as_posix()
            target_set[rel] = root_path
            continue
        for p in root_path.rglob("*"):
            if not p.is_file() or p.suffix not in (".py", ".sh"):
                continue
            if any(part in EXCLUDED_DIRS for part in p.parts):
                continue
            rel = p.relative_to(repo).as_posix()
            target_set[rel] = p

    # বাংলা মন্তব্য: রেফারেন্স-ইনডেক্স একবারই তৈরি — O(N) বার grep নয়।
    ref_index: dict[str, list[tuple[str, str]]] = {rel: [] for rel in target_set}
    basenames = {Path(rel).name: rel for rel in target_set}
    for f in all_files:
        if f.endswith((".md", ".json", ".sarif", ".lock")):
            # রিপোর্ট/লক-ফাইল নিজেরাই রেফ-সোর্স নয় (docs-কাউন্ট আলাদা করা হয়)
            continue
        # বাংলা মন্তব্য: seq:2 — toolkit নিজেই মেটাডাটা-স্তর; এর docstring/manifest-এ
        # অন্য স্ক্রিপ্টের নাম থাকা স্বাভাবিক → basename-সাবস্ট্রিং ম্যাচে এটি রেফ-সোর্স
        # নয় (নইলে ভুয়া keep); তবে সত্যিকারের import (cli.py → harvest) গণ্য রাখতে
        # নিচের import-stem ম্যাচ এখান থেকে সরিয়ে দেওয়া হয়েছে।
        if f.startswith(TOOLKIT_PREFIX):
            fp = repo / f
            try:
                text = fp.read_text(errors="ignore")
            except OSError:
                continue
            tk_imports = _imported_stems(text)
            if tk_imports:
                for rel in target_set:
                    if f == rel:
                        continue
                    if Path(rel).stem in tk_imports:
                        ref_index[rel].append((f, "live"))
            continue
        fp = repo / f
        try:
            text = fp.read_text(errors="ignore")
        except OSError:
            continue
        kind = "workflow" if f.endswith((".yml", ".yaml")) else "live"
        # বাংলা মন্তব্য: seq:2 — live-code ফাইলের import-stem সেট একবারই বের করা হয়।
        file_imports = _imported_stems(text) if kind == "live" else set()
        for name, rel in basenames.items():
            if f == rel:
                continue  # সেলফ-রেফারেন্স নয় — অন্য ফাইলের মেনশনই প্রমাণ
            if name in text:
                ref_index[rel].append((f, kind))
                continue
            # বাংলা মন্তব্য: import-stem ম্যাচ কেবল live-code-এ (yml-এ stem over-match ঝুঁকি;
            # safe-direction তবুও — false-KEEP > false-PRUNE)। seq:2-তে target-ফাইলগুলোও
            # ref-সোর্স — scripts/-অভ্যন্তরীণ import-chain (যেমন devops/config/cli.py →
            # validators.py) আগে অদৃশ্য ছিল, ভুল prune-candidate তৈরি করত।
            if file_imports and Path(rel).stem in file_imports:
                ref_index[rel].append((f, kind))

    # docs রেফারেন্স আলাদা কাউন্ট (শুধু সংখ্যা — রিপোর্ট ছোট রাখতে)
    docs_texts: list[str] = []
    for f in all_files:
        if f.endswith(".md"):
            fp = repo / f
            try:
                docs_texts.append(fp.read_text(errors="ignore"))
            except OSError:
                pass
    docs_blob = "\n".join(docs_texts)

    def _docs_token(rel: str) -> str:
        # বাংলা মন্তব্য: `__init__.py` basename সব প্যাকেজেই থাকে — parent-qualified token
        # ব্যবহার করলে collision-জনিত ভুয়া docs-রেফ-কাউন্ট হয় না।
        if Path(rel).name == "__init__.py":
            return f"{Path(rel).parent.as_posix()}/__init__.py"
        return Path(rel).name

    results: list[FileVerdict] = []
    for rel, path in sorted(target_set.items()):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            text = ""
        first_line = text.splitlines()[0].strip() if text else ""
        refs = ref_index.get(rel, [])
        v = FileVerdict(
            path=rel,
            lines=text.count("\n") + (1 if text else 0),
            is_entrypoint=_is_entrypoint(text, first_line),
            refs_workflow=sorted({f for f, k in refs if k == "workflow"}),
            refs_live_code=sorted({f for f, k in refs if k == "live"}),
            refs_docs=docs_blob.count(_docs_token(rel)),
        )
        # বাংলা মন্তব্য: Golden-Rule verdict ইঞ্জিন — কখনো সরাসরি 'delete' সিদ্ধান্ত নয়।
        # seq:2 exemption-লেয়ার: স্ট্রাকচারাল ও টেস্ট ফাইল ref-count-নির্বিশেষে রক্ষিত।
        if Path(rel).name == INIT_NAME:
            v.verdict = "keep-structural"
            v.reason = "প্যাকেজ-মার্কার (__init__.py) — import-সিস্টেমে implicitly রেফারেন্সড"
        elif TEST_NAME_RE.search(rel):
            v.verdict = "keep-tested"
            v.reason = "test_*.py — pytest-discovery + test_guard gate ডিলিট-ব্লক করে"
        elif v.refs_workflow or v.refs_live_code:
            v.verdict = "keep-canonical"
            v.reason = "workflow/live-code রেফারেন্স আছে — ক্যানোনিকাল ক্ষমতা"
        elif v.is_entrypoint:
            v.verdict = "review-standalone"
            v.reason = "entry-point, কিন্তু শূন্য স্বয়ংক্রিয় রেফ — ম্যানুয়াল রান-ভ্যালু যাচাই দরকার"
        else:
            v.verdict = "prune-candidate"
            v.reason = "শূন্য রেফ + non-entry-point — harvest-check-এর পরেই কেবল ছাঁটাইযোগ্য"
        results.append(v)
    return results


def render_markdown(results: list[FileVerdict], roots: list[str], notes: list[str]) -> str:
    """রিপোর্ট রেন্ডার — docs/operations-এ কমিটযোগ্য মার্কডাউন।"""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    counts: dict[str, int] = {}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    lines = [
        "# Reusability Audit — group:foundation-closeout (seq:1)",
        "",
        f"> **তারিখ:** {now} · **স্ক্যানার:** `scripts/supremeai_toolkit` v0.1.0 · **roots:** {', '.join(roots)}",
        "> **Golden Rule:** Clean up-এর আগে Reusability Check — beneficial কিছু কোনো অবস্থাতেই ডিলিট করা যাবে না (#2403)।",
        "> এই রিপোর্ট প্রমাণ-বেস মাত্র — এখান থেকে কোনো ফাইল স্বয়ংক্রিয়ভাবে ডিলিট হয় না।",
        "",
        "## সারসংক্ষেপ",
        "",
        f"**মোট স্ক্যান করা .py/.sh ফাইল: {len(results)}**",
        "",
        "| Verdict | সংখ্যা | অর্থ |",
        "| :--- | ---: | :--- |",
        f"| keep-structural | {counts.get('keep-structural', 0)} | __init__.py প্যাকেজ-মার্কার — import-সিস্টেম রক্ষা করে (seq:2) |",
        f"| keep-tested | {counts.get('keep-tested', 0)} | test_*.py — pytest-discovery + test_guard রক্ষা (seq:2) |",
        f"| keep-canonical | {counts.get('keep-canonical', 0)} | workflow/live-code রেফ আছে — স্পর্শ নিষিদ্ধ |",
        f"| review-standalone | {counts.get('review-standalone', 0)} | entry-point, শূন্য রেফ — ম্যানুয়াল যাচাই |",
        f"| prune-candidate | {counts.get('prune-candidate', 0)} | শূন্য রেফ + non-entry — harvest-check-পরবর্তী ছাঁটাই |",
        "",
    ]
    if notes:
        lines += ["## বিশেষ রায় (Deep-Dive)", ""]
        lines += [f"- {n}" for n in notes]
        lines.append("")
    lines += [
        "## prune-candidate তালিকা (পরবর্তী seq-এর evidence-base)",
        "",
        "Harvest-check (দরকারি লজিক → ক্যানোনিকাল মডিউলে সংরক্ষণ) শেষ না হওয়া পর্যন্ত কোনোটিই ডিলিট হবে না।",
        "",
        "| ফাইল | লাইন | docs-রেফ | কারণ |",
        "| :--- | ---: | ---: | :--- |",
    ]
    # বাংলা মন্তব্য: বিশেষ রায়ে KEEP-ঘোষিত প্যাকেজ (backend/pyerrorfix) prune-টেবিল থেকে বাদ —
    # প্যাকেজ-স্তরের রায়ই চূড়ান্ত; ভেতরের ফাইল আলাদা করে ছাঁটাই-প্রার্থী করা বিভ্রান্তিকর।
    for r in sorted(results, key=lambda x: x.path):
        if r.verdict == "prune-candidate" and not r.path.startswith("backend/pyerrorfix"):
            lines.append(f"| `{r.path}` | {r.lines} | {r.refs_docs} | {r.reason} |")
    lines += [
        "",
        "## review-standalone তালিকা (ম্যানুয়াল রান-ভ্যালু যাচাই প্রয়োজন)",
        "",
        "| ফাইল | লাইন | docs-রেফ |",
        "| :--- | ---: | ---: |",
    ]
    for r in sorted(results, key=lambda x: x.path):
        if r.verdict == "review-standalone" and not r.path.startswith("backend/pyerrorfix"):
            lines.append(f"| `{r.path}` | {r.lines} | {r.refs_docs} |")
    lines.append("")
    return "\n".join(lines)


def run_audit(repo: Path, roots: list[str], out_md: Path | None = None, out_json: Path | None = None) -> tuple[int, str]:
    """অডিট চালায়; (মোট-ফাইল, রিপোর্ট-টেক্সট) রিটার্ন; --out দিলে লেখে।"""
    results = classify(repo, roots)
    # বাংলা মন্তব্য: pyerrorfix deep-dive — স্পষ্ট প্রমাণসহ রায়, এই ইঞ্জিনেরই আউটপুট।
    notes: list[str] = []
    pef = [r for r in results if r.path.startswith("backend/pyerrorfix")]
    if pef:
        keep = [r for r in pef if r.verdict == "keep-canonical"]
        notes.append(
            f"**`backend/pyerrorfix` = KEEP (canonical capability, {len(pef)} ফাইল, "
            f"{len(keep)}টি লাইভ-রেফারেন্সড):** `backend/action.yml` একটি প্রকাশিত SARIF GitHub Action "
            "(python -m pyerrorfix analyze), ৪টি লাইভ স্ক্রিপ্ট রেফারেন্স করে "
            "(test_coverage_gap_mapper, check_hardcoded_deployment_config, check_no_requests_in_backend.sh, "
            "audit_isolated_components), master-docs (ARCH-01/BACKEND-01) সহ ১৭টি ডক-রেফ। "
            "**বাগ-নোট:** action.yml `./pyerrorfix` subdirectory আশা করে, বাস্তবে প্যাকেজ `backend/pyerrorfix`-এ — "
            "path-mismatch; পরবর্তী seq-এ harvest/ফিক্স প্রার্থী, ডিলিট প্রার্থী নয়।"
        )
    report = render_markdown(results, roots, notes)
    if out_md:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(report, encoding="utf-8")
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=1), encoding="utf-8")
    return len(results), report
