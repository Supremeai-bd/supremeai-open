#!/usr/bin/env python3
"""Unified Issue Creator — blocker + discovery, একক স্ক্রিপ্ট (#2841 PR-6)।
==========================================================================
দুই টুইন-স্ক্রিপ্ট (`create_blocker_issue.py` + `create_discovery_issue.py`)
এক ফাইলে; আচরণ আগের মতোই, শুধু `--type` দিয়ে লেন নির্বাচন:

    # Blocker: প্রয়োজনীয় পূর্বশর্ত — বর্তমান ইস্যু শেষ হওয়ার আগে যেটা মেরামত বাধ্যতামূলক
    python scripts/agents/create_issue.py --type blocker \\
        --parent-issue 1690 \\
        --title "fix(db): Missing tenant isolation check in mesh registry" \\
        --body "Mesh registry queries fail under multi-tenant isolation..." \\
        --role platform

    # Discovery: কাজের সময় পাওয়া অসম্পর্কিত বাগ/গ্যাপ — Charter Rule #7
    python scripts/agents/create_issue.py --type discovery \\
        --parent-issue 1690 \\
        --title "fix(db): vector store leaks across tenants on pagination" \\
        --body "While fixing #1690, discovered pagination doesn't enforce tenant_id..." \\
        --role coder --severity high

    # Dry-run (উভয় টাইপে): python scripts/agents/create_issue.py --type discovery ... --dry-run

পার্থক্য (আগের চুক্তি অক্ষত):
    - Blocker  : prerequisite — `type:blocker` + `handoff:<role>` + exact-title dedup (#1997)
    - Discovery: অসম্পর্কিত আবিষ্কার — `type:discovery` + `discovered-by:<role>` + severity
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# #3088: universal fingerprint-dedup — title-keyword নয়, সেমান্টিক জাল (both lanes)।
sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue_fingerprint import duplicate_guard, fingerprint, prepend_marker  # noqa: E402
from gh_label_ensure import LabelEnsureError, ensure_labels  # noqa: E402  # #3278

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

VALID_ROLES = ("planner", "coder", "pr-helper", "ci", "platform")
VALID_SEVERITIES = ("low", "medium", "high", "critical")
VALID_TYPES = ("blocker", "discovery")


# ---------------------------------------------------------------------------
# Blocker লেন (প্রাক্তন create_blocker_issue.py — অপরিবর্তিত আচরণ)
# ---------------------------------------------------------------------------
@dataclass
class BlockerIssueResult:
    new_issue_number: int | None
    new_issue_url: str
    parent_issue_number: int
    title: str
    role: str
    labels: list[str]
    is_dry_run: bool = False
    success: bool = True
    error_message: str = ""
    duplicate_of: int | None = None  # identical open issue থাকলে সেট


def _gh_available() -> bool:
    return subprocess.run(["gh", "--version"], capture_output=True).returncode == 0


def find_existing_blocker(title: str, repo_dir: Path = ROOT_DIR) -> int | None:
    """Open ইস্যুর মধ্যে exact-title ম্যাচ খুঁজে নম্বর দেয় (ডেডুপ গার্ড #1997)।

    ২০২৬-০৯-২৭-এর ডুপ্লিকেট-বন্যা হয়েছিল phrase-সার্চে; এই হেল্পার REAL title
    দিয়ে সার্চ করে লোকাল exact-match যাচাই করে — '#', প্যারেন, কোলন-নিরাপদ।
    """
    if not _gh_available():
        return None
    try:
        res = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--limit",
                "50",
                "--search",
                f'"{title}" in:title',
                "--json",
                "number,title",
            ],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if res.returncode != 0:
            return None
        for issue in json.loads(res.stdout or "[]"):
            if str(issue.get("title", "")).strip() == title.strip():
                return int(issue["number"])
    except (subprocess.SubprocessError, OSError, ValueError, json.JSONDecodeError):
        return None
    return None


# --- #3211 Living Issue Architecture ----------------------------------------

def append_living_observation(
    issue_number: int,
    title: str,
    body: str,
    fingerprint: str,
    role: str = "",
    repo_dir: Path = ROOT_DIR,
) -> tuple[bool, str]:
    """#3211 AC-2: duplicate-সিগনেচার মিললে নতুন issue না খুলে বিদ্যমান living
    issue-তে observation অ্যাপেন্ড করে (gh issue comment)।

    Returns (success, error_or_url). নেটওয়ার্ক-ব্যর্থতা fail-honest —
    caller সিদ্ধান্ত নেবে (block নাকি advisory)।
    """
    observation = (
        f"### 🔁 Living Issue Update (#3211 AC-2)\n\n"
        f"একই canonical signature-এ নতুন observation এসেছে — নতুন issue **নয়**, "
        f"এই living issue-তেই সংযোজন (#3088 fingerprint dedup):\n\n"
        f"- **Fingerprint:** `{fingerprint}`\n"
        f"- **Would-be title:** {title.strip()}\n"
        + (f"- **Lane:** `{role}`\n" if role else "")
        + f"\n**Observation:**\n\n{body.strip()}\n\n"
        f"_Automated by scripts/agents/create_issue.py — duplicate প্রতিরোধ, context এক জায়গায়।_"
    )
    try:
        res = subprocess.run(
            ["gh", "issue", "comment", str(issue_number),
             "--body", observation, "--repo", _repo_slug(repo_dir)],
            capture_output=True, text=True, timeout=30, check=False,
            cwd=str(repo_dir),
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, str(exc)
    if res.returncode != 0:
        return False, (res.stderr or res.stdout or "gh issue comment failed").strip()
    url = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
    return True, url


def format_alternative_solutions_ledger(
    approach_a: str,
    approach_b: str,
    recommendation: str,
) -> str:
    """#3211 AC-4: Alternative Solutions Ledger — মাল্টি-হাইপোথিসিস সংরক্ষণ।

    Pure formatter (নেটওয়ার্ক নেই) — পুরোনো সমাধান ওভাররাইট/বিলোপ নয়,
    তুলনামূলক টেবিল হিসেবে বিদ্যমান issue-তে অ্যাপেন্ড হয়।
    """
    return (
        "### ⚖️ Alternative Solutions Ledger (#3211 AC-4)\n\n"
        "| Approach | Description | Trade-offs |\n"
        "|---|---|---|\n"
        f"| **A (previous)** | {approach_a.strip()} | প্রতিষ্ঠিত, পরিচিত রিস্ক |\n"
        f"| **B (proposed)** | {approach_b.strip()} | নতুন ট্রেড-অফ, যাচাই-প্রয়োজন |\n\n"
        f"**Comparative Recommendation:** {recommendation.strip()}\n\n"
        f"_পরবর্তী implementing agent উভয় দৃষ্টিভঙ্গি দেখে সেরা (বা মিশ্র) পথ বেছে নেবে — "
        f"প্রতিযোগী issue নয় (#3211 মাল্টি-হাইপোথিসিস চুক্তি)।_"
    )


def append_alternative_solution(
    issue_number: int,
    approach_a: str,
    approach_b: str,
    recommendation: str,
    repo_dir: Path = ROOT_DIR,
) -> tuple[bool, str]:
    """#3211 AC-4: বিদ্যমান issue-তে Alternative Solutions Table অ্যাপেন্ড।"""
    table = format_alternative_solutions_ledger(approach_a, approach_b, recommendation)
    try:
        res = subprocess.run(
            ["gh", "issue", "comment", str(issue_number),
             "--body", table, "--repo", _repo_slug(repo_dir)],
            capture_output=True, text=True, timeout=30, check=False,
            cwd=str(repo_dir),
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, str(exc)
    if res.returncode != 0:
        return False, (res.stderr or res.stdout or "gh issue comment failed").strip()
    url = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
    return True, url


def _repo_slug(repo_dir: Path) -> str:
    """owner/name নিষ্কাশন — gh --repo এর জন্য (git remote থেকে, echo-নিরাপদ)।"""
    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=10, check=False,
            cwd=str(repo_dir),
        )
        url = res.stdout.strip()
        for prefix in ("git@github.com:", "https://github.com/"):
            if url.startswith(prefix):
                return url[len(prefix):].removesuffix(".git")
    except (subprocess.SubprocessError, OSError):
        pass
    return "SaifulHaqueNiloy/supremeai"


def format_blocker_body(parent_issue: int, description: str, role: str) -> str:
    """স্ট্যান্ডার্ড blocker-বডি — অডিট-লিংকসহ + fixed-template চুক্তি (#2912)।

    #2912: agent-তৈরি প্রতিটি কাজ-ইস্যুর Mission/Priority/Touching Files/
    Verification সেকশন বাধ্যতামূলক (Template Gate) — blocker-ও ব্যতিক্রম নয়।
    """
    return f"""### 🛑 Prerequisite Blocker

**Discovered while working on:** #{parent_issue}  
**Target Role Lane:** `{role}`  
**Dependency Type:** Upstream Prerequisite Blocker  

---

### Mission & Problem Statement
{description.strip()}

---

### Priority Tier
P1-high (upstream prerequisite — এটি না মিটলে #{parent_issue} স্তব্ধ)

### Touching Files (Scope Gate Boundary)
ক্লেইম-সময় ঘোষিত হবে — `scripts/ci/atomic_claim.sh <this-issue> <agent> --files "…"` (coder সঠিক ফাইল-তালিকা ঘোষণা করবে; Scope Gate সেটিই যাচাই করবে)।

### 3-Tier Verification Contract
1. Reflection Check: `git grep -n "<symbol>"`
2. Boot Smoke Test: `python -c "import backend.main; print('Boot smoke passed')"`
3. Pytest Suite: `pytest <test_file_path> -v`

---

### 🔗 Dependency Links
- **Blocks:** #{parent_issue}
- **Action Required:** Resolve and merge this issue before completing #{parent_issue}.

_Automated by `scripts/agents/create_issue.py --type blocker` per AGENTS.md Constitution Invariant 9 + Fixed Template Mandate (#2912)._"""


def format_parent_comment(new_issue_number: int, title: str, role: str) -> str:
    """প্যারেন্ট-ইস্যুকে blocked-নোটিফিকেশন কমেন্ট।"""
    return f"""⚠️ **Blocked by Prerequisite Issue: #{new_issue_number}**

> **Title:** {title}  
> **Assigned Role Lane:** `{role}`  
> **Status:** Unclaimed (`status:unclaimed`)  

Work on this issue is dependent on resolving #{new_issue_number} first to avoid out-of-scope drive-by changes."""


def create_blocker_issue(
    parent_issue: int,
    title: str,
    body: str,
    role: str = "coder",
    extra_labels: list[str] | None = None,
    dry_run: bool = False,
    repo_dir: Path = ROOT_DIR,
    allow_duplicate: bool = False,
) -> BlockerIssueResult:
    """নতুন prerequisite blocker ইস্যু তৈরি করে প্যারেন্টের সাথে লিংক করে।"""
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        normalized_role = "coder"

    labels = ["type:blocker", "status:unclaimed", f"handoff:{normalized_role}"]
    if extra_labels:
        for lbl in extra_labels:
            clean_lbl = lbl.strip()
            if clean_lbl and clean_lbl not in labels:
                labels.append(clean_lbl)

    formatted_body = format_blocker_body(
        parent_issue=parent_issue,
        description=body,
        role=normalized_role,
    )

    # --- ডেডুপ গার্ড (#1997): এক blocker, এক ট্র্যাকার -------------------------
    if not dry_run and not allow_duplicate:
        existing = find_existing_blocker(title, repo_dir=repo_dir)
        if existing is not None:
            print(
                f"♻️  Duplicate blocker suppressed: open issue #{existing} already tracks "
                f"'{title}' — linking parent to it instead of creating a new one.",
                file=sys.stderr,
            )
            # প্যারেন্ট যেন জানে সে blocked — আইডেম্পোটেন্ট কমেন্ট।
            try:
                subprocess.run(
                    [
                        "gh",
                        "issue",
                        "comment",
                        str(parent_issue),
                        "--body",
                        f"⚠️ Blocked by prerequisite issue #{existing} (already tracked — duplicate suppressed, #1997).",
                    ],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20,
                )
            except (subprocess.SubprocessError, OSError):
                pass
            return BlockerIssueResult(
                new_issue_number=existing,
                new_issue_url=f"https://github.com/SaifulHaqueNiloy/supremeai/issues/{existing}",
                parent_issue_number=parent_issue,
                title=title,
                role=normalized_role,
                labels=labels,
                is_dry_run=False,
                success=True,
                duplicate_of=existing,
            )

    if dry_run:
        return BlockerIssueResult(
            new_issue_number=9999,
            new_issue_url="https://github.com/SaifulHaqueNiloy/supremeai/issues/9999",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            labels=labels,
            is_dry_run=True,
            success=True,
        )

    cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        title,
        "--body",
        formatted_body,
    ]
    for lbl in labels:
        cmd.extend(["--label", lbl])

    try:
        res = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=30,
        )
        url = res.stdout.strip()
        # URL থেকে ইস্যু-নম্বর পার্স (https://github.com/.../issues/1786 -> 1786)
        issue_num = None
        if "/issues/" in url:
            try:
                issue_num = int(url.split("/issues/")[-1].strip().split("#")[0])
            except ValueError as err:
                print(f"Warning: could not parse issue number from '{url}': {err}", file=sys.stderr)

        if issue_num is not None:
            comment_body = format_parent_comment(issue_num, title, normalized_role)
            try:
                subprocess.run(
                    ["gh", "issue", "comment", str(parent_issue), "--body", comment_body],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20,
                )
            except Exception as e:
                print(f"Warning: Failed to comment on parent issue #{parent_issue}: {e}", file=sys.stderr)

        return BlockerIssueResult(
            new_issue_number=issue_num,
            new_issue_url=url,
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            labels=labels,
            is_dry_run=False,
            success=True,
        )
    except (subprocess.SubprocessError, OSError, Exception) as e:
        return BlockerIssueResult(
            new_issue_number=None,
            new_issue_url="",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            labels=labels,
            is_dry_run=False,
            success=False,
            error_message=str(e),
        )


