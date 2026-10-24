#!/usr/bin/env python3
"""SupremeAI Pre-Merge Guard (প্রি-মার্জ গার্ড) — one command, every class of problem.

Why this exists
---------------
The repo already has 30+ check scripts (detect_silent_errors.py, scripts/ci/*,
ci-full-audit.sh, pre_deploy_check.sh) — yet on 2026-03-09 three production
outages shipped that none of them caught:

  1. CORSMiddleware.allow_headers missing X-Device-Fingerprint  -> every frontend 400
  2. USER_CORS_ORIGINS on Render missing user app domain         -> user app 400
  3. Vercel build pointing at a dead host                        -> admin calls 503

Root reason: each script checks one file in isolation. Nothing checked the
*contract* between frontend and backend, nothing probed the *live* services
with the *real* headers, and typecheck was non-blocking so 133 TS errors piled up.

This guard fixes that by:
  * REUSING every existing checker (no duplicated logic)
  * ADDING contract + live-probe checks for the bug classes that slipped through
  * BASELINING counts so legacy debt does not block merges, but *new* debt does
  * NOTIFYING Discord / Telegram / GitHub step summary with a ranked list

Zero third-party Python deps (stdlib only). Tools it shells out to are optional —
a missing tool is reported as SKIP, never as a crash.

Usage
-----
  python scripts/pre_merge_guard.py                 # full local run (static only)
  python scripts/pre_merge_guard.py --quick         # fast subset (< 2 min)
  python scripts/pre_merge_guard.py --live          # + probe Render/Firebase/Vercel
  python scripts/pre_merge_guard.py --changed       # only files changed vs origin/main
  python scripts/pre_merge_guard.py --only cors,ts  # run selected groups
  python scripts/pre_merge_guard.py --skip pytest   # skip a group
  python scripts/pre_merge_guard.py --baseline      # record current counts as accepted debt
  python scripts/pre_merge_guard.py --notify        # push summary to Discord/Telegram
  python scripts/pre_merge_guard.py --json out.json --md out.md

Exit codes: 0 = safe to merge · 1 = blocking findings · 2 = guard itself failed

Groups: cors, env, fe-contract, ts, eslint, ruff, pysyntax, silent, config,
        secrets, topology, api-contract, routers, live, pytest

SCRIPT-INTELLIGENCE v9: auto-discovers targets via scripts/lib/auto_discovery.py — no hardcoded file inventories.
Service URLs are RESOLVED, never guessed:
  1. PRE_MERGE_DOMAINS            explicit human override (JSON {role:url}
                                  or comma-separated domains; fail-loud when set)
  2. PRE_MERGE_SERVICE_URLS       CI JSON pin {"primary": "https://..."}
  3. RENDER_*_URL env vars / RENDER_SERVICES JSON
  4. render.yaml service names -> https://<name>.onrender.com (discovery lib)
If NOTHING is discoverable the guard fails with exit 2 (guard itself failed)
instead of silently probing stale literal domains.  The app_builder module
reference is discovered by role (discover_core_modules) with a candidates
fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

# SCRIPT-INTELLIGENCE v9: shared discovery lib (stdlib only, first-party).
sys.path.insert(0, str(Path(__file__).resolve().parent))  # -> scripts/
from lib.auto_discovery import (  # noqa: E402
    DiscoveryError,
    discover_core_modules,
    discover_service_urls,
    existing_paths,
)
from ci.merge_policy import classify_result, load_policy, record_decision  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
BASELINE_FILE = ROOT / ".pre_merge_baseline.json"
REPORT_DIR = ROOT / "ci-reports"

# ---------------------------------------------------------------------------
# Live topology (SCRIPT-INTELLIGENCE v9: DISCOVERED at runtime, never literals).
# Resolution order: PRE_MERGE_DOMAINS (human override, fail-loud) ->
# PRE_MERGE_SERVICE_URLS pin -> RENDER_*_URL / RENDER_SERVICES -> render.yaml
# convention (via the discovery lib).  Nothing discoverable -> DiscoveryError.
# ---------------------------------------------------------------------------
HEALTH_PATHS = {
    "primary": "/api/v1/health/live",
    "worker": "/health",
    "scraper": "/api/v1/health/live",
    "mcp": "/health",
    "edge": "/",
}
# Routes a real browser preflights on first load / login.
PREFLIGHT_ROUTES = ["/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/admin/health"]

_ROLE_KEYWORDS = (("mcp", "mcp"), ("scraper", "scraper"), ("worker", "worker"),
                  ("primary", "primary"), ("node", "primary"))


def _normalize_url(u: str) -> str:
    u = u.strip().rstrip("/")
    if u and not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def _role_for(name: str) -> str:
    low = name.lower()
    for kw, role in _ROLE_KEYWORDS:
        if kw in low:
            return role
    return name


def _parse_pre_merge_domains(raw: str) -> dict[str, str]:
    """PRE_MERGE_DOMAINS human override: JSON {role: url} or comma-separated
    domains mapped onto (primary, worker, scraper, mcp, edge) in order.
    Fail-loud on anything malformed: a human pinned these values, silently
    ignoring them would probe the wrong targets."""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DiscoveryError(f"PRE_MERGE_DOMAINS is not valid JSON: {exc}") from exc
        if not isinstance(data, dict) or not data:
            raise DiscoveryError("PRE_MERGE_DOMAINS JSON must be a non-empty object {role: url}")
        return {str(k).lower(): _normalize_url(str(v)) for k, v in data.items()}
    domains = [d for d in (x.strip() for x in raw.split(",")) if d]
    if not domains:
        raise DiscoveryError("PRE_MERGE_DOMAINS is set but empty")
    return {role: _normalize_url(d)
            for role, d in zip(("primary", "worker", "scraper", "mcp", "edge"), domains)}


def resolve_live_targets() -> tuple[dict[str, str], list[str], list[str]]:
    """Resolve live backends/frontends from env + repo discovery.

    Returns (backends {role: url}, frontends [url], discovery notes).
    Raises DiscoveryError when no backend URL is discoverable -- the guard
    must never probe a guessed production domain.
    """
    notes: list[str] = []
    backends: dict[str, str] = {}

    pmd = os.getenv("PRE_MERGE_DOMAINS")
    if pmd:
        backends = _parse_pre_merge_domains(pmd)
        notes.append(f"[discovery] backends from PRE_MERGE_DOMAINS (human override): "
                     f"{sorted(backends)}")
    else:
        disc = discover_service_urls(fail_loud=False, env_override="PRE_MERGE_SERVICE_URLS")
        for svc in disc.services:
            backends[_role_for(svc.name)] = svc.url.rstrip("/")
            notes.append(f"[discovery] backend '{svc.name}' -> {svc.url} (source: {svc.source})")
        for n in disc.notes:
            notes.append(f"[discovery] {n}")
        if not backends:
            raise DiscoveryError(
                "No service URLs discoverable. Set PRE_MERGE_DOMAINS or "
                "PRE_MERGE_SERVICE_URLS (JSON), RENDER_<NAME>_URL env vars, or commit "
                "render.yaml -- the guard never probes guessed production domains."
            )

    edge = os.getenv("SUPREMEAI_CF_WORKER_URL")
    if edge:
        backends.setdefault("edge", _normalize_url(edge))
        notes.append("[discovery] backend 'edge' -> SUPREMEAI_CF_WORKER_URL")

    frontends: list[str] = []
    cors = os.getenv("CORS_ORIGINS", "")
    if cors.strip():
        frontends = [u.strip().rstrip("/") for u in cors.split(",") if u.strip()]
        notes.append(f"[discovery] frontends from CORS_ORIGINS env: {len(frontends)}")
    for role in ("frontend", "user", "admin"):
        if role in backends and backends[role] not in frontends:
            frontends.append(backends[role])
            notes.append(f"[discovery] frontend from pin role '{role}'")
    if not frontends:
        notes.append("[discovery] no frontend origins discoverable "
                     "(live frontend probes will SKIP, never guess)")
    return backends, frontends, notes

SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
BLOCKING = {"CRITICAL", "HIGH"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    check: str
    severity: str
    message: str
    location: str = ""
    fix: str = ""


@dataclass
class CheckResult:
    name: str
    group: str
    status: str  # PASS | FAIL | WARN | SKIP | ERROR
    duration_s: float
    findings: list[Finding] = field(default_factory=list)
    count: int = 0  # numeric metric used for baseline comparison
    note: str = ""


@dataclass
class Check:
    name: str
    group: str
    fn: Callable[["Ctx"], CheckResult]
    quick: bool = True  # included in --quick
    live: bool = False  # requires network
    slow: bool = False  # excluded unless --full


@dataclass
class Ctx:
    args: argparse.Namespace
    changed_files: set[str]
    baseline: dict
    backends: dict = field(default_factory=dict)    # v9: discovered {role: base_url}
    frontends: list = field(default_factory=list)   # v9: discovered frontend origins


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run(cmd: list[str], cwd: Path = ROOT, timeout: int = 600, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
            env={**os.environ, **(env or {})},
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s: {' '.join(cmd)}"


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def http(url: str, method: str = "GET", headers: dict | None = None, timeout: int = 30) -> tuple[int, dict, str]:
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(600).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read(600).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - probe must never crash the guard
        return 0, {}, f"{type(e).__name__}: {e}"


def timed(name: str, group: str, body: Callable[[], tuple[str, list[Finding], int, str]]) -> CheckResult:
    t0 = time.time()
    try:
        status, findings, count, note = body()
    except Exception as e:  # noqa: BLE001
        return CheckResult(name, group, "ERROR", time.time() - t0, [Finding(name, "HIGH", f"guard crashed: {e}")], 0)
    return CheckResult(name, group, status, time.time() - t0, findings, count, note)


def grep_files(base: Path, exts: tuple[str, ...], pattern: re.Pattern, exclude: tuple[str, ...] = ()) -> list[tuple[Path, int, str]]:
    hits = []
    for p in base.rglob("*"):
        if not p.is_file() or p.suffix not in exts:
            continue
        sp = str(p)
        if any(x in sp for x in ("node_modules", "/dist/", "/.git/", "__pycache__", "_archive", *exclude)):
            continue
        try:
            for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if pattern.search(line):
                    hits.append((p, i, line.strip()))
        except OSError:
            continue
    return hits


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def parse_env_list(text: str, key: str) -> list[str]:
    m = re.search(rf"^{key}\s*=\s*(.+)$", text, re.M)
    if not m:
        return []
    raw = m.group(1).strip().strip("'\"")
    try:
        v = json.loads(raw)
        return [str(x).rstrip("/") for x in v] if isinstance(v, list) else [raw]
    except json.JSONDecodeError:
        return [x.strip().strip("'\"").rstrip("/") for x in raw.strip("[]").split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Wrapper: reuse an EXISTING repo script as a check (no logic duplication)
# ---------------------------------------------------------------------------
def existing_script(name: str, group: str, cmd: list[str], severity: str = "HIGH", cwd: Path = ROOT,
                    quick: bool = True, slow: bool = False, count_re: str | None = None) -> Check:
    def fn(ctx: Ctx) -> CheckResult:
        def body():
            script = next((c for c in cmd if c.endswith((".py", ".sh"))), None)
            if script and not (cwd / script).exists() and not Path(script).exists():
                return "SKIP", [], 0, f"script missing: {script}"
            if cmd[0] not in (sys.executable, "python", "bash", "sh") and not have(cmd[0]):
                return "SKIP", [], 0, f"tool not installed: {cmd[0]}"
            rc, out = run(cmd, cwd=cwd, timeout=1800 if slow else 600)
            if rc == 127:
                return "SKIP", [], 0, out.strip()[:200]
            count = 0
            if count_re:
                m = re.search(count_re, out)
                count = int(m.group(1)) if m else (0 if rc == 0 else 1)
            else:
                count = 0 if rc == 0 else 1
            if rc == 0:
                return "PASS", [], count, ""
            tail = "\n".join(out.strip().splitlines()[-12:])
            return "FAIL", [Finding(name, severity, f"exit {rc}", location=" ".join(cmd), fix=tail)], count, ""
        return timed(name, group, body)
    return Check(name, group, fn, quick=quick, slow=slow)


# ---------------------------------------------------------------------------
# NEW CHECKS — the bug classes that slipped through on 2026-03-09
# ---------------------------------------------------------------------------
def check_cors_header_contract(ctx: Ctx) -> CheckResult:
    """Every X-* header the frontend sends MUST be in CORSMiddleware.allow_headers."""
    def body():
        # SCRIPT-INTELLIGENCE v9: app_builder discovered by role, with a
        # candidates fallback -- a rename no longer silently voids the check.
        ab = discover_core_modules().get("app_builder")
        if ab is None:
            cands = existing_paths([BACKEND / "core" / "app_builder.py",
                                    BACKEND / "app_builder.py"])
            ab = cands[0] if cands else None
        if ab is None:
            return "SKIP", [], 0, "app_builder not discoverable (role missing)"
        src = ab.read_text(errors="replace")
        m = re.search(r"allow_headers\s*=\s*\[(.*?)\]", src, re.S)
        if not m:
            return "FAIL", [Finding("cors-header-contract", "CRITICAL", "CORSMiddleware has no allow_headers list", rel(ab))], 1, ""
        allowed = {h.strip().strip("'\"").lower() for h in m.group(1).split(",") if h.strip().strip("'\"")}
        wildcard = "*" in allowed
        # Headers the frontend actually sets
        pat = re.compile(r"""['"`](X-[A-Za-z0-9-]+)['"`]\s*[:\]=]""")
        sent: dict[str, str] = {}
        for p, i, line in grep_files(FRONTEND / "src", (".ts", ".tsx"), pat, exclude=(".test.", ".stories.")):
            for h in pat.findall(line):
                sent.setdefault(h.lower(), f"{rel(p)}:{i}")
        findings = []
        for h, loc in sorted(sent.items()):
            if not wildcard and h not in allowed:
                findings.append(Finding(
                    "cors-header-contract", "CRITICAL",
                    f"frontend sends header '{h}' but CORSMiddleware.allow_headers does not include it -> browser preflight 400",
                    loc, f"add \"{h}\" to allow_headers in {rel(ab)}"))
        return ("FAIL" if findings else "PASS"), findings, len(findings), f"{len(sent)} custom headers sent, {len(allowed)} allowed"
    return timed("cors-header-contract", "cors", body)


