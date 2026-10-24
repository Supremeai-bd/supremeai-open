#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import jwt
import requests

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
VAULT_ENV_PATH = SCRIPTS_DIR.parent / "vault.env"

# (#1821) Slot -> GitHub App credential mapping inlined here: this script is the
# SOLE consumer, and the old 5th registry copy (scripts/agents/agent_bot_registry.py)
# drifted from the governance YAML (docs/master_docs/AGENT_SLOT_REGISTRY.yaml).
# Slots not listed fall back to the GITHUB_APP_* default credentials.
BOT_SLOT_CREDENTIALS = {
    "agent-1": {"bot_name": "supremeai-planner", "env_prefix": "GITHUB_APP"},
    "agent-2": {"bot_name": "supremeai-pr-helper", "env_prefix": "AGENT_PR_HELPER"},
    "agent-3": {"bot_name": "supremeai-coder-1", "env_prefix": "AGENT_CODER_1"},
    "agent-5": {"bot_name": "supremeai-ci-action", "env_prefix": "AGENT_CI_ACTION"},
    "agent-6": {"bot_name": "supremeai-coder-2", "env_prefix": "AGENT_CODER_2"},
}

# (#1838 follow-up) CLI surface merged from PR #1840: --slot replaces the
# hardcoded agent-3 default, --repo overrides the push target, --dry-run
# prints instead of pushing, and push output is token-masked before logging.


def log(s, m):
    print(f"[{s}] {m}", file=sys.stderr, flush=True)


def load_vault(p):
    env = {}
    for l in p.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l or l.startswith("#") or "=" not in l:
            continue
        k, _, v = l.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def fetch_creds(vault, slot):
    cfg = BOT_SLOT_CREDENTIALS.get(slot)
    if not cfg:
        raise ValueError(f"Unknown slot: {slot}")
    env_prefix = cfg["env_prefix"]
    r = requests.post(
        "https://app.infisical.com/api/v1/auth/universal-auth/login",
        data={
            "clientId": vault["INFISICAL_CLIENT_ID"],
            "clientSecret": vault["INFISICAL_CLIENT_SECRET"],
        },
        timeout=30,
    )
    at = r.json()["accessToken"]
    r = requests.get(
        "https://app.infisical.com/api/v3/secrets/raw",
        params={
            "workspaceId": vault["INFISICAL_PROJECT_ID"],
            "environment": "prod",
            "secretPath": "/",
            "include_imports": "true",
        },
        headers={"Authorization": f"Bearer {at}"},
        timeout=30,
    )
    secrets = {
        s["secretKey"]: s.get("secretValue", "") or "" for s in r.json()["secrets"]
    }
    app_id = secrets.get(f"{env_prefix}_APP_ID") or secrets.get("GITHUB_APP_ID")
    inst_id = secrets.get(f"{env_prefix}_INSTALLATION_ID") or secrets.get(
        "GITHUB_APP_INSTALLATION_ID"
    )
    pem = secrets.get(f"{env_prefix}_PRIVATE_KEY") or secrets.get(
        "GITHUB_APP_PRIVATE_KEY"
    )
    if not all([app_id, inst_id, pem]):
        raise RuntimeError(f"Missing GitHub App creds for slot: {slot}")
    return {
        "slot": slot,
        "bot_name": cfg.get("bot_name", slot),
        "app_id": app_id,
        "installation_id": inst_id,
        "private_key": pem,
    }


def mint_token(c):
    now = int(time.time())
    jt = jwt.encode(
        {"iat": now - 60, "exp": now + 600, "iss": c["app_id"]},
        c["private_key"],
        algorithm="RS256",
    )
    r = requests.post(
        f"https://api.github.com/app/installations/{c['installation_id']}/access_tokens",
        headers={
            "Authorization": f"Bearer {jt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    return r.json()["token"]


def _mask(text, token):
    """Mask the installation token before it can reach logs/CI output."""
    if not token or not text:
        return text
    return text.replace(
        token, "x-access-token:" + "*" * max(0, len(token) - 4) + token[-4:]
    )


def push(token, owner, name, branch, dry=False):
    url = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
    if dry:
        log("git", f"[DRY-RUN] would push {branch} -> {owner}/{name}")
        return True, "dry-run"
    r = subprocess.run(
        ["git", "push", url, f"HEAD:refs/heads/{branch}"],
        cwd=SCRIPTS_DIR.parent,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    out, err = _mask(r.stdout, token), _mask(r.stderr, token)
    if r.returncode == 0:
        return True, out or "(no output)"
    return False, err or out


def main():
    import argparse

    p = argparse.ArgumentParser(description="Push HEAD to upstream as a GitHub App bot")
    p.add_argument("--slot", default=os.environ.get("AGENT_SLOT", "agent-3"))
    p.add_argument(
        "--repo", default=None, help="owner/name (default: SaifulHaqueNiloy/supremeai)"
    )
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    vault = load_vault(VAULT_ENV_PATH)
    creds = fetch_creds(vault, a.slot)
    token = mint_token(creds)
    owner, name = a.repo.split("/", 1) if a.repo else ("SaifulHaqueNiloy", "supremeai")
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=SCRIPTS_DIR.parent, text=True
    ).strip()
    ok, msg = push(token, owner, name, branch, dry=a.dry_run)
    print(msg, file=sys.stderr)
    return 0 if ok else 6


if __name__ == "__main__":
    sys.exit(main())
