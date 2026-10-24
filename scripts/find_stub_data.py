#!/usr/bin/env python3
"""
find_stub_data.py — Zero-Gap Deployment Gate
=============================================
SupremeAI 2.0-এর জন্য CI gate স্ক্রিপ্ট। পুরো কোডবেসে stub/placeholder/dummy
প্যাটার্ন স্ক্যান করে এবং কোনো ম্যাচ পেলে non-zero exit code রিটার্ন করে —
যাতে CI pipeline fail করে এবং stub কোড প্রোডাকশনে merge হওয়া থেকে বাধা পায়।

ব্যবহার:
    python scripts/find_stub_data.py                  # পুরো কোডবেস স্ক্যান
    python scripts/find_stub_data.py --path backend/   # শুধু backend/
    python scripts/find_stub_data.py --exclude tests/  # tests/ বাদ দিয়ে

Exit codes:
    0 — কোনো stub প্যাটার্ন পাওয়া যায়নি (PASS)
    1 — অন্তত একটি stub প্যাটার্ন পাওয়া গেছে (FAIL)
"""

import argparse
import os
import re
import sys
from pathlib import Path

# 🚨 Stub প্যাটার্ন — এগুলো কোডবেসে থাকা মানে ফিচার production-ready না
STUB_PATTERNS: list[tuple[str, str, str]] = [
    # (pattern_name, regex, severity)
    ("simulated_api_key", r'simulated_api_key_\w+', "CRITICAL"),
    ("test_user_id", r'user_id\s*=\s*["\']test_user_id["\']', "CRITICAL"),
    ("placeholder_token", r'YOUR_DECRYPTED_TOKEN_HERE', "CRITICAL"),
    ("placeholder_api_key", r'YOUR_API_KEY_HERE', "CRITICAL"),
    ("placeholder_secret", r'YOUR_SECRET_HERE', "CRITICAL"),
    ("dummy_email", r'recovery@yourdomain\.com', "HIGH"),
    ("dummy_domain", r'@yourdomain\.com', "HIGH"),
    ("simulate_saving", r'Simulate saving to database', "HIGH"),
    ("simulate_saving_comment", r'# Simulate saving', "HIGH"),
    ("fake_response", r'Mock different responses based on provider', "MEDIUM"),
    ("placeholder_implementation", r'placeholder implementation', "MEDIUM"),
    ("stub_response", r'return f"Response from.*:.*\.\.\."', "MEDIUM"),
    ("hardcoded_localhost_redirect", r'redirect_uri\s*=\s*["\']http://localhost:8000', "MEDIUM"),  # is_local()
    ("hardcoded_localhost_frontend", r'RedirectResponse\(url=["\']http://localhost:5173', "MEDIUM"),  # is_local()
    ("mock_data_constant", r'\bconst\s+MOCK_[A-Z_]+\s*[:=]', "HIGH"),
    ("mock_data_constant_py", r'^\s*MOCK_[A-Z_]+\s*[:=]\s*\[', "HIGH"),
    ("hardcoded_mock_pr_url", r'["\']https://github\.com/[^"\']*/pull/\d+["\']', "CRITICAL"),
    ("mock_commit_hash", r'mock_commit_hash', "CRITICAL"),
    ("simulating_action_log", r'[Ss]imulat(e|ing)\s+(git\s+)?commit', "HIGH"),
    ("todo_replace_mock", r'TODO.*(replace|remove).*mock', "MEDIUM"),
    # ERR-M01 FIX (2026-09-16): the register audit found the gate was blind to
    # mock/fake/Math.random/canned responses (1,157 backend stub hits went
    # undetected). Hardened with the missing detection classes below.
    ("mock_output_fabrication", r'["\']Mock (output|response|result|data) for', "CRITICAL"),
    ("mock_session_id", r'mock_session_\d+|["\']mock_session', "CRITICAL"),
    ("frozen_timestamp_telemetry", r'last_activity["\']?\s*[:=]\s*["\']20\d\d-0[1-9]-01T00:00:00', "CRITICAL"),
    ("fabricated_success_toast", r'setTimeout\([^;]{0,120}["\']✅', "HIGH"),
    ("canned_agent_placeholder", r'["\'](Investigation complete\.|Fix applied\.|Implementation placeholder)["\']', "HIGH"),
    ("math_random_metrics", r'(?i)Math\.random\(\)[^;\n]{0,80}(cpu|memory|usage|metric|load|percent)', "HIGH"),
    ("python_random_metrics", r'(?i)random\.(uniform|randint|random)\([^)]*\)[^;\n]{0,80}(cpu|memory|usage|metric|load|percent)', "HIGH"),
    ("mock_provider_adapter", r'(?i)provider\s*=\s*["\']mock["\']', "HIGH"),
    ("mock_result_return", r'(?i)\bmock\s*:\s*True', "MEDIUM"),
    # ERR-M01 round 2: match the marker ANYWHERE in the comment — the classic
    # template stub `# Task execution logic would go here` has prose between the
    # hash and the marker, which the old `#\s*(...)` regex never matched.
    ("stub_marker_comment", r'(?i)#.*(stub|not implemented|would go here)', "MEDIUM"),
]