def check_cors_origin_drift(ctx: Ctx) -> CheckResult:
    """USER_CORS_ORIGINS overrides CORS_ORIGINS. Every live frontend must be in the winning list.
    Checks .env.example (repo) and process env (Render/CI) if present."""
    def body():
        findings = []
        sources = {}
        envx = ROOT / ".env.example"
        if envx.exists():
            sources[".env.example"] = envx.read_text(errors="replace")
        if os.getenv("USER_CORS_ORIGINS") or os.getenv("CORS_ORIGINS"):
            sources["process.env"] = "\n".join(f"{k}={os.getenv(k, '')}" for k in ("CORS_ORIGINS", "USER_CORS_ORIGINS", "ADMIN_CORS_ORIGINS"))
        for src_name, text in sources.items():
            cors = parse_env_list(text, "CORS_ORIGINS")
            user = parse_env_list(text, "USER_CORS_ORIGINS")
            admin = parse_env_list(text, "ADMIN_CORS_ORIGINS")
            effective = set(user) if user else set(cors)
            effective |= set(admin)
            if not ctx.frontends:
                return ("WARN" if findings else "SKIP"), findings, len(findings), \
                    f"checked {list(sources)}; [discovery] no live frontends discovered -- membership check skipped"
            for fe in ctx.frontends:
                if fe not in effective:
                    findings.append(Finding(
                        "cors-origin-drift", "CRITICAL",
                        f"live frontend {fe} NOT in effective CORS allow-list ({'USER_CORS_ORIGINS wins' if user else 'CORS_ORIGINS'})",
                        src_name, f"add \"{fe}\" to USER_CORS_ORIGINS (it overrides CORS_ORIGINS)"))
            for o in set(cors) - effective:
                findings.append(Finding("cors-origin-drift", "HIGH",
                                        f"origin {o} is in CORS_ORIGINS but silently ignored because USER_CORS_ORIGINS is set",
                                        src_name, "move it into USER_CORS_ORIGINS or delete it"))
        return ("FAIL" if findings else "PASS"), findings, len(findings), f"checked {list(sources)}"
    return timed("cors-origin-drift", "cors", body)


