#!/usr/bin/env python3
"""platform deep-audit engine — vault-driven dynamic discovery + intelligent classification.

বাংলা মন্তব্য: এটি `platform_agent_check.py`-এর উন্নত সংস্করণ — স্ট্যাটিক প্রোব-তালিকার বদলে
vault (Infisical) থেকে কী-প্যাটার্ন দেখে প্ল্যাটফর্ম নিজে আবিষ্কার করে, শুধু ping নয়
settings/quota/staleness-সহ গভীর পরীক্ষা চালায়, প্রতিটি ত্রুটিকে বুদ্ধিমানভাবে শ্রেণিবদ্ধ
করে (AUTH_INVALID / REGION_BLOCKED / BOT_PROTECTION / QUOTA_EXCEEDED / …) এবং
বাংলা রিপোর্ট + fingerprint-deduped GitHub issue স্বয়ংক্রিয়ভাবে তৈরি করে।

Design notes:
- stdlib-only (no pip install) — CI-friendly, fast cold start.
- Concurrency: ThreadPoolExecutor (probe গুলো parallel চলে)।
- প্রতিটি finding-এ stable fingerprint: `deep-audit-fp:<sha1[:12]>` — issue dedup-এ ব্যবহৃত।
- Issue dedup দুই স্তরে: (১) fingerprint exact, (২) open issue title-এ platform+check ম্যাচ।
- Exit codes: 0 = clean বা warn-only, 1 = অন্তত একটি FAIL (severity P0/P1), 2 = fatal setup error.

Usage:
  python .github/scripts/platform_deep_audit.py [--dry-run] [--json PATH]
         [--max-workers 8] [--timeout 20] [--verbose]

Env:
  INFISICAL_CLIENT_ID / INFISICAL_CLIENT_SECRET / INFISICAL_PROJECT_ID (vault creds)
  GITHUB_TOKEN (GitHub + mirror probes; issue-তৈরির জন্য issues:write প্রয়োজন)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# ── ধ্রুবক ────────────────────────────────────────────────────────────────────
INFISICAL_HOST = os.environ.get("INFISICAL_HOST", "https://app.infisical.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "SaifulHaqueNiloy/supremeai")
TRACKER_PREFIX = "[deep-audit]"
FP_MARK = "deep-audit-fp:"  # issue-তে fingerprint-এর hidden marker
HTTP_TIMEOUT_DEFAULT = 20
MIRROR_TARGET_REPO = "paykaribazaronline/supremeai"
MIRROR_ORIGIN_REPO = "SaifulHaqueNiloy/supremeai"

# বাংলা (#25): Google API key-এ HTTP-referrer restriction থাকলে probe-এর referer
# ফাঁকা (`<empty>`) হলে Google 403 "Requests from referer <empty> are blocked."
# দেয় — সেটি আমাদের Cloudflare/BOT_PROTECTION শ্রেণিতে ভুল পড়ত। সৎ ও
# বর্ণনামূলক referer (এই প্রোব যে রিপো থেকে চলে) পাঠানো হয়; key-নির্দিষ্ট
# referrer-তালিকাভুক্ত হলে তবুও 403 হবে এবং সেটি অ্যাকশনেবল (owner-কে
# allowlist/নতুন-কী দরকার) — নীরব-পাস নয়, শ্রেণি বদলায় না।
GOOGLE_PROBE_REFERER = "https://github.com/SaifulHaqueNiloy/supremeai"

# বাংলা মন্তব্য: পরিচিত AI হোস্ট — যেকোনো *_API_KEY এই হোস্ট-ম্যাপে পড়লে generic models-প্রোব পাবে
KNOWN_AI_HOSTS = {
    "GROQ_API_KEY": "https://api.groq.com/openai/v1/models",
    "OPENAI_API_KEY": "https://api.openai.com/v1/models",
    "CEREBRAS_API_KEY": "https://api.cerebras.ai/v1/models",
    "MISTRAL_API_KEY": "https://api.mistral.ai/v1/models",
    "XAI_API_KEY": "https://api.x.ai/v1/models",
    "DEEPSEEK_API_KEY": "https://api.deepseek.com/v1/models",
    "OPENROUTER_API_KEY": "https://openrouter.ai/api/v1/models",
}

# বাংলা মন্তব্য: কোন vault-key প্যাটার্ন কোন প্রোব গ্রাস করবে (discovery-তে consumed হিসেবে চিহ্নিত)
CONSUMED_KEY_HINTS = [
    r"^UPSTASH_", r"^RENDER_", r"^SUPABASE_", r"^VERCEL_", r"^CLOUDFLARE_",
    r"^FIRECRAWL_API_KEY$", r"^GITHUB_TOKEN$", r"^KAGGLE_API_TOKENS?$",
    r"^GEMINI_API_KEY$", r"^MCP_URL$", r"^MCP_API_KEY$", r"^MCP_ADMIN_KEY$",
    r"^INFISICAL_", r"^RENDER_MCP_URL$",
    # বাংলা মন্তব্য (#2713): নিচের প্ল্যাটফর্মগুলো এখন probe_known_keys গ্রাস করে —
    # আর UNMONITORED-তে নয়েজ হিসেবে দেখাবে না।
    r"^STRIPE_API_KEY$", r"^RESEND_API_KEY$", r"^NEON_API_KEY$",
    r"^LAUNCHDARKLY_API_KEY$", r"^TELEGRAM_BOT_TOKEN$", r"^NEON_ORG_ID$",
    r"^GOOGLE_API_KEY$",  # বাংলা (#3693): probe_ai_hosts-এ google-প্রোব যোগ হয়েছে
] + [f"^{k}$" for k in KNOWN_AI_HOSTS]


# ── Finding মডেল + ক্লাসিফায়ার ────────────────────────────────────────────────
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

# বাংলা মন্তব্য: প্রতিটি ক্যাটাগরির সিরিয়াসনেস ও বাংলা প্রতিকার-নির্দেশনা
CATEGORY_META = {
    "PASS":             ("P3", "—"),
    "AUTH_INVALID":     ("P1", "কী নবীকরণ/রোটেট করুন এবং vault-এ হালনাগাদ করুন; তারপর পুনঃপ্রোব করুন।"),
    "REGION_BLOCKED":   ("P3", "এটি পরিবেশ-নির্ভর false alarm হতে পারে (US runner-এ পাস করে কি?) — কী/প্ল্যাটফর্ম অঞ্চল-নীতি যাচাই করুন।"),
    "BOT_PROTECTION":   ("P2", "প্ল্যাটফর্মের Cloudflare/bot-protection আমাদের probe-কে আটকাচ্ছে — support-এ allowlist চান বা probe-ডেগ্রেডেশন পলিসি নিন।"),
    "QUOTA_EXCEEDED":   ("P1", "কোটা/লিমিট শেষ — প্ল্যান আপগ্রেড, লোড-শিফট বা TTL-ক্যাশিং প্রয়োজন; লিমিট-উইন্ডো (দৈনিক UTC?) নোট করুন।"),
    "SERVICE_UNHEALTHY":("P1", "সাব-সার্ভিস ডাউন — dashboard থেকে restart করুন; না ফিরলে প্ল্যাটফর্ম support ticket।"),
    "SERVER_ERROR":     ("P1", "প্ল্যাটফর্ম-সাইড 5xx — status page দেখুন; স্থায়ী হলে support ticket।"),
    "NETWORK":          ("P2", "DNS/টাইমআউট — রানারের ইগ্রেস ও হোস্টের availability যাচাই করুন।"),
    "CONFIG_MISSING":   ("P2", "প্রয়োজনীয় key/ID vault/Actions secrets-এ নেই — যোগ করুন অথবা প্রোব বাদ দিন।"),
    "DATA_STALE":       ("P2", "ডেটা/ডিপ্লয় স্টেল — সিঙ্ক/ডিপ্লয় পাইপলাইন পুনরায় চালু করুন।"),
    "SETTINGS_RISK":    ("P2", "কনফিগ-ঝুঁকি (free plan/health-path অনুপস্থিত/flexible SSL) — সেটিংস পরিবর্তনের প্রস্তাব দেখুন।"),
    "SERVICE_DELETED":  ("P2", "vault-রেফারেন্সড সার্ভিস প্ল্যাটফর্মে নেই (#2711) — owner নিশ্চিত করুন: ডিকমিশন-ইনটেন্ট হলে একই PR-এ vault থেকে ID সরান; দুর্ঘটনা হলে রিস্টোর করুন।"),
    "UNMONITORED":      ("P3", "vault-এ সচল key আছে কিন্তু কোনো প্রোব নেই — কভারেজ যোগ করুন বা key রিটায়ার করুন।"),
    "UNCLASSIFIED":     ("P2", "অজানা ত্রুটি — raw detail দেখে ম্যানুয়াল ট্রায়াজ করুন।"),
}


def fingerprint(platform: str, check: str, category: str) -> str:
    """বাংলা মন্তব্য: স্থিতিশীল fingerprint — platform+check+category থেকে; রান-জুড়ে dedup-কী।"""
    raw = f"{platform}|{check}|{category}".lower()
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def classify(platform: str, check: str, status: int, body: str) -> tuple[str, str]:
    """বাংলা মন্তব্য: HTTP স্টেটাস + বডি প্যাটার্ন দেখে বুদ্ধিমান ক্যাটাগরি নির্ণয়।
    রিটার্ন: (category, extra_note)"""
    low = body.lower()
    if status == 0:
        return "NETWORK", ""
    if "max requests limit" in low or "quota" in low or "rate limit exceeded" in low \
            or status == 429 or "credit" in low and "exhaust" in low:
        # বাংলা মন্তব্য: কোটা-জাতীয় ত্রুটি আলাদা চেনা গুরুত্বপূর্ণ (#2452 শিক্ষা)
        reset = " (দৈনিক UTC-উইন্ডো হলে মধ্যরাতে রিসেট)" if "max requests limit" in low else ""
        return "QUOTA_EXCEEDED", reset
    if status in (401,):
        return "AUTH_INVALID", ""
    if status in (400, 403) and ("unsupported_country" in low or "location is not supported" in low):
        # বাংলা মন্তব্য: রিজিওন-ব্লক আসল আউটেজ নয় (#2423 শিক্ষা) — WARN-ডিগ্রেড; Gemini 400-ও দেয়
        return "REGION_BLOCKED", ""
    if status == 403 and ("error code: 1010" in low or "cloudflare" in low or "<!doctype html" in low):
        return "BOT_PROTECTION", ""
    if "referer" in low and "blocked" in low:
        # বাংলা (#25): Google-র HTTP-referrer restriction — "Requests from
        # referer <empty> are blocked." — এটি WAF/bot-block নয়, key-config
        # (allowed-referrer তালিকা)। snapshot-remediation অনুযায়ী owner-অ্যাকশন:
        # Google Cloud console-এ key-এর referrer-allowlist আপডেট।
        return "BOT_PROTECTION", " (Google key-এ HTTP-referrer restriction — console-এ probe-origin allowlist করুন বা unrestricted key; provider outage নয়)"
    if status in (403, 407):
        # বাংলা মন্তব্য (#2714): plain-JSON 403-ফ্যামিলি (groq `{"error":{"message":"Forbidden"}}`-স্টাইল)
        # সাধারণত provider-পাশের WAF/bot-ব্লক (#2423/#2483 প্রমাণিত জ্ঞান) — সংজ্ঞাগত
        # invalid-key বডি-ফিঙ্গারপ্রিন্ট না থাকলে BOT_PROTECTION (P2); AUTH_INVALID (P1)
        # শুধু 401 অথবা স্পষ্ট key-ত্রুটি বডিতে — নলেজ-ড্রিফট বন্ধ।
        if any(sig in low for sig in ("invalid api key", "incorrect api key", "api key expired",
                                       "invalid_access_key", "authentication failed")):
            return "AUTH_INVALID", ""
        return "BOT_PROTECTION", ""
    if status >= 500:
        return "SERVER_ERROR", ""
    if status == 404 and ("not found: service" in low or "service not found" in low):
        # বাংলা মন্তব্য (#2711): Render `not found: service: srv-xxx` — সার্ভিস ডিলিটেড/স্টেল
        # vault-ID; এটা UNCLASSIFIED নয় — সুনির্দিষ্ট প্রতিকার-পাথ আছে (vault hygiene)।
        return "SERVICE_DELETED", ""
    if status in (404,) and "page not found" in low:
        return "UNCLASSIFIED", "endpoint-path পরিবর্তিত হতে পারে — API docs যাচাই করুন"
    return "UNCLASSIFIED", ""


def mk(platform: str, check: str, ok: bool | None, detail: str,
       category: str | None = None, severity: str | None = None,
       remediation: str | None = None, note: str = "") -> dict:
    """বাংলা মন্তব্য: finding-নির্মাতা — ok=True/False/None(PASS/FAIL/WARN); category দিলে
    সিরিয়াসনেস+প্রতিকার স্বয়ংক্রিয়। ok=False ও category=None হলে raw থেকে classify চেষ্টা হয়।"""
    if category is None:
        category = "PASS" if ok is True else "UNCLASSIFIED"
    if severity is None:
        base_sev, base_rem = CATEGORY_META[category]
        severity = base_sev
        # বাংলা মন্তব্য: REGION_BLOCKED/UNMONITORED ফেইল নয় — WARN-এ ডিগ্রেড (#2423 পলিসি)
        if category in ("REGION_BLOCKED", "UNMONITORED") and ok is False:
            ok = None
        remediation = base_rem
    remediation = remediation or CATEGORY_META[category][1]
    return {
        "platform": platform, "check": check, "ok": ok, "detail": detail[:400],
        "category": category, "severity": severity, "remediation": remediation,
        "note": note, "fp": fingerprint(platform, check, category),
    }


# ── HTTP + retry ─────────────────────────────────────────────────────────────
def http(method: str, url: str, headers: dict | None = None, body=None, timeout: int = HTTP_TIMEOUT_DEFAULT):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    hdrs = {"User-Agent": "supremeai-deep-audit/2.0", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:600]
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def _jbody(st: int, raw: str):
    """বাংলা মন্তব্য (#2869): http()-এর raw str-বডিকে নিরাপদে JSON-এ রূপান্তর —
    নন-JSON/খালি বডিতে None; কলার অবশ্যই isinstance(data, dict) গার্ড ব্যবহার করবে।"""
    try:
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001 — নন-JSON বডি এখানেই গ্রাস করা ডিজাইন-অংশ
        return None


def jget(url: str, headers: dict, timeout: int = HTTP_TIMEOUT_DEFAULT):
    st, body = http("GET", url, headers=headers, timeout=timeout)
    try:
        return st, json.loads(body)
    except Exception:
        return st, {"_raw": body[:300]}


def retry(fn, tries=3, base=1.5):
    """বাংলা মন্তব্য: transient নেটওয়ার্ক ফ্ল্যাপে exponential retry — শুধু status 0 (network) ও 5xx-এ।"""
    last = None
    for i in range(tries):
        st, body = fn()
        if st in (0,) or st >= 500:
            last = (st, body)
            time.sleep(base * (2 ** i))
            continue
        return st, body
    return last


# ── Vault লেয়ার ──────────────────────────────────────────────────────────────
def vault_secrets() -> dict:
    """বাংলা মন্তব্য: Infisical universal-auth → v3 raw secrets; env-fallback ছাড়া সরাসরি।"""
    cid = os.environ.get("INFISICAL_CLIENT_ID", "")
    csec = os.environ.get("INFISICAL_CLIENT_SECRET", "")
    pid = os.environ.get("INFISICAL_PROJECT_ID", "")
    if not (cid and csec and pid):
        raise SystemExit("FATAL: INFISICAL_CLIENT_ID/SECRET/PROJECT_ID সেট করা নেই")
    st, body = http("POST", f"{INFISICAL_HOST}/api/v1/auth/universal-auth/login",
                    {"Content-Type": "application/json"},
                    {"clientId": cid, "clientSecret": csec})
    if st != 200:
        raise SystemExit(f"FATAL: Infisical login HTTP {st}: {body[:200]}")
    tok = json.loads(body)["accessToken"]
    q = urllib.parse.urlencode({"workspaceId": pid, "environment": "prod", "recursive": "true"})
    st, raw = retry(lambda: jget(f"{INFISICAL_HOST}/api/v3/secrets/raw?{q}", {"Authorization": f"Bearer {tok}"}))
    if st != 200:
        raise SystemExit(f"FATAL: secrets pull HTTP {st}")
    kv = {}
    for s in raw.get("secrets", []):
        k = (s.get("secretKey") or s.get("key") or "").upper()
        v = s.get("secretValue")
        if v is None:
            v = s.get("value", "")
        kv[k] = v or ""
    return kv


# ── প্রোবগুলো (প্রতিটি রিটার্ন findings list) ─────────────────────────────────
def age_hours(iso_ts: str) -> float | None:
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return None


def probe_upstash(kv: dict) -> list[dict]:
    out = []
    suffixes = ["", "SECONDARY_", "TERTIARY_", "QUATERNARY_", "QUINARY_", "SENARY_", "SEPTENARY_"]
    for suf in suffixes:
        url, tok = kv.get(f"UPSTASH_REDIS_{suf}REST_URL", ""), kv.get(f"UPSTASH_REDIS_{suf}REST_TOKEN", "")
        label = (suf.rstrip("_") or "primary").lower()
        if not url or not tok:
            continue  # বাংলা মন্তব্য: অ্যাকাউন্ট অনুপস্থিত — ফাঁকা প্রোব নয়
        st, body = http("POST", f"{url}/ping", {"Authorization": f"Bearer {tok}"})
        if st == 200 and "pong" in body.lower():
            out.append(mk("upstash", f"ping[{label}]", True, "HTTP 200 PONG"))
        else:
            cat, note = classify("upstash", f"ping[{label}]", st, body)
            sev = "P1" if label == "primary" else "P2"  # বাংলা মন্তব্য: primary কোটা-ডাউন সবচেয়ে জরুরি
            out.append(mk("upstash", f"ping[{label}]", False, f"HTTP {st}: {body[:160]}",
                          category=cat, severity=sev, note=note))
        # গভীর পরীক্ষা: dbsize + কোটা-স্পেশাল (#2452)
        st2, b2 = http("POST", f"{url}/dbsize", {"Authorization": f"Bearer {tok}"})
        if st2 == 200:
            out.append(mk("upstash", f"dbsize[{label}]", True, f"keys={b2.strip()[:20]}"))
        else:
            cat2, note2 = classify("upstash", f"dbsize[{label}]", st2, b2)
            out.append(mk("upstash", f"dbsize[{label}]", False, f"HTTP {st2}: {b2[:160]}", category=cat2, note=note2))
    return out


def probe_render(kv: dict) -> list[dict]:
    out = []
    services = [("tower", "RENDER_MCP_SVC_ID", "RENDER_API_KEY_4"),
                ("primary", "RENDER_PRIMARY_SVC_ID", "RENDER_API_KEY_1"),
                ("worker", "RENDER_WORKER_SVC_ID", "RENDER_API_KEY_2"),
                ("scraper", "RENDER_SCRAPER_SVC_ID", "RENDER_API_KEY_3")]
    for name, se, ke in services:
        sid, akey = kv.get(se, ""), kv.get(ke, "")
        if not sid or not akey:
            out.append(mk("render", f"settings[{name}]", None,
                          f"{se}/{ke} নেই", category="CONFIG_MISSING"))
            continue
        H = {"Authorization": f"Bearer {akey}"}
        st, svc = retry(lambda: jget(f"https://api.render.com/v1/services/{sid}", H))
        if st != 200:
            cat, note = classify("render", f"settings[{name}]", st, json.dumps(svc))
            out.append(mk("render", f"settings[{name}]", False, f"HTTP {st}", category=cat, note=note))
            continue
        sc = svc if "id" in svc else svc.get("service", svc)
        plan = (sc.get("serviceDetails") or {}).get("plan") or "unknown"
        hcp = sc.get("healthCheckPath") or ""
        # বাংলা মন্তব্য: সেটিংস-ঝুঁকি যাচাই (#2454 শিক্ষা) — free plan + health-path অনুপস্থিত
        if plan == "free":
            out.append(mk("render", f"settings[{name}].plan", None,
                          f"plan=free — ১৫m idle spin-down + 512MB RAM ঝুঁকি",
                          category="SETTINGS_RISK"))
        if not hcp:
            out.append(mk("render", f"settings[{name}].healthCheckPath", None,
                          "healthCheckPath সেট নেই — ভাঙা ডিপ্লয়ও 'live' হতে পারে",
                          category="SETTINGS_RISK"))
        st, deps = retry(lambda: jget(f"https://api.render.com/v1/services/{sid}/deploys?limit=5", H))
        if st == 200:
            rows = [d.get("deploy", d) for d in (deps if isinstance(deps, list) else [])]
            bad = [d for d in rows if d.get("status") in ("build_failed", "update_failed", "canceled")]
            if bad:
                out.append(mk("render", f"deploys[{name}]", False,
                              f"{len(bad)} failed/canceled (latest: {bad[0].get('status')})",
                              category="SERVER_ERROR"))
            else:
                latest = rows[0].get("status", "?") if rows else "?"
                out.append(mk("render", f"deploys[{name}]", True, f"latest={latest}, শেষ ৫-এ ব্যর্থতা নেই"))
        else:
            cat, note = classify("render", f"deploys[{name}]", st, json.dumps(deps))
            out.append(mk("render", f"deploys[{name}]", False, f"HTTP {st}", category=cat, note=note))
    return out


def probe_supabase(kv: dict) -> list[dict]:
    out = []
    url, key = kv.get("SUPABASE_URL", "").rstrip("/"), kv.get("SUPABASE_KEY", "")
    if url and key:
        st, body = http("GET", f"{url}/auth/v1/health", {"apikey": key})
        if st == 200:
            out.append(mk("supabase", "auth[anon]", True, "HTTP 200"))
        else:
            cat, note = classify("supabase", "auth[anon]", st, body)
            out.append(mk("supabase", "auth[anon]", False, f"HTTP {st}: {body[:120]}", category=cat, note=note))
    # বাংলা মন্তব্য: গভীর পরীক্ষা — management token থাকলে per-service health (#2453 শিক্ষা)
    sat = kv.get("SUPABASE_ACCESS_TOKEN", "")
    if not sat:
        return out
    st, projs = retry(lambda: jget("https://api.supabase.com/v1/projects", {"Authorization": f"Bearer {sat}"}))
    if st != 200 or not isinstance(projs, list):
        cat, note = classify("supabase", "mgmt.projects", st, json.dumps(projs))
        out.append(mk("supabase", "mgmt.projects", False, f"HTTP {st}", category=cat, note=note))
        return out
    for p in projs:
        ref, nm = p.get("id", ""), p.get("name", "?")
        if p.get("status") not in ("ACTIVE_HEALTHY",):
            out.append(mk("supabase", f"project[{nm}]", False, f"status={p.get('status')}",
                          category="SERVICE_UNHEALTHY"))
        else:
            out.append(mk("supabase", f"project[{nm}]", True, f"status={p.get('status')}"))
        st, hg = jget(f"https://api.supabase.com/v1/projects/{ref}/health?services=auth,rest,db,storage,realtime",
                      {"Authorization": f"Bearer {sat}"})
        if st == 200 and isinstance(hg, list):
            for s in hg:
                svc, healthy = s.get("name", "?"), s.get("healthy")
                if healthy is False:
                    out.append(mk("supabase", f"service[{svc}]", False, f"status={s.get('status')}",
                                  category="SERVICE_UNHEALTHY"))
                elif svc:
                    out.append(mk("supabase", f"service[{svc}]", True, f"{s.get('status')}"))
    return out


def probe_vercel(kv: dict) -> list[dict]:
    out = []
    vt, prj, org = kv.get("VERCEL_TOKEN", ""), kv.get("VERCEL_PROJECT_ID", ""), kv.get("VERCEL_ORG_ID", "")
    if not vt:
        return out
    H = {"Authorization": f"Bearer {vt}"}
    q = f"projectId={prj}&limit=8" + (f"&teamId={org}" if org else "")
    st, deps = retry(lambda: jget(f"https://api.vercel.com/v6/deployments?{q}", H))
    if st != 200:
        cat, note = classify("vercel", "deployments", st, json.dumps(deps))
        out.append(mk("vercel", "deployments", False, f"HTTP {st}", category=cat, note=note))
        return out
    ds = deps.get("deployments", [])
    # বাংলা মন্তব্য: staleness পরীক্ষা (#2455 শিক্ষা) — শেষ production deploy বয়স
    prod = [d for d in ds if d.get("target") == "production"]
    if prod:
        age = age_hours(datetime.fromtimestamp(prod[0].get("created", 0) / 1000, tz=timezone.utc).isoformat())
        if age is not None:
            if age > 168:  # ৭ দিন
                out.append(mk("vercel", "prod-deploy-freshness", False,
                              f"শেষ production deploy {age/24:.1f} দিন আগে — main থেকে পিছিয়ে",
                              category="DATA_STALE"))
            else:
                out.append(mk("vercel", "prod-deploy-freshness", True, f"{age:.1f}h আগে"))
    err = [d for d in ds if d.get("readyState") in ("ERROR", "CANCELED")]
    # বাংলা মন্তব্য (#2714): স্বাস্থ্য-নির্ধারণ = সর্বশেষ production ডিপ্লয়ের readyState —
    # ঐতিহাসিক ERROR-গণনা নয়। প্রমাণ: ERROR→তৎক্ষণাৎ retry→READY প্যাটার্নে
    # সুস্থ প্রোডাকশনেও পুরনো ERROR উইন্ডোতে থাকতে পারে (P1-নয়েজ, #2714 কেস-১)।
    latest_prod = next((d for d in ds if d.get("target") == "production"), None)
    if latest_prod is not None:
        rs = latest_prod.get("readyState") or latest_prod.get("state") or "UNKNOWN"
        if rs in ("ERROR", "CANCELED"):
            out.append(mk("vercel", "deploy-states", False,
                          f"সর্বশেষ production deploy {rs} — প্রোডাকশন ঝুঁকিতে", category="SERVER_ERROR"))
        else:
            out.append(mk("vercel", "deploy-states", True, f"সর্বশেষ production deploy {rs}"))
        if err:
            # বাংলা মন্তব্য: ঐতিহাসিক ERROR = build-ফ্লেক ট্রেন্ড মেট্রিক (WARN) — P1 নয় (#2714)।
            out.append(mk("vercel", "deploy-states-flakiness", None,
                          f"শেষ {len(ds)} ডিপ্লয়ে {len(err)}-টি ERROR/CANCELED — retry-ফ্লেক ট্রেন্ড"))
    elif ds:
        out.append(mk("vercel", "deploy-states", True, f"শেষ {len(ds)}-টি READY"))
    return out


def probe_cloudflare(kv: dict) -> list[dict]:
    out = []
    tok = kv.get("CLOUDFLARE_API_TOKEN", "")
    if tok:
        st, body = http("GET", "https://api.cloudflare.com/client/v4/user/tokens/verify",
                        {"Authorization": f"Bearer {tok}"})
        ok = st == 200 and '"success":true' in body.replace(" ", "")
        out.append(mk("cloudflare", "api-token", ok, f"HTTP {st}", category="AUTH_INVALID" if not ok else None))
    for prefix in ["", "SECONDARY_", "TERTIARY_", "QUATERNARY_", "QUINARY_"]:
        email, gk = kv.get(f"CLOUDFLARE_{prefix}EMAIL", ""), kv.get(f"CLOUDFLARE_{prefix}GLOBAL_API_KEY", "")
        label = (prefix.rstrip("_") or "primary").lower()
        if not email or not gk:
            continue
        H = {"X-Auth-Email": email, "X-Auth-Key": gk}
        st, zones = retry(lambda: jget("https://api.cloudflare.com/client/v4/zones?per_page=50", H))
        if st != 200 or not (zones.get("success") if isinstance(zones, dict) else False):
            out.append(mk("cloudflare", f"zones[{label}]", False, f"HTTP {st}", category="AUTH_INVALID"))
            continue
        zl = zones.get("result", [])
        out.append(mk("cloudflare", f"zones[{label}]", True, f"{len(zl)} জোন"))
        # বাংলা মন্তব্য: সেটিংস-ঝুঁকি স্যাম্পল — ssl=flexible ও dev-mode (প্রথম ৩ জোন)
        for z in zl[:3]:
            st, cfg = jget(f"https://api.cloudflare.com/client/v4/zones/{z.get('id')}/settings", H)
            if st != 200:
                continue
            vals = {s.get("id"): s.get("value") for s in cfg.get("result", [])}
            if vals.get("ssl") == "flexible":
                out.append(mk("cloudflare", f"zone[{z.get('name')}].ssl", None,
                              "SSL=flexible — mixed-content ঝুঁকি, Full(strict) প্রস্তাবিত",
                              category="SETTINGS_RISK"))
            if vals.get("development_mode") == "on":
                out.append(mk("cloudflare", f"zone[{z.get('name')}].dev_mode", None,
                              "development_mode ON — cache অফ চলছে", category="SETTINGS_RISK"))
    return out


def probe_kaggle(kv: dict) -> list[dict]:
    """বাংলা মন্তব্য: নতুন KGAT_ ফরম্যাট → Bearer; পুরনো user:key/user_key → Basic (#2422 ফিক্স এমবেডেড)।"""
    pool = kv.get("KAGGLE_API_TOKENS", "") or kv.get("KAGGLE_API_TOKEN", "")
    if not pool:
        return []
    first = pool.split(",")[0].strip()
    if first.startswith("KGAT_"):
        auth_header = f"Bearer {first}"
    elif ":" in first:
        u, k = first.split(":", 1)
        auth_header = "Basic " + base64.b64encode(f"{u}:{k}".encode()).decode()
    elif "_" in first:
        u, k = first.split("_", 1)
        auth_header = "Basic " + base64.b64encode(f"{u}:{k}".encode()).decode()
    else:
        return [mk("kaggle", "competitions", False, "token format অজানা", category="AUTH_INVALID")]
    st, body = retry(lambda: http("GET", "https://www.kaggle.com/api/v1/competitions/list?page=1",
                                  {"Authorization": auth_header}))
    if st == 200:
        return [mk("kaggle", "competitions", True, "HTTP 200 (KGAT Bearer)" if first.startswith("KGAT_") else "HTTP 200")]
    cat, note = classify("kaggle", "competitions", st, body)
    return [mk("kaggle", "competitions", False, f"HTTP {st}: {body[:140]}", category=cat, note=note)]


def probe_ai_hosts(kv: dict) -> list[dict]:
    out = []
    for key_name, url in KNOWN_AI_HOSTS.items():
        key = kv.get(key_name, "")
        if not key:
            continue
        name = key_name.replace("_API_KEY", "").lower()
        st, body = http("GET", url, {"Authorization": f"Bearer {key}"})
        if st == 200 and '"data"' in body:
            out.append(mk(name, "models", True, "HTTP 200"))
        else:
            cat, note = classify(name, "models", st, body)
            out.append(mk(name, "models", False, f"HTTP {st}: {body[:140]}", category=cat, note=note))
    # বাংলা (#3693): GOOGLE_API_KEY-ও AIza-ফরম্যাট Gemini-কী — vault-এ দুটি
    # আলাদা key-ই আছে (লাইভ-যাচাই 2026-10-06)। দুটোই স্বাধীনভাবে প্রোব হবে —
    # একটি নীরবে মরলে অন্যটি ঢেকে যাবে না (#2713-এর অসম্পূর্ণ অংশ)।
    gemini = kv.get("GEMINI_API_KEY", "")
    google = kv.get("GOOGLE_API_KEY", "")
    if google:
        st, body = http("GET", f"https://generativelanguage.googleapis.com/v1beta/models",
                        {"x-goog-api-key": google, "Referer": GOOGLE_PROBE_REFERER})
        if st == 200:
            out.append(mk("google", "models", True, "HTTP 200"))
        else:
            cat, note = classify("google", "models", st, body)
            out.append(mk("google", "models", False, f"HTTP {st}: {body[:140]}", category=cat, note=note))
    if gemini:
        st, body = http("GET", f"https://generativelanguage.googleapis.com/v1beta/models",
                        {"x-goog-api-key": gemini, "Referer": GOOGLE_PROBE_REFERER})
        if st == 200:
            out.append(mk("gemini", "models", True, "HTTP 200"))
        else:
            # বাংলা মন্তব্য: বডিসহ ক্লাসিফাই — 'location is not supported' → REGION_BLOCKED ধরা পড়বে
            cat, note = classify("gemini", "models", st, body)
            out.append(mk("gemini", "models", False, f"HTTP {st}: {body[:140]}", category=cat, note=note))
    return out


def probe_firecrawl(kv: dict) -> list[dict]:
    key = kv.get("FIRECRAWL_API_KEY", "")
    if not key:
        return []
    st, body = http("GET", "https://api.firecrawl.dev/v1/team/credit-usage",
                    {"Authorization": f"Bearer {key}"})
    if st == 200:
        try:
            used = json.loads(body).get("data", {}).get("credits_used")
            return [mk("firecrawl", "credit-usage", True, f"credits_used={used}")]
        except Exception:
            return [mk("firecrawl", "credit-usage", True, "HTTP 200")]
    cat, note = classify("firecrawl", "credit-usage", st, body)
    return [mk("firecrawl", "credit-usage", False, f"HTTP {st}: {body[:140]}", category=cat, note=note)]


def probe_known_keys(kv: dict) -> list[dict]:
    """বাংলা মন্তব্য (#2713): পরিচিত পাবলিক API-সহ প্ল্যাটফর্মগুলোর সস্তা key-validity প্রোব।
    নীরবে এক্সপায়ার/রিভোক হওয়া Stripe/Resend/Telegram-জাতীয় key ইউজার-ফেসিং
    ফিচার-ব্যর্থতা হিসেবেই প্রকাশ পেত — শিফট-লেফট ধরা এখন প্রতিদিন সম্ভব।"""
    out = []
    # (vault-key, প্ল্যাটফর্ম, চেক-url) — সব GET, Bearer-অথ
    # বাংলা (#3693): NEON নিচে ডেডিকেটেড প্রোবে সরানো হয়েছে — org-scoped token-এ
    # /projects 400 'org_id is required' দেয়, generic-প্রোবে এটা UNCLASSIFIED-নয়েজ ছিল।
    probes = [
        ("STRIPE_API_KEY",       "stripe",        "https://api.stripe.com/v1/balance"),
        ("RESEND_API_KEY",       "resend",        "https://api.resend.com/domains"),
        # বাংলা (#4076): LaunchDarkly-র auth স্কিম ভিন্ন — API key সরাসরি
        # `Authorization: <key>` হেডারে যায়, `Bearer` প্রিফিক্স নয়। Bearer
        # পাঠালে LD REST 401 দেয় → ভুয়া AUTH_INVALID (লাইভ-প্রমাণিত 2026-10-06:
        # Bearer → 401, খালি header → 200)। তাই LD-কে dedicated probe-এ সরানো হলো।
        ("LAUNCHDARKLY_API_KEY", "launchdarkly",  "https://app.launchdarkly.com/api/v2/projects"),
    ]
    # বাংলা (#4076): Bearer-অথ ব্যবহার করা প্ল্যাটফর্মগুলো generic লুপে চলে।
    bearer_platforms = {"stripe", "resend"}
    for key_env, name, url in probes:
        tok = kv.get(key_env, "")
        if not tok:
            continue  # বাংলা মন্তব্য: key-ই না থাকলে প্রোব নয় — CONFIG_MISSING-ও নয়েজ
        # বাংলা (#4076): launchdarkly — `Authorization: <key>` (Bearer নয়);
        # বাকি সব Bearer-অথ প্ল্যাটফর্ম। auth স্কিম প্রতি-প্ল্যাটফর্ম সত্য।
        if name in bearer_platforms:
            H = {"Authorization": f"Bearer {tok}"}
        else:
            H = {"Authorization": tok}
        st, body = retry(lambda: jget(url, H))
        low = (body if isinstance(body, str) else json.dumps(body)).lower()
        if st == 200:
            out.append(mk(name, "key-validity", True, "HTTP 200 — সচল"))
        elif st in (401,) or (st == 403 and any(s in low for s in ("invalid", "expired", "unauthorized"))):
            out.append(mk(name, "key-validity", False, f"HTTP {st} — key নিষ্ক্রিয়/রিভোকড", category="AUTH_INVALID"))
        elif st == 0:
            out.append(mk(name, "key-validity", False, f"HTTP {st}", category="NETWORK"))
        else:
            out.append(mk(name, "key-validity", None, f"HTTP {st} — ম্যানুয়াল ট্রায়াজ ({str(body)[:120]})"))
    # বাংলা (#3693): Neon — org-scoped token। key-validity সস্তা /users/me দিয়ে
    # যাচাই (2026-10-06 লাইভ-প্রমাণিত: /projects → 400 org_id, কিন্তু /users/me →
    # 200 login=paykaribazaronline — key বৈধ)। NEON_ORG_ID থাকলে projects-গভীরতাও;
    # org_id-নির্ভর 400 হলে CONFIG_MISSING (অ্যাকশনেবল) — UNCLASSIFIED নয়।
    ntok = kv.get("NEON_API_KEY", "")
    if ntok:
        NH = {"Authorization": f"Bearer {ntok}"}
        st, me = retry(lambda: jget("https://console.neon.tech/api/v2/users/me", NH))
        if st == 200 and isinstance(me, dict):
            out.append(mk("neon", "key-validity", True, f"HTTP 200 — সচল (login={me.get('login', '?')})"))
            org = kv.get("NEON_ORG_ID", "")
            if org:
                st2, projs = retry(lambda: jget(
                    f"https://console.neon.tech/api/v2/projects?org_id={urllib.parse.quote(org)}", NH))
                if st2 == 200:
                    cnt = len(projs.get("projects", [])) if isinstance(projs, dict) else 0
                    out.append(mk("neon", "projects", True, f"HTTP 200 — org-প্রজেক্ট={cnt}"))
                else:
                    cat, note = classify("neon", "projects", st2, json.dumps(projs))
                    out.append(mk("neon", "projects", False, f"HTTP {st2}", category=cat, note=note))
        elif st in (401,) or (st == 403 and "invalid" in json.dumps(me).lower()):
            out.append(mk("neon", "key-validity", False, f"HTTP {st} — key নিষ্ক্রিয়/রিভোকড", category="AUTH_INVALID"))
        elif st == 400 and "org_id is required" in json.dumps(me).lower():
            # বাংলা: এই পাথ এখন দুর্লভ (/users/me org_id চায় না) — তবু নিরাপত্তা-জাল
            out.append(mk("neon", "key-validity", None,
                          "org_id প্রয়োজন — vault-এ NEON_ORG_ID যোগ করুন", category="CONFIG_MISSING"))
        elif st == 0:
            out.append(mk("neon", "key-validity", False, f"HTTP {st}", category="NETWORK"))
        else:
            out.append(mk("neon", "key-validity", None, f"HTTP {st} — ম্যানুয়াল ট্রায়াজ ({str(me)[:120]})"))
    # বাংলা মন্তব্য: টেলিগ্রাম — token URL-পাথে যায়; getMe সস্তা ও প্রমাণিত-স্কিম
    ttok = kv.get("TELEGRAM_BOT_TOKEN", "")
    if ttok:
        st, body = retry(lambda: jget(f"https://api.telegram.org/bot{ttok}/getMe", {}))
        if st == 200:
            ok_flag = isinstance(body, dict) and body.get("ok") is True
            out.append(mk("telegram", "getMe", ok_flag if ok_flag else None,
                          "bot সচল" if ok_flag else f"অপ্রত্যাশিত বডি: {str(body)[:120]}"))
        elif st in (401, 403):
            out.append(mk("telegram", "getMe", False, f"HTTP {st} — token নিষ্ক্রিয়", category="AUTH_INVALID"))
        elif st == 0:
            out.append(mk("telegram", "getMe", False, f"HTTP {st}", category="NETWORK"))
        else:
            out.append(mk("telegram", "getMe", None, f"HTTP {st} — ম্যানুয়াল ট্রায়াজ"))
    return out


def probe_github_mirror(kv: dict) -> list[dict]:
    out = []
    tok = kv.get("GITHUB_TOKEN", "")
    H = {"Authorization": f"Bearer {tok}"} if tok else {}
    st, rl = jget("https://api.github.com/rate_limit", H)
    if st == 200:
        core = rl.get("resources", {}).get("core", {})
        out.append(mk("github", "rate-limit", True, f"core remaining={core.get('remaining')}"))
    else:
        cat, note = classify("github", "rate-limit", st, json.dumps(rl))
        out.append(mk("github", "rate-limit", False, f"HTTP {st}", category=cat, note=note))
    # বাংলা মন্তব্য: mirror freshness (#2130/#2455-জাতীয় স্টেলনেস চেক)
    st, tgt = jget(f"https://api.github.com/repos/{MIRROR_TARGET_REPO}", H)
    if st == 200:
        age = age_hours(tgt.get("pushed_at", ""))
        st2, org = jget(f"https://api.github.com/repos/{MIRROR_ORIGIN_REPO}", H)
        if st2 == 200 and age is not None:
            gap = age - (age_hours(org.get("pushed_at", "")) or 0)
            if gap > 24:
                out.append(mk("mirror", "target-freshness", False,
                              f"target origin-এর চেয়ে {gap:.1f}h পিছিয়ে (>24h)",
                              category="DATA_STALE"))
            elif gap > 6:
                out.append(mk("mirror", "target-freshness", None, f"{gap:.1f}h পিছিয়ে — WARN"))
            else:
                out.append(mk("mirror", "target-freshness", True, f"{gap:.1f}h ব্যবধান"))
    else:
        # বাংলা (#99): private mirror-target-এ probe-token-এর access না থাকলে
        # GitHub 404 দেয় (repo নেই নয় — private + no-access)। সেটি NETWORK নয়;
        # "DNS/টাইমআউট যাচাই করুন" remediation ভুল দিকে পাঠায়। 404 = token/
        # scope gap (owner: mirror-target-এ প্রোব-টোকেনকে read দিন), 0 = sত্যি
        # নেটওয়ার্ক/egress ঘটনা।
        cat = "CONFIG_MISSING" if st == 404 else "NETWORK"
        out.append(mk("mirror", "target-freshness", False, f"HTTP {st}", category=cat))
    return out


PROBES = [probe_upstash, probe_render, probe_supabase, probe_vercel, probe_cloudflare,
          probe_kaggle, probe_ai_hosts, probe_firecrawl, probe_github_mirror, probe_known_keys]


def discover_unmonitored(kv: dict) -> list[dict]:
    """বাংলা মন্তব্য: ডায়নামিক ডিসকভারি — রেজিস্ট্রি কোনো সচল API-key গ্রাস করেনি তা খুঁজে বার করা।
    অ্যাপ-ইন্টার্নাল secret (JWT/OTP/SIGNING/WEBHOOK-ইত্যাদি) ও public client key (VITE_) বাদ।"""
    consumed = re.compile("|".join(CONSUMED_KEY_HINTS), re.I)
    not_platform = re.compile(r"(_SECRET$|WEBHOOK|JWT|OTP|SIGNING|VITE_|SESSION|SALT|HASH|_KEY_2$)", re.I)
    out = []
    for k, v in kv.items():
        if not v or consumed.search(k) or not_platform.search(k):
            continue
        if re.search(r"(_API_KEY|_TOKEN|_ACCESS_TOKEN)$", k):
            out.append(mk("vault", f"unmonitored[{k}]", None,
                          f"সচল দেখায় (len={len(v)}) কিন্তু কোনো প্রোব নেই",
                          category="UNMONITORED"))
    return out


# ── রানার + রিপোর্ট ───────────────────────────────────────────────────────────
def run_audit(kv: dict, max_workers: int = 8) -> list[dict]:
    findings: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(p, kv): p.__name__ for p in PROBES}
        for f in as_completed(futs):
            name = futs[f]
            try:
                findings.extend(f.result())
            except Exception as e:  # বাংলা মন্তব্য: এক প্রোবের ক্র্যাশ পুরো অডিট ভাঙবে না
                findings.append(mk("audit-engine", f"probe[{name}]", False,
                                   f"probe crash: {type(e).__name__}: {e}", category="NETWORK"))
    findings.extend(discover_unmonitored(kv))
    return findings


def render_report(findings: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    passed = [f for f in findings if f["ok"] is True]
    failed = sorted([f for f in findings if f["ok"] is False], key=lambda x: SEVERITY_ORDER.get(x["severity"], 9))
    warned = [f for f in findings if f["ok"] is None]
    lines = [f"## 🔬 Platform Deep-Audit Engine — {now}", "",
             f"**সারসংক্ষেপ:** {len(passed)} পাস · {len(failed)} ফেইল · {len(warned)} ওয়ার্ন/তথ্য", "",
             "### ❌ ফেইল (সিরিয়াসনেস অনুসারে)", "",
             "| সিরিয়াসনেস | ক্যাটাগরি | প্ল্যাটফর্ম | চেক | বিস্তারিত |", "|---|---|---|---|---|"]
    for f in failed:
        lines.append(f"| **{f['severity']}** | `{f['category']}` | {f['platform']} | `{f['check']}` | {f['detail'][:120]} |")
    if not failed:
        lines.append("| — | — | — | — | কোনো ফেইল নেই 🎉 |")
    lines += ["", "### ⚠️ ওয়ার্ন / ঝুঁকি / তথ্য", "",
              "| ক্যাটাগরি | প্ল্যাটফর্ম | চেক | বিস্তারিত |", "|---|---|---|---|---|"]
    for f in warned:
        lines.append(f"| `{f['category']}` | {f['platform']} | `{f['check']}` | {f['detail'][:120]} |")
    lines += ["", "### ✅ পাস", ""]
    lines.append(" · ".join(f"{f['platform']}:`{f['check']}`" for f in passed) or "—")
    lines += ["", "### 🛠️ প্রতিকার-নির্দেশনা (ফেইল অনুসারে)", ""]
    seen = set()
    for f in failed:
        if f["category"] in seen:
            continue
        seen.add(f["category"])
        lines.append(f"- **{f['category']}** ({f['platform']}:{f['check']}): {f['remediation']}{(' ' + f['note']) if f['note'] else ''}")
    return "\n".join(lines)


# ── GitHub issue লেয়ার (fingerprint + title দুই-স্তর dedup) ────────────────────
def gh_headers() -> dict:
    tok = os.environ.get("GITHUB_TOKEN", "")
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"} if tok else {}


def gh_search_issues(query: str) -> list[dict]:
    st, data = jget(f"https://api.github.com/search/issues?q={urllib.parse.quote(query)}&per_page=20", gh_headers())
    return data.get("items", []) if st == 200 else []


def find_tracker() -> int | None:
    q = f'repo:{REPO} state:open type:issue in:title "{TRACKER_PREFIX}"'
    items = gh_search_issues(q)
    return items[0]["number"] if items else None


def existing_issue_for(finding: dict) -> int | None:
    """বাংলা মন্তব্য: fingerprint অথবা title-কীওয়ার্ড ম্যাচে বিদ্যমান open issue খোঁজা — ডুপ্লিকেট বন্ধ।"""
    fp = f"{FP_MARK}{finding['fp']}"
    hits = gh_search_issues(f'repo:{REPO} state:open type:issue "{fp}"')
    if hits:
        return hits[0]["number"]
    # দ্বিতীয় স্তর: platform নাম title-এ + check-টোকেন
    tokens = [t for t in re.split(r"[\[\]._-]+", finding["check"]) if len(t) > 2][:2]
    hits = gh_search_issues(f'repo:{REPO} state:open type:issue in:title "{finding["platform"]}"')
    for it in hits:
        title = it.get("title", "").lower()
        if any(t.lower() in title for t in tokens) or finding["platform"].lower() in title:
            return it["number"]
    return None


def severity_labels(sev: str) -> list[str]:
    return {"P0": ["P0-critical"], "P1": ["P1-high"], "P2": ["P2-medium"], "P3": ["P2-medium"]}.get(sev, ["P2-medium"])


def close_recovered_findings(current: list[dict], run_url: str) -> list[int]:
    """বাংলা (#46/#26): রান-কালে যেসব চেক **পাস** (ok=True) — সেগুলোর open
    deep-audit issue রিকভারি-প্রমাণ কমেন্ট করে ক্লোজ। নাইটলি রানের পরেও
    (যেমন upstash কোটা UTC-মধ্যরাতে রিসেট) stale issue আর জমে থাকে না।

    নিয়ম (fail-honest): শুধু current-findings-এ ok=True **দেখা** চেকই ক্লোজ
    ট্রিগার করে — skip (ok=None) বা বর্তমান রানে অনুপস্থিত চেক নয় (creds-অভাব
    = recovery নয়, অনির্দিষ্ট statusस)।"""
    closed = []
    passed_fps = [f["fp"] for f in current if f.get("ok") is True]
    if not passed_fps:
        return closed
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for fp in passed_fps:
        hits = gh_search_issues(f'repo:{REPO} state:open type:issue "{FP_MARK}{fp}"')
        for it in hits:
            num = it.get("number")
            if not num:
                continue
            body = (
                f"✅ **Recovered** ({now}): deep-audit re-probe PASSED for this check. "
                "Auto-closed on verified recovery.\n\n"
                + (f"[Run log]({run_url})\n\n" if run_url else "")
                + "_স্বয়ংক্রিয়ভাবে: `.github/scripts/platform_deep_audit.py` — verified pass-এ auto-close (stale-tracker drift বন্ধ, #46/#26)।_"
            )
            st, _ = http("POST", f"https://api.github.com/repos/{REPO}/issues/{num}/comments",
                         gh_headers() | {"Content-Type": "application/json"}, {"body": body})
            if st not in (200, 201):
                print(f"[deep-audit] recovery-comment FAILED issue #{num} HTTP {st}")
                continue
            st, data = http("PATCH", f"https://api.github.com/repos/{REPO}/issues/{num}",
                            gh_headers() | {"Content-Type": "application/json"}, {"state": "closed", "state_reason": "completed"})
            if st == 200:
                closed.append(num)
                print(f"[deep-audit] recovered → closed issue #{num}")
            else:
                print(f"[deep-audit] close FAILED issue #{num} HTTP {st}: {str(data)[:120]}")
    return closed


def upsert_issues(findings: list[dict], report: str) -> list[int]:
    """বাংলা মন্তব্য: tracker update + নতুন ফেইলের জন্য deduped per-finding issue। রিটার্ন: তৈরি issue-নম্বর।"""
    created = []
    failed = [f for f in findings if f["ok"] is False]
    tracker = find_tracker()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if tracker:
        http("POST", f"https://api.github.com/repos/{REPO}/issues/{tracker}/comments",
             gh_headers() | {"Content-Type": "application/json"}, {"body": report + f"\n\n<!-- run {now} -->"})
        print(f"[deep-audit] tracker #{tracker} updated")
    else:
        st, data = http("POST", f"https://api.github.com/repos/{REPO}/issues", gh_headers() | {"Content-Type": "application/json"},
                        {"title": f"{TRACKER_PREFIX} {len(failed)} finding(s) — {now}", "body": report,
                         "labels": ["handoff:platform"]})
        parsed = _jbody(st, data)  # #2869: http() raw str রিটার্ন করে — পার্স বাধ্যতামূলক (raw data সংরক্ষণ)
        if st in (200, 201) and isinstance(parsed, dict):
            tracker = parsed.get("number")
            print(f"[deep-audit] tracker created #{tracker}")
        else:
            print(f"[deep-audit] tracker create FAILED HTTP {st}: {str(data)[:200]}")
    for f in failed:
        if existing_issue_for(f):
            print(f"[deep-audit] skip (existing issue) — {f['platform']}:{f['check']}")
            continue
        body = (f"## 🚨 Deep-Audit ফাইন্ডিং ({now})\n\n"
                f"- **প্ল্যাটফর্ম:** {f['platform']} · **চেক:** `{f['check']}`\n"
                f"- **ক্যাটাগরি:** `{f['category']}` · **সিরিয়াসনেস:** **{f['severity']}**\n"
                f"- **ফিঙ্গারপ্রিন্ট:** `{FP_MARK}{f['fp']}` (ডুপ্লিকেট-প্রতিরোধী কী)\n\n"
                f"### বিস্তারিত\n\n```\n{f['detail']}\n```\n\n"
                f"### 🛠️ প্রতিকার\n\n{f['remediation']}{chr(10) + chr(10) + f['note'] if f['note'] else ''}\n\n"
                f"---\n_স্বয়ংক্রিয়ভাবে তৈরি: `.github/scripts/platform_deep_audit.py` — ফিঙ্গারপ্রিন্ট মিললে পুনরায় তৈরি হবে না।_")
        st, data = http("POST", f"https://api.github.com/repos/{REPO}/issues",
                        gh_headers() | {"Content-Type": "application/json"},
                        {"title": f"[deep-audit:{f['severity']}] {f['platform']}: {f['check']} — {f['category']}",
                         "body": body, "labels": ["handoff:platform"] + severity_labels(f["severity"])})
        parsed = _jbody(st, data)  # #2869: http() raw str রিটার্ন করে — পার্স বাধ্যতামূলক (raw data সংরক্ষণ)
        if st in (200, 201) and isinstance(parsed, dict):
            num = parsed.get("number")
            print(f"[deep-audit] issue created #{num} — {f['platform']}:{f['check']}")
            created.append(num)
        else:
            detail = data if isinstance(data, str) else json.dumps(data)
            print(f"[deep-audit] issue create FAILED HTTP {st}: {detail[:200]}")
    return created


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Platform deep-audit engine (vault-driven, intelligent)")
    ap.add_argument("--dry-run", action="store_true", help="কোনো GitHub write নয় — শুধু রিপোর্ট")
    ap.add_argument("--json", dest="json_path", help="machine-readable JSON আউটপুট পাথ")
    ap.add_argument("--max-workers", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=HTTP_TIMEOUT_DEFAULT)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    kv = vault_secrets()
    findings = run_audit(kv, args.max_workers)
    report = render_report(findings)
    print(report)
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(findings, fh, ensure_ascii=False, indent=2)
    if args.verbose:
        for f in findings:
            if f["ok"] is not True:
                print(json.dumps(f, ensure_ascii=False))
    if args.dry_run:
        failed = [f for f in findings if f["ok"] is False]
        print(f"[deep-audit] dry-run — issue-তৈরি বন্ধ (ফেইল: {len(failed)})")
        return 1 if failed else 0
    created = upsert_issues(findings, report)
    run_url = (f"https://github.com/{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
               if os.environ.get("GITHUB_RUN_ID") else "")
    recovered = close_recovered_findings(findings, run_url)
    failed = [f for f in findings if f["ok"] is False]
    print(f"[deep-audit] done — ফেইল {len(failed)}, নতুন issue {len(created)}, রিকভারি-ক্লোজ {len(recovered)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
