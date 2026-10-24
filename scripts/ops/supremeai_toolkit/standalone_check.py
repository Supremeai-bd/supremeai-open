"""SupremeAI Toolkit — Standalone Run-Value Check Engine (#2403, seq:3).

# বাংলা মন্তব্য: review-standalone বাকেট-ক্লোজার ইঞ্জিন (seq:3)।
# Reusability Audit-এর `review-standalone` verdict (entry-point + শূন্য স্বয়ংক্রিয় রেফ)
# মানে "ম্যানুয়াল রান-ভ্যালু যাচাই দরকার" — এই ইঞ্জিন সেই যাচাইটাই প্রমাণ-ভিত্তিকভাবে করে।
#
# প্রতিটি ফাইলের জন্য সংগৃহীত প্রমাণ:
#   1. runnability     — .py হলে in-process compile() (কোনো side-effect নেই),
#                        .sh হলে `bash -n` syntax-check (stdin-ভিত্তিক, ফাইল-লেখা নেই)।
#   2. stale-signature — ভাঙা repo-internal relative-path রেফারেন্স, Windows ড্রাইভ
#                        artifact (f:\\ স্টাইল), dated one-time নাম-প্যাটার্ন
#                        (যেমন system_defect_scan_2026_09_16.py), deprecation মার্কার।
#   3. unique-capability — ফাইলে সংজ্ঞায়িত def/class সিম্বল রিপোর অন্য কোথাও
#                        আছে কিনা (unique সিম্বল = হারালে ক্যাপাবিলিটি-লস)।
#   4. ops-context     — docs-রেফ সংখ্যা, git last-commit বয়স (দিন), sibling পরিবারের
#                        ঘনত্ব, external-service বাইন্ডিং (requests/infisical/render ইত্যাদি)।
#
# Verdict (read-only, deterministic, safe-direction: over-keep সবসময় শ্রেয়):
#   keep-operational  — চলুচিত অপারেশনাল টুল (মানুষ চালায়; শূন্য রেফ স্বাভাবিকই)
#   absorb-candidate  — পোর্টেবল unique লজিক; পরবর্তী slice-এ toolkit-এ পুনঃসৃষ্টির
#                       হারভেস্ট-ম্যানিফেস্ট এন্ট্রি (এই স্লাইসে কোনো ফাইল সরানো হয় না)
#   stale-review      — ভাঙা/পুরনো প্রমাণ; পরবর্তী slice-এ prune-after-harvest
#                       প্রার্থী (প্রমাণ-বেস মাত্র — এই স্লাইসে কোনো ডিলিট নেই)
#
# Golden Rule প্রযোজ্য: "Clean up-এর আগে Reusability Check — beneficial কিছু কোনো
# অবস্থাতেই ডিলিট করা যাবে না।" এই ইঞ্জিন কখনোই ফাইল ডিলিট/সরায় না — শুধু প্রমাণ তৈরি করে।
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# বাংলা মন্তব্য: একই টুলচেইনের audit-ইঞ্জিন পুনঃব্যবহার — একক সত্য-উৎস (single source of truth);
# review-standalone তালিকা আলাদা কোনো স্ক্যানারে না করে classify() থেকেই আসে।
try:
    from . import reusability_audit as _ra
except ImportError:  # বাংলা মন্তব্য: সরাসরি স্ক্রিপ্ট-হিসেবে চালালে (python standalone_check.py)
    import reusability_audit as _ra

# বাংলা মন্তব্য: repo-internal relative-path স্ট্রিং-লিটারেল — শুধু এই prefix-গুলোই যাচাই হয়
# (যেকোনো স্ট্রিং path ধরলে false-positive আয়োজন হত; সংকীর্ণ স্কোপ = নির্ভরযোগ্য প্রমাণ)।
_INTERNAL_PATH_RE = re.compile(
    r"[\"']((?:scripts|backend|frontend|docs|data|config|tests|deploy)/(?:[\w.\-]+/)*[\w.\-]+\.[\w]{1,6})[\"']"
)

# বাংলা মন্তব্য: Windows ড্রাইভ-লেটার artifact (seq:2-তে f:\-ভাঙা ওয়ান-টাইম স্ক্রিপ্ট ধরা পড়েছিল)।
_WIN_DRIVE_RE = re.compile(r"\b[A-Za-z]:[\\/]")

# বাংলা মন্তব্য: dated one-time নাম — ফাইলনামে YYYY_MM_DD / YYYY-MM-DD / YYYYMMDD প্যাটার্ন।
_DATED_NAME_RE = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

# বাংলা মন্তব্য: deprecation/one-time মার্কার — কেস-ইনসেনসিটিভ সাবস্ট্রিং প্রমাণ।
_STALE_MARKERS = (
    "deprecated",
    "do not use",
    "one-time",
    "one time only",
    "superseded",
    "obsolete",
    "legacy-only",
)

# বাংলা মন্তব্য: external-service বাইন্ডিং সংকেত — এগুলো থাকলে স্ক্রিপ্ট environment-bound
# অপারেশনাল টুল; toolkit-এ পোর্ট করা (absorb) অর্থহীন/ঝুঁকিপূর্ণ, জায়গায় জায়গায় চালানোই মূল্য।
_SERVICE_MARKERS = (
    "requests.", "import requests", "urllib", "httpx", "socket.",
    "boto3", "paramiko", "docker", "kubectl", "infisical",
    "api.github.com", "api.render.com", "smtplib", "smtp.",
    "psycopg2", "asyncpg", "supabase",
)

# বাংলা মন্তব্য: সিম্বল-ইউনিকনেস প্রোবের থ্রেশহোল্ড — unique def/class সিম্বল এই সংখ্যা ছাড়ালে
# ফাইলটি "হারালে লস" শ্রেণিতে পড়ে। এর নিচে হলে সাধারণ অপারেশনাল টুলই ধরা হয়।
ABSORB_UNIQUE_SYMBOLS = 5
ABSORB_MIN_LINES = 150

# বাংলা মন্তব্য: stale-রায়ের থ্রেশহোল্ড — ভাঙা ভেতরের-পাথ রেফারেন্স এই সংখ্যায় পৌঁছালে
# **এবং** সহায়ক প্রমাণ (উত্তরাধিকার মার্কার/Windows artifact/১ বছর-পুরনো) থাকলে তবেই stale।
# কারণ: purge/migration/সচেতন-ডিগ্রেডেশন স্ক্রিপ্ট ডিজাইন-অনুযায়ীই অস্তিত্বহীন পাথ রাখে —
# একার ভাঙা-পাথ গণনা false-positive তৈরি করে (seq:3 রান-১ প্রমাণ: purge_history_secrets.sh)।
STALE_BROKEN_PATHS = 4
STALE_AGE_DAYS = 365

# বাংলা মন্তব্য: history-rewrite টুল-স্বাক্ষর — এই রেগেক্স মিললে ভাঙা-পাথ গণনা বাদ
# (filter-repo purge-তালিকার পাথ ডিজাইন-অনুযায়ীই ওয়ার্কিং-ট্রিতে থাকে না)।
_HISTORY_REWRITE_RE = re.compile(r"filter-repo|filter-branch|FORCE_PURGE|BFG_REPO")


@dataclass
class StandaloneVerdict:
    """একটি review-standalone ফাইলের রান-ভ্যালু প্রমাণ-বান্ডিল (seq:3)।"""

    path: str
    lines: int
    runnable: bool | None
    compile_error: str = ""
    broken_paths: list[str] = field(default_factory=list)
    windows_artifact: bool = False
    stale_markers: list[str] = field(default_factory=list)
    dated_name: bool = False
    total_symbols: int = 0
    unique_symbols: int = 0
    service_bound: bool = False
    docs_refs: int = 0
    last_commit_days: int | None = None
    family_size: int = 0
    verdict: str = "keep-operational"
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _syntax_check(path: Path, suffix: str, text: str) -> tuple[bool | None, str]:
    """রানেবিলিটি প্রমাণ — side-effect-মুক্ত (in-process compile / bash -n via stdin)।"""
    if suffix == ".py":
        try:
            compile(text, str(path), "exec")
            return True, ""
        except SyntaxError as e:
            return False, f"line {e.lineno}: {e.msg}"
    if suffix == ".sh":
        try:
            proc = subprocess.run(
                ["bash", "-n"], input=text, capture_output=True, text=True, timeout=15
            )
            if proc.returncode == 0:
                return True, ""
            return False, (proc.stderr or "bash -n failed").strip().splitlines()[-1][:160]
        except (subprocess.SubprocessError, OSError):
            # বাংলা মন্তব্য: bash অনুপস্থিত হলে প্রমাণ-অজানা — safe-direction হিসেবে ধরে রাখা হয়।
            return None, "bash unavailable"
    return None, ""


def _broken_internal_paths(repo: Path, text: str) -> list[str]:
    """স্ট্রিং-লিটারেলে উল্লিখিত repo-internal পাথ সত্যিই আছে কিনা — ভাঙাগুলোই প্রমাণ।

    # বাংলা মন্তব্য: দুই শ্রেণীর ডিজাইন-স্বাভাবিক ভাঙা-পাথ বাদ:
    #   (ক) dict-ম্যাপিং-কী (migration পুরনো→নতুন পাথ ম্যাপ) — কী-অবস্থানে পুরনো পাথ
    #       অস্তিত্বহীন হওয়াই প্রত্যাশিত;
    #   (খ) history-rewrite টুলের purge-তালিকা — filter-repo পাথ ওয়ার্কিং-ট্রিতে থাকে না।
    """
    if _HISTORY_REWRITE_RE.search(text):
        return []  # বাংলা মন্তব্য: purge-টুল — পাথ-ভাঙা প্রমাণ-হিসেবেই অগ্রহণযোগ্য।
    broken: list[str] = []
    for m in _INTERNAL_PATH_RE.finditer(text):
        rel = m.group(1)
        if "*" in rel or "$" in rel or "{" in rel:
            continue  # বাংলা মন্তব্য: glob/env-টেমপ্লেট পাথ যাচাই-অযোগ্য — false-positive এড়ানো
        # বাংলা মন্তব্য: dict-ম্যাপিং-কী সনাক্তকরণ — রেগেক্স বন্ধ-উদ্ধৃতি-চিহ্নও খায়, তাই
        # ম্যাচ-শেষ সরাসরি `:` দিয়ে শুরু হলেই কী-অবস্থান (যেমন 'old-path': 'new-path')।
        line_end = text.find("\n", m.end())
        rest = text[m.end(): line_end if line_end != -1 else len(text)]
        if re.match(r"\s*:", rest):
            continue
        if not (repo / rel).exists():
            if rel not in broken:
                broken.append(rel)
    return broken


def _unique_symbols(text: str, token_counter: Counter, self_counter: Counter) -> tuple[int, int]:
    """def/class সিম্বল সংগ্রহ + রিপোর অন্য কোথাও আছে কিনা — unique-গুলোই ক্যাপাবিলিটি।

    # বাংলা মন্তব্য: seq:3 রান-১ বাগ-ফিক্স — আগে others_blob-এ ফাইল-নিজেই অন্তর্ভুক্ত ছিল,