# ✅ অনুমোদিত ব্যতিক্রম — যেসব ফাইলে stub প্যাটার্ন থাকা acceptable
# ERR-M01 FIX (2026-09-16, round 2): patterns whose regex TARGETS comment text
# (stub markers like "# Task execution logic would go here", TODO-mock notes).
# The blanket comment-skip in scan_file() made these dead patterns — they could
# never fire, which is exactly how 1,157 stubs (register audit) went undetected.
# Comment lines are now scanned for THESE patterns only; code patterns still
# skip comments to avoid doc false-positives.
COMMENT_AWARE_PATTERNS: set[str] = {
    "stub_marker_comment",
    "todo_replace_mock",
    "simulate_saving_comment",
}


ALLOWED_EXCEPTIONS: list[tuple[str, str]] = [
    # (file_glob, pattern_name)
    ("**/tests/**", "simulated_api_key"),  # টেস্ট ফাইলে mock acceptable
    ("**/tests/**", "test_user_id"),
    ("**/tests/**", "dummy_email"),
    ("**/tests/**", "dummy_domain"),
    ("**/tests/**", "placeholder_implementation"),
    ("**/tests/**", "hardcoded_mock_pr_url"),
    ("**/tests/**", "mock_commit_hash"),
    ("**/tests/**", "mock_data_constant"),
    ("**/tests/**", "mock_data_constant_py"),
    ("**/tests/**", "simulating_action_log"),
    ("**/conftest.py", "simulated_api_key"),
    ("**/conftest.py", "dummy_domain"),
    ("**/test_*.py", "simulated_api_key"),
    ("**/test_*.py", "test_user_id"),
    ("**/test_*.py", "dummy_email"),
    ("**/test_*.py", "dummy_domain"),
    ("**/test_*.py", "placeholder_implementation"),
    ("**/test_*.py", "hardcoded_mock_pr_url"),
    ("**/test_*.py", "mock_commit_hash"),
    ("**/test_*.py", "mock_data_constant_py"),
    ("**/migrations/**", "dummy_email"),  # Alembic migration templates
    ("**/alembic/**", "dummy_email"),
    ("**/multi_account_rotator.py", "dummy_domain"),
    # ERR-M01 FIX: honest mock labeling (ERR-G04 PARTIAL fix) is NOT a stub:
    # CloudSandboxOrchestrator returns "mock": True-labelled output when no
    # provider is configured — deliberate fail-honest behavior, not a lie.
    # Other newly-hardened patterns still apply everywhere.
    ("**/cloud_sandbox_orchestrator.py", "mock_result_return"),
    ("**/cloud_sandbox_orchestrator.py", "mock_output_fabrication"),
    # Explicitly-labelled dev fallback (returns success=False + error note,
    # i.e. honest non-delivery — see MockMessagingAdapter docstring).
    ("**/messaging/service.py", "mock_provider_adapter"),
    # ERR-M01 FIX: tests legitimately use mock fixtures/objects — every new
    # hardened pattern is also excepted inside test files.
    ("**/tests/**", "mock_output_fabrication"),
    ("**/tests/**", "mock_session_id"),
    ("**/tests/**", "mock_provider_adapter"),
    ("**/tests/**", "mock_result_return"),
    ("**/tests/**", "canned_agent_placeholder"),
    ("**/tests/**", "math_random_metrics"),
    ("**/tests/**", "python_random_metrics"),
    ("**/test_*.py", "mock_output_fabrication"),
    ("**/test_*.py", "mock_session_id"),
    ("**/test_*.py", "mock_provider_adapter"),
    ("**/test_*.py", "mock_result_return"),
    ("**/test_*.py", "canned_agent_placeholder"),
    ("**/test_*.py", "math_random_metrics"),
    ("**/test_*.py", "python_random_metrics"),
    # ERR-M01 round 2: comment-marker patterns are also excepted in tests —
    # test files legitimately DESCRIBE stubs (fixtures, planned behaviors).
    ("**/tests/**", "stub_marker_comment"),
    ("**/tests/**", "todo_replace_mock"),
    ("**/tests/**", "simulate_saving_comment"),
    ("**/test_*.py", "stub_marker_comment"),
    ("**/test_*.py", "todo_replace_mock"),
    ("**/test_*.py", "simulate_saving_comment"),
]


