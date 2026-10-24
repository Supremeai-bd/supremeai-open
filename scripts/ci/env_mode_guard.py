#!/usr/bin/env python3
import os
import sys

def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # If CI is true, we skip this check (it's meant for local pre-commit)
    if os.environ.get("CI") == "true":
        return 0

    # Check local .env file
    env_file_path = ".env"
    if not os.path.exists(env_file_path):
        return 0

    has_error = False
    with open(env_file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line.startswith("#"):
                continue

            if "ENV=production" in line.replace(" ", "") or "ENVIRONMENT=production" in line.replace(" ", ""):
                print(f"[WARN] [env-mode-guard] Found in {env_file_path}:{line_num}")
                print(f"   Found production environment in local .env file: {line}")
                print("   Trap #110: Dev/Prod ENV Collapse. Never use production environment locally!")
                has_error = True

    if has_error:
        print("\nFix: Set ENV=development or ENV=local in your .env file.")
        print("[Audit Mode]: Logged warning, returning 0.")
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