# ---------------------------------------------------------------------------
# Discovery লেন (প্রাক্তন create_discovery_issue.py — অপরিবর্তিত আচরণ)
# ---------------------------------------------------------------------------
@dataclass
class DiscoveryIssueResult:
    new_issue_number: int
    new_issue_url: str
    parent_issue_number: int
    title: str
    role: str
    severity: str
    labels: list[str]
    is_dry_run: bool
    success: bool
    error: str | None = None


# #2912: severity → priority-tier ম্যাপিং (fixed-template চুক্তির Priority সেকশন)
_SEVERITY_TO_PRIORITY = {
    "low": "P3-low",
    "medium": "P2-medium",
    "high": "P1-high",
    "critical": "P0-critical",
}


def format_discovery_body(
    parent_issue: int,
    description: str,
    role: str,
    severity: str,
) -> str:
    """স্ট্যান্ডার্ড discovery-বডি (Charter Rule #7) + fixed-template চুক্তি (#2912)।"""
    priority = _SEVERITY_TO_PRIORITY.get(severity.strip().lower(), "P2-medium")
    return f"""### 🔍 Discovery Issue (Charter Rule #7)

**Discovered while working on:** #{parent_issue}
**Discovering Role:** `{role}`
**Severity:** `{severity}`
**Issue Type:** Discovery (NOT a prerequisite blocker — unrelated to parent scope)

---

### Mission & Problem Statement
{description.strip()}

---

### Priority Tier
{priority} (severity `{severity}` থেকে ম্যাপড)

### Touching Files (Scope Gate Boundary)
ক্লেইম-সময় ঘোষিত হবে — `scripts/ci/atomic_claim.sh <this-issue> <agent> --files "…"` (যে agent ক্লেইম করবে সে-ই সঠিক ফাইল-তালিকা ঘোষণা করবে; Scope Gate সেটিই যাচাই করবে)।

### 3-Tier Verification Contract
1. Reflection Check: `git grep -n "<symbol>"`
2. Boot Smoke Test: `python -c "import backend.main; print('Boot smoke passed')"`
3. Pytest Suite: `pytest <test_file_path> -v`

---

### 🔗 Links
- **Discovered in:** #{parent_issue}
- **Discovering agent:** `{role}` role
- **Action Required:** This issue is available for any agent in the appropriate role lane to claim. The discovering agent should NOT fix it unless they claim it after their current PR merges.

_Automated by `scripts/agents/create_issue.py --type discovery` per Charter Rule #7 (Discovery-Driven Issue Creation) + Fixed Template Mandate (#2912)._"""


