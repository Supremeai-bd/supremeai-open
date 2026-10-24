# scripts/ci/check_gateway_bypass.py
"""M03 P0 — Zero-Bypass inference gate (static analysis, ratchet-style).

বাংলা মন্তব্য: নীতি — সব LLM inference গেটওয়ের এক-দরজায় যায়; ব্যতিক্রম কেবল
গেটওয়ে নিজে (core/llm/llm_gateway/**) ও স্পষ্ট-ঘোষিত allowlist-ফাইল। এই
স্ক্যানার backend-এ প্রোভাইডার-সরাসরি কলের চিহ্ন (litellm.*, AsyncOpenAI(,
Anthropic( ইত্যাদি) খোঁজে।

Ratchet নীতি (any-ratchet-প্রেসিডেন্ট): offender-সংখ্যা বেসলাইনের বেশি হলে
exit 2 — নতুন বাইপাস নিষিদ্ধ; কমলে বেসলাইন নিজেই কমিয়ে নেওয়ার প্রত্যাশা
(downward ratchet)। ফেল-ওপেন (`|| true`) বা বেসলাইন-বৃদ্ধি = গেট অর্থহীন
করা — নিষিদ্ধ।
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

#: প্রোভাইডার-সরাসরি কলের চিহ্ন (গেটওয়ে বাইপাসের প্রমাণ-চিহ্ন)।
PROVIDER_DIRECT_PATTERNS = re.compile(
    r"(litellm\.(a?completion|a?embedding)|AsyncOpenAI\(|(?<![A-Za-z_])OpenAI\("
    r"|(?<![A-Za-z_])Anthropic\(|ChatOpenAI\(|generativeai\.GenerativeModel)"
)

#: এই ডিরেক্টরিগুলো গেটওয়ের নিজস্ব-ভূমি — সরাসরি provider-কল বৈধ।
ALLOWED_PREFIXES = (
    "core/llm/llm_gateway/",
    "core/llm/providers/",  # provider adapters — গেটওয়ের অংশ হিসেবে ঘোষিত
)

#: টেস্ট ও টুলিং-স্ক্রিপ্ট স্ক্যান-বহির্ভূত (নিজেরাই প্রমাণ-যন্ত্র)।
EXCLUDED_PREFIXES = (
    "tests/",
    # _archive/ = quarantined dead modules (MAINTAINABILITY_PLAN §2, issue
    # #1340) — not production runtime; same skip policy as
    # check_hardcoded_deployment_config.py.
    "_archive/",
    "scripts/",
    ".venv/",
    "venv/",
    ".env/",
    "env/",
    "__pycache__/",
)

#: স্ক্যান-বহির্ভূত একক ফাইল (প্রতিটির কারণ ঘোষিত — P0 follow-up গেটওয়ে-স্থানান্তর)।
EXCLUDED_FILES: dict[str, str] = {
    "core/self_evolution/agent_breeder.py": "gateway migration pending",
    "core/embeddings.py": "embedding path migration pending",
    "memory/supabase_store.py": "embedding path migration pending",
    "tools/launchdarkly_agent_adapter.py": "gateway migration pending",
}

#: বর্তমান স্বীকৃত offender-সংখ্যা — কেবল নিচের দিকে সংশোধনযোগ্য।
BASELINE = 0


def scan() -> list[str]:
    """backend-এর স্ক্যানযোগ্য ফাইলে প্রোভাইডার-সরাসরি চিহ্ন খুঁজে ফেরত দেয়।"""
    offenders: list[str] = []
    for py_file in sorted(BACKEND_DIR.rglob("*.py")):
        rel = py_file.relative_to(BACKEND_DIR).as_posix()
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        if rel in EXCLUDED_FILES:
            continue
        if rel.startswith(ALLOWED_PREFIXES):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if PROVIDER_DIRECT_PATTERNS.search(line):
                offenders.append(f"{rel}:{lineno}: provider-direct call sign")
                break
    return offenders


def main() -> int:
    offenders = scan()
    report = {
        "offender_count": len(offenders),
        "baseline": BASELINE,
        "offenders": offenders,
    }
    if len(offenders) > BASELINE:
        print(report)
        print(
            "GATEWAY-BYPASS RATCHET BROKEN — নতুন প্রোভাইডার-সরাসরি কল নিষিদ্ধ; "
            "গেটওয়ে (core/llm/llm_gateway) ব্যবহার করুন।",
            file=sys.stderr,
        )
        return 2
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