def check_dead_origins(ctx: Ctx) -> CheckResult:
    """Origins in allow-lists that no longer resolve -> subdomain-takeover risk. Needs --live."""
    def body():
        envx = ROOT / ".env.example"
        if not envx.exists():
            return "SKIP", [], 0, ""
        text = envx.read_text(errors="replace")
        origins = set()
        for k in ("CORS_ORIGINS", "USER_CORS_ORIGINS", "ADMIN_CORS_ORIGINS"):
            origins |= set(parse_env_list(text, k))
        origins = {o for o in origins if o.startswith("https://") and "localhost" not in o}
        findings = []
        for o in sorted(origins):
            code, _, body_txt = http(o, timeout=20)
            if code == 0 or code in (404, 410, 503) and ("onrender" in o or "netlify" in o):
                findings.append(Finding("dead-origins", "HIGH",
                                        f"allow-listed origin {o} is dead (HTTP {code or 'DNS/conn fail'}) -> takeover risk with credentialed CORS",
                                        ".env.example / Render env", "remove from all *_CORS_ORIGINS"))
        return ("FAIL" if findings else "PASS"), findings, len(findings), f"{len(origins)} origins probed"
    return timed("dead-origins", "live", body)


def check_frontend_env_hygiene(ctx: Ctx) -> CheckResult:
    """process.env in Vite browser code is always undefined -> silent isDev()/logging failures.
    Also flags deployed-host URLs hardcoded in src."""
    def body():
        findings = []
        pat = re.compile(r"\bprocess\.env\.")
        for p, i, line in grep_files(FRONTEND / "src", (".ts", ".tsx"), pat, exclude=(".test.", "vite-env", ".d.ts")):
            findings.append(Finding("fe-env-hygiene", "HIGH",
                                    "process.env used in browser code (undefined in Vite bundle -> silently false/undefined)",
                                    f"{rel(p)}:{i}", "use import.meta.env.DEV / import.meta.env.VITE_*"))
        pat2 = re.compile(r"https://[a-z0-9-]+\.(onrender\.com|web\.app|vercel\.app|netlify\.app)")
        for p, i, line in grep_files(FRONTEND / "src", (".ts", ".tsx"), pat2, exclude=(".test.",)):
            findings.append(Finding("fe-env-hygiene", "MEDIUM", "deployed host hardcoded in source (rotation requires rebuild)",
                                    f"{rel(p)}:{i}", "read from VITE_* env via utils/api.ts"))
        return ("FAIL" if any(f.severity in BLOCKING for f in findings) else ("WARN" if findings else "PASS")), findings, len(findings), ""
    return timed("fe-env-hygiene", "fe-contract", body)