def create_discovery_issue(
    parent_issue: int,
    title: str,
    body: str,
    role: str = "coder",
    severity: str = "medium",
    extra_labels: list[str] | None = None,
    dry_run: bool = False,
    repo_dir: Path = ROOT_DIR,
) -> DiscoveryIssueResult:
    """নতুন discovery ইস্যু তৈরি করে প্যারেন্টের সাথে লিংক করে।"""
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        normalized_role = "coder"

    normalized_severity = severity.strip().lower()
    if normalized_severity not in VALID_SEVERITIES:
        normalized_severity = "medium"

    # বাংলা মন্যব্য (#3278): আগে bare severity (`high`) লেবেল হিসেবে যেত — রিপোতে
    # সেটা নেই (`P1-high` আছে) → create-ই মৃত, fallback-ও একই ভাঙা লেবেল
    # ব্যবহার করত। এখন বিদ্যমান P-label-এ ম্যাপ + shared label-ensure।
    priority_label = _SEVERITY_TO_PRIORITY.get(normalized_severity, "P2-medium")
    labels = [
        "type:discovery",
        "status:unclaimed",
        f"discovered-by:{normalized_role}",
        priority_label,
    ]
    if extra_labels:
        for lbl in extra_labels:
            clean_lbl = lbl.strip()
            if clean_lbl and clean_lbl not in labels:
                labels.append(clean_lbl)

    formatted_body = format_discovery_body(
        parent_issue=parent_issue,
        description=body,
        role=normalized_role,
        severity=normalized_severity,
    )

    if dry_run:
        return DiscoveryIssueResult(
            new_issue_number=9999,
            new_issue_url="https://github.com/SaifulHaqueNiloy/supremeai/issues/9999",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=True,
            success=True,
        )

    def _execute_create(active_labels: list[str]) -> subprocess.CompletedProcess[str]:
        current_cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            formatted_body,
        ]
        for lbl in active_labels:
            current_cmd.extend(["--label", lbl])
        return subprocess.run(
            current_cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=30,
        )

    try:
        # #3278: pre-flight label-ensure — অনুপস্থিত লেবেল (যেমন discovered-by:planner)
        # পুরো create-মৃত্যু ঘটায়; shared helper idempotently সৃষ্টি করে।
        # infra-failure হলে warning-skip — fallback-path এখনো label-ত্রুটি ধরবে।
        try:
            labels = ensure_labels(labels)
        except LabelEnsureError as exc:
            print(f"⚠️ [label-ensure] skipped: {exc}", file=sys.stderr)
        try:
            res = _execute_create(labels)
        except subprocess.CalledProcessError as exc:
            # লেবেল-জনিত ব্যর্থতা হলে safe স্ট্যান্ডার্ড-লেবেলে ফলব্যাক
            err_msg = exc.stderr or str(exc)
            if "label" in err_msg.lower():
                # #3278: fallback-এও canonical P-label — bare severity নয়
                safe_fallback_labels = ["status:unclaimed", priority_label]
                res = _execute_create(safe_fallback_labels)
                labels = safe_fallback_labels
            else:
                raise
        url = res.stdout.strip()
        try:
            issue_num = int(url.rsplit("/", 1)[-1])
        except (ValueError, IndexError):
            issue_num = 0
        return DiscoveryIssueResult(
            new_issue_number=issue_num,
            new_issue_url=url,
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=False,
            success=True,
        )
    except subprocess.CalledProcessError as exc:
        return DiscoveryIssueResult(
            new_issue_number=0,
            new_issue_url="",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=False,
            success=False,
            error=f"{exc.stderr or str(exc)}",
        )
    except (OSError, RuntimeError) as exc:
        return DiscoveryIssueResult(
            new_issue_number=0,
            new_issue_url="",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=False,
            success=False,
            error=str(exc),
        )


