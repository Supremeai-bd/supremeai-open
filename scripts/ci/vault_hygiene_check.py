#!/usr/bin/env python3
"""Vault Hygiene Check — registry-driven probe of Infisical vault keys (#3206, from #2900/#2895).

# বাংলা মন্তব্য: #2895-এর মূল সমস্যা — dead vault key নীরব fallback তৈরি করে
# (SELF_HEAL_PAT expired, LaunchDarkly 401 — কেউই জানত না গেটরা ভুল কাজ করছে)।
# #3206 recovery scope: মূল PR #2900-এর hardcoded key-array-এর বদলে
# **secrets_registry.yaml-কেই** authority বানানো হলো —
#   - `criticality: important` → required key (missing হলে FAIL);
#   - `criticality: optional`  → vault-এ থাকলে probe হবে, না থাকলে SKIP;
#   - probe endpoint মূল KEY_PROBES থেকে (key-auth API-ভিত্তিক)।
#
# Security contract: stdout/report-এ **কখনো** secret value ছাপা হয় না —
# শুধু key-এর নাম ও status (PASS/FAIL/MISSING/DEAD/SKIP)।
#
# Usage:
#   INFISICAL_CLIENT_ID=... INFISICAL_CLIENT_SECRET=... INFISICAL_PROJECT_ID=... \
#       python scripts/ci/vault_hygiene_check.py [--dry-run] [--json report.json]
#   # বাংলা: --offline → নেটওয়ার্ক ছাড়া registry-vs-vault inventory check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT_DIR / "secrets_registry.yaml"

INFISICAL_API = "https://app.infisical.com"

# Key → API probe config (endpoint, auth header format, expected status)
# বাংলা: প্রতিটি probeable key-এর জন্য কোন API কল করে liveness যাচাই হয়।
# registry-তে না থাকলেও এগুলো probe হয় না — registry-ই কী-সেট ঠিক করে।
KEY_PROBES: dict[str, dict[str, Any]] = {
    "GITHUB_TOKEN": {"url": "https://api.github.com/user",
                     "header": "Authorization", "format": "token {value}", "expect": 200},
    "LAUNCHDARKLY_API_KEY": {"url": "https://app.launchdarkly.com/api/v2/flags/default",
                             "header": "Authorization", "format": "{value}", "expect": 200},
    "CLOUDFLARE_API_TOKEN": {"url": "https://api.cloudflare.com/client/v4/user/tokens/verify",
                             "header": "Authorization", "format": "Bearer {value}", "expect": 200},
    "RENDER_API_KEY": {"url": "https://api.render.com/v1/services",
                       "header": "Authorization", "format": "Bearer {value}", "expect": 200},
    "SUPABASE_ACCESS_TOKEN": {"url": "https://api.supabase.com/v1/projects",
                              "header": "Authorization", "format": "Bearer {value}", "expect": 200},
    "STRIPE_API_KEY": {"url": "https://api.stripe.com/v1/balance",
                       "header": "Authorization", "format": "Bearer {value}", "expect": 200},
    "TELEGRAM_BOT_TOKEN": {"url": "https://api.telegram.org/bot{value}/getMe",
                           "header": None, "format": None, "expect": 200},
    "GROQ_API_KEY": {"url": "https://api.groq.com/openai/v1/models",
                     "header": "Authorization", "format": "Bearer {value}", "expect": 200},
    "OPENAI_API_KEY": {"url": "https://api.openai.com/v1/models",
                       "header": "Authorization", "format": "Bearer {value}", "expect": 200},
    "GEMINI_API_KEY": {"url": "https://generativelanguage.googleapis.com/v1/models?key={value}",
                       "header": None, "format": None, "expect": 200},
}

# Registry criticality levels যেগুলো "অবশ্যই থাকতে হবে"
REQUIRED_LEVELS = {"important", "critical", "required"}


# ---------------------------------------------------------------------------
# Registry parsing — secrets_registry.yaml = authority (#3206 adjustment)
# ---------------------------------------------------------------------------
def load_registry(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """secrets_registry.yaml → {key_name: {criticality_by_provider, note}}।"""
    import yaml  # local import — script path only

    reg_path = Path(path) if path else REGISTRY_PATH
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    keys: dict[str, dict[str, Any]] = {}
    for entry in data.get("keys") or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        keys[str(entry["name"])] = {
            "criticality": dict(entry.get("criticality") or {}),
            "note": str(entry.get("note", "")),
        }
    return keys


def is_required(entry: dict[str, Any]) -> bool:
    """যেকোনো provider-এ important/critical হলে key required।"""
    return any(
        str(level).lower() in REQUIRED_LEVELS
        for level in entry.get("criticality", {}).values()
    )


# ---------------------------------------------------------------------------
# Vault access + probes — zero secret-value output anywhere
# ---------------------------------------------------------------------------
def fetch_vault_secrets(client_id: str, client_secret: str, project_id: str,
                        environment: str = "prod", timeout: int = 30) -> dict[str, str]:
    """Infisical universal-auth → raw secrets। শুধু in-memory, কোথাও লেখা হয় না।"""
    login_body = json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode()
    login_req = urllib.request.Request(
        f"{INFISICAL_API}/api/v1/auth/universal-auth/login",
        data=login_body, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(login_req, timeout=timeout) as resp:
        access_token = json.load(resp)["accessToken"]

    query = urllib.parse.urlencode(
        {"workspaceId": project_id, "environment": environment, "secretPath": "/"})
    secrets_req = urllib.request.Request(
        f"{INFISICAL_API}/api/v3/secrets/raw?{query}",
        headers={"Authorization": f"Bearer {access_token}"}, method="GET",
    )
    with urllib.request.urlopen(secrets_req, timeout=timeout) as resp:
        payload = json.load(resp)
    return {s["secretKey"]: s["secretValue"] for s in payload.get("secrets", [])}


def probe_key(key_name: str, value: str, config: dict[str, Any],
              timeout: int = 15) -> dict[str, Any]:
    """একটি key-কে তার provider API দিয়ে probe করে — ফলে কোনো value থাকে না।"""
    url = config["url"].replace("{value}", value)
    headers = {}
    if config.get("header"):
        headers[config["header"]] = config["format"].format(value=value)
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            return {"key": key_name, "status": "PASS" if status == config["expect"] else "DEAD",
                    "http_status": status}
    except urllib.error.HTTPError as exc:
        return {"key": key_name, "status": "DEAD", "http_status": exc.code,
                "error": f"HTTP {exc.code}"}
    except Exception as exc:  # network/timeout — dead ধরা হয়, value কখনোই নয়
        return {"key": key_name, "status": "DEAD", "http_status": 0,
                "error": type(exc).__name__}


def run_check(registry_path: Path | None = None, vault_secrets: dict[str, str] | None = None,
              offline: bool = False) -> dict[str, Any]:
    """মূল যাচাই — registry-driven inventory + optional probes।

    vault_secrets inject করা যায় (টেস্ট) — নইলে Infisical থেকে আনতে হয়।
    রিটার্ন: {"results": [...], "summary": {...}, "healthy": bool}
    """
    registry = load_registry(registry_path)
    results: list[dict[str, Any]] = []

    for key_name in sorted(registry):
        entry = registry[key_name]
        required = is_required(entry)
        probeable = key_name in KEY_PROBES

        if vault_secrets is not None:
            value = vault_secrets.get(key_name)
        elif offline:
            value = None
        else:
            raise ValueError("vault_secrets required unless offline=True")

        if value is None:
            results.append({
                "key": key_name, "required": required, "probeable": probeable,
                "status": "MISSING" if required else "SKIP",
            })
            continue

        # value আছে — probe করা গেলে liveness, নইলে presence-ই PASS
        if probeable and not offline:
            probe = probe_key(key_name, value, KEY_PROBES[key_name])
            results.append({"key": key_name, "required": required, "probeable": True,
                            "status": probe["status"], "http_status": probe["http_status"],
                            **({"error": probe["error"]} if probe.get("error") else {})})
        else:
            results.append({"key": key_name, "required": required,
                            "probeable": probeable, "status": "PASS"})

    required_missing = [r["key"] for r in results if r["status"] == "MISSING"]
    dead = [r["key"] for r in results if r["status"] == "DEAD"]
    return {
        "results": results,
        "summary": {
            "total_registered": len(registry),
            "required_missing": len(required_missing),
            "dead": len(dead),
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "skipped": sum(1 for r in results if r["status"] == "SKIP"),
        },
        "healthy": not required_missing and not dead,
    }


def _redacted_report(report: dict[str, Any]) -> dict[str, Any]:
    """বাংলা মন্তব্য: report শুধু status-carrying ফিল্ড রাখে — defense-in-depth
    (value কোনো path-এই ঢোকে না, তবু explicit redaction রাখা হলো)।"""
    allowed = {"key", "required", "probeable", "status", "http_status", "error"}
    out = {"results": [{k: v for k, v in r.items() if k in allowed} for r in report["results"]],
           "summary": report["summary"], "healthy": report["healthy"]}
    return out


def _file_issues(dead_or_missing: list[dict[str, Any]], dry_run: bool) -> list[int]:
    """Dead/missing required key-এর জন্য P1 issue auto-file (#2895 ধারাবাহিকতা)।"""
    if dry_run or not dead_or_missing:
        return []
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")
    filed: list[int] = []
    for item in dead_or_missing:
        kind = "MISSING" if item["status"] == "MISSING" else f"DEAD ({item.get('error', item.get('http_status'))})"
        issue_body = {
            "title": f"[vault-hygiene] P1 — vault key '{item['key']}' is {kind}",
            "body": (
                "## 🔴 Vault Hygiene Finding (registry-driven, #3206)\n\n"
                f"**Key:** `{item['key']}`\n**Status:** {kind}\n"
                f"**Required:** {item['required']}\n\n"
                "### Remediation\n"
                "1. Rotate/renew the key at the provider\n"
                "2. Update the value in the Infisical vault\n"
                "3. Re-run `python scripts/ci/vault_hygiene_check.py --dry-run` to verify\n\n"
                "*Auto-filed by scripts/ci/vault_hygiene_check.py — no secret values included.*"
            ),
            "labels": ["P1-high", "area:infrastructure", "type:security"],
        }
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/issues",
                data=json.dumps(issue_body).encode(),
                headers={"Authorization": f"token {gh_token}",
                         "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                filed.append(json.load(resp)["number"])
        except Exception as exc:
            print(f"  issue filing failed for {item['key']}: {type(exc).__name__}",
                  file=sys.stderr)
    return filed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Registry-driven vault hygiene check")
    parser.add_argument("--dry-run", action="store_true", help="Don't file issues")
    parser.add_argument("--json", type=str, help="Write redacted JSON report to file")
    parser.add_argument("--offline", action="store_true",
                        help="No network: registry inventory check only (all SKIP/MISSING)")
    parser.add_argument("--registry", type=str, default=None,
                        help="Registry path override (default: secrets_registry.yaml)")
    args = parser.parse_args(argv)

    vault_secrets: dict[str, str] | None = None
    if not args.offline:
        client_id = os.environ.get("INFISICAL_CLIENT_ID", "")
        client_secret = os.environ.get("INFISICAL_CLIENT_SECRET", "")
        project_id = os.environ.get("INFISICAL_PROJECT_ID", "")
        if not (client_id and client_secret and project_id):
            print("ERROR: INFISICAL_CLIENT_ID/SECRET/PROJECT_ID not set "
                  "(or use --offline for inventory-only check)", file=sys.stderr)
            return 2
        try:
            vault_secrets = fetch_vault_secrets(client_id, client_secret, project_id)
        except Exception as exc:
            print(f"ERROR: vault fetch failed: {type(exc).__name__}", file=sys.stderr)
            return 2

    registry_path = Path(args.registry) if args.registry else None
    report = run_check(registry_path=registry_path, vault_secrets=vault_secrets,
                       offline=args.offline)

    safe = _redacted_report(report)
    for r in safe["results"]:
        icon = {"PASS": "✅", "DEAD": "❌", "MISSING": "⚠️ "}.get(r["status"], "⏭️ ")
        req_tag = "required" if r["required"] else "optional"
        print(f"  {icon} {r['key']}: {r['status']} ({req_tag})")
    print(f"\nSummary: {json.dumps(safe['summary'])}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report written to {args.json}")

    # বাংলা: dead/missing required → issue file (dry-run ছাড়া)
    failing = [r for r in safe["results"] if r["status"] in ("DEAD", "MISSING")]
    _file_issues(failing, dry_run=args.dry_run)

    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
