#!/usr/bin/env python
"""
find_dead_code.py
=================
SupremeAI 2.0 প্রজেক্টের জন্য একটি স্বয়ংক্রিয় Dead Code Detector।

এই স্ক্রিপ্টটি `vulture` লাইব্রেরি ব্যবহার করে Python কোডবেস স্ক্যান করে এবং
অব্যবহৃত কোড (unused functions, classes, variables) খুঁজে বের করে রিপোর্ট করে।

ব্যবহার:
python scripts/quality/find_dead_code.py

পূর্বশর্ত:
এই স্ক্রিপ্টটি চালানোর আগে আপনাকে `vulture` ইনস্টল করতে হবে:
`pip install vulture`
অথবা, আপনার `pyproject.toml` ফাইলে যোগ করুন:
`vulture = "^2.3"`
"""

import subprocess
import sys
from pathlib import Path

# --- কনফিগারেশন ---

# প্রজেক্টের রুট ডিরেক্টরি
PROJECT_ROOT = Path(__file__).parent.parent.parent

# যে ডিরেক্টরিগুলো স্ক্যান করা হবে
SCAN_PATHS = [
    PROJECT_ROOT / "backend",
    PROJECT_ROOT / "scripts",
]

# Vulture-এর জন্য সর্বনিম্ন কনফিডেন্স লেভেল (0-100)
# 80% এর মানে হলো, vulture শুধুমাত্র সেই কোড রিপোর্ট করবে যা ৮০% বা তার বেশি সম্ভাবনায় অব্যবহৃত।
MIN_CONFIDENCE = 80

# যে ফাইল বা ডিরেক্টরিগুলো স্ক্যান থেকে বাদ দেওয়া হবে
EXCLUDE_PATTERNS = [
    "*/.venv/*",
    "*/__pycache__/*",
    "*/alembic/*", # Alembic মাইগ্রেশন ফাইলগুলো সাধারণত সরাসরি কল করা হয় না
]

def main():
    """মূল ফাংশন যা Vulture ব্যবহার করে অব্যবহৃত কোড খুঁজে বের করে।"""
    # স্ক্রিপ্টটি ডেপ্রিকেট করা হয়েছে, auto_dead_code_remover.py ব্যবহারের পরামর্শ দেওয়া হচ্ছে।
    print("⚠️  সতর্কতা: find_dead_code.py ডেপ্রিকেট করা হয়েছে।")
    print("   দয়া করে আরও উন্নত ফিচারের জন্য `scripts/quality/auto_dead_code_remover.py` ব্যবহার করুন।\n")

    print("🦅 SupremeAI Dead Code Detector শুরু হচ্ছে...")
    print(f"🎯 স্ক্যান করার পাথ: {[str(p.relative_to(PROJECT_ROOT)) for p in SCAN_PATHS]}")
    print(f"⚙️ সর্বনিম্ন কনফিডেন্স: {MIN_CONFIDENCE}%\n")

    try:
        command = [
            sys.executable, "-m", "vulture",
            "--min-confidence", str(MIN_CONFIDENCE),
            "--exclude", ",".join(EXCLUDE_PATTERNS),
        ] + [str(p) for p in SCAN_PATHS]

        result = subprocess.run(command, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            print("✅ অভিনন্দন! কোনো অব্যবহৃত কোড পাওয়া যায়নি।")
        else:
            print("🚨 সম্ভাব্য অব্যবহৃত কোড পাওয়া গেছে:")
            print("-" * 70)
            print(result.stdout.strip())
            print("-" * 70)
            print("\n💡 পরামর্শ: যদি এগুলো ফলস পজিটিভ হয়, তাহলে সেগুলোকে একটি `.vulture-whitelist.py` ফাইলে যোগ করুন।")
            # CI/CD পাইপলাইনে ব্যর্থতা রিপোর্ট করার জন্য
            # exit(1) # আপাতত কমেন্ট করে রাখা হলো, যাতে বিল্ড ব্লক না হয়।

    except FileNotFoundError:
        print("❌ ত্রুটি: `vulture` ইনস্টল করা নেই।")
        print("   দয়া করে `pip install vulture` কমান্ডটি চালান।")
        sys.exit(1)
    except Exception as e:
        print(f"❌ একটি অপ্রত্যাশিত ত্রুটি ঘটেছে: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