def check_duplicates(title: str, repo_dir: Path = ROOT_DIR) -> list[dict]:
    """একই-ধাঁচের open ইস্যু খোঁজে (AUDIT-FIX #1997) — সম্ভাব্য ডুপ্লিকেটের তালিকা।"""
    # শিরোনাম থেকে তাৎপর্যপূর্ণ শব্দ (৪+ অক্ষর, ছোটহাতে)
    words = [w.lower().strip(".,;:()[]{}\"'") for w in title.split() if len(w) >= 4]
    if not words:
        return []

    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--json",
                "number,title",
                "--limit",
                "100",
            ],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        issues = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return []

    duplicates = []
    for issue in issues:
        existing_title = (issue.get("title") or "").lower()
        shared = sum(1 for w in words if w in existing_title)
        # তাৎপর্যপূর্ণ শব্দের >৫০% ম্যাচ = সম্ভাব্য ডুপ্লিকেট
        if shared >= max(2, len(words) // 2):
            duplicates.append(
                {
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "shared_words": shared,
                    "total_words": len(words),
                }
            )
    return duplicates


# ---------------------------------------------------------------------------
# CLI — একক প্রবেশদ্বার, --type দিয়ে লেন-নির্বাচন
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Issue Creator: blocker (prerequisite) + discovery (Charter Rule #7)",
    )
    parser.add_argument(
        "--type",
        choices=VALID_TYPES,
        required=True,
        help="blocker = prerequisite (প্যারেন্টকে ব্লক করে) | discovery = অসম্পর্কিত আবিষ্কার",
    )
    parser.add_argument("--parent-issue", type=int, required=True, help="Parent Issue ID (যেখানে কাজ চলছে / ব্লক হয়েছে)")
    parser.add_argument("--title", type=str, required=True, help="নতুন ইস্যুর শিরোনাম")
    parser.add_argument("--body", type=str, required=True, help="বিস্তারিত বর্ণনা")
    parser.add_argument("--role", choices=VALID_ROLES, default="coder", help="দায়িত্বপ্রাপ্ত রোল-লেন")
    parser.add_argument("--label", action="append", dest="labels", help="অতিরিক্ত লেবেল (বারবার দেওয়া যায়)")
    parser.add_argument("--dry-run", action="store_true", help="GitHub API ছাড়াই অনুকরণ")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="আউটপুট ফরম্যাট")
    # blocker-এক্সক্লুসিভ
    parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="[blocker] identical open ইস্যু থাকলেও তৈরি করো (escape hatch — কারণ লিখে নিন)",
    )
    # discovery-এক্সক্লুসিভ
    parser.add_argument(
        "--severity", choices=VALID_SEVERITIES, default="medium", help="[discovery] তীব্রতা (default: medium)"
    )
    parser.add_argument(
        "--no-check-duplicates",
        dest="check_duplicates",
        action="store_false",
        help="[discovery] সম্ভাব্য-ডুপ্লিকেট যাচাই স্কিপ",
    )
    parser.set_defaults(check_duplicates=True)
    # ── #3088: universal fingerprint dedup (উভয় লেন) + primary-group ──
    parser.add_argument(
        "--group", default=None,
        help="[both] primary group (#3088 §2) — দিলে group:<name> লেবেল + group-scoped dedup",
    )
    parser.add_argument(
        "--scope", default="unspecified",
        help="[both] affected scope (files/component) — fingerprint-উপাদান (#3088 §3)",
    )
    parser.add_argument(
        "--root-cause", default="unspecified",
        choices=["concurrency", "logic", "wiring", "contract", "stale-state",
                 "hardcoding", "security", "reliability", "unspecified"],
        help="[both] root-cause class — fingerprint-উপাদান",
    )
    parser.add_argument(
        "--allow-fingerprint-duplicate", action="store_true",
        help="[both] fingerprint-duplicate থাকলেও create (সচেতন ব্যতিক্রম, কারণ লিখুন)",
    )
    # ── #3211 AC-4: Alternative Solutions Ledger — বিদ্যমান issue-তে অ্যাপেন্ড ──
    parser.add_argument(
        "--alternative-solution", metavar="ISSUE", type=int, default=None,
        help="[#3211] নতুন issue নয় — বিদ্যমান issue-তে Alternative Solutions Table অ্যাপেন্ড",
    )
    parser.add_argument("--approach-a", default="", help="[#3211] Approach A (previous) বর্ণনা")
    parser.add_argument("--approach-b", default="", help="[#3211] Approach B (proposed) বর্ণনা")
    parser.add_argument("--recommendation", default="", help="[#3211] comparative recommendation")
    args = parser.parse_args()

    # #3211 AC-4: alt-solution পথ — সব dedup/creation লজিকের আগেই শেষ।
    if args.alternative_solution is not None:
        if not (args.approach_a and args.approach_b and args.recommendation):
            print("❌ --alternative-solution এর সাথে --approach-a/--approach-b/--recommendation বাধ্যতামূলক", file=sys.stderr)
            return 2
        ok, url_or_err = append_alternative_solution(
            args.alternative_solution, args.approach_a, args.approach_b, args.recommendation,
        )
        if ok:
            print(f"✅ Alternative Solutions Ledger appended to #{args.alternative_solution}: {url_or_err}")
            return 0
        print(f"❌ ledger-append ব্যর্থ: {url_or_err}", file=sys.stderr)
        return 1

    # বাংলা মন্তব্য: টাইপ-ভিত্তিক আর্গুমেন্ট-প্রহর — ভুল লেনে ভুল ফ্ল্যাগ ঢুকবে না।
    if args.type == "blocker" and (args.severity != "medium" or not args.check_duplicates):
        parser.error("--severity/--no-check-duplicates শুধু --type discovery-তে প্রযোজ্য")
    if args.type == "discovery" and args.allow_duplicate:
        parser.error("--allow-duplicate শুধু --type blocker-এ প্রযোজ্য")

    if args.type == "discovery" and args.check_duplicates and not args.dry_run:
        dupes = check_duplicates(args.title)
        if dupes:
            print(f"⚠️  Potential duplicate issues found ({len(dupes)}):")
            for d in dupes:
                print(f"  #{d['number']}: {d['title']} ({d['shared_words']}/{d['total_words']} words match)")
            print()
            print("If this is a genuine duplicate, do not create a new issue.")
            print("If this is a distinct issue, re-run with --no-check-duplicates.")
            return 1

    # ── #3088 §3: universal fingerprint dedup — শিরোনাম-শব্দের নয়, সেমান্টিক-জাল ──
    # বাংলা মন্তব্য: group-first নীতি — প্রথমে একই group-এর active কাজ, তারপরই creation।
    # blocker/discovery উভয় লেনেই; dry-run এ শুধু fingerprint-হিসাব (নেটওয়ার্ক-জাল নয়)।
    fp_marker_line = ""
    if not args.dry_run:
        if args.group:
            try:
                from group_taxonomy import group_first_lookup, validate_primary_group

                validation = validate_primary_group(args.group)
                print(f"🏷️  Group validation: {validation.message}")
                lookup = group_first_lookup(args.group)
                if lookup.lookup_ok and lookup.active_count:
                    states = lookup.issues_by_state()
                    print(f"👥 group:{args.group} active: {lookup.active_count} "
                          f"(in-progress: {len(states['in_progress'])}, has-pr: {len(states['has_pr'])})")
            except Exception as exc:  # noqa: BLE001 — group-রিপোর্ট advisory, কখনো creation আটকাবে না
                print(f"⚠️  group-first lookup skipped: {exc}")
        if not args.allow_fingerprint_duplicate:
            verdict = duplicate_guard(
                primary_group=args.group,
                problem=args.title,
                affected_scope=args.scope,
                root_cause_class=args.root_cause,
            )
            if verdict.action == "update_existing" and not args.allow_fingerprint_duplicate:
                # #3211 AC-2: hard-block নয় — living issue-তে observation অ্যাপেন্ড।
                print(f"♻️  [LIVING-ISSUE] {verdict.reason}")
                ok, url_or_err = append_living_observation(
                    issue_number=int(verdict.duplicate_of or 0),
                    title=args.title,
                    body=args.body,
                    fingerprint=verdict.fingerprint,
                    role=args.role,
                )
                if ok:
                    print(f"✅ Observation appended to living issue #{verdict.duplicate_of}: {url_or_err}")
                    print("   → নতুন issue তৈরি হয়নি (#3211 living-issue চুক্তি)।")
                    return 0
                print(f"⚠️  living-update ব্যর্থ: {url_or_err}")
                print("   → fail-honest: creation আটকানো হলো; ম্যানুয়ালি link/update করুন।")
                return 1
            if verdict.blocked:
                print(f"⛔ [GUARD-DUPLICATE] {verdict.reason}")
                print(f"   fingerprint: {verdict.fingerprint}")
                print("   → বিদ্যমান ইস্যু link/update করুন; নতুন creation নিষিদ্ধ।")
                print("   → (সচেতন ব্যতিক্রম: --allow-fingerprint-duplicate, কারণসহ কমেন্টে)")
                return 1
            print(f"✅ [GUARD-DUPLICATE] {verdict.reason} (fp={verdict.fingerprint})")
            fp_marker_line = prepend_marker("", verdict.fingerprint)
        else:
            print("⚠️  --allow-fingerprint-duplicate: dedup-জাল সচেতনভাবে বাইপাস — কারণ ইস্যুতে লিখুন।")
    else:
        # dry-run: নেটওয়ার্ক-কল ছাড়া fingerprint-হিসাব — প্রিভিউতে মার্কার দেখাবে।
        fp = fingerprint(args.group or "ungrouped", args.title, args.scope, args.root_cause)
        fp_marker_line = prepend_marker("", fp)

    # #3088: primary-group লেবেল প্রচার + fingerprint-মার্কার description-এর শুরুতে।
    if args.group:
        group_label = f"group:{args.group.strip().lower()}"
        if group_label not in (args.labels or []):
            args.labels = list(args.labels or []) + [group_label]
    if fp_marker_line:
        args.body = f"{fp_marker_line}\n{args.body}"

    if args.type == "blocker":
        result: BlockerIssueResult | DiscoveryIssueResult = create_blocker_issue(
            parent_issue=args.parent_issue,
            title=args.title,
            body=args.body,
            role=args.role,
            extra_labels=args.labels,
            dry_run=args.dry_run,
            repo_dir=ROOT_DIR,
            allow_duplicate=args.allow_duplicate,
        )
        success, err = result.success, result.error_message
    else:
        result = create_discovery_issue(
            parent_issue=args.parent_issue,
            title=args.title,
            body=args.body,
            role=args.role,
            severity=args.severity,
            extra_labels=args.labels,
            dry_run=args.dry_run,
        )
        success, err = result.success, (result.error or "")

    if args.format == "json":
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return 0 if success else 1

    if not success:
        print(f"❌ Failed to create {args.type} issue: {err}", file=sys.stderr)
        return 1

    if args.type == "blocker":
        print("✅ Prerequisite Blocker Issue Processed Successfully!")
        if result.duplicate_of:
            print(f"♻️  Existing Issue:  #{result.duplicate_of} (duplicate suppressed — #1997 guard)")
        print(f"🛑 New Issue:       #{result.new_issue_number or 'N/A'}")
        print(f"🔗 URL:             {result.new_issue_url}")
        print(f"📌 Blocks Parent:   #{result.parent_issue_number}")
        print(f"🎭 Target Lane:     {result.role}")
        print(f"🏷️  Labels:          {', '.join(result.labels)}")
        if result.is_dry_run:
            print("🔍 Mode:            Dry Run (No remote GitHub changes made)")
    else:
        print(f"✅ Discovery issue {'[DRY-RUN]' if result.is_dry_run else 'created'}:")
        print(f"   #{result.new_issue_number}: {result.title}")
        print(f"   URL: {result.new_issue_url}")
        print(f"   Role: {result.role} | Severity: {result.severity}")
        print(f"   Labels: {', '.join(result.labels)}")
        print(f"   Parent: #{result.parent_issue_number}")
        # (#2528) কনভেনশন-লাইন — PR body-তে পেস্ট করলে Discovery Gate পাস করে।
        print(f"   ── paste into your PR body: Discovery issue: #{result.new_issue_number}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
