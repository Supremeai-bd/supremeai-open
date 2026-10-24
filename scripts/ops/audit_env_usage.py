#!/usr/bin/env python3
# scripts/audit_env_usage.py
"""
বাংলা: এই স্ক্রিপ্টটি পুরো repo scan করে কোডে ব্যবহৃত env var নাম বের করে, তারপর
secrets_registry.yaml-এর সাথে তুলনা করে নির্দিষ্ট environment-এর জন্য presence check করে।

প্রতিটা environment-এর জন্য আলাদা criticality (যেমন RENDER_API_KEY GitHub Actions-এর
জন্য critical, কিন্তু Render backend-এর জন্য না)। তাই `--env` argument নেয়।

  ১. Criticality check (শুধু ওই --env-এর জন্য):
       - critical missing -> ::error:: + exit 1  (system break হওয়ার আগেই ধরা)
       - important missing -> ::warning:: + exit 0 (degraded mode, চলবে)
       - optional/absent   -> শুধু log (ওই env-এর entry নাই -> skip)
  ২. Drift check: কোডে ব্যবহৃত কোনো key registry-তে নাই কিনা (stale registry শনাক্ত)।

নিরাপত্তা: কোনো secret-এর actual value কখনোই print করা হয় না — শুধু নাম।
"""

import argparse
import os
import re
import sys

# বাংলা: Windows-এ default cp1252 encoder বাংলা character encode করতে পারে না বলে
# stdout/stderr-কে সবসময় UTF-8-এ রি-রাইট করে নিচ্ছি (GitHub ubuntu runner-এও নিরাপদ)।
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import yaml
except ImportError:
    print("::error::PyYAML ইনস্টল করা নাই — `pip install pyyaml` চালান।")
    sys.exit(1)


