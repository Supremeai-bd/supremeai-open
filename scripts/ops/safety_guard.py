#!/usr/bin/env python3
# 🛡️ সেফটি গার্ড - ক্রিটিক্যাল ফাইলের জন্য অনুমোদন সিস্টেম
# বাংলা মন্তব্য: এআই এজেন্ট যেন ক্রিটিক্যাল ফাইলে (auth, security, payment) নিজে থেকে কোনো চেঞ্জ করতে না পারে তা নিশ্চিত করে

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# SIL-0d: discover instead of hardcode — the approval-requests file may live in
# several historical locations; find it instead of pointing at a stale one.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib.auto_discovery import existing_paths
except ImportError:  # standalone use (e.g. vendored copy) — fall back to a local filter
    existing_paths = None

try:
    from loguru import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("safety_guard")


def find_repo_root() -> Path:
    """স্বয়ংক্রিয়ভাবে রিপোজিটরি রুট ডিরেক্টরি নির্ণয় করুন"""
    curr = Path(__file__).resolve().parent
    while curr != curr.parent:
        if (curr / ".git").exists() or (curr / "backend").exists():
            return curr
        curr = curr.parent
    return Path.cwd()


class SafetyGuard:
    """
    ক্রিটিক্যাল ফাইলের জন্য সেফটি চেক সিস্টেম

    কাজ:
    - ক্রিটিক্যাল ফাইল চেঞ্জ ডিটেক্ট করা
    - অনুমোদন প্রয়োজন অনুযায়ী ব্লক করা
    - চেঞ্জলগ এবং নোটিফিকেশন তৈরি করা
    """

    CRITICAL_PATTERNS = [
        # অথেন্টিকেশন এবং অথরাইজেশন
        r".*/(auth|authentication|permission|rbac).*\.py$",
        r".*/(security|jwt|token).*\.py$",

        # পেমেন্ট এবং বিলিং
        r".*/(payment|billing|pricing|subscription).*\.py$",

        # ডাটাবেস এবং স্টোরেজ
        r".*/(database|db_|migration).*\.py$",
        r".*/(alembic)/.*\.py$",

        # অ্যাডমিন এবং গভর্নেন্স
        r".*/(admin|god|superuser).*\.py$",

        # সিকিউরিটি রিলেটেড
        r".*/(secret|credential|vault|encryption).*\.py$",

        # CI/CD এবং ইনফ্রাস্ট্রাকচার
        r".*\.github/workflows/.*\.yml$",
        r".*/(terraform|docker|kubernetes).*",
    ]

    APPROVAL_REQUIRED_ADMINS = [
        "admin@supremeai.dev",
        "security@supremeai.dev",
        "devops@supremeai.dev"
    ]

    # SIL-0d: every historical location the approval file has lived at, tried
    # in order — first hit wins, so the file can move without breaking us.
    APPROVAL_REQUEST_CANDIDATES = (
        "approval_requests.json",
        "config/approval_requests.json",
        "logs/approval_requests.json",
        "data/approval_requests.json",
        ".github/approval_requests.json",
    )
    # Write target when NO candidate exists (under repo root; logs/ is
    # gitignored so runtime approval state never pollutes git).
    DEFAULT_APPROVAL_REQUEST = "logs/approval_requests.json"

    def __init__(self, repo_root: str = ""):
        self.repo_root = Path(repo_root) if repo_root else find_repo_root()
        self.critical_files_log = self.repo_root / "logs" / "critical_files_changes.json"
        self.approval_requests = self._discover_approval_requests_file()

    def _discover_approval_requests_file(self) -> Path:
        """First existing candidate, else the default write target (NOT created here).

        Read-only modes never create anything — a missing file is reported, not
        fabricated.  Directories are only made when an approval is actually
        written (see _log_approval_request).
        """
        candidates = [self.repo_root / rel for rel in self.APPROVAL_REQUEST_CANDIDATES]
        found = existing_paths(candidates) if existing_paths else [c for c in candidates if c.exists()]
        if found:
            logger.info(f"🛡️ approval requests file discovered: {found[0]}")
            return found[0]
        return self.repo_root / self.DEFAULT_APPROVAL_REQUEST

    def _ensure_log_dirs(self):
        """লগ ডিরেক্টরি তৈরি করুন (write-time only — পড়ার সময় কিছু তৈরি হয় না)"""
        self.critical_files_log.parent.mkdir(parents=True, exist_ok=True)
        self.approval_requests.parent.mkdir(parents=True, exist_ok=True)

    def is_critical_file(self, file_path: str) -> bool:
        """ফাইলটি ক্রিটিক্যাল কিনা চেক করুন"""
        normalized_path = str(file_path).replace("\\", "/")

        for pattern in self.CRITICAL_PATTERNS:
            if re.match(pattern, normalized_path):
                return True

        return False

    def get_file_risk_level(self, file_path: str) -> str:
        """ফাইলের ঝুঁকির মাত্রা বের করুন"""
        normalized_path = str(file_path).replace("\\", "/").lower()

        # সর্বোচ্চ ঝুঁকিপূর্ণ ফাইল
        if any(term in normalized_path for term in ["admin_god", "superuser", "secret", "payment"]):
            return "CRITICAL"

        # উচ্চ ঝুঁকি
        if any(term in normalized_path for term in ["auth", "permission", "security", "token", "credential"]):
            return "HIGH"

        # মধ্যম ঝুঁকি
        if any(term in normalized_path for term in ["database", "migration", "workflow"]):
            return "MEDIUM"

        return "LOW"

    def detect_changes(self, file_path: str) -> dict[str, Any]:
        """গিট দিয়ে ফাইলের চেঞ্জ ডিটেক্ট করুন"""
        try:
            # স্টেজড চেঞ্জ পান
            result = subprocess.run(
                ["git", "diff", "--cached", str(file_path)],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0 or not result.stdout:
                return {"has_changes": False, "diff": None}

            diff_content = result.stdout

            return {
                "has_changes": True,
                "diff": diff_content,
                "additions": diff_content.count("\n+"),
                "deletions": diff_content.count("\n-"),
                "total_changes": diff_content.count("\n+") + diff_content.count("\n-")
            }

        except Exception as e:
            logger.error(f"Error detecting changes for {file_path}: {e}")
            return {"has_changes": False, "error": str(e)}

    def check_ai_authored(self, file_path: str) -> bool:
        """চেক করুন ফাইলটি এআই দিয়ে অথর হয়েছে কিনা"""
        try:
            full_path = self.repo_root / file_path if not Path(file_path).is_absolute() else Path(file_path)
            if not full_path.exists():
                return False
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                first_lines = f.read(500).lower()

            ai_markers = [
                "generated by",
                "auto-generated",
                "ai-generated",
                "machine-generated",
                "claude",
                "gpt-",
                "gemini"
            ]

            return any(marker in first_lines for marker in ai_markers)

        except Exception as e:
            logger.warning(f"Could not check AI-authorship marker for {file_path}: {e}")
            return False

    def block_or_approve(
        self,
        file_path: str,
        author: str = "ai-agent",
        reason: str = ""
    ) -> dict[str, Any]:
        """চেঞ্জ অনুমোদন করতে হবে কিনা সিদ্ধান্ত নিন"""
        if not self.is_critical_file(file_path):
            return {
                "allowed": True,
                "reason": "File is not critical",
                "requires_approval": False
            }

        risk_level = self.get_file_risk_level(file_path)
        is_ai_authored = self.check_ai_authored(file_path)

        # এআই অথরড চেঞ্জ সবসময় ব্লক করুন
        if is_ai_authored or author == "ai-agent":
            self._log_approval_request(file_path, author, risk_level, reason)

            return {
                "allowed": False,
                "reason": f"AI-generated changes to critical file ({risk_level} risk) require manual approval",
                "requires_approval": True,
                "approval_contacts": self.APPROVAL_REQUIRED_ADMINS,
                "risk_level": risk_level
            }

        # ম্যানুয়াল চেঞ্জ কিন্তু ক্রিটিক্যাল ফাইল
        if risk_level in ["CRITICAL", "HIGH"]:
            return {
                "allowed": True,
                "reason": f"Manual change to {risk_level} risk file (logged for audit)",
                "requires_approval": False,
                "requires_review": True,
                "risk_level": risk_level
            }

        return {
            "allowed": True,
            "reason": "Low-risk change",
            "requires_approval": False
        }

    def _log_approval_request(
        self,
        file_path: str,
        author: str,
        risk_level: str,
        reason: str
    ):
        """অনুমোদন অনুরোধ লগ করুন (write mode — এখানেই ফাইল/ডির প্রথম তৈরি হয়)"""
        try:
            self._ensure_log_dirs()
            created_here = not self.approval_requests.exists()
            requests = []
            if self.approval_requests.exists():
                with open(self.approval_requests, "r", encoding="utf-8") as f:
                    requests = json.load(f)

            request = {
                "timestamp": datetime.now().isoformat(),
                "file": str(file_path),
                "author": author,
                "risk_level": risk_level,
                "reason": reason,
                "status": "pending",
                "approval_deadline": None
            }

            requests.append(request)

            with open(self.approval_requests, "w", encoding="utf-8") as f:
                json.dump(requests, f, indent=2, ensure_ascii=False)

            if created_here:
                logger.info(f"🛡️ created approval requests file at {self.approval_requests}")
            logger.warning(
                f"🛑 [SAFETY GUARD] Critical file change blocked: {file_path} "
                f"(Author: {author}, Risk: {risk_level})"
            )

        except Exception as e:
            logger.error(f"Failed to log approval request: {e}")

    def generate_safety_report(self) -> dict[str, Any]:
        """সেফটি চেক রিপোর্ট তৈরি করুন (read mode — ফাইল না থাকলে পরিষ্কার বার্তা, crash নয়)"""
        pending_approvals = []
        missing_note = None

        if self.approval_requests.exists():
            try:
                with open(self.approval_requests, "r", encoding="utf-8") as f:
                    all_requests = json.load(f)
                    pending_approvals = [r for r in all_requests if r.get("status") == "pending"]
            except Exception as e:
                logger.warning(f"Could not load approval requests: {e}")
                missing_note = f"approval requests file unreadable: {self.approval_requests} ({e})"
        else:
            searched = ", ".join(str(self.repo_root / c) for c in self.APPROVAL_REQUEST_CANDIDATES)
            missing_note = (
                f"approval requests file not found (searched: {searched}); "
                "it is created automatically the first time a critical-file change is blocked"
            )
            logger.warning(f"🛡️ {missing_note}")

        try:
            file_ref = str(self.approval_requests.relative_to(self.repo_root))
        except ValueError:
            file_ref = str(self.approval_requests)

        return {
            "generated_at": datetime.now().isoformat(),
            "approval_requests_file": file_ref if self.approval_requests.exists() else "NOT FOUND",
            "pending_approvals": len(pending_approvals),
            "critical_files_protected": len(self.CRITICAL_PATTERNS),
            "recent_blocked_changes": pending_approvals[:5],
            "approval_contacts": self.APPROVAL_REQUIRED_ADMINS,
            "note": missing_note,
        }


def create_precommit_hook(repo_root: str = ""):
    """প্রি-কমিট হুক তৈরি করুন যা ক্রিটিক্যাল ফাইল চেঞ্জ ব্লক করে"""
    root = Path(repo_root) if repo_root else find_repo_root()
    hook_path = root / ".git" / "hooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    hook_content = """#!/bin/bash
# 🛡️ Safety Guard Pre-commit Hook

python3 << 'EOF'
import sys
from scripts.safety_guard import SafetyGuard

guard = SafetyGuard(".")
blocked = False

# স্টেজড ফাইল চেক করুন
import subprocess
result = subprocess.run(
    ["git", "diff", "--cached", "--name-only"],
    capture_output=True,
    text=True
)

for file in result.stdout.strip().split("\\n"):
    if not file:
        continue

    check = guard.block_or_approve(file)
    if not check.get("allowed", False):
        print(f"❌ BLOCKED: {file}")
        print(f"   Reason: {check['reason']}")
        blocked = True

if blocked:
    print("\\n⚠️ Critical files modified. Approval required from:")
    for contact in guard.APPROVAL_REQUIRED_ADMINS:
        print(f"   - {contact}")
    sys.exit(1)
EOF

exit $?
"""

    hook_path.write_text(hook_content, encoding="utf-8")
    os.chmod(hook_path, 0o755)
    logger.info(f"✅ Pre-commit hook installed at {hook_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SupremeAI Safety Guard CLI")
    parser.add_argument("file", nargs="?", default=None, help="File to check")
    parser.add_argument("--check-only", action="store_true", help="Only check status without blocking execution")
    parser.add_argument("--report-json", action="store_true", help="Output safety report in JSON format")
    parser.add_argument("--output-file", help="Write report to specified output file path")

    args = parser.parse_args()

    guard = SafetyGuard()
    if args.file and not args.file.startswith("--"):
        result = guard.block_or_approve(args.file)
        result_json = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output_file:
            Path(args.output_file).write_text(result_json, encoding="utf-8")
        else:
            print(result_json)
        if not result.get("allowed", False) and not args.check_only:
            sys.exit(1)
    else:
        report = guard.generate_safety_report()
        report_json = json.dumps(report, indent=2, ensure_ascii=False)
        if args.output_file:
            Path(args.output_file).write_text(report_json, encoding="utf-8")
        else:
            print(report_json)
        if report.get("pending_approvals", 0) > 0 and not args.check_only:
            sys.exit(1)
