#!/usr/bin/env python3
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")

# Words that should NEVER be in a VITE_ variable name
BANNED_WORDS = ["SECRET", "PRIVATE", "PASSWORD", "SERVICE_KEY", "ADMIN_KEY", "STRIPE_SK"]

# Explicitly allowed variables even if they contain "KEY"
ALLOWED_VARS = ["VITE_FIREBASE_API_KEY", "VITE_SUPABASE_ANON_KEY"]

def check_frontend_secrets():
    print("=== Scanning Frontend for Secret Leakage in VITE_ Variables ===")
    leaked_vars = set()
    
    vite_pattern = re.compile(r'VITE_[A-Z0-9_]+')
    
    for root, _, files in os.walk(FRONTEND_DIR):
        if 'node_modules' in root or 'dist' in root:
            continue
        for file in files:
            if file.endswith(('.ts', '.tsx', '.html', '.js', '.jsx', '.json')):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = vite_pattern.findall(content)
                        for match in matches:
                            if match in ALLOWED_VARS:
                                continue
                            
                            # Check against banned words
                            if any(word in match for word in BANNED_WORDS):
                                leaked_vars.add((match, os.path.relpath(path, FRONTEND_DIR)))
                except (OSError, UnicodeError) as exc:
                    print(f"::error::Unable to read frontend file {path}: {exc}")
                    sys.exit(2)

    if leaked_vars:
        print("::error::[Frontend Secret Leakage] Found VITE_ variables containing restricted words:")
        for var, path in leaked_vars:
            print(f"  - {var} in {path}")
        print("VITE_ variables are public. Do not store private keys or passwords in them.")
        sys.exit(1)
    
    print("✅ PASS: No VITE_ secret leakage detected in frontend codebase.")
    sys.exit(0)

if __name__ == "__main__":
    check_frontend_secrets()