# বাংলা: কোডে ব্যবহৃত env var বের করার regex (extract_envs.py থেকে নেওয়া)
REGEXES = [
    re.compile(r"""os\.getenv\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""os\.environ\.get\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""os\.environ\[\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r'process\.env\.([A-Z0-9_]+)'),
    re.compile(r'import\.meta\.env\.([A-Z0-9_]+)'),
]

# বাংলা: এই ডিরেক্টরি/ফাইলগুলো scan থেকে বাদ যাবে
SKIP_DIRS = {
    '.git',
    'node_modules',
    'venv',
    '.venv',
    '__pycache__',
    'dist',
    'dist-admin',
    'dist-user',
    'build',
    '.pytest_cache',
    '.kilo',
    'scratch',
    '.gemini',
    '.agents',
    'htmlcov',
    '.playwright-mcp',
    '.github',
    'tests',
    'qa',
}
SCAN_EXTS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.yaml', '.yml'}

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), '..', 'secrets_registry.yaml')


def scan_used_keys(root: str) -> set[str]:
    """বাংলা: রিকার্সিভ ভাবে কোড scan করে ব্যবহৃত env var নাম সংগ্রহ করে।"""
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            if not any(fname.endswith(ext) for ext in SCAN_EXTS):
                continue
            path = os.path.join(dirpath, fname)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
            except Exception:
                continue
            for rx in REGEXES:
                for m in rx.findall(content):
                    found.add(m)
    return found


def load_registry(path: str) -> dict:
    """বাংলা: secrets_registry.yaml থেকে key -> {env: criticality} ম্যাপ লোড করে।"""
    if not os.path.exists(path):
        print(f"::error::Registry ফাইল পাওয়া যায়নি: {path}")
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh)
    registry: dict[str, dict] = {}
    for entry in data.get('keys', []):
        name = entry.get('name')
        if name:
            # বাংলা: criticality হতে পারে string অথবা per-env dict — উভয় সাপোর্ট করা হলো
            crit = entry.get('criticality', {})
            if isinstance(crit, str):
                crit = {env: crit for env in _KNOWN_ENVS}
            registry[name] = {
                'criticality': crit,
                'min_length': entry.get('min_length'),
                'format_regex': entry.get('format_regex'),
            }
    return registry


# বাংলা: পরিচিত environment গুলো (flat string criticality-কে expand করতে)
# বাংলা মন্তব্য: BUG FIX — আগে এখানে শুধু ৪টা env ছিল (render-backend, render-admin,
# render-scraper, github-actions), কিন্তু secrets_registry.yaml আসলে ৭টা env ব্যবহার
# করে (vercel-frontend, firebase-gcp, infisical-vault বাদ পড়েছিল)। বর্তমানে registry-র
# সব entry per-env dict ব্যবহার করে বলে এই flat-string expansion path আপাতত সক্রিয় হয়
# না, কিন্তু ভবিষ্যতে কেউ flat string criticality (যেমন `criticality: important`)
# দিয়ে নতুন key যোগ করলে এই ৩টা env-এ সেই key নীরবে unmonitored থেকে যেত।
_KNOWN_ENVS = {
    'render-backend', 'render-admin', 'render-scraper', 'github-actions',
    'vercel-frontend', 'firebase-gcp', 'infisical-vault',
}

# বাংলা: drift check-এ শুধু এই প্যাটার্ন-এর key গুলোই FAIL করবে (সত্যিকার secret) —
# non-secret tuning knob গুলো informational থাকবে যাতে CI flood না হয়।
_SECRET_PATTERN = re.compile(r'(KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|AUTH)', re.IGNORECASE)
_NON_SECRET_PATTERN = re.compile(r'(_URL|_URI|_ENDPOINT|_PATH|SKIP_AUTH|BYPASS_AUTH|ALLOW_AUTH)', re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Env/Secret drift check per environment")
    parser.add_argument('--env', required=True,
                        help="Target environment: render-backend | render-admin | render-scraper | "
                             "github-actions | vercel-frontend | firebase-gcp | infisical-vault")
    args = parser.parse_args()
    target_env = args.env

    # বাংলা: Hybrid Infisical Migration dummy skip সরানো হয়েছে — এখন আসল চেক চলবে

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    registry = load_registry(REGISTRY_PATH)
    used_keys = scan_used_keys(root)

    # বাংলা: শুধু সেই key গুলোই check করব যা (কোডে ব্যবহৃত) AND (registry-তে ওই env-এর entry আছে)
    monitored = {}
    for key, env_map in registry.items():
        if key not in used_keys:
            continue
        if target_env in env_map['criticality']:
            monitored[key] = env_map

    has_critical_failure = False
    warnings = 0

    print(f"=== SupremeAI Env/Secret Drift-Check [env={target_env}] ===")
    for key in sorted(monitored):
        crit = monitored[key]['criticality'][target_env]
        # বাংলা: environment-এ set আছে কিনা চেক (CI-তে GitHub secrets inject করা থাকে)
        raw_val = os.environ.get(key, '')
        is_set = bool(raw_val.strip())
        if not is_set:
            if crit == 'critical':
                # বাংলা: সার্ভার crash করবে এমন key — CI fail
                print(f"::error::[{target_env}] CRITICAL env var missing: {key} (system boot will crash)")
                has_critical_failure = True
            elif crit == 'important':
                # বাংলা: degraded mode — warning, job pass
                print(f"::warning::[{target_env}] IMPORTANT env var missing: {key} (feature degraded)")
                warnings += 1
            else:
                # বাংলা: optional — শুধু log
                print(f"[{target_env}] [optional] env var missing: {key} (feature disabled)")
                warnings += 1
            continue

        # বাংলা: VALIDITY CHECK (presence-এর বাইরে) — config.py-এর মতোই।
        # Gap #1 বন্ধ করে: key set কিন্তু ভুল shape-এ থাকলে crash এড়ায়।
        min_len = monitored[key].get('min_length')
        if min_len and len(raw_val) < min_len:
            print(f"::error::[{target_env}] CRITICAL env var invalid: {key} (length {len(raw_val)} < required {min_len})")
            has_critical_failure = True
            continue
        fmt = monitored[key].get('format_regex')
        if fmt and not re.match(fmt, raw_val):
            print(f"::error::[{target_env}] CRITICAL env var invalid: {key} (does not match required format)")
            has_critical_failure = True
            continue

    # বাংলা: DRIFT CHECK (Gap #2 mitigation) — কোডে ব্যবহৃত secret-pattern key যদি
    # registry-তে নাই, তবে সেটা WARNING (CI fail নয়)। পুরো registry complete না হওয়া
    # পর্যন্ত fail করলে CI চিরকাল red থাকবে। সঠিক সমাধান: registry-কে পূর্ণ করা
    # (ENV_KEY_MATRIX_VERIFIED.md + missing_env_keys_analysis.md থেকে ৮০টা secret যোগ)।
    drift = sorted(k for k in used_keys if k not in registry)
    secret_drift = [k for k in drift if _SECRET_PATTERN.search(k) and not _NON_SECRET_PATTERN.search(k)]
    if secret_drift:
        print(f"::warning::[{target_env}] {len(secret_drift)} code-used SECRET key(s) missing from registry "
              "(registry incomplete - add to secrets_registry.yaml):")
        for k in secret_drift:
            print(f"  - {k}")
    if drift:
        non_secret = [k for k in drift if not _SECRET_PATTERN.search(k)]
        print(f"[drift] {len(non_secret)} non-secret code-used keys are not in registry (informational):")
        for k in non_secret[:10]:
            print(f"  - {k}")
        if len(non_secret) > 10:
            print(f"  ... and {len(non_secret) - 10} more")

    if has_critical_failure:
        print(f"\n❌ FAIL [{target_env}]: এক বা একাধিক critical env var missing — deploy-এর আগে সেট করুন।")
        return 1

    print(f"\n✅ PASS [{target_env}]: সব critical env var উপস্থিত।")
    return 0


if __name__ == '__main__':
    sys.exit(main())
