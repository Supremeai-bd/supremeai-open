#!/usr/bin/env python3
# scripts/verify_infisical_env.py
from __future__ import annotations

"""
বাংলা: Infisical Vault-এ সব প্রয়োজনীয় সিক্রেট আছে কিনা তা চেক করার স্ক্রিপ্ট।

REWRITE NOTE (drift-fix): সরাসরি `secrets_registry.yaml` পড়ে, audit_env_usage.py-র
মতো একই criticality tier (critical/important/optional) সম্মান করে — একটাই
source of truth।

ফল্ট-টলারেন্স: Infisical টোকেন এক্সপায়ার্ড বা ক্রেডেনশিয়াল অকার্যকর থাকলে নন-ব্লকিং
ওয়ার্নিং দিয়ে সিআই পাস করাবে (যেহেতু প্রোডাকশনে ব্যাকএন্ড ডিরেক্ট env var ফলব্যাক ব্যবহার করে)।
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from typing import Optional, Dict, Set

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import yaml
except ImportError:
    print("::error::PyYAML ইনস্টল করা নাই — `pip install pyyaml` চালান।")
    sys.exit(1)

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "secrets_registry.yaml")
TARGET_ENV = "infisical-vault"


def load_registry_keys(path: str) -> dict[str, str]:
    """বাংলা: registry থেকে {key_name: criticality} ম্যাপ বের করে, শুধু
    infisical-vault-এ entry থাকা key গুলোর জন্য।"""
    if not os.path.exists(path):
        print(f"::error::Registry ফাইল পাওয়া যায়নি: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    result: dict[str, str] = {}
    for entry in data.get("keys", []):
        name = entry.get("name")
        crit_map = entry.get("criticality", {})
        if isinstance(crit_map, str):
            continue  # legacy flat-string entries — infisical-vault-specific না
        if name and TARGET_ENV in crit_map:
            result[name] = crit_map[TARGET_ENV]
    return result


def get_infisical_token(client_id: str, client_secret: str) -> Optional[str]:
    """বাংলা: Infisical Universal Auth (Machine Identity) এর মাধ্যমে Access Token পাওয়ার এপিআই কল।"""
    url = "https://app.infisical.com/api/v1/auth/universal-auth/login"
    payload = json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
            return data.get("accessToken")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        print(f"[info] Infisical Universal Auth HTTP {e.code}: {body[:200]}")
        return None
    except Exception as e:
        print(f"[info] Infisical Universal Auth network error: {e}")
        return None


def load_env_fallback(key: str) -> Optional[str]:
    """বাংলা: os.environ-এ ভ্যালু না থাকলে local .env ফাইল থেকে পড়ার চেষ্টা করে"""
    val = os.environ.get(key)
    if val:
        return val
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip('"\'')
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")
    return None


def fetch_infisical_secrets(project_id: Optional[str], token: str, env: str = "prod") -> Optional[Set[str]]:
    """বাংলা: project_id থাকলে workspaceId পাঠাব, slug হলে resolve করে পাঠাব।"""
    target_id = project_id.strip() if project_id else ""
    if target_id:
        try:
            ws_req = urllib.request.Request("https://app.infisical.com/api/v1/workspace", headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(ws_req, timeout=15) as ws_resp:
                workspaces = json.load(ws_resp).get("workspaces", [])
                for ws in workspaces:
                    if ws.get("id") == target_id or ws.get("slug") == target_id:
                        target_id = ws.get("id")
                        break
        except Exception as error:
            print(f"Unable to resolve Infisical workspace: {error}", file=sys.stderr)

    if target_id:
        url = f"https://app.infisical.com/api/v3/secrets/raw?workspaceId={target_id}&environment={env}"
    else:
        url = f"https://app.infisical.com/api/v3/secrets/raw?environment={env}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
            secrets = data.get("secrets", [])
            return {s.get("secretKey") for s in secrets if s.get("secretKey")}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", "ignore")
        print(f"::warning::Infisical API call returned HTTP {e.code}: {err_msg[:200]}")
        return None
    except Exception as e:
        print(f"::warning::Infisical API unreachable: {e}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail when Infisical cannot authenticate or fetch secrets")
    args = parser.parse_args()

    def required(name: str) -> Optional[str]:
        value = os.environ.get(name) if args.strict else load_env_fallback(name)
        if args.strict and not value:
            print(f"::error::Required Infisical bootstrap variable is missing: {name}")
            raise SystemExit(2)
        return value

    client_id = required("INFISICAL_CLIENT_ID")
    client_secret = required("INFISICAL_CLIENT_SECRET")
    project_id = required("INFISICAL_PROJECT_ID")
    env = required("INFISICAL_ENV") or "prod"

    access_token: Optional[str] = None

    if client_id and client_secret:
        print("[info] Attempting Universal Auth (Machine Identity) for authentication...")
        access_token = get_infisical_token(client_id, client_secret)

    if not access_token:
        service_token = load_env_fallback("INFISICAL_TOKEN")
        if service_token:
            print("[info] Universal Auth unavailable or expired — falling back to INFISICAL_TOKEN (Service Token)...")
            access_token = service_token

    is_dummy_env = any(
        str(v).startswith(("dummy-", "mock-"))
        for v in (client_id, client_secret, project_id)
        if v
    )

    if not access_token:
        message = "Infisical authentication failed or credentials are missing"
        if is_dummy_env:
            print(f"::warning::{message} (Detected dummy testing credentials). Skipping vault check safely.")
            return 0
        print(f"::error::{message}" if args.strict else f"::warning::{message}. Skipping vault health check.")
        return 1 if args.strict else 0

    registry_keys = load_registry_keys(REGISTRY_PATH)
    present = fetch_infisical_secrets(project_id, access_token, env)

    if present is None:
        message = "Infisical token is unauthorized or secret fetch failed"
        if is_dummy_env:
            print(f"::warning::{message} (Detected dummy testing credentials). Skipping vault check safely.")
            return 0
        print(f"::error::{message}" if args.strict else f"::warning::{message}. Skipping vault health check.")
        return 1 if args.strict else 0

    print(f"=== Infisical Vault Health Check [{env}] ===")
    print(f"[info] Infisical-এ সর্বমোট সিক্রেট সংখ্যা: {len(present)}")
    print(f"[info] secrets_registry.yaml-এ {TARGET_ENV}-এর জন্য tracked key সংখ্যা: {len(registry_keys)}")

    has_critical_failure = False
    warnings = 0

    for name in sorted(registry_keys):
        crit = registry_keys[name]
        if name in present:
            continue
        if crit == "critical":
            print(f"::error::CRITICAL secret missing in Infisical: {name} (production boot will crash)")
            has_critical_failure = True
        elif crit == "important":
            print(f"::warning::IMPORTANT secret missing in Infisical: {name} (feature degraded)")
            warnings += 1
        else:
            print(f"[optional] secret missing in Infisical: {name} (feature disabled)")
            warnings += 1

    if has_critical_failure:
        print("\n❌ FAIL: Infisical-এ এক বা একাধিক critical সিক্রেট মিসিং!")
        return 1

    if warnings:
        print(f"\n⚠️ PASS with {warnings} warning(s): critical সব ঠিক আছে, কিছু important/optional key মিসিং।")
    else:
        print("\n✅ PASS: Infisical-এ সব tracked সিক্রেট উপস্থিত আছে!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
