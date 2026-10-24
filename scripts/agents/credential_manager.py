#!/usr/bin/env python3
"""Scoped JIT Credential Manager for SupremeAI autonomous agents (Issue #2644).

বাংলা পরিচিতি (#2644 — Scoped JIT Credential Injection):
এজেন্টদের আর পুরো environment ডাম্প বা মাস্টার কী দেওয়া হবে না (Principle of
Least Privilege)। এই মডিউলটি হলো single source of truth (SSOT) ব্রোকার:

  1. BOT_SLOT_CREDENTIALS — স্লট → GitHub App mapping (SSOT; push_as_agent.py
     আর inline কপি রাখে না — #1821-এর ৫ম registry-copy drift ঝুঁকি বন্ধ)।
  2. Task-based scope filter — role অনুযায়ী child process-এ ONLY অনুমোদিত
     env key ইনজেক্ট হয় (coder ≠ planner ≠ audit)।
  3. JIT installation-token mint — ১ ঘণ্টার ক্ষণস্থায়ী token, RAM-only;
     কোনো কী কোথাও লেখা হয় না, লগে টোকেন mask হয়।
  4. Ephemeral Coder Lease — ৩য় পক্ষ/অনিবন্ধিত এজেন্ট task claim করলে ফ্রি
     স্লট-পুল থেকে TTL=3600s lease পায় (#2644 item 3 — Task-Claiming Bridge)।
  5. Zero-knowledge audit — সিক্রেটের শুধু নাম/উপস্থিতি যাচাই, ভ্যালু কখনো
     দেখা/প্রিন্ট হয় না (Control Tower masking-এর লোকাল পূরক)।

Rules (#2644 §4-5): স্ক্রিপ্ট সোর্সে কোনো কী হার্ডকোড নিষিদ্ধ; ক্রেডেনশিয়াল
শুধু রানটাইম env (vault.env / Infisical) থেকে মেমরিতে লোড হয়। Rules
Breaker এজেন্ট জিরো-কি স্যান্ডবক্সে চলে — এই মডিউল তাকে কোনো কী দেয় না।

CLI:
    python scripts/agents/credential_manager.py --slot agent-3 --print-scope
    python scripts/agents/credential_manager.py --lease unregistered-agent --ttl 3600
    python scripts/agents/credential_manager.py --audit --require GITHUB_APP_ID --require GITHUB_APP_PRIVATE_KEY

Exit codes: 0 = OK, 1 = credential/lease failure, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_VAULT_ENV = ROOT_DIR / "vault.env"
DEFAULT_LEASE_STORE = Path(os.environ.get("SUPREMEAI_LEASE_STORE", "/tmp/supremeai_agent_leases.json"))

INFISICAL_AUTH_URL = "https://app.infisical.com/api/v1/auth/universal-auth/login"
INFISICAL_SECRETS_URL = "https://app.infisical.com/api/v3/secrets/raw"
GITHUB_TOKEN_URL = "https://api.github.com/app/installations/{installation_id}/access_tokens"

# ─────────────────────────────────────────────────────────────────────────────
# SSOT: slot → GitHub App credential routing (#2644 item 1, #1821 follow-up).
# Governance source: docs/master_docs/AGENT_SLOT_REGISTRY.yaml (role pools);
# this table is its machine-consumable credential-routing projection — the
# ONLY place env-prefix/bot-name wiring lives (push_as_agent.py imports it).
# NO SECRETS HERE — only identities; credentials come from env/vault at runtime.
# ─────────────────────────────────────────────────────────────────────────────
BOT_SLOT_CREDENTIALS = {
    "agent-1": {
        "bot_name": "supremeai-planner",
        "env_prefix": "GITHUB_APP",
        "role": "planner",
        "scopes": ["issues:write"],  # planner = issue-output lane (charter §1)
    },
    "agent-2": {
        "bot_name": "supremeai-pr-helper",
        "env_prefix": "AGENT_PR_HELPER",
        "role": "pr-helper",
        "scopes": ["pull_requests:write", "issues:write"],
    },
    "agent-3": {
        "bot_name": "supremeai-coder-1",
        "env_prefix": "AGENT_CODER_1",
        "role": "coder",
        "scopes": ["contents:write", "pull_requests:write", "issues:write"],
    },
    "agent-5": {
        "bot_name": "supremeai-ci-action",
        "env_prefix": "AGENT_CI_ACTION",
        "role": "ci",
        "scopes": ["contents:write", "workflows:write", "pull_requests:write"],
    },
    "agent-6": {
        "bot_name": "supremeai-coder-2",
        "env_prefix": "AGENT_CODER_2",
        "role": "coder",
        "scopes": ["contents:write", "pull_requests:write", "issues:write"],
    },
    # #2644 item 2/4: 3rd-party audit agents get issue-creation access ONLY,
    # sourced from the shared planner/audit app pool via ephemeral lease —
    # never a dedicated admin key.
    "audit-pool": {
        "bot_name": "supremeai-planner",
        "env_prefix": "GITHUB_APP",
        "role": "auditor",
        "scopes": ["issues:write"],
        "lease_only": True,
    },
}

# Task-based scope filter (#2644 item 1): role → the ONLY env keys a child
# agent subprocess may receive. Anything else in the orchestrator's env
# (vault master creds, other slots' keys) is dropped — least privilege.
# বাংলা (#3229): AI provider keys — coder/ci/auditor roles-কে LLM access দিতে হবে,
# নাহলে autonomous agents + AI PR evaluator llm-unavailable fallback-এ পড়ে।
# rules_breaker stays zero-key (negative testing)। planner/pr-helper/browser
# দরকার নেই (issue-output/PR-gate/E2E — LLM call করে না)।
_AI_PROVIDER_KEYS = {
    "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
}

_BASE_SCOPED_KEYS = {"GH_TOKEN", "GH_REPO", "AGENT_SLOT", "AGENT_ROLE", "AGENT_NAME"}

# #4134: MCP Tower operational keys — the coordination plane every tower-
# coordinated role needs (heartbeat, role updates). NOT master vault creds
# (INFISICAL_*/GITHUB_APP_* stay orchestrator-only in FORBIDDEN_ENV_KEYS).
# mcp_tower_client reads MCP_TOWER_URL (→MCP_SERVER_URL fallback) + MCP_API_KEY;
# without them children silently degrade to viewer mode (read-only).
_MCP_TOWER_KEYS = {"MCP_API_KEY", "MCP_TOWER_URL"}

TASK_SCOPED_ENV_KEYS = {
    "planner": _BASE_SCOPED_KEYS | _MCP_TOWER_KEYS,
    "coder": _BASE_SCOPED_KEYS | _AI_PROVIDER_KEYS | _MCP_TOWER_KEYS,
    "pr-helper": _BASE_SCOPED_KEYS | _MCP_TOWER_KEYS,
    "ci": _BASE_SCOPED_KEYS | _AI_PROVIDER_KEYS | _MCP_TOWER_KEYS,
    "platform": _BASE_SCOPED_KEYS,
    "browser": _BASE_SCOPED_KEYS,
    "auditor": _BASE_SCOPED_KEYS | _AI_PROVIDER_KEYS | _MCP_TOWER_KEYS,
    # Rules Breaker / red-team (#2644 §4): ZERO-KEY sandbox — negative testing
    # proves no key is needed to be refused; the agent gets NOTHING here.
    "rules_breaker": set(),
}

# Env keys that must NEVER leak into a child process regardless of role —
# vault master credentials are orchestrator-only (zero-knowledge broker).
FORBIDDEN_ENV_KEYS = {
    "INFISICAL_CLIENT_ID",
    "INFISICAL_CLIENT_SECRET",
    "INFISICAL_PROJECT_ID",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
}


class CredentialError(RuntimeError):
    """Raised when scoped credentials cannot be resolved or minted."""


def slot_config(slot: str) -> dict:
    cfg = BOT_SLOT_CREDENTIALS.get(slot)
    if not cfg:
        raise CredentialError(
            f"Unknown slot '{slot}'. Known slots: {sorted(BOT_SLOT_CREDENTIALS)}"
        )
    return cfg


def load_vault_env(path: Path | None = None) -> dict:
    """Parse a vault.env file (KEY=VALUE lines; quotes stripped). Values stay
    in memory only — never logged, never returned to callers' __repr__."""
    p = Path(path) if path else DEFAULT_VAULT_ENV
    env: dict = {}
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _vault_extras_from(secrets: dict) -> dict:
    """Curated non-secret-credential delivery set from an already-fetched vault
    response (#4134): MCP Tower operational keys + AI provider keys.

    # বাংলা: fetch_credentials যেই secrets dict এর মধ্যে থাকে সেখান থেকেই scoped
    # spawn-এর জন্য দরকারি operational keys বের করে দেয় — কোনো অতিরিক্ত network
    # call নেই, কোনো নতুন ফ্রেমওয়ার্ক নেই (Rule A)। খালি ভ্যালু কখনো যায় না।
    """
    extras = {
        k: str(secrets[k]) for k in sorted(_AI_PROVIDER_KEYS)
        if str(secrets.get(k, "")).strip()
    }
    api_key = str(secrets.get("MCP_API_KEY", "")).strip()
    if api_key:
        extras["MCP_API_KEY"] = api_key
    # mcp_tower_client resolution order: MCP_TOWER_URL → MCP_SERVER_URL (→ mcp.json).
    # Vault stores the tower URL under whichever name ops chose; canonicalize to
    # MCP_TOWER_URL so children always speak the client's primary env name.
    tower_url = next(
        (str(secrets[k]).strip() for k in ("MCP_TOWER_URL", "MCP_SERVER_URL", "MCP_URL")
         if str(secrets.get(k, "")).strip()),
        "",
    )
    if tower_url:
        extras["MCP_TOWER_URL"] = tower_url
    return extras


