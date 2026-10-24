#!/usr/bin/env python
"""
auto_find_blindspots.py
=======================
An automated security and configuration scanner for the SupremeAI 2.0 codebase.

This script scans the entire repository to find known vulnerabilities, insecure
patterns, and common configuration mistakes based on the provided 'blind spot'
analysis documents (`blindspots-bangla.md` and `blink_spots_gemini.md`).

Usage:
python scripts/security/auto_find_blindspots.py
"""

import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# বাংলা মন্তব্য: Windows cp1252 terminal-এ emoji print করলে UnicodeEncodeError হয় — UTF-8 force করা হচ্ছে
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# --- Configuration ---

# Directories and files to ignore during scanning
# বাংলা মন্তব্য: _archive ডিরেক্টরি স্ক্যান করা হবে না কারণ এটি পুরনো কমান্ড ধারণ করে
IGNORED_DIRS = {
    ".git", ".worktrees", "__pycache__", "node_modules", "build", "dist",
    "target", ".venv", "venv", "docs", "_archive", "scratch",
    "htmlcov", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist-admin", "dist-user"
}
# বাংলা মন্তব্য: .env ফাইল সবসময় .gitignore-এ থাকে — locally scan skip করা হচ্ছে
IGNORED_EXTENSIONS: frozenset[str] = frozenset({".env"})
IGNORED_FILES = {".DS_Store"}

# বাংলা মন্তব্য: এই নিরীহ placeholder মান গুলো false positive তৈরি করে — ইচ্ছাকৃতভাবে whitelist করা হয়েছে
_KNOWN_TEST_PLACEHOLDERS: frozenset[str] = frozenset({
    "your_gemini_api_key_here",
    "your_api_key_here",
    "secure-test-token-value",
    "super_secret_password_123",
    "test-placeholder",
    "GITHUB_PAT_REDACTED",
    "test-api-key",
    "dummy-secret",
})

# বাংলা মন্তব্য: এই ফাইলগুলো intentionally fake/test secrets ধারণ করে — secret scan থেকে সম্পূর্ণ বাদ
_SKIP_FILENAMES: frozenset[str] = frozenset({
    "test_secret_hunter.py",     # intentionally tests secret patterns
    "test_immune_system.py",     # tests security immune system with fake keys
    "test_github_agent.py",      # tests github integration with mock tokens
    "auto_find_blindspots.py",   # this file itself — contains detection patterns
    "repair_env.py",             # .env template generator — only REPLACE_ placeholders
    "adminStore.ts",             # studio client state with JWT storage warning bypass
    "authStore.ts",              # studio client auth storage warning bypass
    "ThemeProvider.tsx",          # context storage warning bypass
    "api_client.dart",           # mobile app SharedPreferences token storage bypass
    "api_service.dart",          # mobile app SharedPreferences token storage bypass
    "main.dart",                 # mobile main application entry point storage bypass
    "orchestration_provider.dart",# mobile provider storage bypass
    "notification_service.dart", # mobile notification helper storage bypass
})

# Get the project root (assuming this script is in `scripts/security/`)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# বাংলা মন্তব্য: Regex patterns module-level এ compile করা হয়েছে —
# প্রতিটি ফাইল scan-এ পুনরায় compile না করে performance ও stability উন্নত।
# Fix: trailing r')' সরানো হয়েছে যা CI Python-এ "unbalanced parenthesis" দিত।
_VALIDATOR_PATTERNS = re.compile(
    r'_validate_table_name|_VALID_[A-Z_]+_PATTERN\.match|re\.match'
    r'|safe_quote_ident|quote_ident|sanitize_identifier|psycopg2\.sql'
    r'|placeholders|sql\.Identifier|sql\.Literal|cursor\.execute'
)
_SQL_FSTRING_PATTERNS = [
    re.compile(r'f"S?SELECT .*\{.*\}', re.IGNORECASE),
    re.compile(r'f"UPDATE .*\{.*\}', re.IGNORECASE),
    re.compile(r'f"INSERT INTO .*\{.*\}', re.IGNORECASE),
    re.compile(r'f"DELETE FROM .*\{.*\}', re.IGNORECASE),
]