def is_excepted(filepath: str, pattern_name: str) -> bool:
    """ফাইল এবং প্যাটার্ন allowed exceptions-এর মধ্যে কিনা চেক করে।"""
    filepath = filepath.replace("\\", "/")
    # বাংলা মন্তব্য: স্ক্রিপ্টটি নিজের চেক নিজেই এড়িয়ে যাবে যাতে কোনো false positive না হয়।
    if "find_stub_data.py" in filepath:
        return True

    import fnmatch
    for file_glob, excepted_pattern in ALLOWED_EXCEPTIONS:
        if pattern_name != excepted_pattern:
            continue
        # fnmatch ব্যবহার করে সঠিকভাবে glob ও ওয়াইল্ডকার্ড ম্যাচ করা হচ্ছে
        if fnmatch.fnmatch(filepath, file_glob) or fnmatch.fnmatch(filepath, f"*/{file_glob}"):
            return True
        if file_glob in filepath:
            return True
    return False


def scan_file(filepath: str) -> list[dict]:
    """একটি ফাইল স্ক্যান করে stub প্যাটার্ন খুঁজে।"""
    findings: list[dict] = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return findings

    lines = content.splitlines()
    for pattern_name, regex, severity in STUB_PATTERNS:
        for i, line in enumerate(lines, start=1):
            # বাংলা মন্তব্য: লাইনটি যদি মন্তব্য (# বা //) দিয়ে শুরু হয়, তবে তা স্কিপ করা হবে।
            stripped = line.strip()
            # ERR-M01: comment lines are still scanned for COMMENT_AWARE_PATTERNS
            # (stub-marker comments) — the blanket skip made them dead patterns.
            if stripped.startswith(("#", "//")) and pattern_name not in COMMENT_AWARE_PATTERNS:
                continue

            if re.search(regex, line):
                if not is_excepted(filepath, pattern_name):
                    findings.append({
                        "file": filepath,
                        "line": i,
                        "pattern": pattern_name,
                        "severity": severity,
                        "snippet": line.strip()[:120],
                    })
    return findings


