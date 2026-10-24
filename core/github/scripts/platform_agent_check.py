#!/usr/bin/env python3
"""platform-agent (agent-11) scheduled sweep — every 3 hours.

Charter: docs/agents/platform-agent-charter.md (issue #1439 ecosystem plan).
Probes every connected 3rd-party platform with its REAL API keys (pulled from
Infisical at runtime via universal auth), writes a markdown report to
$GITHUB_STEP_SUMMARY, and opens/updates a deduped GitHub issue labelled
`handoff:platform` when anything is DOWN/degraded.

stdlib-only (no pip install) — keep it that way for fast, dependency-free CI.

Exit codes: 0 = all checks OK (skips allowed), 1 = at least one FAILED.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

INFISICAL_HOST = os.environ.get("INFISICAL_HOST", "https://app.infisical.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "SaifulHaqueNiloy/supremeai")
ISSUE_TITLE_PREFIX = "[platform-agent]"
ISSUE_LABEL = "handoff:platform"
HTTP_TIMEOUT = 12

results: list[dict] = []


def record(platform: str, check: str, ok: bool | None, detail: str, critical: bool = False) -> None:
    """ok=True PASS, ok=False FAIL, ok=None SKIP."""
    results.append(
        {"platform": platform, "check": check, "ok": ok, "detail": detail, "critical": critical}
    )


def http(method: str, url: str, *, headers: dict | None = None, body: bytes | None = None, timeout: int = HTTP_TIMEOUT):
    req = urllib.request.Request(url, data=body, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8", "replace"), dict(res.headers)
    except urllib.error.HTTPError as err:  # non-2xx
        return err.code, err.read().decode("utf-8", "replace")[:500], dict(err.headers)
    except Exception as err:  # network/timeout/DNS
        return 0, f"{type(err).__name__}: {err}", {}


def json_body(payload) -> bytes:
    return json.dumps(payload).encode()


# ── Infisical ────────────────────────────────────────────────────────────────

def infisical_login() -> str | None:
    client_id = os.environ.get("INFISICAL_CLIENT_ID", "")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        record("infisical", "universal-auth login", None, "INFISICAL_CLIENT_ID/SECRET not set — vault probes will be skipped")
        return None
    status, body, _ = http(
        "POST",
        f"{INFISICAL_HOST}/api/v1/auth/universal-auth/login",
        headers={"Content-Type": "application/json"},
        body=json_body({"clientId": client_id, "clientSecret": client_secret}),
    )
    if status == 200:
        token = json.loads(body).get("accessToken")
        record("infisical", "universal-auth login", True, "HTTP 200")
        return token
    record("infisical", "universal-auth login", False, f"HTTP {status}: {body[:180]}", critical=True)
    return None


def infisical_secrets(token: str | None) -> dict:
    """All prod secrets as a case-insensitive dict (import-aware v3 raw)."""
    if not token:
        return {}
    project_id = os.environ.get("INFISICAL_PROJECT_ID", "")
    if not project_id:
        record("infisical", "secrets pull", None, "INFISICAL_PROJECT_ID not set")
        return {}
    query = urllib.parse.urlencode(
        {"workspaceId": project_id, "environment": "prod", "includeImports": "true", "recursive": "true"}
    )
    status, body, _ = http(
        "GET", f"{INFISICAL_HOST}/api/v3/secrets/raw?{query}", headers={"Authorization": f"Bearer {token}"}
    )
    if status != 200:
        record("infisical", "secrets pull", False, f"HTTP {status}: {body[:180]}", critical=True)
        return {}
    secrets = json.loads(body).get("secrets", [])
    record("infisical", "secrets pull", True, f"{len(secrets)} secrets (incl. imports)")
    # v3 raw API entries carry `secretKey`/`secretValue`; older shapes used
    # `key`/`value`. Parse both — a wrong field name here silently empties the
    # dict and every vault-dependent probe is skipped as "not in vault".
    parsed: dict = {}
    for s in secrets:
        key = (s.get("secretKey") or s.get("key") or "").upper()
        if not key:
            continue
        value = s.get("secretValue")
        if value is None:
            value = s.get("value", "")
        parsed[key] = value
    return parsed


# ── Probes ───────────────────────────────────────────────────────────────────

def probe_upstash_chain(sec: dict) -> None:
    suffixes = ["", "SECONDARY_", "TERTIARY_", "QUATERNARY_", "QUINARY_"]
    for suffix in suffixes:
        url = sec.get(f"UPSTASH_REDIS_{suffix}REST_URL", "")
        token = sec.get(f"UPSTASH_REDIS_{suffix}REST_TOKEN", "")
        label = (suffix.rstrip("_") or "primary").lower()
        if not url or not token:
            record("upstash", f"ping[{label}]", None, "no REST creds in vault — account absent")
            continue
        status, body, _ = http("POST", f"{url}/ping", headers={"Authorization": f"Bearer {token}"})
        ok = status == 200 and "pong" in body.lower()
        record(
            "upstash",
            f"ping[{label}]",
            ok,
            f"HTTP {status}: {body[:120]}" if not ok else f"HTTP {status} PONG",
            critical=(label == "primary" and not ok),
        )


def probe_render() -> None:
    # Service ↔ key map (verified live; each service lives on a different
    # Render account, so its own API key must be used):
    #   tower   → RENDER_API_KEY_4 · primary → KEY_1 · worker → KEY_2 · scraper → KEY_3
    services = [
        ("tower", "RENDER_MCP_SVC_ID", "RENDER_API_KEY_4"),
        ("primary", "RENDER_PRIMARY_SVC_ID", "RENDER_API_KEY_1"),
        ("worker", "RENDER_WORKER_SVC_ID", "RENDER_API_KEY_2"),
        ("scraper", "RENDER_SCRAPER_SVC_ID", "RENDER_API_KEY_3"),
    ]
    seen_keys = set()
    for _, _, key_env in services:
        if key_env in seen_keys:
            continue
        seen_keys.add(key_env)
        api_key = os.environ.get(key_env, "")
        if not api_key:
            record("render", f"auth[{key_env}]", None, f"{key_env} not set in Actions secrets")
            continue
        status, body, _ = http(
            "GET", "https://api.render.com/v1/services?limit=1", headers={"Authorization": f"Bearer {api_key}"}
        )
        record("render", f"auth[{key_env}]", status == 200, f"HTTP {status}")
    for name, svc_env, key_env in services:
        svc_id = os.environ.get(svc_env, "")
        api_key = os.environ.get(key_env, "")
        if not svc_id or not api_key:
            record("render", f"deploy[{name}]", None, f"{svc_env}/{key_env} not set")
            continue
        status, body, _ = http(
            "GET",
            f"https://api.render.com/v1/services/{svc_id}/deploys?limit=1",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if status != 200:
            record("render", f"deploy[{name}]", False, f"HTTP {status}: {body[:120]}")
            continue
        deploys = json.loads(body)
        latest = (deploys[0].get("deploy", {}) if deploys else {}) or {}
        state = latest.get("status", "unknown")
        if state in ("live", "deactivated"):
            record("render", f"deploy[{name}]", True, f"latest deploy status={state}")
        elif state in ("build_in_progress", "update_in_progress", "pre_deploy", "queued", "prepare", "activating"):
            # Rolling deploys are normal operation, not outages — WARN instead
            # of failing (transient noise flooded tracker issue #1810).
            record("render", f"deploy[{name}]", None, f"deploy in progress (transient): {state}")
        else:
            record("render", f"deploy[{name}]", False, f"latest deploy status={state}")


def probe_tower(sec: dict) -> None:
    base = os.environ.get("RENDER_MCP_URL", "") or sec.get("MCP_URL", "")
    api_key = sec.get("MCP_API_KEY", "") or sec.get("MCP_ADMIN_KEY", "")
    if not base:
        record("mcp-tower", "initialize", None, "RENDER_MCP_URL/MCP_URL unavailable")
        return
    if base.endswith("/"):
        base = base.rstrip("/")
    status, body, headers = http(
        "POST",
        f"{base}/mcp",
        headers={
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
            "Accept": "application/json, text/event-stream",
        },
        body=json_body({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "platform-agent-sweep", "version": "1.0"},
        }}),
    )
    session = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
    ok = status == 200 and bool(session)
    record("mcp-tower", "initialize", ok, f"HTTP {status}, session={'yes' if session else 'no'}" if ok else f"HTTP {status}: {body[:160]}")


def probe_cloudflare(sec: dict) -> None:
    # Vault is the source of truth (charter §Check protocol 3): prefer the
    # vault value; the Actions secret is only a fallback and may drift stale.
    token = sec.get("CLOUDFLARE_API_TOKEN", "") or os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if token:
        status, body, _ = http(
            "GET", "https://api.cloudflare.com/client/v4/user/tokens/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        ok = status == 200 and '"success":true' in body.replace(" ", "")
        record("cloudflare", "api-token verify", ok, f"HTTP {status}: {body[:140]}" if not ok else f"HTTP {status} active")
    # Global-key accounts (primary + secondary/tertiary/quaternary/quinary)
    for prefix in ["", "SECONDARY_", "TERTIARY_", "QUATERNARY_", "QUINARY_"]:
        email = sec.get(f"CLOUDFLARE_{prefix}EMAIL", "")
        key = sec.get(f"CLOUDFLARE_{prefix}GLOBAL_API_KEY", "")
        label = (prefix.rstrip("_") or "primary").lower()
        if not email or not key:
            record("cloudflare", f"user[{label}]", None, "no global key in vault")
            continue
        status, body, _ = http(
            "GET", "https://api.cloudflare.com/client/v4/user",
            headers={"X-Auth-Email": email, "X-Auth-Key": key},
        )
        ok = status == 200 and '"success":true' in body.replace(" ", "")
        record("cloudflare", f"user[{label}]", ok, f"HTTP {status}: {body[:120]}" if not ok else f"HTTP {status} ok")


def probe_supabase(sec: dict) -> None:
    url = sec.get("SUPABASE_URL", "").rstrip("/")
    key = sec.get("SUPABASE_KEY", "")
    if not url or not key:
        record("supabase", "auth health", None, "SUPABASE_URL/KEY not in vault")
        return
    status, body, _ = http("GET", f"{url}/auth/v1/health", headers={"apikey": key})
    record("supabase", "auth health", status == 200, f"HTTP {status}: {body[:140]}" if status != 200 else f"HTTP {status}")


def probe_kaggle(sec: dict) -> None:
    pool = sec.get("KAGGLE_API_TOKENS", "") or sec.get("KAGGLE_API_TOKEN", "")
    if not pool:
        record("kaggle", "competitions list", None, "no KAGGLE_API_TOKENS in vault")
        return
    first = pool.split(",")[0].strip()
    # Vault tokens come in two shapes: "user:key" (classic) and "user_key"
    # (single underscore, 32-hex key). Parse both so the honest HTTP result
    # (e.g. 401 for a revoked token) is reported instead of a format error.
    if ":" in first:
        user, token_key = first.split(":", 1)
    elif "_" in first:
        user, token_key = first.split("_", 1)
    else:
        record("kaggle", "competitions list", False, "token format unexpected (expected user:key or user_key)")
        return
    auth = base64.b64encode(f"{user}:{token_key}".encode()).decode()
    status, body, _ = http(
        "GET", "https://www.kaggle.com/api/v1/competitions/list?page=1",
        headers={"Authorization": f"Basic {auth}"},
    )
    record("kaggle", "competitions list", status == 200, f"HTTP {status}: {body[:140]}" if status != 200 else f"HTTP {status} ok")


def probe_ai_providers(sec: dict) -> None:
    def models(name: str, url: str, key: str, headers: dict | None = None, ok_contains: str = '"data"') -> None:
        if not key:
            record(name, "models list", None, "key not in vault")
            return
        status, body, _ = http("GET", url, headers=headers or {"Authorization": f"Bearer {key}"})
        ok = status == 200 and ok_contains in body
        record(name, "models list", ok, f"HTTP {status}: {body[:140]}" if not ok else f"HTTP {status}")

    models("groq", "https://api.groq.com/openai/v1/models", sec.get("GROQ_API_KEY", ""))
    models("openai", "https://api.openai.com/v1/models", sec.get("OPENAI_API_KEY", ""))
    models("cerebras", "https://api.cerebras.ai/v1/models", sec.get("CEREBRAS_API_KEY", ""))
    gemini = sec.get("GEMINI_API_KEY", "")
    if gemini:
        models("gemini", f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini}", gemini,
               {"x-goog-api-key": gemini}, '"models"')
    else:
        record("gemini", "models list", None, "key not in vault")
    firecrawl = sec.get("FIRECRAWL_API_KEY", "")
    if firecrawl:
        # The credit-usage endpoint only accepts GET (POST → HTTP 405).
        status, body, _ = http(
            "GET", "https://api.firecrawl.dev/v1/team/credit-usage",
            headers={"Authorization": f"Bearer {firecrawl}"},
        )
        record("firecrawl", "credit usage", status == 200, f"HTTP {status}: {body[:140]}" if status != 200 else f"HTTP {status}")
    else:
        record("firecrawl", "credit usage", None, "key not in vault")


def probe_github() -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    status, body, _ = http("GET", "https://api.github.com/rate_limit", headers={"Authorization": f"Bearer {token}"})
    record("github", "rate_limit", status == 200, f"HTTP {status}")


# ── Mirror freshness (#2130) ──────────────────────────────────────────────────

MIRROR_TARGET_REPO = "paykaribazaronline/supremeai"
MIRROR_ORIGIN_REPO = "SaifulHaqueNiloy/supremeai"
GITLAB_PROJECT_PATH = "paykaribazaronline%2Fsupremeai"


def _age_hours_since(iso_ts: str) -> float | None:
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return None


def probe_mirror(sec: dict) -> None:
    """Mirror freshness detection (target + gitlab) — issue #2130.
    Public-API only; the sync actuator lives in the agent-11 3h cron daemon.
    Thresholds: <=6h OK, 6-24h WARN, >24h FAIL."""
    gh_headers = {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}"} if os.environ.get("GITHUB_TOKEN") else {}
    status, body, _ = http("GET", f"https://api.github.com/repos/{MIRROR_TARGET_REPO}", headers=gh_headers)
    if status != 200:
        record("mirror", "target freshness", False, f"cannot read pushed_at: HTTP {status}")
    else:
        age = _age_hours_since(json.loads(body).get("pushed_at", ""))
        if age is None:
            record("mirror", "target freshness", False, "pushed_at parse error")
        elif age <= 6:
            record("mirror", "target freshness", True, f"last push {age:.1f}h ago")
        elif age <= 24:
            record("mirror", "target freshness", None, f"target {age:.1f}h behind — WARN")
        else:
            record("mirror", "target freshness", False, f"target {age:.1f}h behind origin")

    gitlab_token = sec.get("GITLAB_PAT", "") or sec.get("GITLAB_PROJECT_ACCESS_TOKEN", "")
    if not gitlab_token:
        record("mirror", "gitlab freshness", None, "pending owner credential (#2130) — no GitLab token in vault")
        return
    status, body, _ = http(
        "GET",
        f"https://gitlab.com/api/v4/projects/{GITLAB_PROJECT_PATH}/repository/commits?ref_name=main&per_page=1",
        headers={"PRIVATE-TOKEN": gitlab_token},
    )
    if status != 200:
        record("mirror", "gitlab freshness", False, f"HTTP {status}")
        return
    try:
        age = _age_hours_since(json.loads(body)[0].get("committed_date", ""))
    except Exception as exc:
        record("mirror", "gitlab freshness", False, f"parse error: {exc}")
        return
    if age is None:
        record("mirror", "gitlab freshness", False, "committed_date parse error")
    elif age <= 6:
        record("mirror", "gitlab freshness", True, f"last commit {age:.1f}h ago")
    elif age <= 24:
        record("mirror", "gitlab freshness", None, f"gitlab {age:.1f}h behind — WARN")
    else:
        record("mirror", "gitlab freshness", False, f"gitlab {age:.1f}h stale")


# ── GitHub issue (dedup) ─────────────────────────────────────────────────────

def gh_api(method: str, path: str, payload=None):
    token = os.environ.get("GITHUB_TOKEN", "")
    status, body, _ = http(
        method, f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        body=json_body(payload) if payload is not None else None,
    )
    try:
        return status, json.loads(body)
    except Exception:
        return status, {"raw": body[:300]}


def ensure_label() -> None:
    gh_api("POST", f"/repos/{REPO}/labels", {
        "name": ISSUE_LABEL, "color": "F9A825",
        "description": "External platform issue — routes to platform-agent (agent-11)",
    })


def upsert_issue(failures: list[dict], run_url: str) -> None:
    if not failures:
        return
    ensure_label()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"- **{f['platform']}** — `{f['check']}`: {f['detail']}" for f in failures]
    body = (
        f"Automated 3-hour sweep failure report ({now}).\n\n"
        + "\n".join(lines)
        + (f"\n\n[Sweep run log]({run_url})" if os.environ.get("GITHUB_RUN_ID") else "")
        + "\n\n"
        + "Charter: `docs/agents/platform-agent-charter.md` — platform-agent (agent-11) owns diagnosis, fix-if-possible, and platform-side config changes (owner approval for destructive/billing)."
    )
    q = urllib.parse.quote(f'repo:{REPO} state:open type:issue in:title "{ISSUE_TITLE_PREFIX}"')
    status, data = gh_api("GET", f"/search/issues?q={q}&per_page=1")
    items = (data.get("items") or []) if status == 200 else []
    if items:
        number = items[0]["number"]
        gh_api("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": body})
        print(f"updated existing issue #{number}")
    else:
        status, data = gh_api("POST", f"/repos/{REPO}/issues", {
            "title": f"{ISSUE_TITLE_PREFIX} {len(failures)} platform check(s) failing — {now}",
            "body": body, "labels": [ISSUE_LABEL],
        })
        if status in (200, 201):
            print(f"created issue #{data.get('number')}")
        else:
            print(f"issue creation FAILED (HTTP {status}): {json.dumps(data)[:400]}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    token = infisical_login()
    sec = infisical_secrets(token)

    probe_upstash_chain(sec)
    probe_render()
    probe_tower(sec)
    probe_cloudflare(sec)
    probe_supabase(sec)
    probe_kaggle(sec)
    probe_ai_providers(sec)
    probe_github()
    probe_mirror(sec)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    failed = [r for r in results if r["ok"] is False]
    skipped = [r for r in results if r["ok"] is None]
    passed = [r for r in results if r["ok"] is True]

    summary_lines = ["## 🛰️ Platform-Agent Sweep (agent-11)", f"**When:** {now}", "",
        "| Result | Platform | Check | Detail |", "|---|---|---|---|"]
    for r in results:
        icon = "✅" if r["ok"] is True else ("❌" if r["ok"] is False else "⏭️")
        summary_lines.append(f"| {icon} | {r['platform']} | `{r['check']}` | {r['detail']} |")
    summary_lines += ["", f"**Totals:** {len(passed)} passed · {len(failed)} failed · {len(skipped)} skipped"]
    report = "\n".join(summary_lines)
    print(report)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")

    run_url = f"https://github.com/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    if failed:
        upsert_issue(failed, run_url)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