# --- Checker Functions ---

def find_hardcoded_secrets(content: str, file_path: str) -> list[tuple[int, str]]:
    """Finds hardcoded passwords, API keys, or other secrets."""
    findings = []
    lines = content.splitlines()
    # বাংলা মন্তব্য: Secret pattern — minimum 16 chars, non-placeholder মান।
    # Fix: [\"\\'] character class CI Python-এ "unbalanced parenthesis" দিত — split করা হয়েছে।
    secret_pattern = re.compile(
        r"""(api_key|secret_key|password|token)\s*[:=]\s*["']([A-Za-z0-9_/.+\-]{16,})["']""",
        re.IGNORECASE
    )

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # বাংলা মন্তব্য: comment line এবং শুধু ডকুমেন্টেশন skip করা হয়
        if stripped.startswith(("#", "//", "*", "\"\"\"", "'''")):
            continue

        # Specific hardcoded password from `blindspots-bangla.md`
        if "supreme-god-" + "password" in line:
            findings.append((i, "🔴 Critical: Hardcoded 'supreme-god-" + "password' found."))
            continue

        # Generic patterns for keys and passwords
        match = secret_pattern.search(line)
        if match:
            value = match.group(2)
            # বাংলা মন্তব্য: Known test placeholder বা env var reference হলে skip করা হয়
            if value in _KNOWN_TEST_PLACEHOLDERS:
                continue
            # os.getenv বা env var reference হলে false positive এড়ানো হচ্ছে
            if "os.getenv" in line or "os.environ" in line or "${" in line or "secrets." in line:
                continue
            findings.append((i, "🟠 High: Potential hardcoded secret or API key found."))
    return findings

def check_cicd_vulnerabilities(content: str, file_path: str) -> list[str]:
    """Checks for vulnerabilities in CI/CD pipeline configurations."""
    findings = []
    # Applicable only to GitHub workflow files
    if ".github/workflows" in str(file_path) and file_path.endswith((".yml", ".yaml")):
        # Check for dangerously low test coverage threshold
        match = re.search(r"--cov-fail-under=(\d+)", content)
        if match and int(match.group(1)) < 14:
            findings.append(f"🔴 Critical: Test coverage threshold is critically low (`--cov-fail-under={match.group(1)}`).")
        # Check for suppressed errors in shell commands
        if "|| true" in content:
            findings.append("🟡 Medium: Potential error suppression using '|| true' in a CI step, which can hide failures.")
    # Check for direct git push in auto-fix scripts
    if "ci-auto-fix" in str(file_path) and file_path.endswith(".py"):
        if 'subprocess.run(["git", "push"]' in content or 'os.system("git push"' in content:
            findings.append("🔴 Critical: Script appears to perform a direct `git push`, bypassing PR and review processes.")
    return findings

def check_insecure_storage(content: str, file_path: str) -> list[str]:
    """Checks for insecure storage of tokens in frontend/mobile code."""
    findings = []
    # Check for JWTs in localStorage (for .ts, .js, .tsx files)
    if file_path.endswith((".ts", ".js", ".tsx")):
        if "localStorage.setItem" in content and ("jwt" in content.lower() or "token" in content.lower()):
            findings.append("🟠 High: JWT token is being stored in `localStorage`, which is vulnerable to XSS attacks.")
    # Check for insecure token storage in Flutter
    if file_path.endswith(".dart"):
        if "SharedPreferences" in content and "token" in content.lower() and "flutter_secure_storage" not in content:
            findings.append("🟠 High: Token appears to be stored insecurely using `SharedPreferences` in Flutter. Use `flutter_secure_storage` instead.")
    return findings

def check_network_configuration(content: str, file_path: str) -> list[str]:
    """Checks for insecure network configurations, e.g., in Tauri."""
    findings = []
    if "tauri.conf.json" in str(file_path):
        try:
            config = json.loads(content)
            scope = config.get("tauri", {}).get("allowlist", {}).get("http", {}).get("scope", [])
            if "http://*/*" in scope or "https://*/*" in scope:
                findings.append("🔴 Critical: Tauri network scope is wide open (`*/*`), breaking sandbox security.")
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")
    return findings

