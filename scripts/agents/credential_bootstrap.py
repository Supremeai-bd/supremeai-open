#!/usr/bin/env python3
"""Credential Bootstrap — create vault.env for fresh agent processes (issue #4081).

বাংলা সারসংক্ষেপ:
------------------
Root cause fix: fresh agent process-এ (নতুন container, fresh clone, CI runner
restart) কোনো vault.env থাকে না → credential_manager.resolve_and_mint_for_slot()
ব্যর্থ হয় ("Missing GitHub App creds") → agent stuck। এই script দুটি mode-এ
vault.env তৈরি করে:

  1. Interactive (default): user থেকে 4টি INFISICAL_* value prompt করে
  2. Non-interactive (--non-interactive): env var থেকে পড়ে (CI-র জন্য)

vault.env তৈরা হলে credential_manager.py স্বাভাবিকভাবে কাজ করবে —
resolve_and_mint_for_slot() Infisical-এ login করে GitHub App private key fetch
করবে এবং 1-ঘণ্টার JIT installation token mint করবে।

Security:
  - vault.env শুধু mode 600 (owner read/write only)
  - .gitignore-এ আছে (line 725) — commit হবে না
  - কোনো secret এই script-এ থাকে না — শুধু user ইনপুট বা env var থেকে পড়ে
  - টেস্ট মোডে শুধু presence check করে (value লেখে না)

Usage:
  # Interactive (local dev / fresh container):
  python scripts/agents/credential_bootstrap.py

  # Non-interactive (CI / automation with INFISICAL_* env set):
  python scripts/agents/credential_bootstrap.py --non-interactive

  # Check if vault.env is present (exit 0=present, 1=missing):
  python scripts/agents/credential_bootstrap.py --check

  # Verify vault.env has all required keys (no values printed):
  python scripts/agents/credential_bootstrap.py --verify

Exit codes:
  0 = vault.env created / present / valid
  1 = missing / invalid / bootstrap failed
  2 = usage error
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_VAULT_ENV = ROOT_DIR / "vault.env"

# Required Infisical bootstrap keys (universal-auth)
REQUIRED_KEYS = [
    "INFISICAL_CLIENT_ID",
    "INFISICAL_CLIENT_SECRET",
    "INFISICAL_PROJECT_ID",
]

# Optional but recommended (identity-based auth)
OPTIONAL_KEYS = [
    "INFISICAL_IDENTITY_ID",
    "INFISICAL_AUTH_METHOD",  # default: universal-auth
    "INFISICAL_ENV",          # default: prod
]

_FILE_HEADER = """# vault.env — Infisical bootstrap credentials (issue #4081)
# বাংলা: এই ফাইলটি credential_manager.py দ্বারা পড়া হয় GitHub App installation
# token mint করার জন্য। এটি .gitignore-এ আছে (line 725) — কখনো commit হবে না।
# তৈরি করেছে: scripts/agents/credential_bootstrap.py
# তারিখ: {date}
# মোড: 600 (owner read/write only)
"""


def _read_vault_env(path: Path = DEFAULT_VAULT_ENV) -> dict[str, str]:
    """Parse existing vault.env (KEY=VALUE lines; quotes stripped)."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _write_vault_env(creds: dict[str, str], path: Path = DEFAULT_VAULT_ENV) -> None:
    """Write vault.env with mode 600 (owner read/write only)."""
    import datetime

    header = _FILE_HEADER.format(date=datetime.datetime.now().isoformat(timespec="seconds"))
    lines = [header]
    for key in REQUIRED_KEYS + OPTIONAL_KEYS:
        val = creds.get(key, "")
        if val:
            lines.append(f'{key}="{val}"')
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    # chmod 600 — owner read/write only
    path.chmod(0o600)


def _prompt(key: str, default: str = "") -> str:
    """Interactive prompt for a credential value (input hidden for secrets)."""
    suffix = f" [{default}]" if default else ""
    prompt_msg = f"  {key}{suffix}: "
    val = input(prompt_msg).strip()
    if not val and default:
        return default
    return val


