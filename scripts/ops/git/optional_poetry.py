#!/usr/bin/env python3
"""Optional-poetry gate wrapper for local pre-commit hooks.

বাংলা মন্তব্য: কিছু pre-commit গেট `poetry -C backend run ...` দিয়ে চলে —
কিন্তু poetry প্রতিটি এনভায়রনমেন্টে নেই (CI-তে আছে)। poetry না থাকলে সেই
গেটগুলো সবসময় লাল হত → পুরো pre-commit অকেজো ("গেট সবসময় লাল = গেট নেই")।

এই wrapper-এর চুক্তি:
- poetry **আছে** → আসল কমান্ড চালায়, exit code অক্ষুণ্ণ প্রতিদান করে (ব্লক করার ক্ষমতা অটুট)।
- poetry **নেই** → **উচ্চস্বরে** জানিয়ে স্কিপ করে (silent নয়) — কারণ একই গেট CI-তে
  কর্তৃপক্ষ হিসেবে তবু চলছে; লোকাল গেট শুধু দ্রুত ফিডব্যাক স্তর, শাসন-স্তর নয়।
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("[optional-poetry] no command given", file=sys.stderr)
        return 1
    if shutil.which("poetry") is None:
        print(
            f"[optional-poetry] ⚠️ poetry নেই — গেট লোকালে স্কিপ: {' '.join(args[:3])}... "
            "(একই গেট CI-তে কর্তৃপক্ষ হিসেবে চলবে; এটি silent skip নয়, স্তর-বিভাজন)"
        )
        return 0
    result = subprocess.run(args, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