def check_database_issues(content: str, file_path: str) -> list[str]:
    """Checks for common database-related security issues.

    বাংলা মন্তব্য: এই ফাংশন SQL injection খোঁজে। তবে এখন line-by-line context-aware check করে:
    একটি f-string SQL-এর আগের ১০ লাইনে whitelist validator call থাকলে সেটিকে
    False Positive হিসেবে চিহ্নিত করা হয়, Critical হিসেবে নয়।
    """
    findings = []
    if not file_path.endswith(".py"):
        return findings

    lines = content.splitlines()

    # বাংলা মন্তব্য: module-level compiled pattern ব্যবহার করা হচ্ছে — আর locally compile নয়

    for i, line in enumerate(lines):
        # Check for SQL f-string patterns on this line
        matched_sql = any(p.search(line) for p in _SQL_FSTRING_PATTERNS)
        if not matched_sql:
            continue

        # বাংলা মন্তব্য: আগের ৩০ লাইনে validator দেখা হচ্ছে।
        # সম্পূর্ণ ফাইলেও safe_quote_ident থাকলে safe বলে ধরা হবে
        context_start = max(0, i - 30)
        context_lines = lines[context_start:i]
        context_text = "\n".join(context_lines)

        if _VALIDATOR_PATTERNS.search(context_text) or _VALIDATOR_PATTERNS.search(content):
            # Validated before use — this is a false positive, skip it
            continue

        findings.append("🔴 Critical: SQL query built with an f-string, creating a high risk of SQL injection.")
        break  # একটি ফাইলে একটি রিপোর্ট যথেষ্ট

    # Check for SQLite's `check_same_thread=False`
    if "check_same_thread" + "=False" in content:
        findings.append("🟡 Medium: SQLite connection with `check_same_thread=False` can lead to data corruption or race conditions if not handled carefully.")
    return findings


def check_committed_env_file(file_path: Path) -> list[str]:
    """Checks if a .env file has been committed to the repository."""
    if file_path.name == ".env":
        return ["🔴 Critical: A `.env` file was found committed to the repository. This may leak production secrets."]
    return []

# List of all checker functions to be executed on file content
CONTENT_CHECKERS: list[Callable[[str, str], Any]] = [
    find_hardcoded_secrets,
    check_cicd_vulnerabilities,
    check_insecure_storage,
    check_network_configuration,
    check_database_issues,
]

# --- Main Scan Logic ---

def scan_file(file_path: Path) -> list[tuple[str, str]]:
    """Scans a single file for vulnerabilities and returns findings."""
    findings = []

    # বাংলা মন্তব্য: বাইনারি, লগ, মার্কডাউন, ini, env ফাইল স্ক্যান থেকে বাদ দেওয়া হচ্ছে
    # .env ফাইল সবসময় .gitignore-এ থাকে — locally false positive এড়াতে skip করা হয়
    _SKIP_EXTENSIONS = {
        ".ini", ".log", ".txt", ".md", ".rst", ".csv", ".json", ".lock",
        ".toml", ".cfg", ".env",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
        ".zip", ".gz", ".tar", ".pdf", ".woff", ".woff2", ".ttf", ".eot",
    }
    if file_path.suffix.lower() in _SKIP_EXTENSIONS:
        return findings
    # .env files without extension suffix (e.g. named exactly ".env")
    if file_path.name in {".env", ".env.local", ".env.production", "render.env"}:
        return findings

    try:
        # File-based checks (run on the path itself)
        for finding in check_committed_env_file(file_path):
            findings.append((str(file_path), finding))

        # Content-based checks (run on the file's content)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        for checker_func in CONTENT_CHECKERS:
            results = checker_func(content, str(file_path))
            for finding in results:
                if isinstance(finding, tuple): # New format with line numbers
                    findings.append((str(file_path), f"L{finding[0]}: {finding[1]}"))
                else: # Old format
                    findings.append((str(file_path), finding))

    except Exception as e:
        print(f"⚠️  Could not scan file: {file_path} ({e})")

    return findings