# ফলে প্রতিটি সিম্বল "অন্য কোথাও" পাওয়া যেত (unique=0 সর্বত্র — অবাস্তব)। এখন টোকেন-কাউন্টার
# তুলনা: ব্লব-গণনা == নিজের-ফাইলের গণনা হলেই কেবল অন্য কোথাও নেই (self-মাত্র)।
    """
    names = set(re.findall(r"^\s*(?:def|class)\s+([A-Za-z_]\w*)", text, re.MULTILINE))
    # বাংলা মন্তব্য: সাধারণ এন্ট্রি-নাম ও টেস্ট-প্যাটার্ন — ইউনিকনেস-গণনা থেকে বাদ।
    names -= {"main", "run", "init", "setup", "teardown"}
    unique = sum(
        1 for n in names if token_counter.get(n, 0) == self_counter.get(n, 0)
    )
    return len(names), unique


def _last_commit_days(repo: Path, rel: str) -> int | None:
    """git last-commit বয়স (দিনে) — freshness প্রমাণ; git না চললে None।"""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", rel],
            cwd=str(repo), capture_output=True, text=True, timeout=20, check=True,
        )
        iso = out.stdout.strip()
        if not iso:
            return None
        dt = datetime.fromisoformat(iso)
        return max(0, (datetime.now(UTC) - dt).days)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def run_standalone_check(
    repo: Path, roots: list[str], out_md: Path | None = None, out_json: Path | None = None
) -> tuple[int, str]:
    """review-standalone বাকেটের রান-ভ্যালু যাচাই — (ফাইল-সংখ্যা, রিপোর্ট) রিটার্ন।"""
    # বাংলা মন্তব্য: একক সত্য-উৎস — audit-ইঞ্জিনের classify() থেকেই review-standalone তালিকা।
    results = _ra.classify(repo, roots)
    targets = [r for r in results if r.verdict == "review-standalone"]

    # বাংলা মন্তব্য: টোকেন-কাউন্টার — এক পাসে গোটা live-blob টোকেনাইজ (পারফরম্যান্স +
    # self-exclusion সঠিকতা একসাথে; প্রতি-ফাইল ব্লব-জয়েন্ট O(N²) ব্যয় এড়ানো)।
    all_files = _ra._repo_git_files(repo)
    docs_texts: list[str] = []
    live_texts: list[dict[str, str]] = []
    for f in all_files:
        if f.startswith(tuple(_ra.EXCLUDED_DIRS)) or "/.git/" in f:
            continue
        fp = repo / f
        try:
            if f.endswith(".md"):
                docs_texts.append(fp.read_text(errors="ignore"))
            elif f.endswith((".py", ".sh", ".yml", ".yaml", ".ts", ".js", ".mjs")):
                live_texts.append({f: fp.read_text(errors="ignore")})
        except OSError:
            continue
    docs_blob = "\n".join(docs_texts)
    live_blob = "\n".join(d for _ in live_texts for d in _.values())
    token_counter = Counter(re.findall(r"[A-Za-z_]\w+", live_blob))

    checks: list[StandaloneVerdict] = []
    for t in targets:
        fp = repo / t.path
        suffix = fp.suffix
        try:
            text = fp.read_text(errors="ignore")
        except OSError:
            text = ""
        runnable, cerr = _syntax_check(fp, suffix, text)
        broken = _broken_internal_paths(repo, text)
        win_art = bool(_WIN_DRIVE_RE.search(text))
        markers = [m for m in _STALE_MARKERS if m in text.lower()]
        dated = bool(_DATED_NAME_RE.search(Path(t.path).name))
        self_counter = Counter(re.findall(r"[A-Za-z_]\w+", text))
        total_sym, unique_sym = _unique_symbols(text, token_counter, self_counter)
        service = any(m in text for m in _SERVICE_MARKERS)
        docs_refs = docs_blob.count(Path(t.path).name) if Path(t.path).name != "__init__.py" else 0
        age = _last_commit_days(repo, t.path)
        family = sum(
            1
            for r2 in results
            if r2.path != t.path and Path(r2.path).parent == Path(t.path).parent
        )

        v = StandaloneVerdict(
            path=t.path,
            lines=t.lines,
            runnable=runnable,
            compile_error=cerr,
            broken_paths=broken[:8],
            windows_artifact=win_art,
            stale_markers=markers,
            dated_name=dated,
            total_symbols=total_sym,
            unique_symbols=unique_sym,
            service_bound=service,
            docs_refs=docs_refs,
            last_commit_days=age,
            family_size=family,
        )
        v.verdict, v.reason = _rule(v)
        checks.append(v)

    report = _render(checks, roots)
    if out_md:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(report, encoding="utf-8")
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps([c.to_dict() for c in checks], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return len(checks), report


def _rule(v: StandaloneVerdict) -> tuple[str, str]:
    """নির্ধারিত রায়-ইঞ্জিন — deterministic, safe-direction (over-keep)।"""
    # ১) সিনট্যাক্স-ভাঙা = চলতে পারে না — সর্বোচ্চ-শক্তির stale প্রমাণ।
    if v.runnable is False:
        return "stale-review", f"syntax-ভাঙা ({v.compile_error}) — রানেবিল নয়, prune-after-harvest প্রার্থী"
    # ২) dated one-time নাম + সহায়ক প্রমাণ (ভাঙা-পাথ/উত্তরাধিকার মার্কার/Windows artifact)।
    if v.dated_name and (v.broken_paths or v.stale_markers or v.windows_artifact):
        return "stale-review", "dated one-time নাম + ভাঙা-পাথ/উত্তরাধিকার প্রমাণ — পরবর্তী slice-এ harvest-check"
    # ৩) বহু ভাঙা পাথ **এবং** সহায়ক প্রমাণ — একার ভাঙা-পাথ purge/migration/সচেতন-ডিগ্রেডেশনেও
    #    হয় (রান-১ প্রমাণ), তাই corroboration বাধ্যতামূলক (Golden-Rule over-keep)।
    corroborated = bool(v.stale_markers) or v.windows_artifact or (
        v.last_commit_days is not None and v.last_commit_days >= STALE_AGE_DAYS
    )
    if len(v.broken_paths) >= STALE_BROKEN_PATHS and corroborated:
        return "stale-review", f"{len(v.broken_paths)}টি ভাঙা repo-internal পাথ-রেফ + সহায়ক প্রমাণ — পরবর্তী slice-এ harvest-check"
    # ৪) পোর্টেবল unique লজিক (service-bound নয়) — toolkit-এ হারভেস্ট-ম্যানিফেস্ট প্রার্থী।
    if (
        v.runnable
        and not v.service_bound
        and v.unique_symbols >= ABSORB_UNIQUE_SYMBOLS
        and v.lines >= ABSORB_MIN_LINES
    ):
        return (
            "absorb-candidate",
            f"{v.unique_symbols}/{v.total_symbols} unique সিম্বল + {v.lines}L পোর্টেবল লজিক — toolkit-এ পুনঃসৃষ্টির প্রার্থী",
        )
    # ৫) ডিফল্ট = চলুচিত অপারেশনাল টুল (Golden-Rule safe-direction)।
    bits = [f"runnable={v.runnable}"]
    if v.docs_refs:
        bits.append(f"docs-রেফ {v.docs_refs}")
    if v.service_bound:
        bits.append("service-bound অপারেশনাল")
    if v.last_commit_days is not None:
        bits.append(f"শেষ কমিট {v.last_commit_days} দিন আগে")
    return "keep-operational", "রানেবিল অপারেশনাল টুল (" + ", ".join(bits) + ") — স্পর্শ নিষিদ্ধ"


def _render(checks: list[StandaloneVerdict], roots: list[str]) -> str:
    """প্রমাণ-রিপোর্ট রেন্ডার — docs/operations-এ কমিটযোগ্য মার্কডাউন।"""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    counts: dict[str, int] = {}
    for c in checks:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
    lines = [
        "# Standalone Run-Value Verification — group:foundation-closeout (seq:3)",
        "",
        f"> **তারিখ:** {now} · **ইঞ্জিন:** `scripts/supremeai_toolkit/standalone_check.py` v0.1.0 · **roots:** {', '.join(roots)}",
        "> **Golden Rule:** Clean up-এর আগে Reusability Check — beneficial কিছু কোনো অবস্থাতেই ডিলিট করা যাবে না (#2403)।",
        "> এই রিপোর্ট review-standalone বাকেটের প্রমাণ-বেস — এখান থেকে কোনো ফাইল স্বয়ংক্রিয়ভাবে ডিলিট বা সরানো হয় না।",
        "",
        "## সারসংক্ষেপ",
        "",
        f"**যাচাই করা review-standalone ফাইল: {len(checks)}**",
        "",
        "| Verdict | সংখ্যা | অর্থ |",
        "| :--- | ---: | :--- |",
        f"| keep-operational | {counts.get('keep-operational', 0)} | চলুচিত অপারেশনাল টুল — মানুষ চালায়, শূন্য স্বয়ংক্রিয় রেফ স্বাভাবিক |",
        f"| absorb-candidate | {counts.get('absorb-candidate', 0)} | পোর্টেবল unique লজিক — পরবর্তী slice-এ toolkit-এ পুনঃসৃষ্টির ম্যানিফেস্ট |",
        f"| stale-review | {counts.get('stale-review', 0)} | ভাঙা/পুরনো প্রমাণ — পরবর্তী slice-এ prune-after-harvest প্রার্থী (এই স্লাইসে ডিলিট নেই) |",
        "",
    ]
    for verdict, title in (
        ("stale-review", "stale-review তালিকা (পরবর্তী slice-এর harvest-check evidence-base)"),
        ("absorb-candidate", "absorb-candidate তালিকা (হারভেস্ট-ম্যানিফেস্ট — toolkit-এ পুনঃসৃষ্টির প্রার্থী)"),
        ("keep-operational", "keep-operational তালিকা (স্পর্শ নিষিদ্ধ — চলুচিত অপারেশনাল টুল)"),
    ):
        subset = sorted((c for c in checks if c.verdict == verdict), key=lambda x: x.path)
        lines += [
            f"## {title}",
            "",
            "| ফাইল | লাইন | রানেবিল | unique-সিম্বল | docs-রেফ | কারণ |",
            "| :--- | ---: | :---: | ---: | ---: | :--- |",
        ]
        for c in subset:
            run_flag = {True: "✅", False: "❌", None: "—"}[c.runnable]
            lines.append(
                f"| `{c.path}` | {c.lines} | {run_flag} | {c.unique_symbols}/{c.total_symbols} | {c.docs_refs} | {c.reason} |"
            )
        lines.append("")
    return "\n".join(lines)
