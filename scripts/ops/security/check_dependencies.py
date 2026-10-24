#!/usr/bin/env python
"""
check_dependencies.py
=====================
SupremeAI 2.0 প্রজেক্টের জন্য একটি স্বয়ংক্রিয় Dependency Health Checker।

এই স্ক্রিপ্টটি Node.js (pnpm) এবং Python (Poetry) উভয় ইকোসিস্টেমের
নির্ভরতা বা dependency স্ক্যান করে এবং পরিচিত নিরাপত্তা ঝুঁকি (vulnerabilities)
এবং অন্যান্য সমস্যা খুঁজে বের করে।

ব্যবহার:
python scripts/quality/check_dependencies.py
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

def run_command(command: str, working_dir: Path) -> bool:
    """একটি নির্দিষ্ট ডিরেক্টরিতে একটি শেল কমান্ড চালায় এবং সফল হয়েছে কিনা তা রিটার্ন করে।"""
    print(f"\n📂 ডিরেক্টরি: {working_dir}")
    print(f"🚀 কমান্ড চালানো হচ্ছে: {command}")
    print("-" * 40)
    try:
        # shell=True ব্যবহার করা হচ্ছে কারণ pnpm এবং poetry সরাসরি এক্সিকিউটেবল হতে পারে
        process = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
        )
        print(process.stdout)
        print("✅ কমান্ড সফলভাবে সম্পন্ন হয়েছে।")
        return True
    except subprocess.CalledProcessError as e:
        print("❌ কমান্ড ব্যর্থ হয়েছে।")
        print(f"Return Code: {e.returncode}")
        print("\n--- STDOUT ---")
        print(e.stdout)
        print("\n--- STDERR ---")
        print(e.stderr)
        return False

def main():
    """মূল ফাংশন যা প্রজেক্টের সকল dependency স্ক্যান করে।"""
    print("ጤ SupremeAI Dependency Health Checker শুরু হচ্ছে...")

    overall_success = True

    # --- Node.js / pnpm Dependency Scan ---
    print("\n" + "="*60)
    print("🟢 Node.js (pnpm) ecosystem স্ক্যান করা হচ্ছে...")
    # `pnpm audit` কমান্ডটি পরিচিত দুর্বলতা খুঁজে বের করে।
    # যদি কোনো দুর্বলতা পাওয়া যায়, এটি একটি non-zero exit code রিটার্ন করবে।
    if not run_command("pnpm audit", PROJECT_ROOT):
        print("\n🚨 Node.js ইকোসিস্টেমে নিরাপত্তা ঝুঁকি পাওয়া গেছে!")
        overall_success = False

    # --- Python / Poetry Dependency Scan ---
    print("\n" + "="*60)
    print("🐍 Python (Poetry) ecosystem স্ক্যান করা হচ্ছে...")
    backend_dir = PROJECT_ROOT / "backend"
    # `poetry check` কমান্ডটি pyproject.toml এবং poetry.lock ফাইলের মধ্যে অসামঞ্জস্য পরীক্ষা করে।
    if not run_command("poetry check", backend_dir):
        print("\n🚨 Poetry dependency-তে অসামঞ্জস্য পাওয়া গেছে!")
        overall_success = False

    print("\n" + "="*60)
    if overall_success:
        print("✅ অভিনন্দন! সকল dependency স্ক্যান সফল হয়েছে এবং কোনো ঝুঁকি পাওয়া যায়নি।")
    else:
        print("❌ স্ক্যান ব্যর্থ হয়েছে। উপরে উল্লিখিত সমস্যাগুলো সমাধান করুন।")
        sys.exit(1) # CI/CD পাইপলাইনে ব্যর্থতা রিপোর্ট করার জন্য

if __name__ == "__main__":
    main()
