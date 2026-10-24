import re
import sys
from pathlib import Path

# --- Merged from fast_secret_scan.py ---

#!/usr/bin/env python3
"""
Fast Secret Scanner for Pre-commit Hook
=======================================
বাংলা: শুধুমাত্র সাধারণ সিক্রেট প্যাটার্ন চেক করে - দ্রুত স্ক্যানের জন্য
"""

import subprocess


def get_staged_files() -> list[str]:
    """Get list of staged files for commit."""
    try:
        result = subprocess.run(['git', 'diff', '--cached', '--name-only'],
                                capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        print("⚠️  Not in a git repository or no staged files found.")
        return []

def fast_secret_scan(file_paths: list[str]) -> tuple[bool, list[tuple[str, int, str]]]:
    """Fast scan for common secret patterns in staged files."""
    # Common secret patterns that can be detected quickly
    patterns = [
        (r'(?i)(password|secret|key|token|api[_-]?key)\s*[=:]\s*["\'][^"\']{10,}', 'Potential secret/password in plain text'),
        (r'(?i)aws[_-]?(access|secret)[_=][^"\']{10,}', 'AWS credential detected'),
        (r'(?i)github[_-]?(token|key)[_=][^"\']{10,}', 'GitHub token/key detected'),
        (r'(ssh-rsa|ssh-ed25519)\s+[A-Za-z0-9+/]{20,}={0,3}\s+.*', 'SSH key detected'),
        (r'-----BEGIN (RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY-----', 'Private key detected'),
    ]

    findings = []

    for file_path in file_paths:
        if not file_path or file_path.startswith('.'):
            continue

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                for pattern, description in patterns:
                    if re.search(pattern, line):
                        findings.append((file_path, line_num, description))

        except Exception:
            # Skip binary files or unreadable files
            continue

    return len(findings) == 0, findings

def main():
    """Main function for fast secret scanning."""
    print("🔍 Running fast secret scan...")

    staged_files = get_staged_files()
    if not staged_files:
        print("✅ No staged files to scan.")
        return 0

    # Filter for text-based files
    text_files = [f for f in staged_files if any(f.endswith(ext) for ext in
                                               ['.py', '.js', '.ts', '.tsx', '.jsx', '.json',
                                                '.yaml', '.yml', '.toml', '.txt', '.md', '.env'])]

    if not text_files:
        print("✅ No text files to scan.")
        return 0

    is_clean, findings = fast_secret_scan(text_files)

    if is_clean:
        print("✅ No secrets detected in staged files.")
        return 0
    else:
        print("\n❌ Potential secrets detected:")
        for file_path, line_num, description in findings:
            print(f"  - {file_path}:{line_num}: {description}")

        print("\n⚠️  Commit blocked due to potential secrets detected.")
        return 1

if __name__ == "__main__":
    sys.exit(main())


# --- Merged from secret_scan_ci.py ---

#!/usr/bin/env python3
"""
Secret Scanning CI Pipeline Script
====================================

CI/CD pipeline script for automated secret scanning using SecretHunter.
Integrates with GitHub Actions for pre-commit and PR checks.

বাংলা: সিক্রেট স্ক্যানিং-এর জন্য CI/CD পাইপলাইন স্ক্রিপ্ট — SecretHunter ব্যবহার করে
প্রি-কমিট এবং PR চেকের জন্য GitHub Actions-এর সাথে ইন্টিগ্রেটেড।

Usage:
    # Scan staged files (pre-commit hook)
    python scripts/devops/secret_scan_ci.py --staged

    # Scan entire codebase (CI pipeline)
    python scripts/devops/secret_scan_ci.py --full

    # Scan specific directory
    python scripts/devops/secret_scan_ci.py --path backend/core

    # Generate pre-commit hook config
    python scripts/devops/secret_scan_ci.py --install-hook
"""



import argparse
import os
import sys

# Ensure we can import core modules from backend directory
project_root = Path(__file__).resolve().parent.parent.parent
backend_dir = project_root / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

try:
    from core.security.secret_hunter import SecretHunter
except ImportError:
    try:
        from backend.core.security.secret_hunter import SecretHunter
    except ImportError:
        print("⚠️  Could not import SecretHunter. Ensure dependencies are installed.")
        SecretHunter = None


# ── Constants ──────────────────────────────────────────────────────────────────

# GitHub Actions output file
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT", "")

# Exit codes
EXIT_SUCCESS = 0
EXIT_SECRETS_FOUND = 1

# Minimum severity to fail CI
CI_FAIL_SEVERITY = "high"  # Fail on critical and high findings

# File patterns to scan
SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".env", ".sh", ".dart", ".go", ".rs", ".java", ".rb",
    ".php", ".swift", ".kt", ".cs", ".ini", ".cfg", ".conf",
}


