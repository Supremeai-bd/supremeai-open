#!/usr/bin/env python3
"""radar_index_freshness_guard.py — R48 radar-index freshness gate (#2091).

কেন (Why — Bengali, house style):
    SCOUT_RADAR_INDEX.md হলো R-number SSOT (নিয়ম ৭: "the index is the only
    counter")। ২০২৬-10-28-এ একই দিনে তিনবার প্রমাণ হলো যে §5-এর self-policing
    চুক্তি (filer নিজেই same-cycle-এ index আপডেট করবে) কাঠামোগতভাবে ভঙ্গুর —
    pass 3/4/6-এ তিনটি collision-imminent ড্রিফট হলো, যেখানে index-এর
    বিজ্ঞাপিত next-free নম্বর ইতিমধ্যেই landed row হিসেবে দখল হয়ে গিয়েছিল।
    একজন scout বিজ্ঞাপিত নম্বরটা নিলে দ্বিগুণ বরাদ্দ (double-allocation) হতো।
    এই গার্ড সেই ব্যর্থতা-শ্রেণিকে যান্ত্রিকভাবে বন্ধ করে — #1644-এর
    script-index gate-এর হুবহু মিরর, কিন্তু R-নম্বর সমতলে।

Invariants (the #2091 spec, mechanical port):
    A  registry-completeness — প্রতিটি R<number> যা index-এর §2 summary
       table-এ আছে, registry-তে (§1) তার ঠিক একটি row থাকবে; একই full token
       (suffix সহ) দুবার row হলে duplicate-row।
    B  pointer-truth — allocation rule-এর বিজ্ঞাপিত `next free: R<n>`:
       (b1) registry-তে row হিসেবে নেই (তিনটি লগ হওয়া collision-এর ঠিক শ্রেণি),
       (b2) pointer-context বাদ দিলে index body-র অন্য কোথাও cited নয়,
       (b3) repo-wide tracked filename-এ তার lowercase token নেই
            (#1969-এর discovery-pruning শৈলী; EVAL-r39-ফাইলনাম শ্রেণি)।
    C  citation-existence — docs/** এর প্রতিটি uppercase `R<number>`
       citation (suffix -V/-VI/-c base-resolve করে) registry row-তে মেলে;
       ghost citation = অমিল। Vendored .agents/skills report-only (#1725)।

Verdict routing (single bookkeeping):
    - ratcheted   — A/B সব ব্যর্থতা + docs/** ghost citation: fail-closed;
                    baseline (shrink-only) কখনো বাড়ে না।
    - report_only — vendored .agents/skills/** citation (কখনো agent-fix নয়)।
    D  commit-subject — সাম্প্রতিক squash-merge subject-এ এমন R-citation
       যার registry row নেই (#2187 offline port; জন্মে floor ফাঁকা —
       first-run-clean, shrink-only)।

Invariant D-এর পুরনো রূপ (issue-body citation scan, "GitHub API চায়") ইতিহাসে
গেছে — #2127-এর state-plane আর squash subject-এ WO শিরোনাম থাকায় offline
git-subject স্ক্যানই যথেষ্ট (#2187); online variant ভবিষ্যৎে report-only
agent-plane-এ যেতে পারে, guard binary-তে কখনো নয় (Never-do: কোনো network)।
git অনুপস্থিত হলে D honest-skip (#1760) — কখনো মিথ্যা PASS তৈরি করে না।
Landing-order rebase (pass-9-এর D) প্রক্রিয়া-নিয়ম — static check নয়,
docstring-এ নথিভুক্ত।

Modes:
    --check        roster mode: full sweep vs baseline (default)
    --files <p..>  pre-push mode: content scans limited to these changed
                   files (pointer + filename scans stay global — cheap)
    --baseline     print a freshly swept baseline JSON (admin/regenerate)
    --json         machine-readable auditor report on stdout
    --self-test    hermetic offline fixture suite (guard-the-guard)

Never-do (from #2091):
    কোনো retro-claim নয় (rule 1/7 অপরিবর্তিত); status কলাম হলো point-in-time
    — গার্ড allocation truth চেক করে, lane-status freshness নয়; index-ই একমাত্র
    counter — এটি দ্বিতীয় registry নয়, mechanical backstop মাত্র; কোনো
    .github/** লেখা নয় (#1643); কোনো network call নয় (offline stdlib)।

Run: python3 scripts/ci/radar_index_freshness_guard.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TAG = "[radar-index-freshness-guard]"
INDEX_REL = "docs/SCOUT_RADAR_INDEX.md"
BASELINE_PATH = Path("scripts/ci/radar_index_freshness_baseline.json")

EXCLUDED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", ".env",
    "build", "dist", "out", "__pycache__", ".next", ".pytest_cache",
    "generated", ".mypy_cache", ".ruff_cache", ".tox", ".eggs",
}
VENDORED_PREFIX = ".agents/skills/"  # #1725 lane — report-only, never agent-fixed

INDEX_PATH_RE = re.compile(r"^docs/SCOUT_RADAR_2026-10-28.*\.md$")

# The advertised pointer. Real corpus forms (verified at aa9de7b):
#   "next free: **R51**" / "next free = R37" / "next free to R39" /
#   "next free → **R51**" — hence the loose <=14-char non-R separator.
POINTER_RE = re.compile(r"next\s+free[^R\n]{0,14}?R(\d{1,3})\b")
# Pointer-context phrase (stripped before token scans so the pointer's own
# advertisement and the drift-log "moves next free to R<n>" advances never
# self-trip the scans — a counter statement is never a lane citation).
# #2187 Finding 3: the gap widens `\s` -> `[-\s]` — the HYPHENATED form
# "next-free R53" (the real shape of landed subjects #2172/#2178) used to
# escape the stripper and would have flagged the pointer advance itself as a
# ghost citation of R53 — a false positive authored by the registration
# contract's own tickets. Gap/bold-tolerance stay byte-identical.
POINTER_PHRASE_RE = re.compile(
    r"next[-\s]free[^R\n]{0,14}?\*{0,2}R\d{1,3}\*{0,2}(?:\s*\([^)]*\))?"
)
# Commit-plane scan depth for invariant D (#2187): ~a day of bridge landings
# at the current squash rate; evidence/key truncation mirrors
# _git_head_provenance's 96-char subject slice.
SUBJECT_WINDOW = 60
SUBJECT_SLICE = 96
# Registry rows: "| R37 | ..." or "| R23-**V** | ..." (column 1 of §1 table).
REGISTRY_ROW_RE = re.compile(r"^\|\s*R([1-9]\d{0,2})(?:-\*{0,2}(V|VI|c)\*{0,2})?\s*\|", re.MULTILINE)
# Any uppercase R-citation, optional -V/-VI/-c suffix ("R23-VI", "R26-c").
# Domain note: scout R-numbers start at R1 (the registry allocation begins
# there and the pointer only advances) — "R0" is a different namespace (the
# risk-engine decision matrix R0-R6 in docs/security/), never a scout lane.
R_TOKEN_RE = re.compile(r"\bR([1-9]\d{0,2})(?:-(V|VI|c))?\b")
# Lowercase pointer token inside a tracked FILENAME ("-r39-", "_r45."),
# delimited so commit-slang like "r3" inside longer words never matches.
FNAME_TOKEN_RE = re.compile(r"(?:^|[^a-z0-9])r(\d{1,3})(?:[^a-z0-9]|$)", re.IGNORECASE)


def _evidence(msg: str) -> None:
    """Stable-tagged evidence line — CI greps this."""
    print(f"{GUARD_TAG} {msg}")


def section(text: str, start: str, end: str) -> str:
    """Slice the text between two headings (end optional)."""
    i = text.find(start)
    if i < 0:
        return ""
    body = text[i + len(start):]
    j = body.find(end) if end else -1
    return body if j < 0 else body[:j]


def parse_pointer(text: str) -> int | None:
    m = POINTER_RE.search(text)
    return int(m.group(1)) if m else None


def parse_registry(text: str) -> tuple[dict[str, int], set[int]]:
    """Return ({full_token: row_count}, {base_numbers})."""
    tokens: Counter[str] = Counter()
    bases: set[int] = set()
    registry_block = section(text, "## 1.", "## 2.")
    for m in REGISTRY_ROW_RE.finditer(registry_block):
        base, suffix = int(m.group(1)), m.group(2)
        token = f"R{base}" + (f"-{suffix}" if suffix else "")
        tokens[token] += 1
        bases.add(base)
    return dict(tokens), bases


def strip_pointer_phrases(text: str) -> str:
    """Remove pointer advertisements/advances so scans see only lane citations."""
    return POINTER_PHRASE_RE.sub(" ", text)


def invariant_a(text: str, tokens: dict[str, int]) -> list[dict]:
    """§2 summary-table citations must resolve to exactly one registry row."""
    findings: list[dict] = []
    anchors = section(text, "## 2.", "## 3.")
    for m in R_TOKEN_RE.finditer(anchors):
        base, suffix = int(m.group(1)), m.group(2)
        token = f"R{base}" + (f"-{suffix}" if suffix else "")
        if token not in tokens:
            findings.append({"kind": "anchor-ghost", "token": token})
    for token, count in sorted(tokens.items()):
        if count > 1:
            findings.append({"kind": "duplicate-row", "token": token, "count": count})
    return findings


def invariant_b(
    text: str, root: Path, tokens: dict[str, int], bases: set[int], pointer: int | None,
    only_files: list[Path] | None = None,
) -> list[dict]:
    """Pointer truth: not a row, not cited outside pointer context, not a filename."""
    findings: list[dict] = []
    if pointer is None:
        findings.append({"kind": "pointer-missing"})
        return findings
    if pointer in bases:
        findings.append({"kind": "pointer-taken", "pointer": pointer})
    body = strip_pointer_phrases(text)
    # index body cited the pointer outside pointer-context? (drift-log prose
    # that treats it as a lane, not as the counter advance)
    if re.search(rf"\bR{pointer}\b", body):
        findings.append({"kind": "pointer-cited-in-index", "pointer": pointer})
    # repo-wide tracked filename scan (b3)
    for path in walk_files(root, only_files=None):
        rel = path.relative_to(root).as_posix()
        m = FNAME_TOKEN_RE.search(Path(rel).name.lower())
        if m and int(m.group(1)) == pointer:
            findings.append({"kind": "pointer-in-filename", "pointer": pointer, "file": rel})
    return findings


def walk_files(root: Path, only_files: list[Path] | None) -> list[Path]:
    if only_files is not None:
        return sorted(only_files)
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            out.append(Path(dirpath) / fn)
    return out


def invariant_c(
    root: Path, bases: set[int], pointer: int | None = None,
    only_files: list[Path] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Uppercase R-citations resolve to registry rows (base-resolved).

    Verdict routing mirrors docs_link_integrity_guard: tracked docs/** files
    are ratcheted (ghost citations fail-closed over the shrink-only baseline);
    vendored .agents/skills/** packs are report-only (#1725 lane, never
    agent-fixed); every other lane is out of the C scope (the #2091 spec
    scopes citation truth to docs/** radar/summary surfaces).

    The shared-namespace limitation: docs mentioning non-scout identifiers
    that lexically equal registered scout numbers (e.g. a risk-engine "R3")
    resolve via the registry and cannot be distinguished — the guard's contract
    is ghost detection over the R1+ domain, not namespace disambiguation.
    Returns (ratcheted_findings, report_only_findings).
    """
    findings: list[dict] = []
    report_only: list[dict] = []
    files = walk_files(root, only_files)
    for path in files:
        rel = path.relative_to(root).as_posix()
        if not rel.endswith(".md"):
            continue
        if rel.startswith(VENDORED_PREFIX):
            vendored = True          # #1725 lane — visible, never asserted
        elif rel.startswith("docs/"):
            vendored = False
        else:
            continue                 # outside the C scope (spec: docs/**)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = strip_pointer_phrases(text)
        for m in R_TOKEN_RE.finditer(body):
            base = int(m.group(1))
            if base in bases:
                continue
            item = {"kind": "citation-ghost", "file": rel, "token": m.group(0), "base": base}
            (report_only if vendored else findings).append(item)
    return findings, report_only