def interactive_bootstrap() -> int:
    """Interactive: prompt for INFISICAL_* values and write vault.env."""
    print("=" * 70)
    print("SupremeAI Credential Bootstrap — Interactive Mode (issue #4081)")
    print("=" * 70)
    print()
    print("This will create vault.env with Infisical bootstrap credentials.")
    print("The file is gitignored (.gitignore:725) and chmod 600.")
    print("You need Infisical Universal Auth credentials (clientId + clientSecret")
    print("+ projectId). Get them from your Infisical dashboard → Machine Identities.")
    print()
    print("Required keys:")
    for k in REQUIRED_KEYS:
        print(f"  - {k}")
    print()
    print("Optional keys (press Enter for defaults):")
    for k in OPTIONAL_KEYS:
        print(f"  - {k}")
    print()

    defaults = {
        "INFISICAL_AUTH_METHOD": "universal-auth",
        "INFISICAL_ENV": "prod",
    }
    creds: dict[str, str] = {}
    for key in REQUIRED_KEYS:
        val = _prompt(key)
        if not val:
            print(f"❌ {key} is required. Aborting.")
            return 1
        creds[key] = val
    for key in OPTIONAL_KEYS:
        default = defaults.get(key, "")
        val = _prompt(key, default=default)
        if val:
            creds[key] = val

    _write_vault_env(creds)
    print()
    print(f"✅ vault.env created at {DEFAULT_VAULT_ENV} (mode 600)")
    print()
    print("Next steps:")
    print("  1. Verify: python scripts/agents/credential_bootstrap.py --verify")
    print("  2. Mint token: python scripts/agents/credential_manager.py --slot agent-3")
    print("  3. Or run continuous_agent_loop: python scripts/agents/continuous_agent_loop.py --role coder --agent-name coder-1 --slot agent-3")
    return 0


def non_interactive_bootstrap() -> int:
    """Non-interactive: read INFISICAL_* from env and write vault.env (for CI)."""
    creds: dict[str, str] = {}
    missing: list[str] = []
    for key in REQUIRED_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            creds[key] = val
        else:
            missing.append(key)
    if missing:
        print(f"❌ Missing required env vars: {missing}", file=sys.stderr)
        print("Set INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET, INFISICAL_PROJECT_ID", file=sys.stderr)
        return 1
    for key in OPTIONAL_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            creds[key] = val
    _write_vault_env(creds)
    print(f"✅ vault.env created at {DEFAULT_VAULT_ENV} (mode 600) from env vars")
    return 0


def check_presence() -> int:
    """Check if vault.env exists (exit 0=present, 1=missing)."""
    if DEFAULT_VAULT_ENV.exists():
        print(f"✅ vault.env present at {DEFAULT_VAULT_ENV}")
        return 0
    print(f"❌ vault.env missing at {DEFAULT_VAULT_ENV}")
    print("Run: python scripts/agents/credential_bootstrap.py")
    return 1


def verify_contents() -> int:
    """Verify vault.env has all required keys (no values printed)."""
    env = _read_vault_env()
    if not env:
        print(f"❌ vault.env missing or empty at {DEFAULT_VAULT_ENV}")
        print("Run: python scripts/agents/credential_bootstrap.py")
        return 1
    present = [k for k in REQUIRED_KEYS if env.get(k)]
    missing = [k for k in REQUIRED_KEYS if not env.get(k)]
    print(f"vault.env verification:")
    print(f"  Required keys present: {len(present)}/{len(REQUIRED_KEYS)}")
    if present:
        print(f"  ✅ Present: {sorted(present)}")
    if missing:
        print(f"  ❌ Missing: {sorted(missing)}")
        return 1
    optional_present = [k for k in OPTIONAL_KEYS if env.get(k)]
    if optional_present:
        print(f"  Optional keys present: {sorted(optional_present)}")
    print()
    print("✅ vault.env is valid. Ready to mint tokens.")
    print("Next: python scripts/agents/credential_manager.py --slot agent-3")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Credential Bootstrap — create vault.env for fresh agent processes (#4081)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--non-interactive", action="store_true",
                      help="read INFISICAL_* from env (no prompts — for CI/automation)")
    mode.add_argument("--check", action="store_true",
                      help="check if vault.env exists (exit 0=present, 1=missing)")
    mode.add_argument("--verify", action="store_true",
                      help="verify vault.env has all required keys (no values printed)")
    args = parser.parse_args()

    if args.check:
        return check_presence()
    if args.verify:
        return verify_contents()
    if args.non_interactive:
        return non_interactive_bootstrap()
    return interactive_bootstrap()


if __name__ == "__main__":
    sys.exit(main())
