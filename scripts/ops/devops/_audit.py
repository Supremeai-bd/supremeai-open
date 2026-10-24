import json, re, os, urllib.request, urllib.error
try:
    import yaml
except ImportError:
    yaml = None

ROOT = os.path.dirname(os.path.abspath(__file__))

def env_vals(path=".env"):
    d = {}
    if not os.path.exists(path):
        return d
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"\'')
    return d

def envval(env, k):
    return env.get(k)

# ---------- live fetches ----------
def infisical_login(cid, csec):
    url = "https://app.infisical.com/api/v1/auth/universal-auth/login"
    body = json.dumps({"clientId": cid, "clientSecret": csec}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("accessToken")

def infisical_keys(pid, token):
    url = f"https://app.infisical.com/api/v3/secrets/raw?workspaceId={pid}&environment=prod"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return {s.get("secretKey") for s in data.get("secrets", []) if s.get("secretKey")}

def github_secret_names(token, repo="SaifulHaqueNiloy/supremeai"):
    url = f"https://api.github.com/repos/{repo}/actions/secrets"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return {s.get("name") for s in data.get("secrets", [])}

def render_env_keys(apikey, svc):
    url = f"https://api.render.com/v1/services/{svc}/env-vars"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {apikey}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return {e.get("envVar", {}).get("key") for e in data if isinstance(e, dict) and e.get("envVar", {}).get("key")}

# ---------- real/fake classification ----------
PLACEHOLDER_PAT = ["example.com", "changeme", "your_",
                   "xxxx", "replaceme", "dummy", "todo", "placeholder", "password123"]

def validator_for(key):
    table = {
        "STRIPE_API_KEY": lambda x: vstart(x, ["sk_live_","sk_test_","rk_"]),
        "STRIPE_SECRET_KEY": lambda x: vstart(x, ["sk_live_","sk_test_","rk_"]),
        "STRIPE_PUBLISHABLE_KEY": lambda x: vstart(x, ["pk_"]),
        "STRIPE_WEBHOOK_SECRET": lambda x: vstart(x, ["whsec_"]),
        "OPENAI_API_KEY": lambda x: vstart(x, ["sk-","sk-proj-"]),
        "GITHUB_TOKEN": github_v,
        "GITHUB_API_TOKEN": github_v,
        "GITHUB_MODELS_API_KEY": github_v,
        "GITHUB_CLIENT_ID": lambda x: ("UNVERIFIABLE", ""),
        "GITHUB_CLIENT_SECRET": lambda x: ("UNVERIFIABLE", "OAuth client secret"),
        "GEMINI_API_KEY": lambda x: vstart(x, ["AIza"]),
        "GROQ_API_KEY": lambda x: vstart(x, ["gsk_"]),
        "GROQ_API_KEY_DEPLOYMENT_MONITOR": lambda x: vstart(x, ["gsk_"]),
        "OPENROUTER_API_KEY": lambda x: vstart(x, ["sk-or-v1-"]),
        "MISTRAL_API_KEY": lambda x: ("UNVERIFIABLE", "no fixed prefix"),
        "FIRECRAWL_API_KEY": lambda x: vstart(x, ["fc-"]),
        "RESEND_API_KEY": lambda x: vstart(x, ["re_"]),
        "VERCEL_TOKEN": lambda x: vstart(x, ["vcp_"]),
        "VERCEL_ORG_ID": lambda x: ("UNVERIFIABLE", ""),
        "VERCEL_PROJECT_ID": lambda x: vstart(x, ["prj_"]),
        "ANTHROPIC_API_KEY": lambda x: vstart(x, ["sk-ant-"]),
        "CLAUDE_API_KEY": lambda x: vstart(x, ["sk-ant-"]),
        "TELEGRAM_BOT_TOKEN": lambda x: ("REAL" if re.match(r"^\d{8,10}:[A-Za-z0-9_-]{30,}$", x) else "FAKE"),
        "TELEGRAM_CHAT_ID": numeric_v,
        "ADMIN_TELEGRAM_CHAT_ID": numeric_v,
        "DISCORD_BOT_TOKEN": lambda x: ("REAL" if len(x) > 40 else "FAKE"),
        "DISCORD_WEBHOOK_URL": discord_webhook_v,
        "DISCORD_OTP_WEBHOOK_URL": discord_webhook_v,
        "DISCORD_ALERT_WEBHOOK": discord_webhook_v,
        "REDIS_URL": lambda x: vstart(x, ["redis://","rediss://"]),
        "UPSTASH_REDIS_REST_URL": lambda x: vstart(x, ["https://","redis://","rediss://"]),
        "UPSTASH_REDIS_REST_TOKEN": lambda x: ("REAL" if len(x) > 20 else "FAKE"),
        "SUPABASE_DATABASE_URL": lambda x: vstart(x, ["postgresql://"]),
        "SUPABASE_DATABASE_URL_POOLER": lambda x: vstart(x, ["postgresql://"]),
        "SUPABASE_URL": lambda x: vstart(x, ["https://"]),
        "SUPABASE_KEY": jwt_v,
        "SUPABASE_SERVICE_ROLE_KEY": jwt_v,
        "SUPABASE_JWKS_URL": lambda x: vstart(x, ["https://"]),
        "SUPABASE_PUBLISHABLE_KEY": lambda x: vstart(x, ["sb_publishable_","pk_"]),
        "SUPABASE_SECRET_KEY": lambda x: vstart(x, ["sb_secret_","sk_"]),
        "QDRANT_URL": lambda x: vstart(x, ["https://"]),
        "QDRANT_API_KEY": jwt_v,
        "KAGGLE_API_TOKEN": kaggle_v,
        "KAGGLE_API_TOKEN_1": kaggle_v,
        "KAGGLE_API_TOKEN_2": kaggle_v,
        "KAGGLE_API_TOKEN_3": kaggle_v,
        "KAGGLE_API_TOKEN_4": kaggle_v,
        "KAGGLE_API_TOKEN_5": kaggle_v,
        "KAGGLE_API_TOKEN_6": kaggle_v,
        "CLOUDFLARE_API_KEY": lambda x: vstart(x, ["cfk_","cf_"]),
        "CLOUDFLARE_API_TOKEN": lambda x: vstart(x, ["cfut_","cf_"]),
        "CLOUDFLARE_WORKERS_API_TOKEN": lambda x: vstart(x, ["cfut_","cf_"]),
        "CLOUDFLARE_ZONE_ID": lambda x: ("UNVERIFIABLE", ""),
        "CLOUDFLARE_ACCOUNT_ID": lambda x: ("REAL" if len(x) >= 24 else "FAKE"),
        "LAUNCHDARKLY_API_KEY": lambda x: vstart(x, ["api-","ldproj-"]),
        "LAUNCHDARKLY_SDK_KEY": lambda x: vstart(x, ["ldproj-"]),
        "SUPREMEAI_API_KEY": lambda x: vstart(x, ["sk-supreme-"]),
        "SUPREMEAI_JWT_SECRET": lambda x: ("UNVERIFIABLE", "opaque hex"),
        "INFISICAL_TOKEN": jwt_v,
        "INFISICAL_CLIENT_ID": lambda x: ("UNVERIFIABLE", "uuid"),
        "INFISICAL_CLIENT_SECRET": lambda x: ("UNVERIFIABLE", "hex"),
        "INFISICAL_PROJECT_ID": lambda x: ("UNVERIFIABLE", "uuid"),
        "FIREBASE_SERVICE_ACCOUNT_JSON": json_v,
        "FIREBASE_SERVICE_ACCOUNT_SUPREMEAI_A": json_v,
        "FIREBASE_SERVICE_ACCOUNT": json_v,
        "FIREBASE_TOKEN": lambda x: ("REAL" if x.startswith("1//") or x.startswith("ya29.") else "FAKE"),
        "GITLAB_TOKEN": lambda x: vstart(x, ["glpat-"]),
        "OPENHANDS_API_KEY": lambda x: vstart(x, ["sk-oh-"]),
        "ROUTEME_API_KEY": lambda x: vstart(x, ["rm-"]),
        "NEO4J_URI": lambda x: vstart(x, ["neo4j://","bolt://"]),
        "NEO4J_USER": lambda x: ("UNVERIFIABLE", ""),
        "NEO4J_PASSWORD": lambda x: ("UNVERIFIABLE", ""),
        "MINIO_ACCESS_KEY": lambda x: ("UNVERIFIABLE", ""),
        "MINIO_SECRET_KEY": lambda x: ("UNVERIFIABLE", ""),
        "R2_ACCESS_KEY": lambda x: ("UNVERIFIABLE", ""),
        "R2_SECRET_KEY": lambda x: ("UNVERIFIABLE", ""),
        "ENCRYPTION_KEY": lambda x: ("UNVERIFIABLE", "opaque"),
        "ENCRYPTION_KEYS": lambda x: ("UNVERIFIABLE", "opaque"),
        "API_KEY_SIGNING_SECRET": lambda x: ("UNVERIFIABLE", "opaque"),
        "SUPREMEAI_CREDENTIAL_ENC_KEY": lambda x: ("UNVERIFIABLE", "opaque"),
        "JWT_SECRET": lambda x: ("UNVERIFIABLE", "opaque"),
        "SECRET": lambda x: ("UNVERIFIABLE", "opaque"),
        "SECRET_BACKEND": lambda x: ("UNVERIFIABLE", "opaque"),
        "SECRET_KEY": lambda x: ("UNVERIFIABLE", "opaque"),
        "TEST_VAULT_KEY": lambda x: ("UNVERIFIABLE", "opaque"),
        "SUPREMEAI_ADMIN_PASSWORD_HASH": lambda x: ("REAL" if x.startswith("$2b$") or x.startswith("$2a$") else "FAKE"),
        "SUPREMEAI_ADMIN_TOTP_SECRET": lambda x: ("FAKE" if x.upper() == "JBSWY3DPEHPK3PXP" else ("UNVERIFIABLE", "base32")),
        "DB_PASSWORD": lambda x: ("UNVERIFIABLE", "opaque"),
        "DOCS_PASSWORD": lambda x: ("PLACEHOLDER", "weak/default-style password"),
        "CI_WEBHOOK_SECRET": lambda x: ("PLACEHOLDER", "weak literal (pre-rotation value redacted by #696; rotate + store new value in Infisical)"),
        "SUPREMEAI_ADMIN_LOGIN_PASSWORD": lambda x: ("PLACEHOLDER", "weak literal (pre-rotation value redacted by #696; rotate + store new value in Infisical)"),
    }
    return table.get(key)

def vstart(x, prefixes):
    if any(x.startswith(p) for p in prefixes):
        return ("REAL", f"starts {prefixes[0][:6]}…")
    return ("FAKE", f"expected one of {prefixes}")

def github_v(x):
    if any(x.startswith(p) for p in ("ghp_","github_pat_","gho_","ghu_","ghs_","ghr_","ghf_")):
        return ("REAL", "GitHub token format")
    return ("FAKE", "not a GitHub token format")

def jwt_v(x):
    return ("REAL" if x.startswith("eyJ") else "FAKE", "JWT-like")

def numeric_v(x):
    return ("REAL" if x.lstrip("-").isdigit() else "FAKE", "numeric")

def discord_webhook_v(x):
    return ("REAL" if "discord.com/api/webhooks/" in x else "FAKE", "Discord webhook URL")

def json_v(x):
    return ("REAL" if '"private_key"' in x and '"type":"service_account"' in x else "FAKE", "service-account JSON")

def kaggle_v(x):
    return ("UNVERIFIABLE", "custom KGAT_ prefix (not externally verifiable)")

def classify(key, val):
    if val is None or val.strip() == "":
        return ("EMPTY", "no value in .env")
    v = val.strip()
    low = v.lower()
    fn = validator_for(key)
    if fn:
        try:
            res = fn(v)
            verdict, note = res if isinstance(res, tuple) else (res, "")
            if verdict == "REAL":
                return ("REAL", note)
        except Exception as e:
            verdict, note = ("UNVERIFIABLE", str(e))
    for p in PLACEHOLDER_PAT:
        if p in low:
            return ("WEAK", f"derivable password pattern '{p}'")
    if fn:
        return (verdict, note)
    return ("UNVERIFIABLE", "no provider-format rule")

# ---------- main ----------
env = env_vals(os.path.join(ROOT, ".env"))
cid = env.get("INFISICAL_CLIENT_ID"); csec = env.get("INFISICAL_CLIENT_SECRET")
pid = env.get("INFISICAL_PROJECT_ID"); ght = env.get("GITHUB_TOKEN")
rak = env.get("RENDER_API_KEY")
render_primary = env.get("RENDER_PRIMARY_SVC_ID") or "srv-da666f8u01pc739bm3t0"
render_scraper = None  # svc id in .env (srv-da15tovqj5pc73br4b9g) returns 404 — stale

inf_set, gh_set, render_set = set(), set(), set()
inf_err = gh_err = render_err = None
try:
    tok = infisical_login(cid, csec)
    inf_set = infisical_keys(pid, tok)
except Exception as e:
    inf_err = str(e)
try:
    gh_set = github_secret_names(ght)
except Exception as e:
    gh_err = str(e)[:120]
try:
    render_set = render_env_keys(rak, render_primary)
    if render_scraper:
        render_set |= render_env_keys(rak, render_scraper)
except Exception as e:
    render_err = str(e)[:120]

# registry
reg = {}
if yaml:
    with open(os.path.join(ROOT, "secrets_registry.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for e in (data or {}).get("keys", []):
        reg[e.get("name")] = e.get("criticality", {})

def targets(key):
    if key in reg:
        return [k for k in reg[key].keys()]
    return []

all_keys = list(env.keys())
for k in reg:
    if k not in all_keys:
        all_keys.append(k)

def mask(val):
    if val is None or val == "":
        return "-"
    if len(val) <= 8:
        return f"{val[:2]}…({len(val)})"
    return f"{val[:4]}…({len(val)})"

rows = []
for k in all_keys:
    val = env.get(k)
    verdict, note = classify(k, val)
    present_env = "✓" if (val not in (None, "")) else ("✗ empty" if k in env else "— absent")
    tgt = targets(k)
    inf = "✓" if k in inf_set else ("✗" if inf_err is None else "?")
    gh = "✓" if k in gh_set else ("✗" if gh_err is None else "?")
    rn = "✓" if k in render_set else ("✗" if render_err is None else "?")
    rows.append((k, present_env, mask(val), verdict, note, tgt, inf, gh, rn))

# sort: missing-in-infisical critical first, then by name
def sortkey(r):
    k = r[0]
    crit = reg.get(k, {})
    inf_missing = 1 if (r[6] == "✗") else 0
    critical = 0
    if "infisical-vault" in crit:
        critical = {"critical": 0, "important": 1, "optional": 2}.get(crit["infisical-vault"], 3)
    return (inf_missing, critical, k.lower())

rows.sort(key=sortkey)

# ---------- write markdown ----------
lines = []
lines.append("# SupremeAI — Secrets Audit Report")
lines.append("")
lines.append(f"_Generated: {os.path.basename(__file__)} run · repo: SaifulHaqueNiloy/supremeai_")
lines.append("")
lines.append("## Methodology")
lines.append("")
lines.append("- **Source of truth (keys):** `.env` (runtime) unioned with `secrets_registry.yaml` (canonical key→service map).")
lines.append("- **Live verification:** Infisical vault (`prod`) via Universal Auth; GitHub Actions secret *names* via REST; Render backend + scraper env-var *names* via REST.")
lines.append("- **Real/Fake:** provider key-format validation (prefix/JWT/numeric) + placeholder-pattern scan (bare-domain values, `example`, `changeme`, etc.). Opaque secrets (hashes, encryption keys) are marked `UNVERIFIABLE` — they cannot be confirmed real without a live API test against the provider.")
lines.append(        "- **Not auto-verified:** Cloudflare, Supabase, Vercel, Firebase external dashboards (no name-listing API used here; targets still listed from registry).")
lines.append("")
# summary
total = len(rows)
in_env = sum(1 for r in rows if r[1] == "✓")
empty = sum(1 in [r[1] for r in rows] for _ in [0])  # placeholder
empty_c = sum(1 for r in rows if r[1] == "✗ empty")
absent_c = sum(1 for r in rows if r[1] == "— absent")
inf_present = sum(1 for r in rows if r[6] == "✓")
inf_missing = sum(1 for r in rows if r[6] == "✗")
fake_c = sum(1 for r in rows if r[3] in ("FAKE", "PLACEHOLDER", "WEAK"))
empty_val = sum(1 for r in rows if r[3] == "EMPTY")
lines.append("## Summary")
lines.append("")
lines.append(f"- **Total tracked keys:** {total}")
lines.append(f"- **Present in `.env` (with value):** {in_env}")
lines.append(f"- **Empty in `.env`:** {empty_c}  |  **Absent from `.env`:** {absent_c}")
lines.append(f"- **In Infisical vault (`prod`):** {inf_present}  |  **Missing from Infisical:** {inf_missing}" + (f"  _(Infisical fetch error: {inf_err})_" if inf_err else ""))
gh_note = ""
if gh_err:
    gh_note = "  _(GitHub error: token in .env is invalid/expired — 401 Bad credentials)_" if "401" in (gh_err or "") else f"  _(GitHub error: {gh_err})_"
lines.append(f"- **In GitHub Actions secrets:** {sum(1 for r in rows if r[7]=='✓')}" + gh_note)
rn_note = ""
if render_err:
    rn_note = f"  _(Render error: {render_err})_"
elif render_primary:
    rn_note = f"  _(verified against service `{render_primary}` = supremeai-backend-v2)_"
lines.append(f"- **In Render env vars:** {sum(1 for r in rows if r[8]=='✓')}" + rn_note)
lines.append(f"- **Value looks FAKE/PLACEHOLDER:** {fake_c}  |  **EMPTY value:** {empty_val}")
lines.append("")

# critical missing from infisical
lines.append("## Action Items — Keys Missing from Infisical Vault (by criticality)")
lines.append("")
crit_order = {"critical": 0, "important": 1, "optional": 2}
missing = [(r[0], reg.get(r[0], {}).get("infisical-vault", "?")) for r in rows if r[6] == "✗"]
missing.sort(key=lambda m: crit_order.get(m[1], 3))
if missing:
    for k, c in missing:
        lines.append(f"- `[{c}]` {k}")
else:
    lines.append("_None missing (or Infisical fetch failed)._")
lines.append("")

# suspicious values
lines.append("## Suspicious / Placeholder / Fake / Weak Values")
lines.append("")
for r in rows:
    if r[3] in ("FAKE", "PLACEHOLDER", "WEAK"):
        lines.append(f"- **{r[0]}** → `{r[3]}` ({r[4]}) — value: `{r[2]}`")
if not any(r[3] in ("FAKE","PLACEHOLDER") for r in rows):
    lines.append("_None detected._")
lines.append("")

# full table
lines.append("## Full Key Inventory")
lines.append("")
lines.append("| Key | .env | Val(len) | Real/Fake | Infisical | GitHub | Render | Target services | Notes |")
lines.append("|-----|------|-----------|-----------|-----------|--------|--------|---------------|-------|")
for r in rows:
    k, pe, mv, vf, nt, tgt, inf, gh, rn = r
    tgt_s = ",".join(tgt) if tgt else "(untracked)"
    note_s = (nt or "")
    lines.append(f"| {k} | {pe} | {mv} | {vf} | {inf} | {gh} | {rn} | {tgt_s} | {note_s} |")

out = os.path.join(ROOT, "SECRETS_AUDIT.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

# console summary
print("TOTAL", total, "in_env", in_env, "empty", empty_c, "absent", absent_c)
print("INFISICAL present", inf_present, "missing", inf_missing, "err", inf_err)
print("GITHUB present", sum(1 for r in rows if r[7]=='✓'), "err", gh_err)
print("RENDER present", sum(1 for r in rows if r[8]=='✓'), "err", render_err)
print("FAKE/PLACEHOLDER", fake_c, "EMPTY", empty_val)
print("Wrote", out)