def scan_directory(root_dir: str, exclude_dirs: list[str] | None = None) -> list[dict]:
    """একটি ডিরেক্টরি রিকার্সিভলি স্ক্যান করে এবং অপ্রয়োজনীয় ডিরেক্টরি এড়ায় (prune করে)।"""
    if exclude_dirs is None:
        exclude_dirs = [".venv", "node_modules", "__pycache__", ".git", ".agent", "docs", "infrastructure"]

    all_findings: list[dict] = []

    # বাংলা মন্তব্য: os.walk ব্যবহার করে excluded ডিরেক্টরিগুলো স্কিপ (prune) করা হলো যাতে রিকার্সন অনেক ফাস্ট হয়।
    for root, dirs, files in os.walk(root_dir):
        # Prune excluded directories in-place
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]

        for file in files:
            filepath = Path(root) / file
            if filepath.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".yaml", ".yml", ".json", ".md"}:
                findings = scan_file(str(filepath))
                all_findings.extend(findings)

    return all_findings


def main():
    parser = argparse.ArgumentParser(
        description="Zero-Gap Deployment Gate — Stub/Placeholder Detector"
    )
    parser.add_argument(
        "--path",
        default=".",
        help="স্ক্যান করার পাথ (ডিফল্ট: current directory)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[".venv", "node_modules", "__pycache__", ".git", ".agent", "docs", "infrastructure"],
        help="এক্সক্লুড করার ডিরেক্টরি",
    )
    parser.add_argument(
        "--fail-on",
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default="MEDIUM",
        help="কোন সিভিরিটি লেভেলে fail করবে (ডিফল্ট: MEDIUM)",
    )
    args = parser.parse_args()

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    fail_threshold = severity_order.get(args.fail_on, 2)

    # বাংলা মন্তব্য: উইন্ডোজ টার্মিনালে UnicodeEncodeError এড়াতে ইমোজিগুলো সাধারণ টেক্সট দিয়ে প্রতিস্থাপন করা হলো।
    print(f"[SCAN] Scanning {args.path} for stub/placeholder patterns...")
    print(f"   Fail threshold: {args.fail_on}")
    print(f"   Excluding: {', '.join(args.exclude)}")
    print()

    findings = scan_directory(args.path, args.exclude)

    if not findings:
        print("[PASS] No stub patterns found")
        sys.exit(0)

    # Group by severity
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    high = [f for f in findings if f["severity"] == "HIGH"]
    medium = [f for f in findings if f["severity"] == "MEDIUM"]
    low = [f for f in findings if f["severity"] == "LOW"]

    print(f"[FAIL] Found {len(findings)} stub pattern(s):")
    print(f"   CRITICAL: {len(critical)}")
    print(f"   HIGH:     {len(high)}")
    print(f"   MEDIUM:   {len(medium)}")
    print(f"   LOW:      {len(low)}")
    print()

    for f in findings:
        sev_icon = {"CRITICAL": "[CRITICAL]", "HIGH": "[HIGH]", "MEDIUM": "[MEDIUM]", "LOW": "[LOW]"}
        # বাংলা মন্তব্য: উইন্ডোজ কনসোলে কোনো ডিকোড না হওয়া ক্যারেক্টার থাকলে তা হ্যান্ডেল করার জন্য backslashreplace ব্যবহার করা হলো।
        safe_pattern = f['pattern'].encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
        safe_file = f['file'].encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
        safe_snippet = f['snippet'].encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
        print(f"  {sev_icon.get(f['severity'], '[INFO]')} {safe_pattern}")
        print(f"     File: {safe_file}:{f['line']}")
        print(f"     Code: {safe_snippet}")
        print()

    # Determine if we should fail
    max_severity = min(
        severity_order.get(f["severity"], 3) for f in findings
    )
    if max_severity <= fail_threshold:
        print(f"[FAIL] FAIL — Found stub patterns at or above '{args.fail_on}' severity")
        sys.exit(1)
    else:
        print(f"[WARN] WARNING — Found stub patterns below '{args.fail_on}' severity threshold (not failing)")
        sys.exit(0)


if __name__ == "__main__":
    main()