def _is_excluded(path: Path) -> bool:
    """Mirror SecretHunter's own directory/file exclusions for staged-file scans.

    বাংলা মন্তব্য: full-codebase স্ক্যানে tests/ ও test_* ফাইল বাদ পড়ে, কিন্তু staged
    স্ক্যানে পড়ত না — ফলে স্ক্যানারের নিজের ডকুমেন্টেড fixture কী কমিট ব্লক করত।
    """
    parts = set(path.parts)
    return bool(parts & {"node_modules", "__pycache__", "tests"}) or path.name.startswith("test_")


def get_staged_files() -> list[Path]:
    """Get list of staged files from git.

    Returns:
        List of staged file paths
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent.parent,
        )
        files = [Path(f.strip()) for f in result.stdout.split("\n") if f.strip()]
        return [
            f
            for f in files
            if f.suffix in SCAN_EXTENSIONS and not _is_excluded(f)
        ]
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"⚠️  Git not available or not a git repository: {e}")
        return []


def scan_staged_files(hunter: SecretHunter) -> bool:
    """Scan only staged files for secrets.

    Args:
        hunter: SecretHunter instance

    Returns:
        True if no secrets found, False otherwise
    """
    staged_files = get_staged_files()
    if not staged_files:
        print("✅ No staged files to scan.")
        return True

    # Filter out deleted files
    existing_files = [f for f in staged_files if f.exists()]
    if not existing_files:
        return True

    print(f"🔍 Scanning {len(existing_files)} staged files for secrets...")
    findings = []

    for file_path in existing_files:
        file_findings = hunter.gitleaks.scan_file(file_path)
        findings.extend(file_findings)

    if findings:
        critical = [f for f in findings if f.severity == "critical"]
        high = [f for f in findings if f.severity == "high"]

        print("\n❌ SECRETS DETECTED IN STAGED FILES!")
        print(f"   Critical: {len(critical)}, High: {len(high)}")

        for f in findings:
            if f.severity in ("critical", "high"):
                print(f"\n   📁 {f.file_path}:{f.line_number}")
                print(f"   🔑 Type: {f.secret_type} (Severity: {f.severity})")
                print(f"   🔧 Fix: {f.remediation}")
                print(f"   📝 Matched: {f.matched_text[:60]}...")

        return False

    print("✅ No secrets found in staged files.")
    return True


def scan_codebase(hunter: SecretHunter, path: str | None = None) -> bool:
    """Scan the entire codebase or a specific path for secrets.

    Args:
        hunter: SecretHunter instance
        path: Specific path to scan (None = whole codebase)

    Returns:
        True if no critical/high secrets found, False otherwise
    """
    target = path or str(Path(__file__).resolve().parent.parent.parent / "backend")

    print(f"🔍 Scanning codebase: {target}")
    print("   This may take a while...")

    # Run the scan
    import asyncio

    report = asyncio.run(hunter.scan_codebase(target, use_ai=False, min_severity=CI_FAIL_SEVERITY))

    # Print summary
    findings = report.findings
    critical_count = report.summary.get("critical_count", 0)
    high_count = report.summary.get("high_count", 0)

    print(f"\n📊 Scan Report: {report.scan_id}")
    print(f"   Files scanned: {report.total_files}")
    print(f"   Total findings: {len(findings)}")
    print(f"   Critical: {critical_count}")
    print(f"   High: {high_count}")

    if findings:
        # Print top findings
        print("\n📋 Top Findings:")
        for f in findings[:10]:  # Show first 10
            severity_icon = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️"}
            icon = severity_icon.get(f.severity, "❓")
            print(f"   {icon} [{f.severity.upper()}] {f.file_path}:{f.line_number}")
            print(f"      Type: {f.secret_type}")
            if f.ai_confidence > 0:
                print(f"      AI Confidence: {f.ai_confidence:.0%}")

        if findings:
            print(f"\n   ... and {len(findings) - min(10, len(findings))} more findings")

    # Set GitHub Actions output
    if GITHUB_OUTPUT:
        _set_github_output("findings_count", str(len(findings)))
        _set_github_output("critical_count", str(critical_count))
        _set_github_output("high_count", str(high_count))

    if critical_count > 0 or high_count > 0:
        print(f"\n❌ FAILED: {critical_count + high_count} critical/high secrets detected!")
        return False

    print("\n✅ PASSED: No critical or high severity secrets detected.")
    return True


def install_pre_commit_hook() -> None:
    """Install SecretHunter pre-commit hook."""
    hook_dir = Path(".git/hooks")
    hook_path = hook_dir / "pre-commit"

    if not hook_dir.exists():
        print("❌ Not a git repository. Cannot install pre-commit hook.")
        sys.exit(1)

    # Generate hook script using SecretHunter
    if SecretHunter:
        hunter = SecretHunter()
        hook_content = hunter.generate_pre_commit_hook()
    else:
        # Fallback hook content
        hook_content = """#!/bin/bash
