#!/usr/bin/env python3
import sys
import re

def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        return 0

    has_error = False

    # Regex to catch uses: owner/repo@vX.Y.Z instead of @SHA
    # Examples:
    # uses: actions/checkout@v3  (BAD)
    # uses: actions/checkout@1234567890abcdef1234567890abcdef12345678 (GOOD)
    unpinned_pattern = re.compile(r'^\s*uses:\s*[^@]+@v[0-9]')

    for filepath in sys.argv[1:]:
        if not filepath.endswith(".yml") and not filepath.endswith(".yaml"):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if unpinned_pattern.match(line):
                    print(f"[WARN] [actions-pin-checker] Unpinned action in {filepath}:{line_num}")
                    print(f"   Found: {line.strip()}")
                    print("   Trap #95: Supply Chain Attack via Unpinned Action. Always use a full SHA.")
                    has_error = True

    if has_error:
        print("\nFix: Replace @vX tags with the exact commit SHA for security.")
        print("[Audit Mode]: Logged warning, returning 0.")
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