def check_api_client_data_misuse(ctx: Ctx) -> CheckResult:
    """apiClient.get<T>() returns T, not {data:T}. `.data` on it is always undefined (silent empty lists)."""
    def body():
        findings = []
        pat = re.compile(r"await\s+apiClient\.(get|post|put|patch|delete)\b")
        for p in (FRONTEND / "src").rglob("*.ts*"):
            if "node_modules" in str(p) or ".test." in p.name:
                continue
            lines = p.read_text(errors="replace").splitlines()
            for i, line in enumerate(lines):
                if not pat.search(line):
                    continue
                m = re.search(r"(?:const|let)\s+(\w+)\s*=\s*await\s+apiClient", line)
                if not m:
                    continue
                var = m.group(1)
                window = "\n".join(lines[i + 1:i + 6])
                if re.search(rf"\b{re.escape(var)}\.data\b", window):
                    findings.append(Finding("apiclient-data-misuse", "HIGH",
                                            f"`{var}.data` read on apiClient result — apiClient already unwraps; this is always undefined",
                                            f"{rel(p)}:{i + 1}", f"use `{var}` directly (or unwrap once in handleResponse)"))
        return ("FAIL" if findings else "PASS"), findings, len(findings), ""
    return timed("apiclient-data-misuse", "fe-contract", body)


def check_middleware_header_conflicts(ctx: Ctx) -> CheckResult:
    """Same security header set with different values in two middlewares -> last one silently wins."""
    def body():
        pat = re.compile(r"""["'](X-Frame-Options|X-XSS-Protection|Content-Security-Policy|Referrer-Policy|Strict-Transport-Security)["']\s*\]?\s*=\s*["']([^"']+)["']""")
        seen: dict[str, dict[str, str]] = {}
        for p, i, line in grep_files(BACKEND, (".py",), pat, exclude=("/tests/",)):
            for h, v in pat.findall(line):
                seen.setdefault(h, {})[f"{rel(p)}:{i}"] = v
        findings = []
        for h, locs in seen.items():
            if len(set(locs.values())) > 1:
                findings.append(Finding("mw-header-conflict", "MEDIUM",
                                        f"{h} set to different values: " + "; ".join(f"{v} @ {l}" for l, v in locs.items()),
                                        "", "set each security header in exactly one middleware"))
            if h == "X-XSS-Protection" and any(v.startswith("1") for v in locs.values()):
                findings.append(Finding("mw-header-conflict", "MEDIUM",
                                        "X-XSS-Protection: 1 is deprecated and introduces XSS in legacy browsers",
                                        next(iter(locs)), "remove it or set to 0; use CSP"))
        return ("WARN" if findings else "PASS"), findings, len(findings), ""
    return timed("mw-header-conflict", "config", body)