def fetch_credentials(slot: str, vault: dict, transport=None) -> dict:
    """Resolve app credentials for a slot from Infisical (universal-auth).

    # বাংলা: ক্রেডেনশিয়াল শুধু রানটাইমে vault থেকে মেমরিতে আসে — সোর্সে
    # হার্ডকোড নিষিদ্ধ (rule 2)। transport injectable = টেস্টে নেটওয়ার্ক লাগে না।
    """
    cfg = slot_config(slot)
    prefix = cfg["env_prefix"]
    secrets = _infisical_fetch_secrets(vault, transport)
    app_id = secrets.get(f"{prefix}_APP_ID") or secrets.get("GITHUB_APP_ID")
    inst_id = secrets.get(f"{prefix}_INSTALLATION_ID") or secrets.get(
        "GITHUB_APP_INSTALLATION_ID"
    )
    pem = secrets.get(f"{prefix}_PRIVATE_KEY") or secrets.get("GITHUB_APP_PRIVATE_KEY")
    if not all([app_id, inst_id, pem]):
        # #4081: actionable error — explain what's missing + how to fix
        prefix_vars = [f"{prefix}_APP_ID", f"{prefix}_INSTALLATION_ID", f"{prefix}_PRIVATE_KEY"]
        fallback_vars = ["GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_PRIVATE_KEY"]
        raise CredentialError(
            f"Missing GitHub App creds for slot '{slot}' (prefix {prefix}).\n"
            f"Expected Infisical secrets (one of):\n"
            f"  Slot-specific: {prefix_vars}\n"
            f"  Fallback: {fallback_vars}\n"
            f"Check Infisical dashboard → prod environment → secretPath '/' → "
            f"ensure these secrets exist for slot '{slot}'.\n"
            f"Verify vault.env: python scripts/agents/credential_bootstrap.py --verify\n"
            f"See: docs/agents/credentials.md"
        )
    return {
        "slot": slot,
        "bot_name": cfg["bot_name"],
        "role": cfg["role"],
        "scopes": list(cfg["scopes"]),
        "app_id": app_id,
        "installation_id": inst_id,
        "private_key": pem,
        # #4134: same-fetch delivery extras (MCP Tower + AI keys) for the scoped
        # child env — orchestrator passes them through build_scoped_env(base_env).
        "vault_extras": _vault_extras_from(secrets),
    }


