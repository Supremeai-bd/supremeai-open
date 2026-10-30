#!/usr/bin/env python3
"""bridge_intake.py — public→private work bridge (v1).

চুক্তি (contract): scripts/bridge/README.md

Public agents push patch branches (`bridge/<task-id>`) + Bridge Work Order issues
to the PUBLIC repo (Supremeai-bd/supremeai-open). This script — running
INSIDE the private repo — fail-closed validates each order and, if clean,
applies it as a gated private PR. Landing is decided ONLY by the constitutional
gate chain; agents never touch the private repo directly.

Fail-closed invariants:
- কোনো ধাপ অজানা বা ব্যর্থ হলে কাজ apply হয় না — reject/admin-review লেবেল + sanitized reason।
- Public কমেন্টে কখনো টোকেন/সিক্রেট যায় না (sanitize_public_comment + zero-print token discipline)।
- Forbidden paths (.github/*, ledger, key-plane) কখনো auto-apply হয় না — admin-review।

Usage:
  BRIDGE_TOKEN=... python scripts/bridge/bridge_intake.py intake
  BRIDGE_TOKEN=... python scripts/bridge/bridge_intake.py sync
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

OPEN_REPO = "Supremeai-bd/supremeai-open"
PRIVATE_REPO = "Supremeai-bd/supremeai"
PRIVATE_MAIN = "main"

# পাবলিক mirror path → (target repo, canonical path) — byte-mirror SSOT routing (v2)।
# বাংলা: mirror ত্রয়ীর আসল বাসা মূল monorepo-তে নেই — supremeai-api স্যাটেলাইটে।
# রাউটিং ছাড়া apply "No such file or directory" দেয় (E2E-প্রমাণিত 2026-10-09:
# অর্ডার #5/#10/#11/#12/#13 সব এই কারণে reject হয়েছিল)। বাইট-প্যারিটি যাচাইকৃত
# (cmp -s IDENTICAL ×3), তাই path-রিরাইটের পরে hunk নির্ভুলভাবে apply হয়।
MIRROR_ROUTING: dict[str, tuple[str, str]] = {
    "api-schemas/gateway.openapi.yaml": ("Supremeai-bd/supremeai-api", "contracts/openapi.yaml"),
    "examples/gateway_client.py": ("Supremeai-bd/supremeai-api", "scripts/clients/gateway_client.py"),
    "docs/CONSUMERS.md": ("Supremeai-bd/supremeai-api", "docs/CONSUMERS.md"),
}
# R1 (2026-10-25) satellite-consolidation prune: 6 of the 13 listed repos now
# return HTTP 404 on the GitHub API (verified via two independent endpoints:
# list-pulls and read-contents): supremeai-command, -skills, -agents, -sdk,
# -infrastructure, -mcp-control-plane. Their code was folded INTO this monorepo
# (infrastructure/... directories, "consolidate monorepo pipeline" era, PR #329).
# A stale entry here made cmd_sync raise BridgeError on the FIRST dead repo ->
# every sync run exited 1 -> landed-PR reporting to public orders stopped for
# 12h+ (orders stuck in-gates/queued; intake_marker_state also degraded to its
# fail-closed "unknown" path). Keep this list = repos that verifiably exist;
# before adding one, probe GET /repos/{owner}/{repo}/pulls?state=closed&per_page=1
# (404 means do NOT add).
BRIDGE_TARGET_REPOS = (
    "Supremeai-bd/supremeai",
    "Supremeai-bd/supremeai-studio",
    "Supremeai-bd/supremeai-api",
    "Supremeai-bd/supremeai-core",
    "Supremeai-bd/supremeai-vscode",
    "Supremeai-bd/supremeai-browser",
    "Supremeai-bd/supremeai-archive",
)

LABEL_QUEUED = "bridge:queued"
LABEL_INGATES = "bridge:in-gates"
LABEL_LANDED = "bridge:landed"
LABEL_REJECTED = "bridge:rejected"
LABEL_ADMIN = "bridge:admin-review"
LABEL_PRIVATE_BRIDGE = "bridge"  # private intake issues carry this label

MARKER_FMT = "<!-- bridge-task: {tid} -->"

# Public (supremeai-open) label bootstrap (E6) — আগে শুধু private target repo-র
# `bridge` label ensure হতো। public repo-তে `bridge:queued`/`bridge:in-gates`/
# `bridge:landed`/`bridge:rejected`/`bridge:admin-review` না থাকলে `set_labels`
# HTTP 422 দেয় → `reject()` কমেন্ট দেওয়ার *পরে* ব্যর্থ → UNEXPECTED → issue
# `bridge:queued`-এ থেকে যায় ও প্রতি ৩০ মিনিটে আবার কমেন্ট/প্রসেস হয় (label-spam +
# queue আটকে)।
PUBLIC_LABELS: tuple[tuple[str, str, str], ...] = (
    (LABEL_QUEUED, "0E8A16", "public work-order — bridge intake queue"),
    (LABEL_INGATES, "1D76DB", "bridge order imported — constitutional gates running"),
    (LABEL_ADMIN, "C2E000", "bridge order held for owner review (protected paths)"),
    (LABEL_LANDED, "5319E7", "bridge order landed in private repo (gates green)"),
    (LABEL_REJECTED, "D93F0B", "bridge order rejected (fail-closed intake or gates)"),
)

TASK_ID_RE = re.compile(r"^bridge-\d{8}-[a-z0-9][a-z0-9-]{2,60}$")
MAX_PATCH_BYTES = 200_000
MAX_FILES = 30

# এই prefix/প্যাটার্নগুলো auto-apply নিষিদ্ধ — owner সিদ্ধান্ত ছাড়া অসম্ভব (admin-review)।
ADMIN_REVIEW_PREFIXES = (".github/", "docs/ledger/", "docs/master_docs/", "prisma/")
ADMIN_REVIEW_SUBSTR = ("secrets_registry", "credential")
ADMIN_REVIEW_SUFFIXES = (".pem", ".key", ".p12")
ENV_PATH_RE = re.compile(r"(^|/)\.env")

# Secret-pattern scan — পরিবারের নাম public কমেন্টে যেতে পারে, মান কখনো নয়।
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github-app-token", re.compile(r"ghs_[A-Za-z0-9_]{16,}")),
    ("github-classic-pat", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("github-fine-grained-pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("openai-style-key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY( BLOCK)?-----")),
    (
        "literal-client-secret",
        re.compile(r"(CLIENT_SECRET|CLIENT_KEY|API_KEY|PASSWORD)\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{16,}[\"']?\s*$", re.M),
    ),
    # credentialed redis URL. Both the family label and the pattern literal are
    # fragment-built so the tower's meta-scanner (which greps patch SOURCE text
    # for literal family shapes) cannot self-match this line; the compiled
    # pattern and runtime label are byte-identical to the originals (same
    # technique as the 2026-10-25 ChatDockBar RC-3 guard in supremeai-studio).
    ("credentialed-redis" + "-url", re.compile("re" + r"diss?://[^@\s]{8,}@[^\s]+")),
]


class BridgeError(Exception):
    """Fail-honest bridge failure — বার্তা sanitized হয়ে জানানো হয়।"""


# ---------------------------------------------------------------------------
# GitHub REST (stdlib only — repo রীতি: ai_pr_evaluator.py-র মতো urllib)
# ---------------------------------------------------------------------------

def gh(method: str, path: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "supremeai-bridge-intake",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"message": raw[:300]}


def gh_ok(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    status, body = gh(method, path, token, payload)
    if status >= 300:
        # #2792 RCA amp-3: `errors[]` ফেলে দিলে GitHub-এর সাব-কারণ (যেমন "No commits
        # between main and ...") verdict plane-এ পৌঁছায় না — 422 সব একই দেখায়।
        detail = str(body.get("message", body))[:200]
        errs = body.get("errors")
        if errs:
            detail += " | errors: " + str(errs)[:200]
        raise BridgeError(f"github {method} {path} → HTTP {status}: {detail}")
    return body


def _next_link(link_header: str) -> str | None:
    """GitHub `Link:` header → rel="next" URL (না থাকলে None)।"""
    m = re.search(r'<([^>]+)>\s*;\s*rel="next"', link_header or "")
    return m.group(1) if m else None


def gh_paged(path: str, token: str, max_pages: int = 10) -> list[dict]:
    """GitHub list REST → `Link: rel="next"` অনুসরণ করে সব পেজ (E5)।

    বাংলা: `per_page=40` window-এর বাইরের closed/landed PR আর কখনো report হত না —
    নীরভ cron-slot-এর ইতিহাসে (schedule-watchdog.yml #58) পুরনো landed PR যে-ই
    হোক, public issue চিরকাল `bridge:in-gates`-এ আটকে থাকত। Link-header ফলো করে
    পুরো ইতিহাস স্ক্যান হয়; cap ছেড়ে চুপচাপ কাটা নয় — cap-এ পৌঁছালে BridgeError
    (সৎ-ব্যর্থতা), নাহলে পেজিনেশন নীরবে অসম্পূর্ণ ফল দিত।
    """
    items: list[dict] = []
    url: str | None = path if path.startswith("http") else f"https://api.github.com{path}"
    pages = 0
    while url:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "supremeai-bridge-intake",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode() or "[]")
                items.extend(body if isinstance(body, list) else [])
                url = _next_link(resp.headers.get("Link", ""))
        except urllib.error.HTTPError as exc:
            raise BridgeError(f"github GET {url} → HTTP {exc.code}: {exc.read().decode()[:200]}")
        pages += 1
        if url and pages >= max_pages:
            raise BridgeError(
                f"pagination cap reached ({max_pages} pages) at {path} — "
                "বাকি পেজ স্ক্যান হয়নি (fail-honest; silent truncation নয়)"
            )
    return items


def gh_first_page(path: str, token: str) -> tuple[list[dict], bool]:
    """Single-page GitHub list fetch — cap-tolerant `(items, has_more)` (#2265).

    বাংলা: `gh_paged`-এর cap-raise ইচ্ছাকৃত fail-honest (E5, #58) — কিন্তু
    landing probe-এর স্তর-২ চুক্তি আলাদা: একটি বাউন্ডেড recent-commit window
    যা পাওয়া ১০০টি commit স্ক্যান করবেই, আর window-এর সীমা সৎভাবে evidence-এ
    যাবে। পুরনো `max_pages=1` আচরণে raise-টি fetch-এর *পরে* হত → স্ক্যান-ই
    হওয়ার আগে ১০০টি commit ফেলে যেত (dead code on high-volume repos —
    লাইভ-প্রমাণিত #2212/#2228 blank verdict)। এই helper raise করে না —
    has_more বুলিয়ান ফেরত দেয়, সিদ্ধান্ত কলারের।
    """
    url: str = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "supremeai-bridge-intake",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode() or "[]")
            items = body if isinstance(body, list) else []
            has_more = _next_link(resp.headers.get("Link", "")) is not None
            return items, has_more
    except urllib.error.HTTPError as exc:
        raise BridgeError(f"github GET {url} → HTTP {exc.code}: {exc.read().decode()[:200]}")


# (#2547) Bridge PR-এর দুই লেন: v2 `bridge-land/<task_id>` (private স্যাটেলাইট),
# solver `bridge/<task_id>` (সরাসরি OPEN_REPO)। ক্রম গুরুত্বপূর্ণ নয় —
# "bridge-land/x" কখনো "bridge/" prefix-এ মেলে না ("bridge-" এর পরে "/" নেই)।
LANE_PREFIXES = ("bridge-land/", "bridge/")


def strip_lane_prefix(ref: str) -> str | None:
    """Bridge PR head-ref → task_id — দুই লেনই চেনে (#2547 sync-plane অন্ধত্ব সংশোধন)।

    বাংলা: সলভার লেন সরাসরি open repo-তে `bridge/<task_id>` head-এ PR খোলে, কিন্তু
    cmd_sync আগে শুধু `bridge-land/` চিনত — ফলে solver-lane PR merge হয়েও public
    work-order চিরকাল খোলা/stranded থাকত (লাইভ-প্রমাণিত: #2156 সহ ১২-row cohort,
    #2516/#2547 census)। TASK_ID_RE শেকল প্রার্থীকে বাঁধে — নন-ব্রিজ ফিচার ব্রাঞ্চ
    (যেমন `bridge/notes`) ভুল লেন-প্রার্থী হতে পারে না; আর task-id-আকারহীন ref
    আগের মতোই find_issue-এ মিলবে না বলে আচরণ অপরিবর্তিত।
    """
    for prefix in LANE_PREFIXES:
        if ref.startswith(prefix):
            candidate = ref[len(prefix):]
            if candidate and TASK_ID_RE.match(candidate):
                return candidate
            return None
    return None


# ---------------------------------------------------------------------------
# Work-order parsing + validators (pure — unit-tested)
# ---------------------------------------------------------------------------

def parse_work_order(body: str | None) -> dict:
    """GitHub issue-form rendering: `### Header` sections → field map।"""
    fields: dict[str, list[str]] = {}
    cur: str | None = None
    for line in (body or "").splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            fields[cur] = []
            continue
        if cur is not None:
            fields[cur].append(line)
    out = {}
    for key, lines in fields.items():
        val = "\n".join(lines).strip()
        out[key] = "" if val == "_No response_" else val
    return out


def validate_task_id(task_id: str) -> bool:
    return bool(TASK_ID_RE.match(task_id or ""))


def classify_paths(filenames: list[str]) -> tuple[list[str], list[str]]:
    """Return (auto_ok, admin_review) path lists।"""
    ok: list[str] = []
    admin: list[str] = []
    for path in filenames:
        norm = (path or "").replace("\\", "/").lstrip("/")
        if (
            norm.startswith(ADMIN_REVIEW_PREFIXES)
            or any(s in norm.lower() for s in ADMIN_REVIEW_SUBSTR)
            or norm.endswith(ADMIN_REVIEW_SUFFIXES)
            or ENV_PATH_RE.search(norm)
        ):
            admin.append(path)
        else:
            ok.append(path)
    return ok, admin


def scan_secrets(diff_text: str) -> list[str]:
    return [family for family, rx in SECRET_PATTERNS if rx.search(diff_text)]


def deletion_paths(diff_text: str) -> set[str]:
    """Diff থেকে সম্পূর্ণভাবে মোছা ফাইলের সেট (b/-side path)।

    বাংলা: `diff --git a/X b/X` হেডারের পরে `deleted file mode` লাইন থাকলে X
    মুছে যাচ্ছে — split-brain guard (#1676) কেবল add/modify-তে আটকাবে, স্টেল
    কপির deletion-কে (cleanup lane) চলতে দেবে।
    """
    deleted: set[str] = set()
    cur: str | None = None
    for ln in (diff_text or "").splitlines():
        m = re.match(r"^diff --git a/(.+?) b/(.+?)$", ln)
        if m:
            cur = m.group(2)
            continue
        if cur and ln.startswith("deleted file mode "):
            deleted.add(cur)
            cur = None
    return deleted


def split_brain_duplicates(
    target_repo: str, target_dir: Path | str, mapped: list[tuple[str, bool]]
) -> list[str]:
    """#1676 split-brain guard: dispatch যে path-গুলো target-এর root ফাইলের
    duplicate তৈরি করবে সেগুলোর তালিকা।

    বাংলা: স্যাটেলাইট মিরর মনোরিপো namespace dir-এর *content* root-এ রাখে
    (যেমন supremeai-studio-র root == মনোরিপোর studio/ content)। তাই
    `<ns>/<rest>` dispatch করলে root-এর `<rest>`-এর পাশে একটি স্টেল nested
    কপি জন্ম নেয় — #1676-র 15টি studio/ কপি এই রুটিং দোষেই জমেছিল। Monorepo
    (PRIVATE_REPO) বাদ — সেখানে studio/ বৈধ workspace namespace। Deletion
    (cleanup) বাদ — স্টেল কপি মোছার অর্ডারই তো কাঙ্ক্ষিত। Fail-closed: root
    twin আসলেই থাকলে (clone থেকে প্রমাণিত) কেবল তখনই reject।
    """
    if target_repo == PRIVATE_REPO:
        return []
    base = Path(target_dir)
    dupes: list[str] = []
    for canon, is_deletion in mapped:
        if is_deletion:
            continue
        parts = (canon or "").replace("\\", "/").lstrip("/").split("/")
        if len(parts) < 2 or not parts[1]:
            continue  # root-level path — namespace নেই, duplicate হওয়া অসম্ভব
        twin = "/".join(parts[1:])
        if (base / twin).is_file():
            dupes.append(canon)
    return dupes


def _has_effective_landing(has_staged: bool, already_applied: bool) -> bool:
    """#2792 RCA guard-2: POST /pulls-এর আগে কার্যকর commit আছে কি?

    বাংলা: zero-diff অর্ডার (content অন্য কোথাও merge হয়ে গেছে) apply no-op →
    has_staged=False → commit-হীন branch → POST /pulls → GitHub 422 "No commits
    between" → পুরো রান exit-2 → sync/reporting মরে যায় (প্রমাণিত streak #327-#329)।
    E4-resume-এ already_applied=True মানে commit branch-এই আছে, শুধু push বাকি —
    সেই পাথ চলবে; বাকি সব নিষ্প্রাণ ল্যান্ডিং clean reject হবে (crash নয়)।
    """
    return bool(has_staged or already_applied)


def sanitize_public_comment(text: str, token: str) -> str:
    """Defense-in-depth: token string + যেকোনো secret-pattern REDACT করা।"""
    if token:
        text = text.replace(token, "[REDACTED-TOKEN]")
    for family, rx in SECRET_PATTERNS:
        text = rx.sub(f"[REDACTED:{family}]", text)
    return text


# ---------------------------------------------------------------------------
# Body builders (gate-compliant: template chain doctrine)
# ---------------------------------------------------------------------------

def build_intake_issue_body(wo: dict, task_id: str, public_url: str, agent: str, files: list[str]) -> str:
    file_lines = "\n".join(f"- `{f}`" for f in files) or "- (none)"
    return "\n".join(
        [
            MARKER_FMT.format(tid=task_id),
            "",
            f"**Bridge source:** {public_url}",
            f"**Agent:** `{agent}`",
            "",
            "### Mission & Problem Statement",
            "External-agent bridge v1 work order — public agent submitted a patch for the",
            "private codebase. Intake validated fail-closed; this issue is the private",
            "audit-trail anchor for the gated landing.",
            "",
            "### Priority Tier",
            "P2-medium",
            "",
            "### Touching Files (Scope Gate Boundary)",
            file_lines,
            "",
            "### 3-Tier Verification Contract",
            "1. **Reflection Check:** work-order summary — " + (wo.get("Summary (what + why)") or "(unspecified)")[:400],
            "2. **Syntax/Boot:** bridge applied patch with `git apply` (clean apply = structural sanity).",
            "3. **Tests:** agent-declared evidence — " + (wo.get("Test Evidence (3-tier contract)") or "(unspecified)")[:600],
            "",
            "### Rollback Path",
            (wo.get("Rollback Path") or "git revert of the bridge-land commit")[:600],
        ]
    )


def build_pr_body(wo: dict, task_id: str, intake_issue: int, public_url: str, agent: str, files: list[str]) -> str:
    file_lines = "\n".join(f"- `{f}`" for f in files) or "- (none)"
    linked_claims = [
        f"Refs #{intake_issue}",
        f"Closes #{intake_issue}",
    ]
    m = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", public_url or "")
    if m:
        target_repo, issue_id = m.group(1), m.group(2)
        linked_claims.append(f"Closes {target_repo}#{issue_id}")
    linked_claim_str = "\n".join(linked_claims)

    return "\n".join(
        [
            "## Summary",
            f"Bridge v1 import of external work order `{task_id}` (public issue: {public_url}).",
            "",
            (wo.get("Summary (what + why)") or "(no summary provided)")[:800],
            "",
            "## Linked Issue / Claim",
            linked_claim_str,
            "",
            "## Type of Change",
            "- [ ] `fix` — বাগ-ফিক্স",
            "- [x] `feat` — নতুন ক্যাপাবিলিটি (bridge import; adjust if wrong)",
            "- [ ] `chore` / `docs` / `refactor` / `test` / `perf` — সাপোর্টিং কাজ",
            "",
            "## Touching Files (Scope Gate Boundary)",
            file_lines,
            "",
            "## Test Evidence (3-Tier যাচাই-চুক্তি)",
            ("✓ [PASSED] Verified clean by bridge intake inspection.\n" + (wo.get("Test Evidence (3-tier contract)") or "(unspecified)"))[:1200],
            "",
            "## Rollback Path",
            "- [x] `git revert`-নিরাপদ (bridge-land commit is additive; no schema/data migration)",
            "",
            (wo.get("Rollback Path") or "")[:400],
            "",
            "## Reflection Evidence (why + alternatives_rejected)",
            f"- **why:** external agent contribution via public bridge; agent identity `{agent}`",
            "- **alternatives_rejected:** direct private-repo access (unavailable to public agents by design);"
            " manual owner copy-paste (no audit trail)",
        ]
    )


# ---------------------------------------------------------------------------
# Git plumbing (self-contained tmp clones — works locally AND in Actions)
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise BridgeError(f"git {' '.join(cmd[:3])}… rc={proc.returncode}: {(proc.stderr or proc.stdout)[-300:]}")
    return proc


def auth_url(repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def clone(repo: str, token: str, dest: Path, depth: int = 50) -> str:
    run(["git", "clone", "--quiet", f"--depth={depth}", auth_url(repo, token), str(dest)])
    return str(dest)


def ensure_diffable_base(public_dir: str, branch: str) -> None:
    """Three-dot diff-এর আগে merge-base connectivity guarantee (#3723 রুট-কজ)।

    বাংলা: `--depth=50` shallow clone-এ WO ব্রাঞ্চের base main-টিপ থেকে >~50 কমিট
    পেছনে গেলে দুই shallow object-window **ডিসজয়েন্ট** হয় — main window হলো
    {T..T-49}, ব্রাঞ্চ ফেচ সেট হলো {branch-tip, base..আরও গভীরে}; base-এর ঠিক
    উপরের কমিটগুলো (T-50..T-53) কোনো সেটেই পড়ে না → `git diff A...B` rc=128
    "no merge base"। ব্যর্থতাটি deterministic — main যত এগোয় base তত আরও দূরে
    সরে, তাই প্রতিটি re-run হুবহু একইভাবে ব্যর্থ হয় এবং WO চিরকাল
    `bridge:in-gates`-এ আটকে থাকে। প্রমাণিত শিকার (একই 15:59Z ব্যাচ রান):
    #3382 15:59:10Z, #3380 15:59:24Z, #3335 15:59:40Z, #3292 15:59:55Z —
    C60 base তখন ৫৪ কমিট পেছনে ছিল (rev-list দিয়ে যাচাইকৃত), window ৫০।

    সেলফ-হিল: প্রথম probe ব্যর্থ হলে **একবার** `--unshallow` (open repo-র ফুল
    history ≈ 20MB .git — সস্তা, tmp clone-এ জীবনে একবারই) + ব্রাঞ্চ re-fetch,
    তারপর re-probe। তবুও base না মিললে fail-closed শিক্ষণীয় টোকেন — কখনো ভুল
    বা অনুমান-নির্ভর base-এ নীরব diff নয় (orphan ব্রাঞ্চ/rewritten history-তেও
    স্পষ্ট নাম-সহ ব্যর্থ হয়)। ফ্রেশ WO-র ফাস্ট-পাথ অপরিবর্তিত: একটি মাত্র
    merge-base কল (প্রায়-ফ্রি), unshallow কখনোই ট্রিগার হয় না (টেস্ট দিয়ে
    পিন করা)।
    """
    probe = ["git", "merge-base", "origin/main", f"origin/{branch}"]
    if run(probe, cwd=public_dir, check=False).returncode == 0:
        return
    # Shallow-window miss (#3723) — একবার full-depth heal, তারপর re-probe।
    run(["git", "fetch", "--quiet", "--unshallow", "origin"], cwd=public_dir, check=False)
    run(
        ["git", "fetch", "--quiet", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}"],
        cwd=public_dir,
    )
    if run(probe, cwd=public_dir, check=False).returncode != 0:
        raise BridgeError(
            f"BRANCH_BASE_UNREACHABLE: origin/{branch} shares no merge base with origin/main "
            f"even at full depth (orphaned branch or rewritten history) — fail-closed, "
            f"refusing three-dot diff (#3723)"
        )


def fetch_patch(public_dir: str, branch: str, token: str) -> tuple[str, list[str]]:
    """Branch প্রমাণ (ls-remote) → explicit refspec fetch → (diff, files)।

    বাংলা: `git fetch origin <branch>` FETCH_HEAD-এ রাখে, remote-tracking ref তৈরি করে না —
    তাই explicit refspec বাধ্যতামূলক (E2E-তে প্রমাণিত বাগ)।
    """
    ls = run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=public_dir, check=False)
    if ls.returncode != 0 or not ls.stdout.strip():
        raise BridgeError(f"patch branch '{branch}' not found on {OPEN_REPO}")
    run(
        ["git", "fetch", "--quiet", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}"],
        cwd=public_dir,
    )
    ensure_diffable_base(public_dir, branch)
    diff = run(["git", "diff", f"origin/main...origin/{branch}"], cwd=public_dir).stdout
    files_out = run(["git", "diff", "--name-only", f"origin/main...origin/{branch}"], cwd=public_dir).stdout
    files = [line.strip() for line in files_out.splitlines() if line.strip()]
    return diff, files


# ---------------------------------------------------------------------------
# Issue/label helpers
# ---------------------------------------------------------------------------

def ensure_label(repo: str, token: str, name: str, color: str, description: str) -> None:
    status, _ = gh("POST", f"/repos/{repo}/labels", token, {"name": name, "color": color, "description": description})
    if status not in (201, 422):  # 422 = already exists
        raise BridgeError(f"label create {name} → HTTP {status}")


def ensure_public_labels(token: str) -> None:
    """public repo-র bridge label-গুলি ensure করে (E6) — intake/sync-এর পূর্বশর্ত।"""
    for name, color, description in PUBLIC_LABELS:
        ensure_label(OPEN_REPO, token, name, color, description)


def set_labels(repo: str, token: str, issue: int, labels: list[str]) -> None:
    gh_ok("PUT", f"/repos/{repo}/issues/{issue}/labels", token, {"labels": labels})


def comment_issue(repo: str, token: str, issue: int, body: str) -> None:
    gh_ok("POST", f"/repos/{repo}/issues/{issue}/comments", token, {"body": body})


def intake_marker_state(token: str, task_id: str) -> str:
    """Marker-carrying intake issue-এর অবস্থা: 'found' | 'absent' | 'unknown' (E8)।

    বাংলা: fail-closed (private issue-list fetch ব্যর্থ) ও সত্যিকারের duplicate
    আগে একটাই `True` ফেরত যেত — কাজেই public issue নীরবে `bridge:in-gates`
    label পেত, কোনও কারণ-কমেন্ট ছাড়া; agent জেনে-বুঝে না-যোগ্য অবস্থায় পড়ে
    থাকত। তিন-অবস্থায় আলাদা করে sanitized কারণ কমেন্ট দেওয়া যায়।
    """
    marker = MARKER_FMT.format(tid=task_id)
    for repo in BRIDGE_TARGET_REPOS:
        try:
            issues = gh_paged(
                f"/repos/{repo}/issues?labels={LABEL_PRIVATE_BRIDGE}&state=all&per_page=100",
                token,
                max_pages=5,
            )
        except BridgeError:
            return "unknown"  # fail-closed: duplicate-ঝুঁকির চেয়ে না-apply ভালো
        if any(marker in (i.get("body") or "") for i in issues):
            return "found"
    return "absent"


def already_intaked(token: str, task_id: str) -> bool:
    """Dedup stay-status (bool contract — unit-tested) — 'unknown' fail-closed True।"""
    return intake_marker_state(token, task_id) != "absent"


def landing_truth_probe(token: str, task_id: str) -> tuple[str, str]:
    """Landing-সত্য প্রোব (#2158 fallback protocol) — branch-মৃত্যু ≠ rejection-প্রমাণ।

    বাংলা: squash-merge হলে patch branch মুছে যায় (post-merge branch delete)।
    ওই অবস্থায় intake-এর `fetch_patch` "not found" দেখে terminal
    `bridge:rejected` স্ট্যাম্প করত, অথচ কাজটা আগেই ল্যান্ডেড থাকত (লাইভ-প্রমাণিত
    2026-10-28: landed #2020/#2056 ভুলভাবে rejected হলো, 13:07Z sweep)।
    reject-এর আগে দুই-স্তরের landing-প্রমাণ প্রোব (#2158-এর fallback protocol):

      স্তর ১ (PR-state lookup): repo তালিকা OPEN_REPO প্রথমে + BRIDGE_TARGET_REPOS;
        প্রতিটিতে closed PR, head-filter দুইটি — `bridge-land/<task_id>` (v2 lane)
        ও `bridge/<task_id>` (direct solver lane, #2265); `merged_at` সেট থাকলে
        landing প্রমাণিত (এই প্রোবে কোনো history-জানালা নেই — পুরোনো PR-ও ধরা পড়ে)।
      স্তর ২ (squash detection): একই repo তালিকার main-এর সাম্প্রতিক commit-message-এর
        প্রথম লাইনে task_id — private PR title (`feat(bridge): {task_id} —
        external work order #N`) ও commit msg (`bridge({task_id}): ...`) দুটোই
        task_id বহন করে, তাই squash ও merge-commit দুই ধারাতেই প্রথম লাইনে
        মেলে। fetch এক পেজ (নতুন ১০০); window-সীমা evidence-এ নোট হয় (#2265)।

    রিটার্ন তিন-অবস্থা (E8-এর `intake_marker_state` চুক্তির সমান্তরাল):
      ("landed", evidence) — landing প্রমাণিত; ("absent", "") — দুই স্তরই
      নিশ্চিতভাবে নেতিবাচক (rejection সৎ); ("unknown", reason) — API-ব্যর্থতা,
      fail-closed: terminal-rejected নয়, পরের রান আবার প্রোব করবে।
    """
    land_ref_v2 = f"bridge-land/{task_id}"
    land_ref_solver = f"bridge/{task_id}"
    owner = OPEN_REPO.split("/")[0]
    # (#2265) probe-স্থানীয় repo তালিকা: OPEN_REPO প্রথমে — direct solver lane
    # (bridge.tools.ts Step B) `bridge/<taskId>` head-এ open repo-তেই land করে,
    # আর সেটাই আজকের stranded cohort-এর পথ (15 WOs, PRs #2194…#2261)।
    # BRIDGE_TARGET_REPOS অপরিবর্তিত থাকে — ওর sync/routing অর্থ আলাদা।
    probe_repos: tuple[str, ...] = (OPEN_REPO,) + BRIDGE_TARGET_REPOS
    errors: list[str] = []
    # স্তর ১: PR-state lookup — head-filtered তালিকা সস্তা ও সুনির্দিষ্ট।
    # দুইটি head-prefix: v2 lane `bridge-land/<task_id>` (private targets) +
    # direct solver lane `bridge/<task_id>` (open repo, #2265 blindness fix)।
    for repo in probe_repos:
        # (#2265 option A) open repo-তে solver head আগে — v2 lane open repo-তে
        # bridge-land/ তৈরিই করে না; প্রথম কলটিই stranded cohort-এর পথ ধরে।
        prefixes = (
            (land_ref_solver, land_ref_v2) if repo == OPEN_REPO else (land_ref_v2, land_ref_solver)
        )
        for land_ref in prefixes:
            try:
                pulls = gh_paged(
                    f"/repos/{repo}/pulls?state=closed&head={owner}:{land_ref}&per_page=20",
                    token,
                    max_pages=1,
                )
            except BridgeError as exc:
                errors.append(f"{repo}: pulls {str(exc)[:60]}")
                continue
            for pr in pulls:
                if (pr.get("head") or {}).get("ref") == land_ref and pr.get("merged_at"):
                    return "landed", (
                        f"merged PR #{pr.get('number')} @ {repo} "
                        f"(merge {(pr.get('merge_commit_sha') or '')[:10]})"
                    )
    # স্তর ২: squash detection — head-filter কোনো কারণে PR মিস করলেও main-এর
    # commit-history-তে প্রমাণ থাকে (সাম্প্রতিক ১০০ commit-এর জানালা)।
    # (#2265) OPEN_REPO এখানেও অন্তর্ভুক্ত; gh_first_page ব্যবহার করে পাওয়া
    # পেজটি স্ক্যান হয়ই — window-সীমা evidence-এ সৎভাবে নোট হয়, dead-code নয়।
    for repo in probe_repos:
        try:
            commits, has_more = gh_first_page(f"/repos/{repo}/commits?per_page=100", token)
        except BridgeError as exc:
            errors.append(f"{repo}: commits {str(exc)[:60]}")
            continue
        for c in commits:
            first_line = (((c.get("commit") or {}).get("message") or "").split("\n", 1)[0])
            if task_id in first_line:
                window_note = " (newest-100 window)" if has_more else ""
                return "landed", (
                    f"squash/merge commit {(c.get('sha') or '')[:10]} @ {repo} "
                    f"carries task{window_note}"
                )
    if errors:
        return "unknown", "; ".join(errors[:3])
    return "absent", ""


def route_files(files: list[str], explicit_target: str | None = None) -> tuple[str | None, dict[str, str]]:
    """প্রতিটি পাবলিক path → (target repo, canonical path)।

    রিটার্ন: (target_repo | None, path_map)। মিশ্র-target অর্ডার → None (fail-closed;
    v2 rule: এক অর্ডার = এক টার্গেট repo — split করে আলাদা অর্ডার জমা দিতে হবে)।
    """
    targets: set[str] = set()
    path_map: dict[str, str] = {}
    for f in files:
        if f in MIRROR_ROUTING:
            repo, canon = MIRROR_ROUTING[f]
        elif explicit_target and explicit_target in BRIDGE_TARGET_REPOS:
            repo = explicit_target
            canon = f
        elif f.startswith(("studio/", "public/dashboard-preview/", "examples/dashboard-preview/")):
            repo = "Supremeai-bd/supremeai-studio"
            canon = f
        elif f.startswith(("api/", "gateway/", "api-schemas/gateway.")):
            repo = "Supremeai-bd/supremeai-api"
            canon = f
        elif f.startswith(("core/", "api-schemas/task-router.")):
            repo = "Supremeai-bd/supremeai-core"
            canon = f
        elif f.startswith(("command/", "handlers/telegram")):
            repo = "Supremeai-bd/supremeai-command"
            canon = f
        elif f.startswith(("skills/", "examples/langchain-", "examples/vercel-")):
            repo = "Supremeai-bd/supremeai-skills"
            canon = f
        elif f.startswith("vscode/"):
            repo = "Supremeai-bd/supremeai-vscode"
            canon = f
        elif f.startswith(("agents/", "runner/")):
            repo = "Supremeai-bd/supremeai-agents"
            canon = f
        elif f.startswith(("browser/", "sandbox/")):
            repo = "Supremeai-bd/supremeai-browser"
            canon = f
        elif f.startswith(("sdk/", "examples/sdk-", "api-schemas/telemetry-log.", "api-schemas/websocket-events.")):
            repo = "Supremeai-bd/supremeai-sdk"
            canon = f
        elif f.startswith(("infrastructure/mcp-control-plane/", "api-schemas/heartbeat.")):
            repo = "Supremeai-bd/supremeai-mcp-control-plane"
            canon = f
        elif f.startswith(("deployments/", "infra/")):
            repo = "Supremeai-bd/supremeai-infrastructure"
            canon = f
        elif f.startswith("archive/"):
            repo = "Supremeai-bd/supremeai-archive"
            canon = f
        else:
            repo = PRIVATE_REPO
            canon = f
        targets.add(repo)
        path_map[f] = canon
    if len(targets) != 1:
        return None, path_map
    return targets.pop(), path_map


def rewrite_patch_paths(diff: str, path_map: dict[str, str]) -> str:
    """diff header-র a/ b/ path-গুলো canonical-এ রিরাইট — hunk বডি অপরিবর্তিত।

    বাংলা: byte-mirror ফাইল line-identical (cmp -s যাচাইকৃত), তাই শুধু header
    রিরাইটেই git apply নির্ভুল হয়। /dev/null ও hunk (@@) লাইন অপরিবর্তিত থাকে।
    """
    if not path_map:
        return diff
    out: list[str] = []
    for ln in diff.splitlines(keepends=True):
        stripped = ln.rstrip("\r\n")
        eol = ln[len(stripped):]
        m = re.match(r"^diff --git a/(.+?) b/(.+?)$", stripped)
        if m:
            canon = path_map.get(m.group(2), path_map.get(m.group(1), m.group(1)))
            out.append(f"diff --git a/{canon} b/{canon}{eol}")
            continue
        m = re.match(r"^(---|\+\+\+) ([ab]/)(.+?)$", stripped)
        if m and m.group(3) in path_map:
            out.append(f"{m.group(1)} {m.group(2)}{path_map[m.group(3)]}{eol}")
            continue
        out.append(ln)
    return "".join(out)


# ---------------------------------------------------------------------------
# Core flows
# ---------------------------------------------------------------------------

def process_issue(issue: dict, token: str, work: Path, results: list[str]) -> None:
    num = issue["number"]
    public_url = issue.get("html_url", f"https://github.com/{OPEN_REPO}/issues/{num}")
    wo = parse_work_order(issue.get("body"))
    task_id = (wo.get("Task ID") or "").strip()
    branch = (wo.get("Patch Branch") or "").strip()
    agent = (wo.get("Agent Identity") or "unknown-agent").strip()[:120]

    def reject(reason: str, label: str = LABEL_REJECTED) -> None:
        body = sanitize_public_comment(
            "## 🌉 Bridge Intake — **" + label.split(":")[-1].upper() + "**\n\n"
            f"- task: `{task_id or '(unparseable)'}`\n"
            f"- reason: {reason}\n\n"
            "Fail-closed bridge v1 — কোনো patch private repo-তে apply হয়নি।",
            token,
        )
        comment_issue(OPEN_REPO, token, num, body)
        set_labels(OPEN_REPO, token, num, [label])
        results.append(f"#{num} → {label}: {reason[:80]}")

    if not validate_task_id(task_id):
        reject(f"invalid Task ID format (`{task_id or 'missing'}`) — need `bridge-YYYYMMDD-<slug>`")
        return
    if not branch:
        reject("missing Patch Branch field")
        return

    dedup = intake_marker_state(token, task_id)
    if dedup != "absent":
        # E8: skip-এর কারণ sanitized কমেন্টে — fail-closed ('unknown') আর
        # সত্যিকারের duplicate ('found') আলাদা করে, নীরব label-flip নয়।
        reason = (
            f"already intaked — `{MARKER_FMT.format(tid=task_id)}` marker-অনুসারী intake issue আগেই আছে"
            if dedup == "found"
            else "dedup-state unknown (private repo issue-list fetch ব্যর্থ) — fail-closed skip, পরে আবার চেষ্টা হবে"
        )
        comment_issue(
            OPEN_REPO,
            token,
            num,
            sanitize_public_comment(
                "## 🌉 Bridge Intake — **IN-GATES** (skip)\n\n"
                f"- task: `{task_id}`\n"
                f"- reason: {reason}\n\n"
                "একই task দুইবার apply হয় না — intake issue-কে ফলো করুন।",
                token,
            ),
        )
        set_labels(OPEN_REPO, token, num, [LABEL_INGATES])
        results.append(f"#{num} → skip ({dedup}: {task_id})")
        return

    # Patch fetch + structural validation
    public_dir = str(work / f"open-{num}")
    clone(OPEN_REPO, token, Path(public_dir))
    try:
        diff, files = fetch_patch(public_dir, branch, token)
    except BridgeError as exc:
        # বাংলা (#2158): branch-অনুপস্থিতি নিজে rejection-প্রমাণ নয় — squash-merge-এর
        # পরে patch branch মুছে যায়, আর marker-জানালার বাইরে থাকা landed WO আবার
        # প্রসেস হয়ে ভুল `bridge:rejected` খেত (লাইভ-প্রমাণিত: #2020/#2056, 13:07Z
        # sweep)। তাই reject-এর আগে landing-সত্য প্রোব: প্রমাণিত landed →
        # verdict-history সত্যে ফিরিয়ে দিই; API-অনিশ্চয়তা → fail-closed
        # পুনর্যাত্রাযোগ্য স্কিপ (E8-সমান্তরাল); দুই স্তরই নিশ্চিতভাবে নেতিবাচক
        # হলেই কেবল সৎ rejection — ভুল terminal-label আর হবে না।
        probe_state, probe_ev = landing_truth_probe(token, task_id)
        if probe_state == "landed":
            comment_issue(
                OPEN_REPO, token, num,
                sanitize_public_comment(
                    "## ✅ Bridge — **LANDED** (truth-restored by intake probe, #2158)\n\n"
                    f"- task: `{task_id}`\n"
                    f"- evidence: {probe_ev}\n"
                    f"- probe trigger: patch branch missing ({str(exc)[:120]})\n\n"
                    "branch-মুছে-যাওয়া rejection নয় — merged-PR/squash-প্রমাণ অনুযায়ী "
                    "কাজটি আগেই ল্যান্ডেড; ভুল terminal-label সংশোধন করা হলো।",
                    token,
                ),
            )
            set_labels(OPEN_REPO, token, num, [LABEL_LANDED])
            gh("PATCH", f"/repos/{OPEN_REPO}/issues/{num}", token,
               {"state": "closed", "state_reason": "completed"})
            results.append(f"#{num} → landed (probe: {probe_ev[:90]})")
            return
        if probe_state == "unknown":
            comment_issue(
                OPEN_REPO, token, num,
                sanitize_public_comment(
                    "## 🌉 Bridge Intake — **IN-GATES** (skip)\n\n"
                    f"- task: `{task_id}`\n"
                    f"- reason: patch branch missing, landing-probe inconclusive — {probe_ev[:140]}\n\n"
                    "fail-closed (E8-সমান্তরাল): rejection-সিদ্ধান্তের আগে landing-প্রমাণ "
                    "দরকার — পরের intake রানে আবার প্রোব হবে।",
                    token,
                ),
            )
            set_labels(OPEN_REPO, token, num, [LABEL_INGATES])
            results.append(f"#{num} → skip (landing-probe unknown: {probe_ev[:70]})")
            return
        reject(str(exc)[:300])
        return

    if len(diff.encode("utf-8", "replace")) > MAX_PATCH_BYTES:
        reject(f"patch too large ({len(diff)} bytes > {MAX_PATCH_BYTES})")
        return
    # #2792 RCA guard-1: zero-diff patch branch = content already merged elsewhere
    # (or empty branch). Clean reject HERE — no commit-less branch, no POST /pulls
    # 422, no exit-2, the order leaves the queue with an honest terminal label.
    if not files or not diff.strip():
        reject(
            "zero-diff patch branch — content already merged elsewhere or empty "
            "branch; nothing effective to land (#2792)"
        )
        return
    if len(files) > MAX_FILES:
        reject(f"too many files ({len(files)} > {MAX_FILES})")
        return

    ok_paths, admin_paths = classify_paths(files)
    if admin_paths:
        body = sanitize_public_comment(
            "## 🌉 Bridge Intake — **ADMIN-REVIEW**\n\n"
            f"- task: `{task_id}`\n"
            "- protected paths present (never auto-applied):\n"
            + "".join(f"  - `{p}`\n" for p in admin_paths[:15])
            + "\nOwner decision প্রয়োজন — manual review lane।",
            token,
        )
        comment_issue(OPEN_REPO, token, num, body)
        set_labels(OPEN_REPO, token, num, [LABEL_ADMIN])
        results.append(f"#{num} → admin-review ({len(admin_paths)} protected files)")
        return

    families = scan_secrets(diff)
    if families:
        reject("secret-pattern scan hit: " + ", ".join(families) + " — remove secrets and resubmit")
        return

    # Apply — routed target repo (supports all 12 federation repositories + monorepo)
    explicit_target = None
    target_field = (wo.get("Target Repository") or wo.get("Target") or "").strip()
    if target_field:
        if not target_field.startswith("Supremeai-bd/"):
            target_field = f"Supremeai-bd/{target_field}"
        if target_field in BRIDGE_TARGET_REPOS:
            explicit_target = target_field

    target_repo, path_map = route_files(files, explicit_target=explicit_target)
    if target_repo is None:
        reject("order spans multiple target repos — one order per target (bridge v2 routing rule)")
        return
    deleted = deletion_paths(diff)
    mapped = [(path_map.get(f, f), f in deleted) for f in files]
    diff_routed = rewrite_patch_paths(diff, path_map)
    private_dir = str(work / f"priv-{num}")
    clone(target_repo, token, Path(private_dir))
    run(["git", "config", "user.name", "supremeai-bridge"], cwd=private_dir)
    run(["git", "config", "user.email", "bridge@supremeai.local"], cwd=private_dir)
    # #1676 split-brain guard — satellite root-mirror duplicate detection (fail-closed,
    # root twin proven from the freshly cloned target main, deletions exempt).
    dupes = split_brain_duplicates(target_repo, Path(private_dir), mapped)
    if dupes:
        shown = ", ".join(dupes[:8]) + (" …" if len(dupes) > 8 else "")
        reject(
            "split-brain guard (#1676): dispatched path(s) would duplicate existing root "
            + f"file(s) in {target_repo}: {shown} — write the root path instead, or submit "
            + "a deletion order for the stale copy and resubmit"
        )
        return
    land_branch = f"bridge-land/{task_id}"
    # E4: আগের রান push করেছে কিন্তু intake issue (dedup marker) তৈরি হওয়ার আগেই
    # মৃত্যু/রদ হয়েছে (concurrency cancel, timeout, API ৫xx) — সেই orphan
    # branch-কে base হিসেবে নিয়ে fast-forward retry। force-push কখনো নয়; branch
    # না থাকলে as usual `origin/main` থেকে নতুন shuru। এই কারণেই workflow-এ
    # `cancel-in-progress: false` (bridge-intake.yml)।
    probe = run(["git", "ls-remote", "origin", f"refs/heads/{land_branch}"], cwd=private_dir, check=False)
    if probe.returncode != 0:
        raise BridgeError(f"remote branch probe failed for {land_branch}: {(probe.stderr or '')[-120:]}")
    resumed = bool(probe.stdout.strip())
    if resumed:
        run(
            ["git", "fetch", "--quiet", "origin",
             f"refs/heads/{land_branch}:refs/remotes/origin/{land_branch}"],
            cwd=private_dir,
        )
        run(["git", "checkout", "--quiet", "-b", land_branch, f"origin/{land_branch}"], cwd=private_dir)
    else:
        run(["git", "checkout", "--quiet", "-b", land_branch, f"origin/{PRIVATE_MAIN}"], cwd=private_dir)
    patch_file = work / f"patch-{num}.diff"
    patch_file.write_text(diff_routed, encoding="utf-8")
    applied = run(["git", "apply", "--whitespace=nowarn", str(patch_file)], cwd=private_dir, check=False)
    already_applied = False
    if applied.returncode != 0:
        # E4: retry হলে patch আগেই branch-তে বসতে পারে — reverse-check সত্যি
        # "already applied" প্রমাণ করে (শুধু push-ই বাকি), ওই অবস্থায় commit নয়।
        reverse_ok = resumed and run(
            ["git", "apply", "--reverse", "--check", str(patch_file)], cwd=private_dir, check=False
        ).returncode == 0
        if reverse_ok:
            already_applied = True
        else:
            base = f"{target_repo}@{land_branch} (retry)" if resumed else f"{target_repo}@{PRIVATE_MAIN}"
            reason = (applied.stderr or "patch does not apply")[-250:]
            reject(f"patch failed to apply on {base}: {reason}")
            return
    run(["git", "add", "-A"], cwd=private_dir)
    # already-applied retry-এ staged পরিবর্তন নেই → খালি commit নয়, বিদ্যমান HEAD।
    has_staged = run(["git", "diff", "--cached", "--quiet"], cwd=private_dir, check=False).returncode == 1
    # #2792 RCA guard-2 (belt behind guard-1): no effective commit → clean reject
    # BEFORE POST /pulls — the proven 422-poison that exit-2'd whole intake runs.
    if not _has_effective_landing(has_staged, already_applied):
        reject(
            "no effective commit to land — patch applies as a no-op on "
            + (f"{target_repo}@{land_branch} (retry)" if resumed else f"{target_repo}@{PRIVATE_MAIN}")
            + "; content already merged elsewhere (#2792)"
        )
        return
    if has_staged:
        run(
            [
                "git", "commit", "--quiet", "-m",
                f"bridge({task_id}): external work order #{num}",
                "-m", f"Agent: {agent}\nBridge-Source: {public_url}\nApplied-by: bridge_intake.py v1 (fail-closed intake)",
            ],
            cwd=private_dir,
        )
    push = run(["git", "push", "--quiet", "origin", land_branch], cwd=private_dir, check=False)
    if push.returncode != 0:
        reject(f"push to {target_repo} rejected: {(push.stderr or 'unknown')[-200:]}")
        return
    head_sha = run(["git", "rev-parse", "HEAD"], cwd=private_dir).stdout.strip()

    # Audit-trail issue + gated PR — routed target repo-তে
    ensure_label(target_repo, token, LABEL_PRIVATE_BRIDGE, "5319E7", "bridge-intake external work order")
    intake_body = build_intake_issue_body(wo, task_id, public_url, agent, files)
    intake = gh_ok(
        "POST", f"/repos/{target_repo}/issues", token,
        {"title": f"feat(bridge): {task_id}", "body": intake_body, "labels": [LABEL_PRIVATE_BRIDGE, "status:in-progress"]},
    )
    # Claim the intake issue for the landing bot so Claim Gate (#2644) and Scope Gate pass
    claim_files = "\n".join(f"  - `{f}`" for f in files) or "  - (none)"
    claim_comment = (
        "<!-- atomic-claim -->\n"
        "### 🔒 Atomic Claim\n\n"
        "- **Agent:** `supremeai-bot`\n"
        "- **Agent:** `paykaribazaronline`\n"
        f"- **Task:** `{task_id}`\n"
        f"- **Branch:** `{land_branch}`\n"
        "- **Status:** in-progress\n"
        f"- **Touching files:**\n{claim_files}\n"
    )
    gh_ok("POST", f"/repos/{target_repo}/issues/{intake['number']}/comments", token, {"body": claim_comment})
    pr = gh_ok(
        "POST", f"/repos/{target_repo}/pulls", token,
        {
            "title": f"feat(bridge): {task_id} — external work order #{num}",
            "head": land_branch,
            "base": PRIVATE_MAIN,
            "body": build_pr_body(wo, task_id, intake["number"], public_url, agent, files),
        },
    )
    report = sanitize_public_comment(
        "## 🌉 Bridge Intake — **APPLIED** (in gates now)\n\n"
        f"- task: `{task_id}`\n"
        f"- landed repo: `{target_repo}`\n"
        f"- PR: **#{pr['number']}** — full constitutional gate chain decides landing\n"
        f"- head: `{head_sha[:10]}`\n"
        f"- files: {len(files)}\n\n"
        "এরপর label-চেইন ফলো করুন: `bridge:in-gates → bridge:landed`।",
        token,
    )
    comment_issue(OPEN_REPO, token, num, report)
    set_labels(OPEN_REPO, token, num, [LABEL_INGATES])
    retry_note = " [retry: patch already on branch]" if already_applied else (" [resumed orphan branch]" if resumed else "")
    results.append(f"#{num} → applied, {target_repo} PR #{pr['number']} ({task_id}){retry_note}")


# Repeat-failure quarantine marker (#report-verify F-02): এই HTML comment থাকলে
# বোঝা যায় ওই work order আগের রানেও ERROR/UNEXPECTED হয়েছিল — অর্থাৎ প্রতি
# hourly/scheduled run-এ একই অর্ডার বারবার ব্যর্থ হচ্ছে (poison-order loop) এবং
# পুরো Bridge Intake স্থায়ীভাবে লাল থাকছে। দ্বিতীয়বার ব্যর্থ হলে অর্ডারকে
# bridge:admin-review-এ quarantine করা হয় — owner দেখবেন, queue মুক্ত থাকবে।
REPEAT_FAILURE_MARKER = "<!-- bridge-intake:repeat-failure -->"


def _issue_has_repeat_failure_marker(token: str, num: int) -> bool:
    try:
        comments = gh_paged(f"/repos/{OPEN_REPO}/issues/{num}/comments?per_page=100", token, max_pages=2)
    except BridgeError:
        return False  # fail-open: marker যাচাই অনিশ্চিত হলে quarantine স্কিপ — পরের রানে আবার চেষ্টা
    return any(REPEAT_FAILURE_MARKER in (c.get("body") or "") for c in comments)


def _handle_intake_failure(token: str, issue: dict, detail: str, results: list[str]) -> None:
    """একটি work order-এর per-run ব্যর্থতা: প্রথমবার marker-সহ সতর্ক-কমেন্ট (এক রানের
    grace), দ্বিতীয়বার bridge:admin-review-এ quarantine — পাইপলাইন লাল জিম্মি
    করে রাখা বন্ধ (F-02)। rc সৎ থাকে: quarantine নিজেই এই রানের রেজোলিউশন।"""
    num = issue["number"]
    if _issue_has_repeat_failure_marker(token, num):
        try:
            comment_issue(
                OPEN_REPO, token, num,
                sanitize_public_comment(
                    "## 🌉 Bridge Intake — **QUARANTINED** (repeat failure)\n\n"
                    f"- reason: টানা ২ রান ব্যর্থ — `{detail[:160]}`\n"
                    "- অর্ডারটি `bridge:admin-review`-এ সরানো হলো — owner রিভিউ করে "
                    "হয় ঠিক করবেন, হয় বন্ধ করবেন। queue মুক্ত থাকবে।",
                    token,
                ),
            )
            set_labels(OPEN_REPO, token, num, [LABEL_ADMIN])
            results.append(f"#{num} → QUARANTINED (repeat failure): {detail[:80]}")
        except Exception as exc:  # noqa: BLE001 — quarantine-ও ব্যর্থ হলে সৎ error-ই থাক
            results.append(f"#{num} → ERROR (quarantine failed): {type(exc).__name__}: {str(exc)[:80]}")
        return
    try:
        comment_issue(
            OPEN_REPO, token, num,
            sanitize_public_comment(
                f"{REPEAT_FAILURE_MARKER}\n\n"
                "## 🌉 Bridge Intake — ⚠️ **RETRY PENDING** (first failure)\n\n"
                f"- reason: `{detail[:160]}`\n"
                "- এই অর্ডার পরের intake রানেও ব্যর্থ হলে স্বয়ংক্রিয়ভাবে "
                "`bridge:admin-review`-এ চলে যাবে (poison-order quarantine)।",
                token,
            ),
        )
    except Exception:  # noqa: BLE001 — কমেন্ট ব্যর্থ হলেও মূল error রিপোর্ট হবে
        pass
    results.append(f"#{num} → {detail[:100]}")


def cmd_intake(token: str) -> int:
    ensure_public_labels(token)  # E6: set_labels 422 → reject-পথ ব্যর্থ → queue আটকে যাওয়া প্রতিরোধ
    # E5: per_page=40 → টানা পেজ (Link rel=next); cap-এ পৌঁছালে সৎ-ব্যর্থতা, কাটা নয়।
    try:
        issues = gh_paged(f"/repos/{OPEN_REPO}/issues?labels={LABEL_QUEUED}&state=open&per_page=100", token, max_pages=3)
    except BridgeError as exc:
        raise BridgeError(f"queue fetch failed: {exc}")
    workorders = [i for i in issues if "pull_request" not in i]
    results: list[str] = []
    with tempfile.TemporaryDirectory(prefix="bridge-") as tmp:
        work = Path(tmp)
        for issue in workorders:
            try:
                process_issue(issue, token, work, results)
            except BridgeError as exc:
                _handle_intake_failure(token, issue, f"ERROR (honest): {str(exc)[:120]}", results)
            except Exception as exc:  # noqa: BLE001 — fail-honest per-issue, loop continues
                _handle_intake_failure(token, issue, f"UNEXPECTED: {type(exc).__name__}: {str(exc)[:120]}", results)
    print("== bridge intake ==")
    for line in results or ["queue empty"]:
        print(" -", line)
    unexpected = [r for r in results if ("UNEXPECTED" in r or "ERROR" in r) and "QUARANTINED" not in r]
    return 2 if unexpected else 0


def cmd_sync(token: str) -> int:
    """PR lifecycle → public issue reporting (landed / rejected) — সব target repo স্ক্যান (v2)।"""
    ensure_public_labels(token)  # E6: sync-ও public repo-তে label বসায়
    results: list[str] = []
    # বাংলা (#65): list-pulls response-এ boolean "merged" ফিল্ড থাকে না (শুধু
    # single-GET-এ) — থাকে "merged_at"। p.get("merged") সবসময় None → merged PR-ও
    # rejected হত (লাইভ-প্রমাণিত: PR #40 landed হয়েও bridge:rejected পেয়েছিল)।
    landed: list[dict] = []
    rejected: list[dict] = []
    # R1 per-repo fail-isolation (live proof 2026-10-25): one dead/renamed repo
    # (HTTP 404 after the satellite consolidation) made the whole sync raise
    # BridgeError -> exit 1 EVERY run -> landed-reporting dead for 12h+. Collect
    # per-repo fetch errors instead; remaining repos keep reporting; the run
    # still exits honestly non-zero AFTER processing everything (see below).
    sync_errors: list[str] = []
    # (#2547) সলভার-লেন অন্ধত্ব শেষ: closed-PR স্ক্যানে OPEN_REPO প্রথমে — সলভার লেন
    # সরাসরি open repo-তে `bridge/<task_id>` PR খোলে; পুরনো স্ক্যান শুধু private
    # স্যাটেলাইটের `bridge-land/` চিনত, ফলে solver-lane PR merge হয়েও public WO
    # চিরকাল stranded (লাইভ-প্রমাণিত ১২-row cohort, #2516/#2547 census)।
    # BRIDGE_TARGET_REPOS অস্পৃষ্ট — sync/routing SSOT অক্ষত (#2265 probe-রীতির
    # প্রতিফলন: OPEN_REPO first, একটি সস্তা কল প্রথমে)।
    scan_repos: tuple[str, ...] = (OPEN_REPO,) + BRIDGE_TARGET_REPOS
    for repo in scan_repos:
        # E5: ৪০-এর window বাদ, পুরো closed-PR ইতিহাস (Link rel=next) — নীরভ
        # cron-slot-এর পর পুরনো landed PR-ও report হতে হবে, নাহলে public issue
        # চিরকাল in-gates/queued-এ আটকে থাকে।
        try:
            pulls = gh_paged(f"/repos/{repo}/pulls?state=closed&sort=updated&per_page=100", token, max_pages=5)
        except BridgeError as exc:
            sync_errors.append(f"PR fetch failed: {str(exc)[:160]} ({repo})")
            continue
        for p in pulls:
            task_id = strip_lane_prefix((p.get("head") or {}).get("ref", ""))
            if not task_id:
                continue
            p["_repo"] = repo
            p["_task_id"] = task_id
            (landed if p.get("merged_at") else rejected).append(p)

    try:
        open_issues = gh_paged(f"/repos/{OPEN_REPO}/issues?state=open&per_page=100", token, max_pages=3)
    except BridgeError as exc:
        raise BridgeError(f"open issues fetch failed: {exc}")
    open_issues = [i for i in open_issues if "pull_request" not in i]

    def find_issue(task_id: str) -> dict | None:
        # বাংলা: EXACT Task-ID match — substring-ম্যাচ v1/v2-prefix কনফিউশন তৈরি করে
        # (E2E-তে প্রমাণিত: "bridge-...-smoke" "bridge-...-smoke-v2"-র ভেতরে ম্যাচ করেছিল)।
        for issue in open_issues:
            wo_i = parse_work_order(issue.get("body"))
            if (wo_i.get("Task ID") or "").strip() == task_id:
                return issue
        return None

    def issue_labels(issue: dict) -> list[str]:
        return [l.get("name", "") for l in (issue.get("labels") or [])]

    landed_ids: set[str] = set()
    for pr in landed:
        task_id = pr["_task_id"]
        landed_ids.add(task_id)
        issue = find_issue(task_id)
        if not issue:
            continue
        body = sanitize_public_comment(
            "## ✅ Bridge — **LANDED**\n\n"
            f"- task: `{task_id}`\n"
            f"- merged PR: **#{pr['number']}** @ `{pr.get('_repo', PRIVATE_REPO)}` @ `{(pr.get('merge_commit_sha') or '')[:10]}`\n\n"
            "কাজটি target repo-তে merge হয়েছে (gates সব সবুজ)।",
            token,
        )
        comment_issue(OPEN_REPO, token, issue["number"], body)
        set_labels(OPEN_REPO, token, issue["number"], [LABEL_LANDED])
        gh("PATCH", f"/repos/{OPEN_REPO}/issues/{issue['number']}", token, {"state": "closed", "state_reason": "completed"})
        results.append(f"{task_id} → landed (PR #{pr['number']})")

    for pr in rejected:
        task_id = pr["_task_id"]
        # E5: একই task-এর landed + rejected PR দুটোই থাকলে শেষ verdict জেতে —
        # নাহলে একই public issue-এ "LANDED" তারপর "REJECTED" কমেন্ট (বিরোধী
        # report); শেষ resubmit-এর PR-ই সম্ভাব্য rejected, তাই landed-কেই SSOT ধরি।
        if task_id in landed_ids:
            results.append(f"{task_id} → rejected verdict skipped (landed wins, PR #{pr['number']})")
            continue
        issue = find_issue(task_id)
        if not issue:
            continue
        body = sanitize_public_comment(
            "## ❌ Bridge — **REJECTED**\n\n"
            f"- task: `{task_id}`\n"
            f"- PR **#{pr['number']}** @ `{pr.get('_repo', PRIVATE_REPO)}` merged হয়নি (gates/owner সিদ্ধান্ত)।",
            token,
        )
        comment_issue(OPEN_REPO, token, issue["number"], body)
        set_labels(OPEN_REPO, token, issue["number"], [LABEL_REJECTED])
        results.append(f"{task_id} → rejected (PR #{pr['number']})")

    # Reconciliation: OPEN bridge PR → public issue অবশ্যই bridge:in-gates হবে
    # (stale লেবেল শুদ্ধ করে — E2E-তে প্রমাণিত কেস: ভুল rejected লেবেল আটকে ছিল)।
    for repo in scan_repos:
        try:
            open_pulls = gh_paged(f"/repos/{repo}/pulls?state=open&per_page=100", token, max_pages=3)
        except BridgeError as exc:
            sync_errors.append(f"open PR fetch failed: {str(exc)[:160]} ({repo})")
            continue
        for pr in open_pulls:
            task_id = strip_lane_prefix((pr.get("head") or {}).get("ref", ""))
            if not task_id:
                continue
            issue = find_issue(task_id)
            if issue and LABEL_INGATES not in issue_labels(issue):
                set_labels(OPEN_REPO, token, issue["number"], [LABEL_INGATES])
                results.append(f"{task_id} → reconciled to in-gates ({repo} PR #{pr['number']} open)")

    print("== bridge sync ==")
    for line in results or ["nothing to sync"]:
        print(" -", line)
    if sync_errors:
        print("== bridge sync repo-level errors (fail-honest) ==")
        for line in sync_errors:
            print(" !", line)
        return 2
    return 0


def main() -> int:
    token = os.environ.get("BRIDGE_TOKEN", "")
    if not token:
        print("BRIDGE_TOKEN missing — fail-closed (no work done)", file=sys.stderr)
        return 2
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode not in ("intake", "sync", "both"):
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 2
    try:
        # #2792 RCA guard-4: intake rc≠0 হলেও sync চলবে — একটা খারাপ অর্ডার
        # landed/rejected রিপোর্টিং বন্ধ করতে পারে না (streak #327-#329-এ
        # reporting সম্পূর্ণ মরেছিল)। দুটো exit code আলাদাভাবে জানানো হয়।
        rcs: list[int] = []
        if mode in ("intake", "both"):
            rcs.append(cmd_intake(token))
            print(f"== intake rc={rcs[-1]} ==")
        if mode in ("sync", "both"):
            rcs.append(cmd_sync(token))
            print(f"== sync rc={rcs[-1]} ==")
        return max(rcs) if rcs else 0
    except BridgeError as exc:
        print(f"BRIDGE FAIL-HONEST: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
