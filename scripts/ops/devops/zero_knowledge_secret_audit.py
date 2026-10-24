#!/usr/bin/env python3
"""Zero-Knowledge Secret Drift Validator (Issue #2644 item 7 — local half).

বাংলা: জিরো-নলেজ অডিট — কোন সিক্রেট কী উপস্থিত আছে আর কোনটা missing, শুধু
**নাম** ধরে রিপোর্ট করে; কোনো ভ্যালু কখনো দেখা/প্রিন্ট/লগ হয় না। MCP Control
Tower-এর masking (`infisical_audit_secrets` → `missing_keys: [...]`) এর লোকাল
পূরক — একই চুক্তি, একই আউটপুট শেপ।

Sources checked (in order, first hit wins per key):
  1. process env (--source env, default)
  2. vault.env file (--source vault / --vault-path)
  3. Infisical live (--source infisical — universal-auth; needs INFISICAL_*)

Required keys come from:
  * --require KEY (repeatable), and/or
  * --from-registry — all keys classified in secrets_registry.yaml
    (reuses the existing registry SSOT; reconcile_secrets_registry.py-এর
    code↔registry sync থেকে আলাদা কনসার্ন: এটা presence-drift, ওটা ক্লাসিফিকেশন)

Usage:
    python scripts/devops/zero_knowledge_secret_audit.py \
        --require GITHUB_APP_ID --require GITHUB_APP_PRIVATE_KEY
    python scripts/devops/zero_knowledge_secret_audit.py --from-registry --source vault

Exit codes: 0 = all present, 1 = missing keys (gate-able), 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agents.credential_manager import (  # noqa: E402
    audit_secret_presence,
    load_vault_env,
)

REGISTRY_PATH = REPO_ROOT / "secrets_registry.yaml"


def registry_keys() -> list:
    """All classified key names from secrets_registry.yaml (names only)."""
    try:
        import yaml
    except ImportError:
        print("::warning::PyYAML unavailable — cannot read the registry", file=sys.stderr)
        return []
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    # registry shape: {keys: [{name: ...}, ...]} (tolerate a flat list too)
    entries = data.get("keys") if isinstance(data, dict) else data
    keys = []
    for e in entries or []:
        if isinstance(e, dict) and e.get("name"):
            keys.append(str(e["name"]))
        elif isinstance(e, str):
            keys.append(e)
    return sorted(set(keys))


def main() -> int:
    parser = argparse.ArgumentParser(description="Zero-knowledge secret drift validator (#2644)")
    parser.add_argument("--require", action="append", default=[],
                        help="key that must be present (repeatable)")
    parser.add_argument("--from-registry", action="store_true",
                        help="require every key classified in secrets_registry.yaml")
    parser.add_argument("--source", choices=("env", "vault", "infisical"), default="env",
                        help="where to check presence (default: process env)")
    parser.add_argument("--vault-path", default=str(REPO_ROOT / "vault.env"))
    parser.add_argument("--json", action="store_true", help="JSON report (CI-friendly)")
    args = parser.parse_args()

    required = list(dict.fromkeys(args.require))
    if args.from_registry:
        required.extend(k for k in registry_keys() if k not in required)
    if not required:
        print("nothing to check — pass --require KEY or --from-registry", file=sys.stderr)
        return 2

    if args.source == "env":
        import os

        report = audit_secret_presence(required, source_env=dict(os.environ), label="env")
    elif args.source == "vault":
        vault = load_vault_env(Path(args.vault_path))
        report = audit_secret_presence(required, source_env=vault, label=f"vault:{args.vault_path}")
    else:  # infisical — live fetch, presence only
        from scripts.agents.credential_manager import (
            CredentialError,
            _infisical_fetch_secrets,
        )

        vault = load_vault_env(Path(args.vault_path))
        if not vault.get("INFISICAL_CLIENT_ID"):
            import os

            vault = {k: v for k, v in os.environ.items() if k.startswith("INFISICAL_")}
        try:
            secrets = _infisical_fetch_secrets(vault)
        except CredentialError as err:
            print(f"ERROR: infisical fetch failed: {err}", file=sys.stderr)
            return 1
        report = audit_secret_presence(required, source_env=secrets, label="infisical")

    if args.json:
        print(json.dumps(report, indent=1))
    else:
        status = "✅" if report["ok"] else "❌"
        print(f"{status} zero-knowledge audit ({report['source']}): "
              f"{report['checked']} checked, {len(report['present_keys'])} present, "
              f"{len(report['missing_keys'])} missing")
        if report["missing_keys"]:
            print("  missing_keys:")
            for k in report["missing_keys"]:
                print(f"    - {k}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