def check_live_health(ctx: Ctx) -> CheckResult:
    def body():
        findings = []
        for node, base in ctx.backends.items():
            code, _, txt = http(base.rstrip("/") + HEALTH_PATHS.get(node, "/health"))
            if code != 200:
                findings.append(Finding("live-health", "CRITICAL", f"{node} health {code or 'unreachable'}: {txt[:120]}", base))
        return ("FAIL" if findings else "PASS"), findings, len(findings), f"{len(ctx.backends)} nodes"
    return timed("live-health", "live", body)


def check_live_preflight(ctx: Ctx) -> CheckResult:
    """Real browser-equivalent preflight: real Origin + the headers the bundle actually sends."""
    def body():
        # derive header list from frontend source so the probe never goes stale
        pat = re.compile(r"""['"`](X-[A-Za-z0-9-]+)['"`]\s*[:\]=]""")
        custom = sorted({h.lower() for _, _, line in grep_files(FRONTEND / "src", (".ts", ".tsx"), pat, exclude=(".test.",)) for h in pat.findall(line)})
        req_headers = ",".join(["content-type", "authorization", *custom])
        base = ctx.backends.get("primary")
        if not base:
            return "SKIP", [], 0, "[discovery] no 'primary' backend discovered -- preflight skipped"
        if not ctx.frontends:
            return "SKIP", [], 0, "[discovery] no frontend origins discovered -- preflight skipped"
        base = base.rstrip("/")
        findings = []
        for origin in ctx.frontends:
            for route in PREFLIGHT_ROUTES:
                code, hdrs, txt = http(base + route, "OPTIONS", {
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": req_headers,
                })
                aco = hdrs.get("access-control-allow-origin", "")
                if code != 200 or aco not in (origin, "*"):
                    findings.append(Finding("live-preflight", "CRITICAL",
                                            f"preflight {origin} -> {route}: HTTP {code} '{txt[:60]}' (allow-origin='{aco}')",
                                            base + route,
                                            "fix USER_CORS_ORIGINS on Render and/or allow_headers in app_builder.py, redeploy"))
        return ("FAIL" if findings else "PASS"), findings, len(findings), f"{len(ctx.frontends)}x{len(PREFLIGHT_ROUTES)} probes, headers={req_headers}"
    return timed("live-preflight", "live", body)


def check_live_frontend_bundles(ctx: Ctx) -> CheckResult:
    """Download each deployed bundle, extract backend hosts it was built with, verify each is alive."""
    def body():
        findings = []
        if not ctx.frontends:
            return "SKIP", [], 0, "[discovery] no frontend origins discovered -- bundle probe skipped"
        for fe in ctx.frontends:
            code, _, html = http(fe, timeout=30)
            if code != 200:
                findings.append(Finding("live-bundles", "CRITICAL", f"frontend {fe} HTTP {code}", fe))
                continue
            # need full html for asset paths
            try:
                with urllib.request.urlopen(fe, timeout=30) as r:
                    html = r.read().decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001
                findings.append(Finding("live-bundles", "HIGH", f"cannot read {fe}: {e}", fe))
                continue
            assets = re.findall(r'src="(/assets/[^"]+\.js)"', html)[:3]
            hosts = set()
            for a in assets:
                try:
                    with urllib.request.urlopen(fe + a, timeout=60) as r:
                        js = r.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    continue
                hosts |= set(re.findall(r"https://[a-z0-9-]+\.onrender\.com", js))
            if not hosts:
                findings.append(Finding("live-bundles", "HIGH", f"{fe}: no backend host found in bundle (missing VITE_USER_BACKEND at build?)", fe))
            for h in sorted(hosts):
                c, _, t = http(h + "/api/v1/health/live", timeout=40)
                if c == 404:
                    c, _, t = http(h + "/health", timeout=40)
                if c != 200:
                    findings.append(Finding("live-bundles", "CRITICAL",
                                            f"{fe} was built against {h} which returns HTTP {c or 'unreachable'}",
                                            fe, "fix VITE_USER_BACKEND / VITE_ADMIN_BACKEND in the hosting provider env and redeploy"))
        return ("FAIL" if findings else "PASS"), findings, len(findings), ""
    return timed("live-bundles", "live", body)


def check_ts(ctx: Ctx) -> CheckResult:
    def body():
        if not (FRONTEND / "node_modules" / ".bin" / "tsc").exists():
            return "SKIP", [], 0, "frontend node_modules missing (run pnpm install)"
        rc, out = run(["npx", "tsc", "-p", "tsconfig.app.json", "--noEmit", "--pretty", "false"], cwd=FRONTEND, timeout=900)
        errs = [l for l in out.splitlines() if "error TS" in l]
        non_test = [l for l in errs if ".test." not in l and ".stories." not in l]
        findings = [Finding("tsc", "HIGH", l.strip()[:220], "") for l in non_test[:40]]
        status = "FAIL" if non_test else ("WARN" if errs else "PASS")
        return status, findings, len(non_test), f"{len(errs)} total, {len(non_test)} in non-test files"
    return timed("tsc", "ts", body)