def _infisical_fetch_secrets(vault: dict, transport=None) -> dict:
    """Universal-auth login + raw secrets fetch. transport(requests-like) is
    injectable for offline tests.

    # বাংলা (#4081): Infisical login/secrets fetch-এ যেকোনো network/JSON error
    # হলে actionable CredentialError দেয় — silent KeyError নয়।
    """
    if transport is None:
        try:
            import requests as transport  # type: ignore[no-redef]
        except ImportError as err:
            raise CredentialError(
                "network transport unavailable (pip install requests) "
                "and no test transport injected"
            ) from err
    try:
        login = transport.post(
            INFISICAL_AUTH_URL,
            data={
                "clientId": vault.get("INFISICAL_CLIENT_ID", ""),
                "clientSecret": vault.get("INFISICAL_CLIENT_SECRET", ""),
            },
            timeout=30,
        )
    except Exception as err:
        raise CredentialError(
            f"Infisical login request failed (network error): {err}. "
            f"Check network connectivity to {INFISICAL_AUTH_URL}."
        ) from err
    try:
        login_json = login.json()
    except Exception as err:
        raise CredentialError(
            f"Infisical login returned non-JSON response (HTTP {login.status_code}). "
            f"Possible server error or wrong auth URL."
        ) from err
    access_token = login_json.get("accessToken")
    if not access_token:
        # #4081: actionable error — Infisical login failed (wrong creds)
        raise CredentialError(
            f"Infisical login failed — no accessToken in response. "
            f"Check INFISICAL_CLIENT_ID / INFISICAL_CLIENT_SECRET in vault.env. "
            f"Verify: python scripts/agents/credential_bootstrap.py --verify\n"
            f"See: docs/agents/credentials.md"
        )
    try:
        resp = transport.get(
            INFISICAL_SECRETS_URL,
            params={
                "workspaceId": vault.get("INFISICAL_PROJECT_ID", ""),
                "environment": "prod",
                "secretPath": "/",
                "include_imports": "true",
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except Exception as err:
        raise CredentialError(
            f"Infisical secrets fetch request failed (network error): {err}."
        ) from err
    try:
        secrets_payload = resp.json()
    except Exception as err:
        raise CredentialError(
            f"Infisical secrets fetch returned non-JSON (HTTP {resp.status_code}). "
            f"Possible token expiry or wrong INFISICAL_PROJECT_ID."
        ) from err
    if "secrets" not in secrets_payload:
        raise CredentialError(
            f"Infisical returned no 'secrets' key in response. "
            f"Check INFISICAL_PROJECT_ID in vault.env. "
            f"Verify: python scripts/agents/credential_bootstrap.py --verify"
        )
    return {
        s["secretKey"]: s.get("secretValue", "") or ""
        for s in secrets_payload["secrets"]
    }


def mint_installation_token(app_id: str, installation_id: str, private_key: str,
                            transport=None, now=None) -> dict:
    """Mint a 1-hour GitHub App installation token (JIT, memory-only).

    Returns {"token": ..., "expires_at": epoch_seconds}. The token is never
    written to disk; callers must mask it in logs (see mask_token()).
    """
    try:
        import jwt  # PyJWT — backend dep (pyjwt[crypto]); lazy import
    except ImportError as err:
        raise CredentialError(
            "PyJWT unavailable (pip install 'pyjwt[crypto]') — cannot mint JIT token"
        ) from err
    if transport is None:
        try:
            import requests as transport  # type: ignore[no-redef]
        except ImportError as err:
            raise CredentialError(
                "network transport unavailable (pip install requests) "
                "and no test transport injected"
            ) from err
    t = int(now if now is not None else time.time())
    app_jwt = jwt.encode(
        {"iat": t - 60, "exp": t + 600, "iss": app_id},
        private_key,
        algorithm="RS256",
    )
    resp = transport.post(
        GITHUB_TOKEN_URL.format(installation_id=installation_id),
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    data = resp.json()
    token = data.get("token")
    if not token:
        raise CredentialError(f"installation token mint failed: {data}")
    return {"token": token, "expires_at": t + 3600}


def mask_token(token: str) -> str:
    """Mask a token for safe logging (first chars never shown)."""
    if not token:
        return ""
    return "ghs_***" + token[-4:] if len(token) > 8 else "***"


# ─────────────────── scoped child-env construction (#2644 item 2) ───────────────────

def build_scoped_env(role: str, token: str = "", agent_name: str = "",
                     slot: str = "", repo: str = "SaifulHaqueNiloy/supremeai",
                     base_env: dict | None = None) -> dict:
    """Least-privilege env for a child agent subprocess (role-keyed, pure).

    # বাংলা: orchestrator-এর নিজের env (vault মাস্টার কী সহ) কখনোই সরাসরি
    # child-এ যায় না — role-এর TASK_SCOPED_ENV_KEYS allowlist ছাড়া কিছুই
    # পাস হয় না, FORBIDDEN keys টা-তেই বাদ। rules_breaker = জিরো-কি স্যান্ডবক্স।
    """
    allowed = TASK_SCOPED_ENV_KEYS.get(role)
    if allowed is None:
        raise CredentialError(
            f"no scoped env contract for role '{role}' "
            f"(known: {sorted(TASK_SCOPED_ENV_KEYS)})"
        )
    scoped: dict = {"GH_REPO": repo, "AGENT_ROLE": role}
    if slot:
        scoped["AGENT_SLOT"] = slot
    if agent_name:
        scoped["AGENT_NAME"] = agent_name
    if "GH_TOKEN" in allowed:
        scoped["GH_TOKEN"] = token
    if base_env:
        for k in allowed:
            if k in scoped:
                continue
            if k in base_env and k not in FORBIDDEN_ENV_KEYS:
                scoped[k] = base_env[k]
    leaked = FORBIDDEN_ENV_KEYS & set(scoped)
    if leaked:
        raise CredentialError(f"scope violation: forbidden keys leaked: {sorted(leaked)}")
    return scoped


def build_scoped_child_env(slot: str, token: str, agent_name: str = "",
                           repo: str = "SaifulHaqueNiloy/supremeai",
                           base_env: dict | None = None) -> dict:
    """Slot convenience wrapper over build_scoped_env (role from the SSOT)."""
    cfg = slot_config(slot)
    return build_scoped_env(
        cfg["role"], token=token, agent_name=agent_name,
        slot=slot, repo=repo, base_env=base_env,
    )


# ─────────────────── ephemeral coder lease (#2644 item 3) ───────────────────

def acquire_ephemeral_lease(agent_name: str, ttl: int = 3600,
                            lease_store: Path | None = None,
                            clock=None) -> dict:
    """Task-Claiming Bridge: unregistered/3rd-party agents get a 1-hour
    ephemeral lease from the shared audit-pool app after winning a claim.

    The lease record (agent, slot, expiry) persists in a tmp JSON store so
    expiry survives across processes; the TOKEN itself is minted on demand
    and never persisted (memory-only JIT).
    """
    if ttl <= 0 or ttl > 3600:
        raise CredentialError("ephemeral lease TTL must be in (0, 3600] seconds")
    store = Path(lease_store) if lease_store else DEFAULT_LEASE_STORE
    t = int(clock() if clock else time.time())
    leases = _load_leases(store)
    # housekeeping: drop expired leases
    leases = {k: v for k, v in leases.items() if v.get("expires_at", 0) > t}
    lease_id = f"lease-{agent_name}-{t}"
    leases[lease_id] = {
        "agent": agent_name,
        "slot": "audit-pool",
        "role": "auditor",
        "granted_at": t,
        "expires_at": t + ttl,
    }
    _save_leases(store, leases)
    return {"lease_id": lease_id, "slot": "audit-pool", "expires_at": t + ttl, "ttl": ttl}


def active_leases(lease_store: Path | None = None, clock=None) -> list:
    """Currently-active ephemeral leases (audit view — no tokens inside)."""
    store = Path(lease_store) if lease_store else DEFAULT_LEASE_STORE
    t = int(clock() if clock else time.time())
    return [
        {**v, "lease_id": k}
        for k, v in _load_leases(store).items()
        if v.get("expires_at", 0) > t
    ]


def _load_leases(store: Path) -> dict:
    try:
        return json.loads(store.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_leases(store: Path, leases: dict) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(leases, indent=1), encoding="utf-8")


# ─────────────────── zero-knowledge audit (#2644 item 7 core) ───────────────────

def audit_secret_presence(required_keys, source_env=None, label="env") -> dict:
    """Presence-only audit: which required keys exist — values NEVER surfaced.

    # বাংলা: জিরো-নলেজ ভ্যালিডেটর — কোন কী আছে/নেই শুধু নাম ধরে বলে
    # (missing_keys), ভ্যালু কখনো দেখে না। Control Tower masking-এর লোকাল পূরক।
    """
    env = source_env if source_env is not None else dict(os.environ)
    present, missing = [], []
    for key in required_keys:
        (present if str(env.get(key, "")).strip() else missing).append(str(key))
    return {
        "source": label,
        "checked": len(list(required_keys)),
        "present_keys": sorted(present),
        "missing_keys": sorted(missing),
        "ok": not missing,
    }


def resolve_and_mint_for_slot(slot: str, vault_path: Path | None = None,
                              transport=None) -> dict:
    """Convenience: fetch creds + mint JIT token for a slot (one call).

    # বাংলা (#4081): vault.env না থাকলে বা INFISICAL_* env না থাকলে actionable
    # error দেয় — "Missing GitHub App creds" এর বদলে bootstrap command দেখায়।
    """
    vault = load_vault_env(vault_path)
    if not vault:
        # fall back to process env (CI may inject INFISICAL_* directly)
        vault = {k: v for k, v in os.environ.items() if k.startswith("INFISICAL_")}
    if not vault:
        # #4081: actionable error — point to bootstrap script
        raise CredentialError(
            f"No Infisical credentials found for slot '{slot}'. "
            f"Either:\n"
            f"  1. Create vault.env: python scripts/agents/credential_bootstrap.py\n"
            f"  2. Set INFISICAL_* env vars (CI mode): "
            f"INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET, INFISICAL_PROJECT_ID\n"
            f"  3. Verify: python scripts/agents/credential_bootstrap.py --verify\n"
            f"See: docs/agents/credentials.md"
        )
    creds = fetch_credentials(slot, vault, transport=transport)
    minted = mint_installation_token(
        creds["app_id"], creds["installation_id"], creds["private_key"],
        transport=transport,
    )
    # private key never leaves this function's frame
    return {
        "slot": slot,
        "bot_name": creds["bot_name"],
        "role": creds["role"],
        "scopes": creds["scopes"],
        "token": minted["token"],
        "expires_at": minted["expires_at"],
        # #4134: MCP Tower + AI keys fetched in the same vault round-trip —
        # the loop gap-fills these into the child's base_env (ambient wins).
        "vault_extras": creds["vault_extras"],
    }


def run(cmd: list, env: dict) -> int:
    """Run a child agent process with a scoped env (#2644 item 2 wiring)."""
    merged = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL")}
    merged.update(env)
    proc = subprocess.run(cmd, env=merged, check=False)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Scoped JIT Credential Manager (#2644)")
    parser.add_argument("--slot", help="slot to resolve (e.g. agent-3, audit-pool)")
    parser.add_argument("--print-scope", action="store_true",
                        help="print the slot's scope contract (no secrets)")
    parser.add_argument("--lease", metavar="AGENT_NAME",
                        help="grant a 1h ephemeral lease to an unregistered agent")
    parser.add_argument("--ttl", type=int, default=3600)
    parser.add_argument("--list-leases", action="store_true")
    parser.add_argument("--audit", action="store_true",
                        help="zero-knowledge presence audit of required keys")
    parser.add_argument("--require", action="append", default=[],
                        help="key required by --audit (repeatable)")
    args = parser.parse_args()

    if args.print_scope:
        if not args.slot:
            print("--print-scope needs --slot", file=sys.stderr)
            return 2
        cfg = slot_config(args.slot)
        print(json.dumps({
            "slot": args.slot,
            "bot_name": cfg["bot_name"],
            "role": cfg["role"],
            "scopes": cfg["scopes"],
            "env_keys": sorted(TASK_SCOPED_ENV_KEYS.get(cfg["role"], set())),
        }, indent=1))
        return 0

    if args.lease:
        lease = acquire_ephemeral_lease(args.lease, ttl=args.ttl)
        print(json.dumps(lease, indent=1))
        return 0

    if args.list_leases:
        print(json.dumps(active_leases(), indent=1))
        return 0

    if args.audit:
        if not args.require:
            print("--audit needs at least one --require KEY", file=sys.stderr)
            return 2
        report = audit_secret_presence(args.require)
        print(json.dumps(report, indent=1))
        return 0 if report["ok"] else 1

    if args.slot:
        # mint path: token printed ONLY in masked form — real use is programmatic
        try:
            result = resolve_and_mint_for_slot(args.slot)
        except CredentialError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 1
        print(json.dumps({
            "slot": result["slot"],
            "bot_name": result["bot_name"],
            "role": result["role"],
            "scopes": result["scopes"],
            "token": mask_token(result["token"]),
            "expires_at": result["expires_at"],
        }, indent=1))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