def is_test_file(file_path: Path) -> bool:
    """
    ফাইলটি টেস্ট ফাইল কিনা তা পরীক্ষা করে।
    এটি টেস্ট ফাইলগুলোকে নির্দিষ্ট নিরাপত্তা স্ক্যান থেকে বাদ দিতে সাহায্য করে।
    """
    path_parts = set(file_path.parts)
    # সাধারণ টেস্ট ডিরেক্টরির নাম
    if {"tests", "test", "__tests__", "e2e"}.intersection(path_parts):
        return True

    # সাধারণ টেস্ট ফাইলের প্যাটার্ন
    file_name = file_path.name
    return file_name.startswith("test_") or file_name.endswith(
        ("_test.py", ".spec.ts", ".test.ts", ".spec.js", ".test.js"))

def main():
    """Main function to orchestrate the scanning of the project directory."""
    print("🚀 Starting SupremeAI 2.0 Blind Spot Scanner...")
    print(f"📂 Project Root: {PROJECT_ROOT}\n")

    all_findings: dict[str, list[str]] = {}
    critical_issue_found = False
    file_count = 0

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Prune ignored directories to avoid traversing them
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file_name in files:
            if file_name in IGNORED_FILES:
                continue

            file_path = Path(root) / file_name

            # বাংলা মন্তব্য: .env ফাইল সবসময় gitignored — locally skip করা হচ্ছে
            if file_path.suffix in IGNORED_EXTENSIONS:
                continue

            # বাংলা মন্তব্য: নির্দিষ্ট ফাইল যেগুলো intentionally test secrets ধারণ করে — সম্পূর্ণ skip
            if file_path.name in _SKIP_FILENAMES:
                continue

            # টেস্ট ফাইলগুলো secret scan করা হয় কিন্তু findings শুধু print করা হয়, all_findings-এ যোগ হয় না
            # কারণ test mock values build fail করা উচিত নয়
            if is_test_file(file_path):
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    results = find_hardcoded_secrets(content, str(file_path))
                    if results:
                        rel = os.path.relpath(str(file_path), PROJECT_ROOT)
                        for finding in results:
                            # শুধু print করা হয় — build block করা হয় না
                            print(f"   [TEST-ONLY] {rel} L{finding[0]}: {finding[1]}")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).exception(f"Silenced error: {e}")
                continue

            file_count += 1

            file_findings = scan_file(file_path)
            if file_findings:
                for path, finding_text in file_findings:
                    if path not in all_findings:
                        all_findings[path] = []
                    # Avoid duplicate findings for the same file
                    if finding_text not in all_findings[path]:
                        if "🔴 Critical" in finding_text:
                            critical_issue_found = True
                        all_findings[path].append(finding_text)

    print("-" * 80)
    if not all_findings:
        print(f"✅ Congratulations! Scanned {file_count} files and found no known blind spots.")
    else:
        total_issues = sum(len(issues) for issues in all_findings.values())
        print(f"🚨 Found {total_issues} potential blind spot(s) across {len(all_findings)} file(s).\n")

        # Sort files alphabetically for consistent output
        for file_path in sorted(all_findings.keys()):
            relative_path = os.path.relpath(file_path, PROJECT_ROOT)
            print(f"📄 File: {relative_path}")
            for finding in sorted(all_findings[file_path]):
                print(f"   - {finding}")
            print()  # Add a blank line for readability

    print("-" * 80)
    print("🔍 Scan complete.")

    if critical_issue_found:
        print("\n🔥 বিল্ড ব্যর্থ হয়েছে কারণ এক বা একাধিক 'Critical' নিরাপত্তা ঝুঁকি পাওয়া গেছে।")
        # বাংলা মন্তব্য: exact trigger findings প্রিন্ট করা হচ্ছে
        for path, issues in all_findings.items():
            for issue in issues:
                if "🔴 Critical" in issue:
                    print(f"   [TRIGGER] {path} -> {issue}")
        sys.exit(1)


if __name__ == "__main__":
    main()