def check_eslint(ctx: Ctx) -> CheckResult:
    def body():
        if not (FRONTEND / "node_modules" / ".bin" / "eslint").exists():
            return "SKIP", [], 0, "eslint not installed"
        rc, out = run(["npx", "eslint", "src", "--ext", ".ts,.tsx", "-f", "json"], cwd=FRONTEND, timeout=900)
        try:
            data = json.loads(out[out.index("["):])
        except Exception:  # noqa: BLE001
            return ("FAIL" if rc else "PASS"), [], 0 if rc == 0 else 1, out[-300:]
        errs = sum(f["errorCount"] for f in data)
        warns = sum(f["warningCount"] for f in data)
        findings = []
        for f in data:
            for m in f["messages"]:
                if m["severity"] == 2 and len(findings) < 40:
                    findings.append(Finding("eslint", "MEDIUM", f"{m['ruleId']}: {m['message']}", f"{rel(Path(f['filePath']))}:{m['line']}"))
        return ("FAIL" if errs else ("WARN" if warns else "PASS")), findings, errs, f"{errs} errors, {warns} warnings"
    return timed("eslint", "eslint", body)


def check_ruff(ctx: Ctx) -> CheckResult:
    def body():
        cmd = ["ruff"] if have("ruff") else [sys.executable, "-m", "ruff"]
        rc, probe = run(cmd + ["--version"])
        if rc != 0:
            return "SKIP", [], 0, "ruff not installed (pip install ruff)"
        # F821 undefined name / F811 redefinition / B006 mutable default / E722 bare except / B904 raise-from
        rc, out = run(cmd + ["check", ".", "--select", "F821,F811,E722,B006,B904,F841", "--exclude", "tests,alembic_migrations,_archive,docs",
                             "--output-format", "json"], cwd=BACKEND, timeout=600)
        try:
            data = json.loads(out[out.index("["):])
        except Exception:  # noqa: BLE001
            return ("FAIL" if rc else "PASS"), [], 0, out[-300:]
        sevmap = {"F821": "CRITICAL", "F811": "HIGH", "E722": "MEDIUM", "B006": "MEDIUM", "B904": "LOW", "F841": "LOW"}
        findings = [Finding("ruff", sevmap.get(d["code"], "LOW"), f"{d['code']} {d['message']}",
                            f"{rel(Path(d['filename']))}:{d['location']['row']}") for d in data]
        findings.sort(key=lambda f: SEV_ORDER[f.severity])
        blocking = sum(1 for f in findings if f.severity in BLOCKING)
        return ("FAIL" if blocking else ("WARN" if findings else "PASS")), findings[:60], len(findings), f"{blocking} blocking of {len(findings)}"
    return timed("ruff", "ruff", body)


def check_py_compile(ctx: Ctx) -> CheckResult:
    def body():
        rc, out = run([sys.executable, "-m", "compileall", "-q", ".", "-x", r"tests|_archive|alembic|node_modules|\.venv"], cwd=BACKEND, timeout=600)
        errs = [l for l in out.splitlines() if "Error" in l or "error" in l]
        return ("FAIL" if rc else "PASS"), [Finding("py-compile", "CRITICAL", l[:220]) for l in errs[:20]], len(errs), ""
    return timed("py-compile", "pysyntax", body)