echo "🔍 Running SecretHunter pre-commit scan..."
python scripts/devops/secret_scan_ci.py --staged
if [ $? -ne 0 ]; then
    echo "❌ Secret scan failed! Fix issues before committing."
    exit 1
fi
echo "✅ No secrets detected."
exit 0
"""

    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(hook_content)

    # Make executable on Unix
    if sys.platform != "win32":
        hook_path.chmod(0o755)

    print(f"✅ Pre-commit hook installed at {hook_path}")


def _set_github_output(name: str, value: str) -> None:
    """Set GitHub Actions output variable.

    Args:
        name: Output variable name
        value: Output value
    """
    if GITHUB_OUTPUT:
        try:
            with open(GITHUB_OUTPUT, "a") as f:
                f.write(f"{name}={value}\n")
        except OSError as e:
            print(f"⚠️  Failed to write GitHub output: {e}")


def main() -> int:
    """Main entry point for CI secret scanning.

    Returns:
        Exit code (0 = success, 1 = secrets found)
    """
    parser = argparse.ArgumentParser(
        description="SecretHunter CI — Automated Secret Scanning Pipeline",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan only staged files (pre-commit use case)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Scan entire codebase (CI pipeline use case)",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Scan specific path",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="Install pre-commit hook",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Handle hook installation
    if args.install_hook:
        install_pre_commit_hook()
        return EXIT_SUCCESS

    # Ensure SecretHunter is available
    if SecretHunter is None:
        print("❌ SecretHunter not available. Install dependencies first.")
        return EXIT_SECRETS_FOUND

    hunter = SecretHunter()

    # Handle staged file scan
    if args.staged:
        success = scan_staged_files(hunter)
        return EXIT_SUCCESS if success else EXIT_SECRETS_FOUND

    # Handle full/partial scan
    if args.full or args.path:
        success = scan_codebase(hunter, args.path)
        return EXIT_SUCCESS if success else EXIT_SECRETS_FOUND

    # No mode selected — show help
    parser.print_help()
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())


# --- Merged from wire_error_bus.py ---


# Python script to safely auto-wire @with_error_bus decorators to functions
# containing silent exceptions or manual ErrorEvent triggers.
#
# বাংলা মন্তব্য: এই স্ক্রিপ্টটি স্বয়ংক্রিয়ভাবে functions সনাক্ত করে যেগুলোতে silent exceptions
# বা manual ErrorEvent ব্যবহার করা হয়েছে, এবং সেগুলোতে @with_error_bus decorator বসায়।

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception as e:
    import logging
    logging.getLogger(__name__).exception(f"Silenced error: {e}")

def get_indent(line: str) -> str:
    return line[:len(line) - len(line.lstrip())]

def process_file(filepath: Path, dry_run: bool = True) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    content = "".join(lines)

    # Target patterns

    # Find all function definition lines and their indents
    func_pattern = re.compile(r'^(\s*)(async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(')
    functions = [] # list of (line_idx, indent, name)
    for idx, line in enumerate(lines):
        match = func_pattern.match(line)
        if match:
            functions.append((idx, match.group(1), match.group(3)))

    if not functions:
        return False

    # Find target lines (ErrorEvent or silent exception pattern)
    target_lines = []
    for idx, line in enumerate(lines):
        # Silent exception or manual ErrorEvent
        if 'ErrorEvent(' in line or 'except Exception:' in line or 'except:' in line:
            target_lines.append(idx)

    if not target_lines:
        return False

    # Map target lines to the closest preceding function
    funcs_to_decorate = set()
    for t_line in target_lines:
        closest_func = None
        for f_idx, f_indent, f_name in functions:
            if f_idx < t_line:
                closest_func = (f_idx, f_indent, f_name)
            else:
                break
        if closest_func:
            # বাংলা মন্তব্য: ইতিমধ্যেই ডেকোরেট করা ফাংশন ডুপ্লিকেট রিনেমিং/ডেকোরেটিং প্রতিরোধে ফিল্টার করা হচ্ছে
            f_idx = closest_func[0]
            prev_lines = "".join(lines[max(0, f_idx - 3):f_idx])
            if "@with_error_bus" not in prev_lines:
                funcs_to_decorate.add(closest_func)

    if not funcs_to_decorate:
        return False

    # Check if we need to modify the file
    modified = False
    offset = 0

    # Sort functions by line index ascending so we can insert decorators correctly
    sorted_funcs = sorted(funcs_to_decorate, key=lambda x: x[0])

    # Prepare import statement
    import_line = "from core.error_bus import with_error_bus\n"
    has_import = "from core.error_bus import with_error_bus" in content or "import with_error_bus" in content

    new_lines = list(lines)

    # Track decorated function names for reporting
    decorated_names = []

    for f_idx, indent, name in sorted_funcs:
        # Check if already decorated
        already_decorated = False
        check_idx = f_idx + offset - 1
        while check_idx >= 0:
            prev_line = new_lines[check_idx].strip()
            if prev_line.startswith("@with_error_bus"):
                already_decorated = True
                break
            if prev_line == "" or prev_line.startswith("#"):
                check_idx -= 1
                continue
            break

        if not already_decorated:
            decorator = f"{indent}@with_error_bus(\"{name}\")\n"
            new_lines.insert(f_idx + offset, decorator)
            offset += 1
            modified = True
            decorated_names.append(name)

    if modified:
        if not has_import:
            # Find a good place to insert import: after __future__ or other imports
            insert_idx = 0
            in_docstring = False
            for idx, line in enumerate(new_lines):
                cleaned = line.strip()
                if cleaned.startswith(('"""', "'''")):
                    if cleaned.count('"""') % 2 != 0 or cleaned.count("'''") % 2 != 0:
                        in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                if "__future__" in line:
                    insert_idx = idx + 1
                    continue
                if re.match(r'^\s*(import\s+|from\s+)', line):
                    insert_idx = max(idx, insert_idx)
                    break
            new_lines.insert(insert_idx, import_line)

        if not dry_run:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"[Done] Modified {filepath} (Decorated: {', '.join(decorated_names)})")
        else:
            print(f"[Dry-Run] Would modify {filepath} (Decorated: {', '.join(decorated_names)})")

    return modified

def main():
    dry_run = "--apply" not in sys.argv
    backend_dir = Path("backend")

    # File filters
    py_files = list(backend_dir.glob("**/*.py"))

    modified_count = 0
    for f in py_files:
        if "test_" in f.name or f.name == "error_bus.py" or ".venv" in str(f) or "conftest.py" in f.name:
            continue
        try:
            if process_file(f, dry_run=dry_run):
                modified_count += 1
        except Exception as e:
            print(f"Error processing {f}: {e}")

    print("\nSummary:")
    if dry_run:
        print(f"Found {modified_count} files to modify. Run with --apply to write changes.")
    else:
        print(f"Successfully modified {modified_count} files.")

if __name__ == "__main__":
    main()