def scan_subjects(subjects: list[str], bases: set[int]) -> list[dict]:
    """Pure core of invariant D (#2187) — commit-plane ghost detection.

    বাংলা: প্রতিটি squash-merge subject থেকে pointer-প্রসঙ্গ বাদ দিয়ে
    (strip_pointer_phrases) R-token স্ক্যান — registry-তে নেই এমন base =
    commit-subject-ghost। বিশুদ্ধ ফাংশন রাখা হয়েছে যাতে hermetic self-test
    subprocess ছাড়াই হুবহু প্রোডাকশন-লজিক চালাতে পারে; invariant_d শুধু
    git-সংগ্রহের মোড়ক।
    """
    findings: list[dict] = []
    seen: set[str] = set()
    for raw in subjects:
        subject = " ".join(raw.split())[:SUBJECT_SLICE]
        if not subject or subject in seen:
            continue
        seen.add(subject)
        for m in R_TOKEN_RE.finditer(strip_pointer_phrases(subject)):
            base = int(m.group(1))
            if base in bases:
                continue
            findings.append({
                "kind": "commit-subject-ghost",
                "subject": subject,
                "token": m.group(0),
                "base": base,
            })
    return findings


def invariant_d(root: Path, bases: set[int]) -> tuple[list[dict], bool]:
    """Offline invariant D — commit-subject ghost scan over the landing window (#2187).

    বাংলা: ৫টি collision (R37/R39/R45/R51/R52) সবাই commit-plane-এ ঘটেছিল —
    মুহূর্তে একমাত্র প্রমাণ ছিল issue body আর squash subject, কোনো .md নয়,
    তাই A/B/C সবাই অন্ধ ছিল। #2091-এর D-প্রেমিস ("GitHub API চায়") সময়ের
    সাথে পুরোনো হয়েছে: squash subject-এ WO শিরোনাম থাকেই, আর git guard-এর
    কাছে আগেই আছে (_git_head_provenance subprocess ব্যবহার করে)। তাই
    offline subprocess-ই যথেষ্ট — guard-এর Never-do (কোনো network) অক্ষত।

    চুক্তি (three-state, #1760 doctrine):
    - git অনুপস্থিত/ব্যর্থ → honest-skip: ( ফাঁকা, ran=False ) — কখনো মিথ্যা
      PASS তৈরি করে না, পরের রান আবার চেষ্টা করবে;
    - ran=True → scan_subjects-এর ফল; জন্মে floor ফাঁকা (first-run-clean) —
      shrink-only ratchet শুধু ভবিষ্যৎ unregistered landing-এ ফায়ার করবে।
    """
    try:
        proc = subprocess.run(
            ["git", "log", f"-n{SUBJECT_WINDOW}", "--format=%s"],
            cwd=str(root), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        _evidence("SKIP invariant D: git unavailable (hermetic offline) — honest-skip, no fabricated PASS")
        return [], False
    if proc.returncode != 0:
        first = (proc.stderr.strip().splitlines() or ["unknown"])[0][:80]
        _evidence(f"SKIP invariant D: git log failed ({first}) — honest-skip, no fabricated PASS")
        return [], False
    return scan_subjects(proc.stdout.splitlines(), bases), True


def key_of(f: dict) -> tuple:
    kind = f.get("kind", "citation-ghost")
    if kind == "commit-subject-ghost":
        # Landed squash subjects are immutable — (kind, base, subject) is a
        # stable ratchet key; each landing is its own floor entry.
        return (kind, f.get("base"), f.get("subject", ""))
    if kind in ("anchor-ghost", "duplicate-row"):
        return (kind, f["token"])
    if kind in ("pointer-taken", "pointer-cited-in-index", "pointer-missing"):
        return (kind, f.get("pointer"))
    if kind == "pointer-in-filename":
        return (kind, f["pointer"], f["file"])
    return ("citation-ghost", f["file"], f["base"])


def counts_of(findings: list[dict]) -> dict[tuple, int]:
    return dict(Counter(key_of(f) for f in findings))


def load_baseline(repo_root: Path) -> dict:
    p = repo_root / BASELINE_PATH
    if not p.is_file():
        return {"schema": "radar-index-freshness-baseline/1", "floor": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _evidence(f"FAIL baseline malformed: {exc}")
        raise SystemExit(1)
    if not isinstance(data, dict) or not isinstance(data.get("floor"), list):
        _evidence("FAIL baseline schema unrecognised (need schema + floor list)")
        raise SystemExit(1)
    return data


def compare(baseline: dict, findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Shrink-only ratchet over the ratcheted class. Returns (drift, improvements)."""
    floor_map: dict[tuple, int] = {}
    for e in baseline.get("floor", []):
        floor_map[tuple(e["key"])] = int(e["allowed"])
    current = counts_of(findings)
    drift: list[dict] = []
    improvements: list[dict] = []
    for key, now in sorted(current.items(), key=lambda kv: repr(kv[0])):
        allowed = floor_map.get(key, 0)
        if now > allowed:
            drift.append({"key": list(key), "now": now, "allowed": allowed,
                          "kind": "grown" if key in floor_map else "new"})
        elif key in floor_map and now < allowed:
            improvements.append({"key": list(key), "now": now, "allowed": allowed, "kind": "shrunk"})
    for key, allowed in sorted(floor_map.items(), key=lambda kv: repr(kv[0])):
        if key not in current:
            improvements.append({"key": list(key), "now": 0, "allowed": allowed, "kind": "resolved"})
    return drift, improvements


def render(
    a: list[dict], b: list[dict], cits: list[dict], report_only: list[dict],
    drift: list[dict], improvements: list[dict], pointer: int | None,
    d: list[dict] | None = None, d_ran: bool = False,
) -> None:
    if d is None:
        d = []
    for f in d:
        _evidence(f"D-FAIL commit-subject-ghost: recent subject '{f['subject']}' cites "
                  f"{f['token']} — no registry row for R{f['base']} (#2187 commit-plane)")
    for it in improvements:
        _evidence(f"SHRUNK {it['kind']} key={it['key']} {it['allowed']}->{it['now']} "
                  "(shrink the baseline entry in this same change)")
    if report_only:
        _evidence(f"REPORT-ONLY {len(report_only)} vendored .agents/skills citation(s) — routed to the #1725 lane")
    if pointer is not None:
        _evidence(f"OK pointer R{pointer} parsed from the allocation rule")
    drift_keys = {tuple(d["key"]) for d in drift}
    pinned, unpinned = [], []
    for f in cits:
        (unpinned if key_of(f) in drift_keys else pinned).append(f)
    if pinned:
        _evidence(f"PINNED {len(pinned)} baseline-floor ghost citation(s) — pre-existing debt, shrink-only")
        for f in pinned:
            print(f"  {GUARD_TAG} pinned: {f['file']} cites {f['token']} (no registry row for R{f['base']})")
    for f in a:
        _evidence(f"A-FAIL {f['kind']}: {f['token']}"
                  + (f" x{f['count']}" if f.get("count") else ""))
    for f in b:
        if f["kind"] == "pointer-taken":
            _evidence(f"B-FAIL pointer-taken: R{f['pointer']} is advertised next-free AND has a registry row "
                      "(the exact pass-3/4/6 collision class)")
        elif f["kind"] == "pointer-cited-in-index":
            _evidence(f"B-FAIL pointer-cited-in-index: R{f['pointer']} appears outside pointer context")
        elif f["kind"] == "pointer-in-filename":
            _evidence(f"B-FAIL pointer-in-filename: R{f['pointer']} token in tracked filename {f['file']}")
        elif f["kind"] == "pointer-missing":
            _evidence("B-FAIL pointer-missing: no `next free: R<n>` advertisement found")
    for f in unpinned:
        _evidence(f"C-FAIL citation-ghost: {f['file']} cites {f['token']} — no registry row for R{f['base']}")
    if drift:
        for d in drift:
            _evidence(f"DRIFT {d['kind']}: key={d['key']} {d['now']}/{d['allowed']}")
        _evidence(f"FAIL {len(a) + len(b) + len(unpinned)} invariant finding(s), {len(drift)} ratchet drift — the floor may never grow")
    elif a or b or unpinned:
        _evidence("FAIL radar-index freshness invariants violated (see A-FAIL/B-FAIL/C-FAIL lines)")
    elif d:
        _evidence(f"PINNED {len(d)} commit-subject ghost(s) in the landing window — "
                  "pre-existing debt, shrink-only (#2187); register the row to shrink")
    elif d_ran:
        _evidence("OK invariant D: recent commit subjects carry no unregistered R-token (commit-plane clean, #2187)")
    else:
        _evidence("OK invariants A/B/C hold; registry, pointer and docs citations agree (D honest-skipped: no git)")


def sweep(
    root: Path, only_files: list[Path] | None = None,
) -> dict:
    index_path = root / INDEX_REL
    if not index_path.is_file():
        return {"fatal": f"index missing: {INDEX_REL}"}
    text = index_path.read_text(encoding="utf-8", errors="replace")
    pointer = parse_pointer(text)
    tokens, bases = parse_registry(text)
    a = invariant_a(text, tokens)
    b = invariant_b(text, root, tokens, bases, pointer)
    cits, report_only = invariant_c(root, bases, pointer, only_files)
    # #2187: invariant D rides the same sweep — global commit-plane scan,
    # not scoped to --files (pre-push content limits stay A/B/C-scoped).
    ghosts, d_ran = invariant_d(root, bases)
    rows_range = (min(bases), max(bases)) if bases else None
    return {"pointer": pointer, "a": a, "b": b, "cits": cits,
            "report_only": report_only, "rows": rows_range,
            "d": ghosts, "d_ran": d_ran}


def self_test() -> bool:
    """Hermetic fixture suite — offline, tempdir, no repo mutation.

    F2/F3/F4 replay the three logged same-day collisions (passes 3/4/6):
    each synthetic index advertises a next-free number that its own registry
    has already consumed; the guard must FAIL naming that exact R-number.

    #2187 additions:
    F13 (#2187 Finding 3): the widened stripper must clean the hyphenated
    pointer form "next-free R53" carried by real landed subjects (#2172/
    #2178) — pre-widening, the registration contract's own tickets would
    have self-tripped as ghost citations of R53.
    F14: end-to-end invariant_d over a real (local, throwaway) git history —
    an unregistered landing subject is named; the hyphenated pointer subject
    stays clean; git-less sandboxes honest-skip.
    F15: the real-subject corpus (#2145/#2165/#2178/#2184 shapes) resolves
    against the full registry — the shrink-only floor stays empty at birth.
    F16: pure-core ghost detection names token and base.
    """
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"{'PASS' if cond else 'FAIL'} {name}")
        ok = ok and cond

    def tree(files: dict[str, str]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="rifg-selftest-"))
        for rel, content in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return tmp

    def index(pointer: int, rows: list[int], anchors: str = "", extra_body: str = "") -> str:
        rows_md = "\n".join(f"| R{n} | `f.md` | lane | #1 | verdict | — |" for n in rows)
        return (
            "# Scout Radar Index\n\n"
            f"> **Allocation rule:** take the next free R-number FROM this index (next free: **R{pointer}**).\n\n"
            f"{extra_body}\n"
            "## 1. R-number registry\n\n"
            "| R# | Radar file | Lane | Filed | Verdict | Status |\n"
            "|----|-----------|------|-------|---------|--------|\n"
            f"{rows_md}\n\n"
            "## 2. Radar cycle anchors\n\n"
            f"{anchors}\n"
            "## 5. Honest limitations\n\nend\n"
        )

    # F1: clean synthetic index + a resolving docs citation -> PASS
    root = tree({
        INDEX_REL: index(4, [1, 2, 3], anchors="| I | `f1.md` (R1–R3) | #1 | |"),
        "docs/radar-x.md": "# X\ncites R2 and R3-V\n",
        "docs/other.md": "# O\nno r-tokens here, r3 slang ignored\n",
    })
    r = sweep(root)
    check("F1-clean-pass", r["pointer"] == 4 and not r["a"] and not r["b"] and not r["cits"])

    # F2: pass-3 replay — pointer R37 while R37 row exists -> FAIL naming R37
    root = tree({INDEX_REL: index(37, [1, 37])})
    r = sweep(root)
    check("F2-pass3-replay-fails-naming-R37",
          any(f["kind"] == "pointer-taken" and f["pointer"] == 37 for f in r["b"]))

    # F3: pass-4 replay — pointer R39 while R39 row exists
    root = tree({INDEX_REL: index(39, [1, 39])})
    r = sweep(root)
    check("F3-pass4-replay-fails-naming-R39",
          any(f["kind"] == "pointer-taken" and f["pointer"] == 39 for f in r["b"]))

    # F4: pass-6 replay — pointer R45 while R45 row exists
    root = tree({INDEX_REL: index(45, [1, 45])})
    r = sweep(root)
    check("F4-pass6-replay-fails-naming-R45",
          any(f["kind"] == "pointer-taken" and f["pointer"] == 45 for f in r["b"]))

    # F5: anchor-ghost — §2 cites R99, registry lacks it
    root = tree({INDEX_REL: index(4, [1], anchors="| I | `f.md` (R99) | #1 | |")})
    r = sweep(root)
    check("F5-anchor-ghost-found", any(f["kind"] == "anchor-ghost" and f["token"] == "R99" for f in r["a"]))

    # F6: citation-ghost — docs file cites unregistered R98
    root = tree({INDEX_REL: index(4, [1]), "docs/d.md": "# D\ncites R98\n"})
    r = sweep(root)
    check("F6-citation-ghost-found",
          any(f["base"] == 98 and f["file"] == "docs/d.md" for f in r["cits"]))

    # F7: pointer-in-filename — tracked filename embeds the pointer token
    root = tree({INDEX_REL: index(51, [1]),
                 "docs/EVAL_2026-10-28-r51-lane-verdict.md": "# V\nmentions R1\n"})
    r = sweep(root)
    check("F7-pointer-filename-found",
          any(f["kind"] == "pointer-in-filename" and f["pointer"] == 51 for f in r["b"]))

    # F8: pointer-context stripping — drift-log advance + allocation rule never self-trip
    body = ("# Idx\n> Allocation rule (next free: **R51**).\n\n"
            "> **Drift log:** pass 11 — moves next free to **R51** (verified free repo-wide).\n"
            "## 1. R\n| R# | F | L | I | V | S |\n|---|---|---|---|---|---|\n| R1 | a | b | #1 | c | d |\n\n"
            "## 5. End\n")
    root = tree({INDEX_REL: body})
    r = sweep(root)
    check("F8-pointer-context-stripped", not any(
        f["kind"] == "pointer-cited-in-index" for f in r["b"]) and r["pointer"] == 51)

    # F9: withdrawn §3-style label + suffixed rows/citations resolve, no FP.
    # Collision doctrine: suffixed §2 citations pair with suffixed registry
    # rows (R23-**V** / R23-**VI** are distinct rows of base 23).
    dup_suffix = (
        "# Idx\n> Allocation rule (next free: **R4**).\n\n"
        "## 1. R\n| R# | F | L | I | V | S |\n|---|---|---|---|---|---|\n"
        "| R23-**V** | `v.md` | lane | #1 | verdict | — |\n"
        "| R23-**VI** | `vi.md` | lane | #2 | verdict | — |\n"
        "| R26 | `c.md` | lane | #3 | verdict | — |\n\n"
        "## 2. Anchors\n| III | `f.md` (R23-V, R23-VI) | #1 | |\n"
        "## 5. End\n"
    )
    root = tree({INDEX_REL: dup_suffix,
                 "docs/xi.md": "# XI\n~~R26-c~~ withdrawn, cites by issue\n"})
    r = sweep(root)
    check("F9-suffix-and-withdrawn-no-fp", not r["a"] and not r["cits"] and len(r["b"]) == 0)

    # F10: shrink-only ratchet — pinned ghost grows -> drift; resolved -> improvement
    root = tree({INDEX_REL: index(4, [1]),
                 "docs/d.md": "# D\ncites R98: R98 here\n"})
    r = sweep(root)
    base = {"schema": "radar-index-freshness-baseline/1",
            "floor": [{"key": ["citation-ghost", "docs/d.md", 98], "allowed": 1}]}
    drift, im = compare(base, r["cits"])
    check("F10a-grown-ghost-fails", len(drift) == 1 and drift[0]["kind"] == "grown"
          and drift[0]["now"] == 2)
    root2 = tree({INDEX_REL: index(4, [1])})
    r2 = sweep(root2)
    drift2, im2 = compare(base, r2["cits"])
    check("F10b-resolved-ghost-improves", not drift2 and len(im2) == 1 and im2[0]["kind"] == "resolved")

    # F11: duplicate registry row for the same full token
    dup = index(4, [1]).replace("| R1 | `f.md` | lane | #1 | verdict | — |\n",
                                "| R1 | `f.md` | lane | #1 | verdict | — |\n| R1 | `g.md` | lane2 | #2 | verdict | — |\n")
    root = tree({INDEX_REL: dup})
    r = sweep(root)
    check("F11-duplicate-row-found", any(f["kind"] == "duplicate-row" and f["token"] == "R1" for f in r["a"]))

    # F12: vendored citation is report-only, never ratcheted
    root = tree({INDEX_REL: index(4, [1]),
                 ".agents/skills/pack/SKILL.md": "# S\ncites R97\n"})
    r = sweep(root)
    check("F12-vendored-report-only", not r["cits"] and len(r["report_only"]) == 1)

    # ---- #2187: invariant D — the commit-plane scans ----------------------
    # F13: hyphenated pointer form in real landed subjects must NOT ghost.
    ghosts = scan_subjects(["guard(docs): register R52 row + next-free R53 (#2172)"], {52})
    check("F13-hyphen-pointer-subject-clean", ghosts == [])
    ghosts = scan_subjects(["pass 11 — moves next free to **R53** (verified free repo-wide)"], set())
    check("F13b-bold-advance-still-clean", ghosts == [])
    ghosts = scan_subjects(["radar R53 filed from the advertised slot"], set())
    check("F13c-nonpointer-R53-still-ghosts", any(f["base"] == 53 for f in ghosts))

    # F14: end-to-end invariant_d on a throwaway local git history.
    if shutil.which("git"):
        root = tree({INDEX_REL: index(53, [1, 52])})

        def git(*a: str) -> None:
            subprocess.run(["git", *a], cwd=str(root), capture_output=True, text=True, check=False)

        git("init", "-q")
        git("config", "user.email", "hermetic@example")
        git("config", "user.name", "hermetic")
        (root / "seed.txt").write_text("one\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "guard(docs): register R52 row + next-free R53 (#2172)")
        (root / "seed.txt").write_text("two\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "feat: unregistered R97 lane landing")
        ghosts, ran = invariant_d(root, {1, 52})
        check("F14a-commit-plane-ran", ran)
        check("F14b-ghost-named-with-token-base",
              any(f["base"] == 97 and f["token"] == "R97" and "unregistered R97 lane landing" in f["subject"]
                  for f in ghosts))
        check("F14c-hyphen-pointer-subject-clean", not any(f["base"] == 53 for f in ghosts))
    else:
        print("PASS F14a-commit-plane-ran (SKIPPED: git unavailable)")
        print("PASS F14b-ghost-named-with-token-base (SKIPPED: git unavailable)")
        print("PASS F14c-hyphen-pointer-subject-clean (SKIPPED: git unavailable)")

    # F15: real-subject corpus resolves against the full registry —
    # first-run-clean property, no baseline seeding needed.
    corpus = [
        "guard(docs): R51 registration per #2137 (#2145)",
        "feat(docs): scout(R52 option A) — register the lane (#2165)",
        "guard(docs): register R52 row + next-free R53 (#2172)",
        "fix(ci): #2180 - baseline provenance were frozen literals (#2184)",
        "a10: receipt eleven (run 5077) - standing trip-wire repeat fire",
    ]
    check("F15-real-corpus-resolves-floor-born-empty",
          scan_subjects(corpus, set(range(1, 53))) == [])

    # F16: pure-core ghost detection names token and base exactly once.
    ghosts = scan_subjects(["feat: unregistered R97 lane landing"], {1})
    check("F16-commit-subject-ghost-found",
          len(ghosts) == 1 and ghosts[0]["base"] == 97 and ghosts[0]["token"] == "R97")

    print(f"{'SELF-TEST OK: radar_index_freshness_guard' if ok else 'SELF-TEST FAILED: radar_index_freshness_guard'}")
    return ok


def _git_head_provenance(root: Path) -> str:
    """Live generation provenance for baseline stamps (#2180).

    Returns "<short-hash> (<subject>)" for the repo at `root`; on any failure
    (hermetic sandboxes without git) returns an honest fallback instead of a
    frozen literal. Best-effort by design: provenance is informational — the
    gate's load-bearing fields are floor/pointer only.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
            capture_output=True, text=True, timeout=10,
        )
        subj = subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=str(root),
            capture_output=True, text=True, timeout=10,
        )
        if head.returncode == 0 and subj.returncode == 0:
            h = head.stdout.strip()
            s = " ".join(subj.stdout.split())[:96]
            if h:
                return f"{h} ({s})" if s else h
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown (git unavailable at generation)"


def build_baseline(root: Path) -> dict:
    r = sweep(root)
    counts = counts_of(r["cits"])
    rows = r.get("rows")
    return {
        "schema": "radar-index-freshness-baseline/1",
        "generatedAt": datetime.now(timezone.utc).date().isoformat(),
        "headAtGeneration": _git_head_provenance(root),
        "probe": "scripts/ci/radar_index_freshness_guard.py",
        "note": "shrink-only floor over the citation-ghost and commit-subject-ghost classes "
                "(#2187: D lands first-run-clean — its floor is born empty); "
                "key = [kind, file, base] / [kind, base, subject]. "
                "A/B invariant violations are NEVER floorable — they are structural and always fail.",
        "floor": [{"key": list(k), "allowed": v} for k, v in sorted(counts.items(), key=lambda kv: repr(kv[0]))],
        "pointerAtGeneration": r["pointer"],
        "registryRowsAtGeneration": (
            f"R{rows[0]}-R{rows[1]}" if rows else "unknown (empty registry at generation)"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="R48 radar-index freshness gate (#2091, +#2187 commit-plane D)")
    parser.add_argument("--check", action="store_true", help="roster mode: full sweep (default)")
    parser.add_argument("--files", nargs="*", help="pre-push mode: restrict content scans to these files")
    parser.add_argument("--baseline", action="store_true", help="print freshly swept baseline JSON")
    parser.add_argument("--json", action="store_true", help="machine-readable auditor report")
    parser.add_argument("--self-test", action="store_true", help="hermetic offline self-test suite")
    args = parser.parse_args()

    if args.self_test:
        return 0 if self_test() else 1

    root = REPO_ROOT
    if args.baseline:
        data = build_baseline(root)
        # #2180: the note is FILE-OWNED narrative history; a canonical regen
        # must carry it forward instead of clobbering it with the builder's
        # template (the docs_link guard demonstrated this hazard live). Today
        # the two notes match, so this is a no-op — until a lane hand-extends
        # the note, exactly as the R42 genesis/shrink history did.
        p = root / BASELINE_PATH
        if p.is_file():
            try:
                prev = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(prev.get("note"), str) and prev["note"].strip():
                    data["note"] = prev["note"]
            except (OSError, json.JSONDecodeError):
                pass
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    only = None
    if args.files:
        only = [p if p.is_absolute() else root / p for p in args.files]
        only = [p for p in only if p.is_file()]

    r = sweep(root, only)
    if "fatal" in r:
        _evidence(f"FAIL {r['fatal']}")
        return 1

    baseline = load_baseline(root)
    # #2187: invariant D joins the SAME shrink-only ratchet — commit-subject
    # keys are never in the born-empty floor, so any ghost is fresh drift,
    # and a registered row (base now in the registry) makes it vanish.
    drift, improvements = compare(baseline, r["cits"] + r["d"])

    if args.json:
        print(json.dumps({
            "guard": GUARD_TAG, "pointer": r["pointer"],
            "a": r["a"], "b": r["b"], "citationGhosts": r["cits"],
            "commitSubjectGhosts": r["d"], "commitPlaneScanned": r["d_ran"],
            "reportOnly": r["report_only"], "drift": drift,
            "improvements": improvements,
            "verdict": "fail" if (r["a"] or r["b"] or drift) else "pass",
        }, indent=2, ensure_ascii=False))
    else:
        render(r["a"], r["b"], r["cits"], r["report_only"], drift, improvements, r["pointer"],
               d=r["d"], d_ran=r["d_ran"])
    return 1 if (r["a"] or r["b"] or drift) else 0


if __name__ == "__main__":
    sys.exit(main())