def check_pytest(ctx: Ctx) -> CheckResult:
    def body():
        if not have("pytest") and run([sys.executable, "-m", "pytest", "--version"])[0] != 0:
            return "SKIP", [], 0, "pytest not installed"
        rc, out = run([sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider", "tests"], cwd=BACKEND, timeout=1800)
        tail = "\n".join(out.strip().splitlines()[-15:])
        m = re.search(r"(\d+) failed", out)
        n = int(m.group(1)) if m else (0 if rc == 0 else 1)
        return ("FAIL" if rc else "PASS"), ([Finding("pytest", "HIGH", "test failures", "backend/tests", tail)] if rc else []), n, ""
    return timed("pytest", "pytest", body)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def build_registry() -> list[Check]:
    return [
        # -- NEW contract checks (would have caught 2026-03-09 outages) --
        Check("cors-header-contract", "cors", check_cors_header_contract),
        Check("cors-origin-drift", "cors", check_cors_origin_drift),
        Check("fe-env-hygiene", "fe-contract", check_frontend_env_hygiene),
        Check("apiclient-data-misuse", "fe-contract", check_api_client_data_misuse),
        Check("mw-header-conflict", "config", check_middleware_header_conflicts),
        # -- Language-level --
        Check("py-compile", "pysyntax", check_py_compile),
        Check("ruff", "ruff", check_ruff),
        Check("tsc", "ts", check_ts, quick=False),
        Check("eslint", "eslint", check_eslint, quick=False),
        # -- REUSED existing repo scripts --
        existing_script("silent-errors", "silent",
                        [sys.executable, "scripts/detect_silent_errors.py", "--json", "ci-reports/silent_errors.json"],
                        severity="MEDIUM", count_re=r"(\d+)\s+finding"),
        existing_script("config-contract", "config", [sys.executable, "scripts/ci/check_config_contract.py"]),
        existing_script("config-registry", "config", [sys.executable, "scripts/ci/validate_config_registry.py"]),
        existing_script("hardcoded-deploy-config", "config", [sys.executable, "scripts/ci/check_hardcoded_deployment_config.py"], severity="MEDIUM"),
        existing_script("frontend-secrets", "secrets", [sys.executable, "scripts/ci/check_frontend_secrets.py"], severity="CRITICAL"),
        existing_script("required-secrets", "secrets", [sys.executable, "scripts/ci/check_required_secrets.py"], severity="MEDIUM"),
        existing_script("service-topology", "topology", [sys.executable, "scripts/ci/check_service_topology.py"]),
        existing_script("router-imports", "routers", [sys.executable, "scripts/ci/validate_router_imports.py", "--strict"]),
        existing_script("api-contract", "api-contract", [sys.executable, "scripts/ci/verify_api_contract.py"], quick=False),
        existing_script("no-requests-lib", "config", ["bash", "scripts/check_no_requests_in_backend.sh"], severity="LOW"),
        existing_script("migration-safety", "config", [sys.executable, "scripts/ci/check_migration_safety.py"], quick=False),
        # -- Live probes (--live) --
        Check("live-health", "live", check_live_health, live=True),
        Check("live-preflight", "live", check_live_preflight, live=True),
        Check("live-bundles", "live", check_live_frontend_bundles, live=True),
        Check("dead-origins", "live", check_dead_origins, live=True),
        # -- Slow --
        Check("pytest", "pytest", check_pytest, quick=False, slow=True),
    ]


# ---------------------------------------------------------------------------
# Baseline (accepted legacy debt) — fail only on regression
# ---------------------------------------------------------------------------
def load_baseline() -> dict:
    if BASELINE_FILE.exists():
        try:
            return json.loads(BASELINE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def apply_baseline(results: list[CheckResult], baseline: dict) -> list[str]:
    """Downgrade FAIL -> WARN when count did not grow vs baseline. Returns regression notes."""
    notes = []
    for r in results:
        base = baseline.get(r.name)
        if base is None or r.status != "FAIL":
            continue
        # contract/live checks are never baselined: they are always blocking
        if r.group in ("cors", "live", "pysyntax", "secrets"):
            continue
        if r.count <= base:
            r.status = "WARN"
            r.note = (r.note + f" | baseline {base}, now {r.count} (no regression)").strip(" |")
        else:
            notes.append(f"{r.name}: {base} -> {r.count} (+{r.count - base})")
            r.note = (r.note + f" | REGRESSION vs baseline {base}").strip(" |")
    return notes


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_console(results: list[CheckResult], regressions: list[str]) -> str:
    icon = {"PASS": "OK  ", "WARN": "WARN", "FAIL": "FAIL", "SKIP": "SKIP", "ERROR": "ERR "}
    lines = ["", "=" * 96, " SupremeAI Pre-Merge Guard", "=" * 96]
    for r in results:
        lines.append(f" [{icon[r.status]}] {r.name:<26} {r.group:<12} {r.duration_s:6.1f}s  n={r.count:<4} {r.note[:60]}")
    all_f = sorted((f for r in results for f in r.findings), key=lambda f: SEV_ORDER[f.severity])
    if all_f:
        lines += ["", "-" * 96, " FINDINGS (ranked)", "-" * 96]
        for f in all_f[:80]:
            lines.append(f" {f.severity:<8} {f.check:<24} {f.message}")
            if f.location:
                lines.append(f"          at  {f.location}")
            if f.fix:
                lines.append(f"          fix {f.fix.splitlines()[0][:110]}")
        if len(all_f) > 80:
            lines.append(f" ... and {len(all_f) - 80} more (see --json)")
    if regressions:
        lines += ["", " REGRESSIONS vs baseline:"] + [f"   - {n}" for n in regressions]
    return "\n".join(lines)


def render_markdown(results: list[CheckResult], regressions: list[str], verdict: str) -> str:
    md = [f"## Pre-Merge Guard: **{verdict}**", "", "| Check | Group | Status | Count | Note |", "|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r.name} | {r.group} | {r.status} | {r.count} | {r.note[:80]} |")
    all_f = sorted((f for r in results for f in r.findings), key=lambda f: SEV_ORDER[f.severity])
    if all_f:
        md += ["", "### Findings", ""]
        for f in all_f[:60]:
            md.append(f"- **{f.severity}** `{f.check}` {f.message}" + (f" — `{f.location}`" if f.location else "") + (f"\n  - fix: {f.fix.splitlines()[0][:140]}" if f.fix else ""))
    if regressions:
        md += ["", "### Regressions vs baseline", ""] + [f"- {n}" for n in regressions]
    return "\n".join(md)


def notify(summary: str, verdict: str) -> None:
    text = f"Pre-Merge Guard: {verdict}\n{summary}"[:1900]
    dc = os.getenv("DISCORD_ALERT_WEBHOOK") or os.getenv("DISCORD_WEBHOOK_URL")
    if dc:
        try:
            req = urllib.request.Request(dc, data=json.dumps({"content": f"```\n{text}\n```"}).encode(), headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:  # noqa: BLE001
            print(f"[notify] discord failed: {e}", file=sys.stderr)
    tg, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("ADMIN_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if tg and chat:
        try:
            req = urllib.request.Request(f"https://api.telegram.org/bot{tg}/sendMessage",
                                         data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:  # noqa: BLE001
            print(f"[notify] telegram failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def changed_files_vs(base_ref: str) -> set[str]:
    rc, out = run(["git", "diff", "--name-only", f"{base_ref}...HEAD"])
    if rc != 0:
        rc, out = run(["git", "diff", "--name-only", "HEAD~1"])
    return {l.strip() for l in out.splitlines() if l.strip()}


def select_checks(reg: list[Check], args: argparse.Namespace, changed: set[str]) -> list[Check]:
    only = set(args.only.split(",")) if args.only else None
    skip = set(args.skip.split(",")) if args.skip else set()
    out = []
    for c in reg:
        if only and c.group not in only and c.name not in only:
            continue
        if c.group in skip or c.name in skip:
            continue
        if c.live and not args.live:
            continue
        if c.slow and not args.full:
            continue
        if args.quick and not c.quick:
            continue
        if args.changed and changed:
            fe = any(f.startswith("frontend/") for f in changed)
            be = any(f.startswith("backend/") for f in changed)
            cfg = any(f in (".env.example",) or f.startswith(("scripts/", ".github/", "infrastructure/")) for f in changed)
            if c.group in ("ts", "eslint", "fe-contract") and not fe:
                continue
            if c.group in ("ruff", "pysyntax", "silent", "routers", "pytest") and not be:
                continue
            if c.group == "cors" and not (fe or be or cfg):
                continue
        out.append(c)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="fast subset")
    ap.add_argument("--full", action="store_true", help="include slow checks (pytest)")
    ap.add_argument("--live", action="store_true", help="probe live Render/Firebase/Vercel")
    ap.add_argument("--changed", action="store_true", help="scope to files changed vs --base")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--only", default="", help="comma list of groups/names")
    ap.add_argument("--skip", default="", help="comma list of groups/names")
    ap.add_argument("--baseline", action="store_true", help="write current counts as accepted baseline")
    ap.add_argument("--no-baseline", action="store_true", help="ignore baseline, fail on any finding")
    ap.add_argument("--notify", action="store_true", help="send summary to Discord/Telegram")
    ap.add_argument("--json", default="", help="write JSON report")
    ap.add_argument("--md", default="", help="write Markdown report")
    ap.add_argument("--fail-on", default="HIGH", choices=list(SEV_ORDER), help="min severity that blocks")
    args = ap.parse_args(argv)

    # SCRIPT-INTELLIGENCE v9: resolve live targets from env + repo discovery
    # (fail-loud exit 2 when nothing is discoverable -- never probe guessed
    # domains).
    try:
        backends, frontends, discovery_notes = resolve_live_targets()
    except DiscoveryError as exc:
        print(f"[discovery] ERROR: {exc}", file=sys.stderr)
        print("guard itself failed: no service topology discoverable", file=sys.stderr)
        return 2
    for note in discovery_notes:
        print(note, flush=True)

    REPORT_DIR.mkdir(exist_ok=True)
    changed = changed_files_vs(args.base) if args.changed else set()
    baseline = {} if (args.no_baseline or args.baseline) else load_baseline()
    ctx = Ctx(args, changed, baseline, backends=backends, frontends=frontends)
    checks = select_checks(build_registry(), args, changed)
    if not checks:
        print("no checks selected", file=sys.stderr)
        return 2

    print(f"running {len(checks)} checks" + (f" (changed: {len(changed)} files)" if changed else ""), flush=True)
    results: list[CheckResult] = []
    for c in checks:
        print(f"  -> {c.name} ...", end="", flush=True)
        r = c.fn(ctx)
        results.append(r)
        print(f" {r.status} ({r.duration_s:.1f}s)", flush=True)

    regressions = apply_baseline(results, baseline)
    try:
        policy = load_policy()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[policy] ERROR: {exc}", file=sys.stderr)
        return 2
    classifications = [classify_result(r.name, r.group, r.status, r.count, policy) for r in results]

    if args.baseline:
        BASELINE_FILE.write_text(json.dumps({r.name: r.count for r in results if r.status in ("FAIL", "WARN", "PASS")}, indent=2, sort_keys=True))
        print(f"baseline written -> {rel(BASELINE_FILE)}")

    threshold = SEV_ORDER[args.fail_on]
    blocking = [f for r in results for f in r.findings if r.status in ("FAIL", "ERROR") and SEV_ORDER[f.severity] <= threshold]
    hard_fail = any(r.status in ("FAIL", "ERROR") for r in results)
    verdict = "BLOCKED" if (blocking or hard_fail) else ("PASS WITH WARNINGS" if any(r.status == "WARN" for r in results) else "PASS")

    console = render_console(results, regressions)
    print(console)
    print(f"\nVERDICT: {verdict}  ({len(blocking)} blocking findings, {len(regressions)} regressions)\n")

    md = render_markdown(results, regressions, verdict)
    if args.md:
        Path(args.md).write_text(md)
    if args.json:
        Path(args.json).write_text(json.dumps({"verdict": verdict, "regressions": regressions,
                                                "results": [asdict(r) for r in results]}, indent=2))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(md + "\n")
    if args.notify:
        top = "\n".join(f"{f.severity} {f.check}: {f.message[:120]}" for f in sorted(
            (f for r in results for f in r.findings), key=lambda f: SEV_ORDER[f.severity])[:12])
        notify(top or "no findings", verdict)

    record_decision(verdict, classifications)
    if args.json:
        report = json.loads(Path(args.json).read_text())
        report["policy"] = {"mode": policy["mode"], "version": policy["version"]}
        report["classifications"] = classifications
        Path(args.json).write_text(json.dumps(report, indent=2))

    return 0 if verdict != "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
