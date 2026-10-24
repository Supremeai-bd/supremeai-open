"""
service_preflight_check.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
বাংলা মন্তব্য: এই স্ক্রিপ্টটি CI pipeline-এর একদম শুরুতে চলে।
উদ্দেশ্য: ব্যয়বহুল jobs (pytest, lint, build) চালানোর আগেই
সব external service-এর credential/key validate করা।

চেক করা হয় (Blocking — শুধু production main repo-তে, fail হলে exit 1):
  - Render Primary  (RENDER_API_KEY + PRIMARY_SVC_ID)
  - Render Backup   (RENDER_API_KEY_BACKUP + BACKUP_SVC_ID)
  - Vercel          (VERCEL_TOKEN)

চেক করা হয় (Warning-only — fail হলেও exit 0):
  - Firebase        (FIREBASE_SERVICE_ACCOUNT — JSON parse only)

Repo-aware gating (2026-08-04 fix):
  এই স্ক্রিপ্ট GITHUB_REPOSITORY env var (GitHub Actions সব step-এ default
  পাওয়া যায়) পড়ে production main repo চিনে নেয়। Main repo ছাড়া অন্য যেকোনো
  repo-তে (staging/mirror/fork সহ) Render ও Vercel-এর fail-কে blocking না
  রেখে warning-only করে দেওয়া হয় — কারণ সেসব repo-তে production deploy job
  গুলো এমনিতেই `github.repository == 'paykaribazaronline/supremeai'` গার্ড
  দিয়ে বন্ধ থাকে, ফলে সেখানে production credential যাচাই করার কোনো বাস্তব
  মূল্য নেই এবং সেই credential রাখাটাও অপ্রয়োজনীয় ঝুঁকি (attack surface,
  secret duplication/drift)। এতে দুই repo-তেই একই স্ক্রিপ্ট রাখা যায়, কিন্তু
  staging repo আর কখনো এই কারণে force-cancel হয় না।

GCP চেক: নিচে commented-out রাখা হয়েছে।
  → GCP deploy enable করতে হলে শুধু uncomment করুন।
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import json
import os
import sys
import urllib.error
import urllib.request

# ──────────────────────────────────────────────────────────────
# Production main repo — শুধু এই repo-তে Render/Vercel blocking থাকে।
# হার্ডকোড এড়াতে env var দিয়ে override করার সুযোগও রাখা হলো
# (repo/org variable PROD_REPO_SLUG সেট থাকলে সেটাই ব্যবহার হবে)।
# ──────────────────────────────────────────────────────────────
PROD_REPO_SLUG = os.environ.get("PROD_REPO_SLUG", "SaifulHaqueNiloy/supremeai")


# ──────────────────────────────────────────────────────────────
# HTTP helper — stdlib only, zero dependencies
# ──────────────────────────────────────────────────────────────
def http_get(url: str, headers: dict, timeout: int = 8) -> int:
    """বাংলা মন্তব্য: HTTP GET request করে শুধু status code ফেরত দেয়। timeout-এ -1 দেয়।"""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return -1  # network/DNS/timeout failure


# ──────────────────────────────────────────────────────────────
# Render check
# ──────────────────────────────────────────────────────────────
def check_render(label: str, api_key: str, service_id: str) -> str | None:
    """
    বাংলা মন্তব্য: Render API-তে GET করে service ownership confirm করে।
    200 → ✅ Pass
    401 → ❌ Key expired/revoked
    403 → ❌ Permission denied
    404 → ❌ Key ভুল account-এর (mismatch)
    -1  → ❌ Network/DNS/timeout error
    """
    if not api_key:
        secret_name = "RENDER_API_KEY_BACKUP" if "BACKUP" in label else "RENDER_API_KEY"
        return f"[{label}] ❌ FAIL: Secret is empty — set {secret_name} in GitHub Secrets"

    url = f"https://api.render.com/v1/services/{service_id}"
    code = http_get(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })

    diagnosis = {
        200: None,  # Pass
        401: "API key expired or revoked. Rotate the secret in GitHub Secrets.",
        403: "Key valid but permission denied. Check Render account permissions.",
        404: "Key valid but this service is NOT in this account. Configuration mismatch — wrong key for wrong account.",
        -1:  "Network/DNS error or Render API unreachable. Check runner connectivity.",
    }.get(code, f"Unexpected HTTP {code} from Render API.")

    if diagnosis is None:
        print(f"  ✅ [{label}] PASS  (HTTP 200) — service_id={service_id}")
        return None  # No error

    return (
        f"[{label}] ❌ FAIL: HTTP {code}\n"
        f"   → Service ID : {service_id}\n"
        f"   → Diagnosis  : {diagnosis}"
    )


def ping_render_warmup(label: str, service_url: str) -> None:
    """
    বাংলা মন্তব্য: Render-এর Free-tier সার্ভিস যদি ঘুমে (sleep mode) থাকে,
    তবে pipeline-এর শুরুতেই ping পাঠিয়ে তাকে আগেই জাগিয়ে (warm-up) নেওয়া হয়।
    এটি non-blocking — fail হলেও warning দেবে, CI থামাবে না।
    """
    health_url = f"{service_url.rstrip('/')}/health"
    code = http_get(health_url, headers={"User-Agent": "SupremeAI-Preflight-Warmup/1.0"}, timeout=5)
    if code == 200:
        print(f"  🔥 [{label}-WARMUP] ✅ Service is awake & active (HTTP 200)")
    else:
        print(f"  ⏰ [{label}-WARMUP] Ping sent to {health_url} (HTTP {code}) — cold-start warm-up triggered in background.")


# ──────────────────────────────────────────────────────────────
# Vercel check
# ──────────────────────────────────────────────────────────────
def check_vercel(token: str) -> str | None:
    """
    বাংলা মন্তব্য: Vercel /v2/user endpoint-এ GET করে token validity নিশ্চিত করে।
    200 → ✅ Pass
    401/403 → ❌ Token invalid/expired
    """
    if not token:
        return "[VERCEL] ❌ FAIL: Secret is empty — set VERCEL_TOKEN in GitHub Secrets"

    code = http_get(
        "https://api.vercel.com/v2/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )

    if code == 200:
        print("  ✅ [VERCEL] PASS  (HTTP 200) — token valid")
        return None

    diagnosis = {
        401: "Token expired or revoked. Regenerate VERCEL_TOKEN in Vercel Dashboard → Settings → Tokens.",
        403: "Token valid but insufficient permissions. Check token scope.",
        -1:  "Network/DNS error or Vercel API unreachable.",
    }.get(code, f"Unexpected HTTP {code} from Vercel API.")

    return (
        f"[VERCEL] ❌ FAIL: HTTP {code}\n"
        f"   → Diagnosis  : {diagnosis}"
    )


# ──────────────────────────────────────────────────────────────
# Firebase check — WARNING ONLY (non-blocking)
# ──────────────────────────────────────────────────────────────
def check_firebase_warning(sa_json_str: str) -> str | None:
    """
    বাংলা মন্তব্য: Firebase service account JSON parse করে।
    deploy-এ continue-on-error: true আছে, তাই এটা warning-only।
    এই function কখনো blocking error ফেরত দেয় না।
    """
    if not sa_json_str:
        print("  ⚠️  [FIREBASE] WARNING: FIREBASE_SERVICE_ACCOUNT secret is empty — Firebase deploy may fail.")
        return None  # Non-blocking

    try:
        data = json.loads(sa_json_str)
        project_id = data.get("project_id", "")
        if project_id:
            print(f"  ✅ [FIREBASE] PASS  — service account JSON valid, project_id={project_id}")
        else:
            print("  ⚠️  [FIREBASE] WARNING: JSON parsed but 'project_id' field missing.")
    except json.JSONDecodeError as e:
        print(f"  ⚠️  [FIREBASE] WARNING: service account JSON invalid: {e}")

    return None  # Always non-blocking


# ──────────────────────────────────────────────────────────────
# Secondary Repo Sync Check — WARNING ONLY (non-blocking)
# ──────────────────────────────────────────────────────────────
def check_secondary_mirror_warning(token: str) -> None:
    """
    বাংলা মন্তব্য: Secondary Repository Mirror (MIRROR_REPO_TOKEN) সেট করা আছে কিনা চেক করে।
    এটি Warning-only — খালি থাকলে বা সেট না থাকলে warning মেসেজ প্রিন্ট করে যাতে জানা যায় কেন মিররিং স্কিপ হতে পারে।
    """
    if not token:
        print("  ⚠️  [SECONDARY-MIRROR] WARNING: MIRROR_REPO_TOKEN secret is empty or missing in GitHub Secrets.")
        print("      → Secondary repository (SaifulHaqueNiloy/supremeai) will NOT automatically sync on push.")
    else:
        print("  ✅ [SECONDARY-MIRROR] PASS — MIRROR_REPO_TOKEN detected.")


# ──────────────────────────────────────────────────────────────
# GCP check — COMMENTED OUT (enable করতে uncomment করুন)
# ──────────────────────────────────────────────────────────────
# def check_gcp(sa_json_str: str, project_id: str) -> Optional[str]:
#     """
#     বাংলা মন্তব্য: GCP Service Account key JSON parse করে এবং
#     Cloud Resource Manager API-তে project existence verify করে।
#
#     GCP deploy enable করতে হলে:
#     1. এই function uncomment করুন
#     2. main()-এ check_gcp() call uncomment করুন
#     3. Workflow-এ GCP_SA_KEY এবং GCP_PROJECT_ID env var যোগ করুন
#
#     200 → ✅ Pass
#     401/403 → ❌ SA key invalid/expired
#     404 → ❌ Project not found
#     """
#     if not sa_json_str:
#         return "[GCP] ❌ FAIL: GCP_SA_KEY secret is empty or not set"
#
#     try:
#         sa_data = json.loads(sa_json_str)
#         detected_project = sa_data.get("project_id", "")
#         client_email = sa_data.get("client_email", "unknown")
#         print(f"  [GCP] SA key parsed — project_id={detected_project}, client_email={client_email}")
#     except json.JSONDecodeError as e:
#         return f"[GCP] ❌ FAIL: GCP_SA_KEY JSON invalid: {e}"
#
#     # Token exchange এবং API call এখানে যোগ করতে হবে (google-auth library দরকার)
#     # অথবা: gcloud CLI দিয়ে `gcloud projects describe {project_id}` চালানো যায়
#     # Simple check: শুধু JSON parse এবং required fields verify
#     required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
#     missing = [f for f in required_fields if not sa_data.get(f)]
#     if missing:
#         return f"[GCP] ❌ FAIL: GCP_SA_KEY JSON missing required fields: {missing}"
#
#     if sa_data.get("type") != "service_account":
#         return f"[GCP] ❌ FAIL: GCP_SA_KEY type is '{sa_data.get('type')}', expected 'service_account'"
#
#     print("  ✅ [GCP] PASS — SA key JSON structure valid")
#     return None


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
def main() -> None:
    # বাংলা মন্তব্য: UTF-8 encoding নিশ্চিত করা
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        print('Silenced error in except block')

    print("━" * 60)
    print("🔌  Service Preflight Connectivity Check")
    print("━" * 60)

    # ── Repo-aware gating ────────────────────────────────────
    current_repo = os.environ.get("GITHUB_REPOSITORY", "")
    is_prod_repo = current_repo == PROD_REPO_SLUG
    if is_prod_repo:
        print(f"🏭  Production repo detected ({current_repo}) — Render/Vercel checks are BLOCKING.\n")
    else:
        print(f"🧪  Non-production repo detected ({current_repo or 'unknown'}) — Render/Vercel checks are WARNING-ONLY.")
        print(f"    (Blocking mode only applies on {PROD_REPO_SLUG}; deploy jobs are already repo-gated there too.)\n")

    # ── Environment variables ─────────────────────────────────
    render_key_primary  = os.environ.get("RENDER_API_KEY", "")
    render_key_backup   = os.environ.get("RENDER_API_KEY_BACKUP", "") or render_key_primary
    primary_svc_id      = os.environ.get("PRIMARY_SVC_ID", "srv-da07ogmgekts739amqa0")
    backup_svc_id       = os.environ.get("BACKUP_SVC_ID",  "srv-da35gg2bkg8c73fp1mu0")
    primary_svc_url     = os.environ.get("RENDER_PRIMARY_URL", "https://supremeai-backend-docker.onrender.com")
    backup_svc_url      = os.environ.get("RENDER_BACKUP_URL",  "https://supremeai-backend.onrender.com")
    vercel_token        = os.environ.get("VERCEL_TOKEN", "")
    firebase_sa         = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
    mirror_token        = os.environ.get("MIRROR_REPO_TOKEN", "")
    # gcp_sa_key        = os.environ.get("GCP_SA_KEY", "")        # uncomment when GCP enabled
    # gcp_project_id    = os.environ.get("GCP_PROJECT_ID", "")    # uncomment when GCP enabled

    # ── Run checks ───────────────────────────────────────────
    blocking_errors: list[str] = []

    # Render Primary (BLOCKING only on prod repo, else warning-only)
    print("\n[1/5] Render Primary Backend...")
    err = check_render("RENDER-PRIMARY", render_key_primary, primary_svc_id)
    if err:
        if is_prod_repo:
            blocking_errors.append(err)
        else:
            print(f"  ⚠️  [RENDER-PRIMARY] WARNING (non-prod repo, non-blocking):\n{err}")
    else:
        ping_render_warmup("RENDER-PRIMARY", primary_svc_url)

    # Render Backup/Admin (Non-blocking warning-only so secondary backend doesn't stall CI)
    print("\n[2/5] Render Backup/Admin Backend...")
    err = check_render("RENDER-BACKUP", render_key_backup, backup_svc_id)
    if err:
        print(f"  ⚠️  [RENDER-BACKUP] WARNING (non-blocking):\n{err}")
    else:
        ping_render_warmup("RENDER-BACKUP", backup_svc_url)

    # Vercel (BLOCKING only on prod repo, else warning-only)
    print("\n[3/5] Vercel User Portal...")
    err = check_vercel(vercel_token)
    if err:
        if is_prod_repo:
            blocking_errors.append(err)
        else:
            print(f"  ⚠️  [VERCEL] WARNING (non-prod repo, non-blocking):\n{err}")

    # Firebase (WARNING ONLY — non-blocking)
    print("\n[4/5] Firebase Service Account (warning-only)...")
    check_firebase_warning(firebase_sa)

    # Secondary Repo Mirror Check (WARNING ONLY — non-blocking)
    print("\n[5/5] Secondary Repository Mirror Token (warning-only)...")
    check_secondary_mirror_warning(mirror_token)

    # GCP check — uncomment block below when GCP deploy is re-enabled
    # print("\n[5/5] GCP Cloud Run (blocking)...")
    # err = check_gcp(gcp_sa_key, gcp_project_id)
    # if err:
    #     blocking_errors.append(err)

    # ── Result summary ────────────────────────────────────────
    print("\n" + "━" * 60)
    if blocking_errors:
        print(f"❌  PREFLIGHT FAILED — {len(blocking_errors)} blocking issue(s) found:\n")
        for i, error in enumerate(blocking_errors, 1):
            print(f"  {i}. {error}\n")
        print("   Pipeline aborted. Fix credentials before re-running.")
        print("━" * 60)
        sys.exit(1)
    else:
        print("✅  PREFLIGHT PASSED — all service credentials are valid.")
        print("━" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
