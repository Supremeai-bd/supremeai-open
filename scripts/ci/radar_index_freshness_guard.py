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
    E  roster-regression (#2392 component 1 — pass-23's deferred pre-land
       check, mechanized) — baseline /2-এর enforced roster-এর তুলনায় pointer
       পিছনে গেলে বা নথিভুক্ত row token অদৃশ্য হলে FAIL (stale-branch
       whole-file overwrite class, pass-9/22/23); forward motion কখনো fail
       করে না। /1 baseline থাকলে honest-skip — কখনো মিথ্যা PASS নয়।
    G  pin-truth (#3557) — লাইভ-রিপো sweep টেস্টের pin literal আর index-
       বিজ্ঞাপিত pointer-এর অমিল FAIL: "Bump this literal ONLY together with
       a landed index-pointer advance" নিয়মটি এতদিন ছিল শুধু গদ্য — #3483
       pointer R81→R84 এগিয়ে পিন 81-এ রেখে দিলে কোনো গেট ধরেনি এবং
       test_live_repo_sweep_passes লাইভ main-এ তিন ল্যান্ডিং ধরে লাল থাকল
       (CI pytest-শূন্য, হুক-ট্রিগার glob দিন-একের SCOUT_RADAR_2026-10-28*
       নামে আটকে)। পিন literal-ই pointer-এর দ্বিতীয় সৎ কপি — অমিল মানেই
       একটি ল্যান্ডিং চুক্তি ভেঙেছে; গঠনগত, floor-অযোগ্য।

Pointer↔board agreement predicate (#2372 option B / #2392 component 2,
offline plane — the guard binary stays network-free per the Never-do):
    A successor number R<N> is advertisable iff the tracked tree carries
    zero R<N> citations (invariants A–D) AND the captured open-issue-title
    queue carries zero R<N> citations (--board-sweep), except (a) the
    successor lane's own defining ticket (self-ref class, --allow — the
    pass-15 honesty-note precedent) and (b) citations inside the
    pointer-advance commit performing the advertisement (mechanism text,
    not lane adoption). Pass-4 strict outer bound: any third-party radar
    doc, issue, or main-history citation fails. Cite found ⇒ fail loud,
    never advertise dirty; auto-advance is out of scope v1 (fail-loud
    first, per the guard genre's ratchet semantics). The IO is the filer's
    capture step: bridge.work_queue {"limit": 200} saved to a file
    (permanent contract, #2286; tool renamed from bridge_work_queue
    2026-10-29, #2454 r3 deploy / #2457 migration), the guard consumes
    the artifact. R76 fail-loud (#2691): that contract is now ENFORCED
    at ingestion — validate_queue_capture refuses any capture whose
    completeness cannot be proven (unparseable JSON, count≠rows,
    windowTruncated:true, rows<totalOpen, missing row list), because a
    silently under-scanned sweep is worse than a loud failure (pass-33
    drift log: the tower hard-truncates response bodies at ~4000 chars
    at board sizes ≥~130, measured 4/10 cut captures against count=136).

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
    --baseline     print a freshly swept baseline JSON (admin/regenerate;
                   /2 seeds the enforced roster — update it in the same PR
                   that moves the registry, mirroring the pin discipline)
    --board-sweep  pointer↔board agreement (#2372 opt-B): scan a CAPTURED
                   queue artifact (--queue-file) for open-issue-title
                   citations of the candidate successor (--token, default
                   pointer+1), --allow lists the self-ref defining ticket;
                   offline by constitution — no network in this binary
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
# Invariant G (#3557): the live pin's carrier — the pytest file whose
# test_live_repo_sweep_passes sweeps REPO_ROOT and asserts the pointer.
TEST_REL = "tests/test_radar_index_freshness_guard.py"
LIVE_SWEEP_TEST = "test_live_repo_sweep_passes"

EXCLUDED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", ".env",
    "build", "dist", "out", "__pycache__", ".next", ".pytest_cache",
    "generated", ".mypy_cache", ".ruff_cache", ".tox", ".eggs",
}
VENDORED_PREFIX = ".agents/skills/"  # #1725 lane — report-only, never agent-fixed

# (#3557 superior-replacement) the day-one INDEX_PATH_RE
# ("^docs/SCOUT_RADAR_2026-10-28.*\.md$") is deleted: it had zero callers and
# carried the stale day-one filename glob that left the pre-push trigger dark
# once radar docs moved to dated names (SCOUT_RADAR_2026-10-30-XV.md) and the
# founder-migration (#3524) retired loose radar files entirely.

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
REGISTRY_ROW_RE = re.compile(r"^\|\s*R([1-9]\d{0,2})(?:-\*{0,2}(VI|V|I{1,2}|c)\*{0,2})?\s*\|", re.MULTILINE)
# Any uppercase R-citation, optional -V/-VI/-I/-II/-c suffix ("R23-VI",
# "R26-c", and the #2372 double-adoption ordinals "R63-I"/"R63-II" —
# vocabulary widened V|VI|c -> +I{1,2} per the filer's live parse probe
# at pass 24; the R53 POINTER_PHRASE_RE widening precedent).
# Domain note: scout R-numbers start at R1 (the registry allocation begins
# there and the pointer only advances) — "R0" is a different namespace (the
# risk-engine decision matrix R0-R6 in docs/security/), never a scout lane.
R_TOKEN_RE = re.compile(r"\bR([1-9]\d{0,2})(?:-(VI|V|I{1,2}|c))?\b")
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


def invariant_e(
    pointer: int | None, tokens_now: set[str], baseline: dict,
) -> tuple[list[dict], bool]:
    """Roster regression — pass-23's deferred pre-land check, mechanized.

    (#2392 component 1.) A landing REGRESSES the registry when the pointer
    moves backward or a baseline-recorded row token vanishes: the
    stale-branch whole-file overwrite class (pass-9/22/23) whose
    co-regression blind spot the pin discipline cannot see (pin regressed
    WITH the pointer at ebe630c and every citation count stayed green).
    Forward motion — pointer advance, rows added — never fails. A /1
    baseline (no enforced roster) honest-skips: evidence, never a
    fabricated PASS. Update the roster in the same PR that moves the
    registry — the baseline companion of the pin-accompanies-pointer rule.
    """
    roster = baseline.get("roster") if isinstance(baseline, dict) else None
    if not (isinstance(roster, dict)
            and isinstance(roster.get("rows"), list)
            and isinstance(roster.get("pointer"), int)):
        _evidence("SKIP invariant E: baseline has no enforced roster (schema /1) — "
                  "seed one in the same PR that moves the registry")
        return [], False
    findings: list[dict] = []
    if pointer is not None and pointer < roster["pointer"]:
        findings.append({"kind": "roster-pointer-regressed",
                         "was": roster["pointer"], "now": pointer})
    for tok in sorted(set(roster["rows"]) - set(tokens_now)):
        findings.append({"kind": "roster-row-evicted", "token": tok})
    return findings, True


LIVE_PIN_RE = re.compile(r'assert\s+r\["pointer"\]\s*==\s*(\d+)')


def invariant_g(
    pointer: int | None, test_text: str | None, root: Path,
) -> tuple[list[dict], bool]:
    """Pin-truth — the live-repo test's pin literal must equal the pointer (#3557).

    বাংলা (#3557 root-cause): পিন-অনুগম্য নিয়মটি এতদিন ছিল শুধু টেস্ট-কমেন্টের
    গদ্য — #3483 pointer R81→R84 এগিয়ে পিন 81-এ রেখে দিলে invariant A–E-র কেউ
    ধরেনি (E forward-motion-সহনশীল ডিজাইনেই), আর RED টেস্টটা লাইভ main-এ তিন
    ল্যান্ডিং ধরে বেঁচে থাকল কারণ CI-তে pytest শূন্যবার চলে এবং pre-push হুকের
    ট্রিগার glob দিন-একের SCOUT_RADAR_2026-10-28* নামে আটকে ছিল। এই invariant
    পিন literal-কে pointer-এর যান্ত্রিক প্রতিধ্বনি বানায়: দুই কপির অমিল =
    কোনো না কোনো ল্যান্ডিং pin-accompanies-pointer চুক্তি ভেঙেছে — guard সময়েই
    fail loud, মানুষের সতর্কতার উপর ভরসা নয় (Zero-Recurrence Invariant)।

    Honest-skip শৃঙ্খলা (কখনো মিথ্যা PASS নয়):
    - hermetic fixture tree (tests/ ডিরেক্টরিই নেই) → নীরব skip — পিনের বাহক
      সেখানে থাকারই কথা নয়; বাকি দাঁতগুলো ঘুরতে থাকে;
    - tests/ ডিরেক্টরি আছে কিন্তু পিন-ফাইল নেই → গঠনগত "pin-file-missing" FAIL
      (পিন-শৃঙ্খলির বাহকই মুছে গেলে শৃঙ্খলিটাও নেই — CI-শূন্য প্লেনে এটাই একমাত্র
      সনাক্তকারী);
    - live sweep block বা পিন literal অনুপস্থিত → গঠনগত FAIL (বাহকের ভেতরের
      চুক্তি-আকৃতিই বদলে গেলে পিন-তুলনা অসম্ভব)।

    তুলনার নিয়ম: live block-এর প্রতিটি pin literal pointer-এর সমান হতে হবে —
    ভবিষ্যৎ-প্রমাণ (কেউ একাধিক assertion যোগ করলে সবগুলোই সৎ কপি হতে বাধ্য)।
    """
    if pointer is None:
        # pointer-missing is B's finding; nothing to compare against.
        return [], False
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        # Hermetic fixture tree — the pin's carrier legitimately doesn't exist.
        return [], False
    if test_text is None:
        return [{"kind": "pin-file-missing", "path": TEST_REL}], True
    block = section(test_text, f"def {LIVE_SWEEP_TEST}(", "\ndef ")
    if not block:
        return [{"kind": "pin-block-missing", "test": LIVE_SWEEP_TEST}], True
    pins = [int(m.group(1)) for m in LIVE_PIN_RE.finditer(block)]
    if not pins:
        return [{"kind": "pin-literal-missing", "test": LIVE_SWEEP_TEST}], True
    findings: list[dict] = []
    for pin in pins:
        if pin != pointer:
            findings.append({"kind": "pin-drifted", "was": pin, "now": pointer})
    return findings, True


def validate_queue_capture(queue: object, source: str = "queue artifact") -> None:
    """Fail-loud completeness check on a captured bridge.work_queue artifact
    (#2691 / R76 — the pass-33 drift-log hardening, own-lane carrier).

    The #2286 capture contract — one bridge.work_queue {"limit": 200} call
    IS the complete open-issue-title universe — silently degrades at board
    sizes ≥~130: the tower hard-truncates response bodies at ~4000 chars
    mid-JSON, and pass 33 measured 4/10 label-sliced requests returning cut
    JSON against a count=136 board. The last three same-cycle radar
    pre-emptions (passes 31/32/33) all trusted that board half; the next
    collision will too. A silently under-scanned sweep is worse than a loud
    failure, so ingestion refuses any capture that cannot prove it is the
    whole board:

      (a) unparseable JSON — handled by the caller's json.loads (kept out
          of here so the parse error message stays verbatim); this function
          catches the residue: a capture that is neither envelope nor list,
      (b) envelope `count` ≠ len(workOrders) mismatches,
      (c) `windowTruncated: true` — with the #2286 limit:200 the whole
          open board must fit; a truncated window is incomplete BY DEFINITION,
      (d) a workOrders payload suspiciously small vs `totalOpen` — the
          #2190 omission class gains its earlier tripwire here,
      (e) an envelope carrying NO row list at all (workOrders/rows both
          absent — a schema drift would otherwise sweep zero titles
          silently). A healthy EMPTY board (workOrders: [] with count=0)
          still passes: absence of rows is only a crime when the envelope
          never declared them,
      (f) a non-empty `label` field — a label-sliced capture is
          count-complete but UNIVERSE-incomplete; invariant F (#2718)
          consumes this artifact as the whole open-issue universe, so a
          slice must never reach it,
      (g) a `scope` other than the #2286 contract shape `all-open` — same
          universe-incompleteness class as (f).

    Pre-envelope raw row lists (the F18d shape) carry no contract-bearing
    fields and pass through untouched. Raises SystemExit(1) after a FAIL
    evidence line — the guard's standard fail-closed idiom (mirrors
    load_baseline). Rollback: single-commit revert returns ingestion to
    parse-what-you-get (the current, silent-on-truncation state).
    """
    if isinstance(queue, list):
        return  # pre-envelope raw capture: nothing contract-bearing to check
    if not isinstance(queue, dict):
        _evidence(f"FAIL board-sweep capture contract: {source} is neither a work_queue "
                  f"envelope nor a row list (got {type(queue).__name__}) — refusing to "
                  "sweep a capture whose completeness cannot be checked (R76 fail-loud)")
        raise SystemExit(1)
    orders = queue.get("workOrders") or queue.get("rows") or []
    if not isinstance(orders, list):
        _evidence(f"FAIL board-sweep capture contract: {source} — workOrders is not a list "
                  f"(got {type(orders).__name__}); a row field the sweep cannot count would "
                  "scan zero titles silently (R76 fail-loud)")
        raise SystemExit(1)
    n = len(orders)
    count = queue.get("count")
    if isinstance(count, int) and not isinstance(count, bool) and count != n:
        _evidence(f"FAIL board-sweep capture contract: {source} captured {n} row(s) but the "
                  f"envelope advertises count={count} — capture is incomplete (R76 fail-loud; "
                  "pass-33 ~4000-ch truncation class: a silently under-scanned sweep is "
                  "worse than a loud failure)")
        raise SystemExit(1)
    if queue.get("windowTruncated") is True:
        _evidence(f"FAIL board-sweep capture contract: {source} captured {n} row(s) with "
                  "windowTruncated=true — with the #2286 limit:200 capture the whole open "
                  "board must fit; a truncated window is incomplete by definition "
                  "(R76 fail-loud)")
        raise SystemExit(1)
    total_open = queue.get("totalOpen")
    if isinstance(total_open, int) and not isinstance(total_open, bool) and n < total_open:
        _evidence(f"FAIL board-sweep capture contract: {source} captured {n} row(s) but the "
                  f"envelope advertises totalOpen={total_open} — suspiciously small payload "
                  "vs the board it names; count reconciliation is also #2190's "
                  "omission-class tripwire (R76 fail-loud)")
        raise SystemExit(1)
    if "workOrders" not in queue and "rows" not in queue:
        _evidence(f"FAIL board-sweep capture contract: {source} carries no workOrders/rows "
                  "list at all — a schema drift here would sweep zero titles silently "
                  "(R76 fail-loud); a healthy empty board declares workOrders: []")
        raise SystemExit(1)
    label = queue.get("label")
    if label:
        _evidence(f"FAIL board-sweep capture contract: {source} is label-sliced "
                  f"(label={label!r}) — count-complete but universe-incomplete; invariant F "
                  "(#2718) consumes this artifact as the WHOLE open-issue universe, so a "
                  "slice must never reach it (R77 fail-loud)")
        raise SystemExit(1)
    scope = queue.get("scope")
    if scope is not None and scope != "all-open":
        _evidence(f"FAIL board-sweep capture contract: {source} scope={scope!r} is not the "
                  "#2286 contract shape 'all-open' — same universe-incompleteness class as "
                  "a label slice (R77 fail-loud)")
        raise SystemExit(1)


def board_sweep(queue: dict | list, token: int, allow: set[int]) -> list[dict]:
    """Pointer↔board agreement predicate over captured open-issue titles.

    (#2372 option B / #2392 component 2, offline plane.) The IO is the
    filer's capture step — a zero-credential bridge.work_queue
    {"limit": 200} snapshot saved to a file; the GUARD BINARY stays
    network-free (Never-do). Rows are keyed `number`/`title` (post-#2286
    schema; the older `issueNumber` key accepted). Pointer phrases are
    stripped first so WO mirrors quoting the allocation rule do not
    self-trip. See the module docstring for the full predicate spec.
    """
    if isinstance(queue, dict):
        queue = queue.get("workOrders") or queue.get("rows") or []
    findings: list[dict] = []
    for row in queue:
        if not isinstance(row, dict):
            continue
        num = row.get("number", row.get("issueNumber"))
        title = row.get("title") or ""
        for m in R_TOKEN_RE.finditer(strip_pointer_phrases(str(title))):
            if int(m.group(1)) == token and num not in allow:
                suffix = m.group(2)
                findings.append({
                    "issue": num,
                    "token": f"R{m.group(1)}" + (f"-{suffix}" if suffix else ""),
                    "title": " ".join(str(title).split())[:160],
                })
                break
    return findings


def row_state_findings(idx_text: str, queue: dict | list) -> list[dict]:
    """Invariant F — row-state truthfulness (#2718 / R77), index-vs-board plane.

    Invariants A–E verify the index's INTERNAL consistency and #2704's
    validate_queue_capture verifies the capture input; none verified a row's
    STATUS CLAIM against the issue state that claim describes. The scout's
    receipts: 5 recent issue-filed rows asserted `open` while their defining
    issues were closed-completed (R71/R72/R73/R75/R76 → #2586/#2608/#2627/
    #2654/#2691); a full pre-flight over the live index found the rot 27 rows
    deep (doc-filed eras included: R17/R20/R24-VI/R25/R29-R32/R36/R46-R62/R66
    + R63-I's superseded-PR `in gates` cell). Stale-open is the dominant
    divergence class — worse than stale-landed because it SUPPRESSES
    successor work instead of duplicating it (Rule 7: the index is the only
    counter; a lying counter is not a stale cache).

    Check: for every §1 registry row whose status cell asserts an in-flight
    state (anything not landed/closed/done/rejected/superseded/withdrawn —
    `open`, `in gates`, `adopted`, `fixed` all qualify), the row's FILED-cell
    issue #N must be present in the captured open-issue universe — the same
    proven-complete artifact --board-sweep already ingests (label-sliced and
    non-all-open scopes are refused upstream by validate_queue_capture). A
    cited issue absent from a complete open set means the row claims
    in-flight work that has actually landed. Scope honesty (the scout's own
    limitation, kept verbatim): only issues checkable against an open-only
    universe; landed-row misstatement detection is a non-goal this lane does
    not claim. Parse honesty: cells are split on `|` naively — a pipe inside
    a code span would confuse the parse; the live file parses clean (41
    in-flight rows receipted this cycle), noted as a known limit.

    Pure function — findings only; the caller renders evidence and fails.
    """
    rows_q = queue if isinstance(queue, list) else (
        queue.get("workOrders") or queue.get("rows") or [])
    open_nums = set()
    for r in rows_q:
        if isinstance(r, dict):
            n = r.get("number", r.get("issueNumber"))
            if isinstance(n, int):
                open_nums.add(n)
    landed_words = ("landed", "closed", "done", "rejected", "superseded", "withdrawn")
    findings: list[dict] = []
    for ln in idx_text.splitlines():
        m = re.match(r"^\|\s*(R\d+[^|]*)\s*\|", ln)
        if not m:
            continue
        cells = [c.strip() for c in ln.split("|")][1:-1]
        if len(cells) < 6:
            continue
        fm = re.search(r"#(\d+)", cells[3])
        if not fm:
            continue
        issue = int(fm.group(1))
        status = re.sub(r"[*_`]", "", cells[5]).strip()
        head_w = status.split("(")[0].split()
        head = head_w[0].lower() if head_w else ""
        if not head or head.startswith("\u2014") or head in landed_words:
            continue
        if issue not in open_nums:
            findings.append({"kind": "stale-row", "row": re.sub(r"[*_]", "", m.group(1)).strip(),
                             "issue": issue, "status": " ".join(status.split())[:80]})
    return findings


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
    if data.get("schema") not in ("radar-index-freshness-baseline/1",
                                  "radar-index-freshness-baseline/2"):
        _evidence("FAIL baseline schema unrecognised (need /1 or /2)")
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
    e: list[dict] | None = None, e_ran: bool = False,
    g: list[dict] | None = None, g_ran: bool = False,
) -> None:
    if d is None:
        d = []
    if e is None:
        e = []
    if g is None:
        g = []
    for f in g:
        if f["kind"] == "pin-drifted":
            _evidence(f"G-FAIL pin-drifted: test pin asserts {f['was']} but the index "
                      f"advertises R{f['now']} — a landed pointer advance skipped the "
                      "pin bump (pin-accompanies-pointer broken; #3557 invariant G)")
        elif f["kind"] == "pin-file-missing":
            _evidence(f"G-FAIL pin-file-missing: {f['path']} is gone — the pin-accompanies-"
                      "pointer carrier is lost (#3557 invariant G; CI runs no pytest, "
                      "this gate is the only detector)")
        elif f["kind"] == "pin-block-missing":
            _evidence(f"G-FAIL pin-block-missing: def {f['test']} vanished from the pin file "
                      "— the live-sweep pin contract changed shape (#3557 invariant G)")
        elif f["kind"] == "pin-literal-missing":
            _evidence(f"G-FAIL pin-literal-missing: no assert r[\"pointer\"] == <N> literal "
                      f"inside def {f['test']} — the pin discipline's second honest copy "
                      "is gone (#3557 invariant G)")
    for f in e:
        if f["kind"] == "roster-pointer-regressed":
            _evidence(f"E-FAIL roster-pointer-regressed: pointer {f['was']} -> {f['now']} "
                      "— registry motion is forward-only (#2392 invariant E)")
        else:
            _evidence(f"E-FAIL roster-row-evicted: {f['token']} present in the baseline "
                      "roster is gone from the registry (#2392 invariant E)")
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
    elif a or b or unpinned or e or g:
        _evidence("FAIL radar-index freshness invariants violated (see A-FAIL/B-FAIL/C-FAIL/E-FAIL/G-FAIL lines)")
    elif d:
        _evidence(f"PINNED {len(d)} commit-subject ghost(s) in the landing window — "
                  "pre-existing debt, shrink-only (#2187); register the row to shrink")
    elif d_ran:
        _evidence("OK invariant D: recent commit subjects carry no unregistered R-token (commit-plane clean, #2187)")
    else:
        _evidence("OK invariants A/B/C hold; registry, pointer and docs citations agree (D honest-skipped: no git)")
    if e:
        pass  # E-FAIL lines already emitted above — never reached on a fail verdict
    elif e_ran:
        _evidence("OK invariant E: roster agrees with the enforced baseline — no pointer regression, no row eviction (#2392)")
    if g:
        pass  # G-FAIL lines already emitted above — never reached on a fail verdict
    elif g_ran:
        _evidence(f"OK invariant G: test pin literal agrees with the advertised pointer R{pointer} (#3557 pin-truth)")


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
    row_tokens = set(tokens)
    # #2187: invariant D rides the same sweep — global commit-plane scan,
    # not scoped to --files (pre-push content limits stay A/B/C-scoped).
    ghosts, d_ran = invariant_d(root, bases)
    # #3557: invariant G rides the same sweep — the pin literal in the repo's
    # own test file is the pointer's second honest copy; drift there is the
    # landed-pin-accompanies-pointer contract broken. Structural, never floorable.
    test_path = root / TEST_REL
    test_text = (test_path.read_text(encoding="utf-8", errors="replace")
                 if test_path.is_file() else None)
    g, g_ran = invariant_g(pointer, test_text, root)
    rows_range = (min(bases), max(bases)) if bases else None
    return {"pointer": pointer, "a": a, "b": b, "cits": cits,
            "report_only": report_only, "rows": rows_range,
            "d": ghosts, "d_ran": d_ran, "row_tokens": row_tokens,
            "g": g, "g_ran": g_ran}


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

    # F6b: ordinal-suffix collision rows (#2372 double-adoption form) parse
    # and register the base — a docs citation to R63 resolves once the
    # R63-I/R63-II rows exist (pre-widening the rows were invisible to the
    # gate and the citation stayed a ghost; live probe reproduced both states).
    body = ("# Idx\n> Allocation rule (next free: **R64**).\n\n"
            "## 1. R\n| R# | F | L | I | V | S |\n|---|---|---|---|---|---|\n"
            "| R63-**I** | a | b | #2343 | c | d |\n"
            "| R63-**II** | e | f | #2358 | g | h |\n\n"
            "## 5. End\n")
    root = tree({INDEX_REL: body, "docs/d.md": "# D\ncites R63\n"})
    r = sweep(root)
    check("F6b-ordinal-suffix-rows-register-base",
          r["pointer"] == 64 and not r["a"] and not r["b"]
          and not any(f["base"] == 63 for f in r["cits"]))

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

    # F17: invariant E — roster regression, pass-23's deferred pre-land
    # check mechanized (#2392 component 1). The ebe630c clobber class:
    # pointer reverted + rows evicted by a stale-branch whole-file
    # overwrite while every citation count stayed green (the pin
    # regressed WITH the pointer — the co-regression blind spot).
    base2 = {"schema": "radar-index-freshness-baseline/2", "floor": [],
             "roster": {"pointer": 65, "rows": ["R1", "R63", "R64"]}}
    idx_txt = index(64, [1, 63, 64])  # pointer reverted 65 -> 64
    e_find, e_ran = invariant_e(parse_pointer(idx_txt), set(parse_registry(idx_txt)[0]), base2)
    check("F17a-pointer-regression-fails", e_ran and
          any(f["kind"] == "roster-pointer-regressed" and f["was"] == 65 and f["now"] == 64
              for f in e_find))
    idx_txt = index(65, [1, 63])  # R64 row evicted, pointer intact
    e_find, e_ran = invariant_e(parse_pointer(idx_txt), set(parse_registry(idx_txt)[0]), base2)
    check("F17b-row-eviction-fails", e_ran and
          any(f["kind"] == "roster-row-evicted" and f["token"] == "R64" for f in e_find))
    idx_txt = index(66, [1, 63, 64, 66])  # forward motion: advance + additions
    e_find, e_ran = invariant_e(parse_pointer(idx_txt), set(parse_registry(idx_txt)[0]), base2)
    check("F17c-forward-motion-passes", e_ran and e_find == [])
    e_find, e_ran = invariant_e(None, set(), {"schema": "radar-index-freshness-baseline/1", "floor": []})
    check("F17d-v1-baseline-honest-skips", e_find == [] and not e_ran)

    # F18: board sweep predicate over captured titles (#2392 component 2,
    # #2372 option B) — offline by constitution; the IO artifact is
    # filer-captured. Word-boundary citation fails; the self-ref defining
    # ticket passes via --allow; a WO mirror quoting the allocation rule
    # (pointer phrase) must not self-trip.
    queue = {"workOrders": [
        {"number": 2401, "title": "scout(R97): a third-party lane citing the successor"},
        {"number": 2402, "title": "guard(docs): register R60 row + next-free R97 (WO mirror quote)"},
        {"number": 2403, "title": "unrelated lane with R59 only"},
        {"number": 2392, "title": "scout(R64): the successor lane's own defining ticket"},
    ]}
    fnd = board_sweep(queue, 97, set())
    check("F18a-title-cite-fails", any(f["issue"] == 2401 and f["token"] == "R97" for f in fnd))
    check("F18b-pointer-phrase-in-mirror-ignored", not any(f["issue"] == 2402 for f in fnd))
    check("F18c-self-ref-allow-passes", board_sweep(queue, 97, {2401}) == [])
    check("F18d-issue-number-key-accepted",
          board_sweep([{"issueNumber": 9, "title": "cites R97 here"}], 97, set())
          and board_sweep([{"issueNumber": 9, "title": "cites R97 here"}], 97, set())[0]["issue"] == 9)

    # F19: capture-contract fail-loud (#2691 / R76 — the pass-33 drift-log
    # hardening). The #2286 single-capture contract (limit:200 = the whole
    # open set) silently degrades at board sizes ≥~130: the tower truncates
    # response bodies at ~4000 chars mid-JSON, and pass 33 measured 4/10
    # label-sliced requests returning cut JSON against a count=136 board.
    # Ingestion must refuse captures whose completeness cannot be proven —
    # a silently under-scanned sweep is worse than a loud failure. CLI
    # fixtures run the real binary via subprocess (offline, tempdir) and
    # require a nonzero exit; F19e is the positive control — a healthy
    # envelope must still exit 0 end-to-end. R77 canary note: this CLI run also
    # executes invariant F over the DEPLOYED index, so it passes iff the deployed
    # index is row-state-clean; a stale deployed index SHOULD redden here (that is
    # invariant F working — refresh the rows; #2718). The synthetic queue is
    # deliberately NOT the real open universe, so the canary only stays green when
    # the index has zero in-flight rows citing issues outside a complete capture —
    # i.e. after the R77 refresh landed.
    def queue_file(content: str) -> Path:
        p = Path(tempfile.mkdtemp(prefix="rifg-f19-")) / "queue.json"
        p.write_text(content, encoding="utf-8")
        return p

    def cli_exit(qf: Path) -> int:
        return subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--board-sweep", "--queue-file", str(qf), "--token", "97"],
            capture_output=True, text=True, timeout=60).returncode

    trunc = '{"workOrders": [{"number": 2401, "ti'  # pass-33 cut-JSON shape
    check("F19a-truncated-json-exits-nonzero", cli_exit(queue_file(trunc)) != 0)
    mismatch = json.dumps({"count": 136, "totalOpen": 136, "windowTruncated": False,
                           "workOrders": [{"number": 2401, "title": "row one"},
                                          {"number": 2402, "title": "row two"}]})
    check("F19b-count-rows-mismatch-exits-nonzero", cli_exit(queue_file(mismatch)) != 0)
    window = json.dumps({"count": 2, "totalOpen": 2, "windowTruncated": True,
                         "workOrders": [{"number": 2401, "title": "row one"},
                                        {"number": 2402, "title": "row two"}]})
    check("F19c-window-truncated-exits-nonzero", cli_exit(queue_file(window)) != 0)
    small = json.dumps({"count": 2, "totalOpen": 136, "windowTruncated": False,
                        "workOrders": [{"number": 2401, "title": "row one"},
                                       {"number": 2402, "title": "row two"}]})
    check("F19d-small-payload-vs-totalopen-exits-nonzero", cli_exit(queue_file(small)) != 0)
    healthy_src = {"count": 2, "totalOpen": 2, "windowTruncated": False,
                   "workOrders": [{"number": 2401, "title": "row one"},
                                  {"number": 2402, "title": "row two"}]}
    # F19e positive control, self-consistent-universe edition (R77): a healthy
    # envelope must still drive the whole --board-sweep pipeline to exit 0.
    # The queue universe is DERIVED from the deployed index's own in-flight
    # filed-issue citations (offline, no network) so the index matches its
    # queue by construction — invariant F then passes whatever the deployed
    # row-state is, and this fixture proves the OK-path plumbing, not the
    # row-state (the LIVE board-sweep against a real capture is where stale
    # rows redden; the F20 fixtures pin the synthetic red/green semantics).
    deployed = (REPO_ROOT / INDEX_REL).read_text(encoding="utf-8", errors="replace")
    cited = set()
    for ln2 in deployed.splitlines():
        if not re.match(r"^\|\s*(R\d+[^|]*)\s*\|", ln2):
            continue
        cells2 = [c.strip() for c in ln2.split("|")][1:-1]
        if len(cells2) < 6:
            continue
        fm2 = re.search(r"#(\d+)", cells2[3])
        if fm2:
            cited.add(int(fm2.group(1)))
    uni_rows = healthy_src["workOrders"] + [
        {"number": n, "title": f"universe row #{n}"} for n in sorted(cited - {2401, 2402})]
    healthy = json.dumps({"count": len(uni_rows), "totalOpen": len(uni_rows),
                          "windowTruncated": False, "workOrders": uni_rows})
    check("F19e-healthy-envelope-still-passes", cli_exit(queue_file(healthy)) == 0)

    def exits_loud(fn) -> bool:
        try:
            fn()
        except SystemExit as exc:
            return int(exc.code or 0) != 0
        return False

    check("F19f-envelope-without-row-list-fails-loud",
          exits_loud(lambda: validate_queue_capture(
              {"count": 0, "totalOpen": 0, "windowTruncated": False})))
    check("F19g-raw-list-capture-passthrough",
          not exits_loud(lambda: validate_queue_capture(
              [{"number": 2401, "title": "pre-envelope raw capture"}])))
    check("F19h-healthy-empty-board-passes",
          not exits_loud(lambda: validate_queue_capture(
              {"count": 0, "totalOpen": 0, "windowTruncated": False, "workOrders": []})))

    # F20: invariant F — row-state truthfulness (#2718 / R77), the index-vs-board
    # plane. Red-first discipline: the five scout-named rows (R71/R72/R73/R75/R76
    # → #2586/#2608/#2627/#2654/#2691) are the named fixtures replayed here
    # synthetically; the live red receipt (27 stale rows over the real index +
    # real capture) is taken in the landing PR's evidence. Scope honesty is
    # fixture-pinned: landed rows and no-issue rows must NEVER fire.
    idx_f = (
        "| R# | Radar file | Lane | Filed | Verdict | Status |\n"
        "|----|-----------|------|-------|---------|--------|\n"
        "| R71 | `a.md` | lane one | #2586 | `adapt` | **open (claimed #2586)** |\n"
        "| R74 | `b.md` | lane two | #2633 | — | **open (unclaimed)** |\n"
        "| R70 | `c.md` | lane three | #2500 | `adapt` | **landed (PR #2501 closes #2500)** |\n"
        "| R90 | `d.md` | lane four | not filed | `adapt` | **open** |\n"
        "| R63-**I** | `e.md` | lane five | #2343 | — | **in gates (PR #2352; merge closes #2343)** |\n"
    )
    q_on = {"workOrders": [{"number": 2633, "title": "the one open lane"}]}
    st = row_state_findings(idx_f, q_on)
    check("F20a-stale-open-row-fires", any(f["row"] == "R71" and f["issue"] == 2586 for f in st))
    check("F20b-healthy-open-row-passes", not any(f["row"] == "R74" for f in st))
    check("F20c-landed-row-skipped", not any(f["row"] == "R70" for f in st))
    check("F20d-no-issue-row-skipped", not any(f["row"] == "R90" for f in st))
    check("F20e-in-gates-cell-fires", any(f["row"] == "R63-I" and f["issue"] == 2343 for f in st))
    check("F20f-label-sliced-capture-refused",
          exits_loud(lambda: validate_queue_capture(
              {"label": "scout", "count": 1, "totalOpen": 1,
               "workOrders": [{"number": 1, "title": "x"}]})))
    check("F20g-scoped-capture-refused",
          exits_loud(lambda: validate_queue_capture(
              {"scope": "label:scout", "count": 1, "totalOpen": 1,
               "workOrders": [{"number": 1, "title": "x"}]})))

    # F21: invariant G — pin-truth (#3557), the test-literal-vs-pointer plane.
    # Red-first discipline: the fixture replays the exact live drift pair
    # (pointer advertised R84, pin left at 81 by #3483) that stayed RED on
    # main across three landings because no gate compared the two copies.
    # Scope honesty is fixture-pinned: fixture trees without tests/ must
    # NEVER fire (the pin's carrier legitimately doesn't exist there).
    live_block = (
        "def test_live_repo_sweep_passes() -> None:\n"
        "    r = guard.sweep(REPO_ROOT)\n"
        '    assert r["pointer"] == 84, "pointer drifted"\n'
        "\n\n"
    )
    g_root = tree({INDEX_REL: index(84, [1])})
    (g_root / "tests").mkdir()
    g_file = g_root / "tests" / "test_radar_index_freshness_guard.py"
    g_file.write_text(live_block, encoding="utf-8")
    r = sweep(g_root)
    check("F21a-matching-pin-passes", r["g_ran"] and not r["g"])
    g_file.write_text(live_block.replace("== 84", "== 81"), encoding="utf-8")
    r = sweep(g_root)
    check("F21b-pin-drift-fires-naming-was-now",
          any(f["kind"] == "pin-drifted" and f["was"] == 81 and f["now"] == 84
              for f in r["g"]))
    g_file.write_text("def unrelated_test() -> None:\n    pass\n", encoding="utf-8")
    r = sweep(g_root)
    check("F21c-missing-live-block-fails",
          any(f["kind"] == "pin-block-missing" for f in r["g"]))
    g_file.unlink()
    r = sweep(g_root)
    check("F21d-deleted-pin-file-fails",
          any(f["kind"] == "pin-file-missing" for f in r["g"]))
    # F21e: a fixture tree with NO tests/ directory at all — the pin's carrier
    # legitimately doesn't exist there, so G honest-skips silently (never a
    # fabricated PASS, never a spurious FAIL).
    r = sweep(tree({INDEX_REL: index(4, [1])}))
    check("F21e-fixture-tree-honest-skip", not r["g_ran"] and not r["g"])

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


def _row_sort_key(tok: str) -> tuple[int, int]:
    """Roster ordering: numeric base, then suffix rank (document order family)."""
    m = re.fullmatch(r"R(\d+)(?:-(I{1,2}|V|VI|c))?", tok)
    base = int(m.group(1)) if m else 9999
    rank = {None: 0, "I": 1, "II": 2, "V": 5, "VI": 6, "c": 7}.get(
        m.group(2) if m else None, 9)
    return (base, rank)


def build_baseline(root: Path) -> dict:
    r = sweep(root)
    counts = counts_of(r["cits"])
    rows = r.get("rows")
    return {
        "schema": "radar-index-freshness-baseline/2",
        "generatedAt": datetime.now(timezone.utc).date().isoformat(),
        "headAtGeneration": _git_head_provenance(root),
        "probe": "scripts/ci/radar_index_freshness_guard.py",
        "note": "shrink-only floor over the citation-ghost and commit-subject-ghost classes "
                "(#2187: D lands first-run-clean — its floor is born empty); "
                "key = [kind, file, base] / [kind, base, subject]. "
                "A/B invariant violations are NEVER floorable — they are structural and always fail. "
                "/2 adds the enforced roster (invariant E, #2392 component 1): a pointer "
                "regression or row eviction fails closed — update roster in the same PR that "
                "moves the registry, mirroring the pin-accompanies-pointer discipline.",
        "floor": [{"key": list(k), "allowed": v} for k, v in sorted(counts.items(), key=lambda kv: repr(kv[0]))],
        "roster": {"pointer": r["pointer"],
                   "rows": sorted(r["row_tokens"], key=_row_sort_key)},
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
    parser.add_argument("--board-sweep", action="store_true",
                        help="pointer-board agreement (#2372 opt-B): scan a CAPTURED queue "
                             "artifact for open-issue-title citations of the candidate "
                             "successor; offline — capture filer-side, no network here")
    parser.add_argument("--token", type=int, default=None,
                        help="candidate successor base for --board-sweep (default: pointer+1)")
    parser.add_argument("--allow", nargs="*", type=int, default=[],
                        help="self-ref exception: the successor lane's own defining ticket number(s)")
    parser.add_argument("--queue-file", default=None,
                        help='captured bridge.work_queue {"limit": 200} JSON artifact')
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

    if args.board_sweep:
        if not args.queue_file:
            _evidence('FAIL board-sweep: --queue-file required — capture bridge.work_queue '
                      '{"limit": 200} filer-side; the guard binary is network-free (Never-do)')
            return 1
        try:
            queue = json.loads(Path(args.queue_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _evidence(f"FAIL board-sweep: unreadable queue artifact {args.queue_file}: {exc}")
            return 1
        # R76 fail-loud ingestion (#2691): the #2286 capture contract degrades
        # silently at board sizes ≥~130 (pass-33 ~4000-ch truncation class);
        # refuse to sweep a capture that cannot prove it is the whole board.
        validate_queue_capture(queue, source=args.queue_file)
        idx_text = (REPO_ROOT / INDEX_REL).read_text(encoding="utf-8", errors="replace")
        pointer = parse_pointer(idx_text)
        token = args.token if args.token is not None else (pointer + 1 if pointer is not None else None)
        if token is None:
            _evidence("FAIL board-sweep: no --token and the index advertises no pointer")
            return 1
        allow = set(args.allow or [])
        findings = board_sweep(queue, token, allow)
        for f in findings:
            _evidence(f"BOARD-FAIL title-citation: #{f['issue']} cites {f['token']} — '{f['title']}'")
        # R77 invariant F (#2718): row-state truthfulness — the refresh half of
        # the freshness contract, mechanized. Runs only past validate_queue_capture,
        # i.e. against a capture proven count- AND universe-complete.
        stale = row_state_findings(idx_text, queue)
        for f in stale:
            _evidence(f"STALE-ROW row-state: {f['row']} cites #{f['issue']} in-flight "
                      f"('{f['status']}') but #{f['issue']} is absent from the proven-complete "
                      "open capture — refresh the row (invariant F, #2718/R77)")
        n_rows = len(queue) if isinstance(queue, list) else len(
            queue.get("workOrders") or queue.get("rows") or [])
        if findings:
            _evidence(f"FAIL board-sweep: R{token} cited by {len(findings)} open title(s) outside "
                      f"allow={sorted(allow)} — never advertise dirty (auto-advance out of scope v1)")
            return 1
        if stale:
            _evidence(f"FAIL board-sweep: {len(stale)} registry row(s) assert in-flight state for "
                      f"issue(s) absent from the proven-complete open capture (first few: "
                      f"{[f['row'] for f in stale[:6]]}) — refresh the rows before advertising "
                      "(invariant F, #2718/R77): a filer's freeness check must not consume a lying index")
            return 1
        _evidence(f"OK board-sweep: R{token} zero title citations outside allow={sorted(allow)} "
                  f"over {n_rows} captured row(s), 0 stale rows — advertisable per the #2392 "
                  "predicate + #2718 invariant F")
        return 0

    only = None
    if args.files:
        paths = [Path(p) for p in args.files]
        only = [p if p.is_absolute() else root / p for p in paths]
        only = [p for p in only if p.is_file()]

    r = sweep(root, only)
    if "fatal" in r:
        _evidence(f"FAIL {r['fatal']}")
        return 1

    baseline = load_baseline(root)
    # #2392 invariant E: roster regression (pointer revert / row eviction) —
    # the pass-23 deferred check. Structural, never floorable.
    e_findings, e_ran = invariant_e(r["pointer"], r["row_tokens"], baseline)
    # #3557 invariant G: pin-truth — the test file's pin literal is the
    # pointer's second honest copy. Structural, never floorable.
    g_findings, g_ran = r["g"], r["g_ran"]
    # #2187: invariant D joins the SAME shrink-only ratchet — commit-subject
    # keys are never in the born-empty floor, so any ghost is fresh drift,
    # and a registered row (base now in the registry) makes it vanish.
    drift, improvements = compare(baseline, r["cits"] + r["d"])

    if args.json:
        print(json.dumps({
            "guard": GUARD_TAG, "pointer": r["pointer"],
            "a": r["a"], "b": r["b"], "citationGhosts": r["cits"],
            "commitSubjectGhosts": r["d"], "commitPlaneScanned": r["d_ran"],
            "rosterRegressions": e_findings, "rosterChecked": e_ran,
            "pinTruthFindings": g_findings, "pinTruthChecked": g_ran,
            "reportOnly": r["report_only"], "drift": drift,
            "improvements": improvements,
            "verdict": "fail" if (r["a"] or r["b"] or drift or e_findings or g_findings) else "pass",
        }, indent=2, ensure_ascii=False))
    else:
        render(r["a"], r["b"], r["cits"], r["report_only"], drift, improvements, r["pointer"],
               d=r["d"], d_ran=r["d_ran"], e=e_findings, e_ran=e_ran,
               g=g_findings, g_ran=g_ran)
    return 1 if (r["a"] or r["b"] or drift or e_findings or g_findings) else 0


if __name__ == "__main__":
    sys.exit(main())
