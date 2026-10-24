import json
import os
import sys
import urllib.error
import urllib.request


def trigger_deploy_for_service(
    api_key: str, service_id: str, image_url: str | None = None
) -> bool:
    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    payload = {"clearCache": "do_not_clear"}
    if image_url:
        payload["imageUrl"] = image_url

    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            if status_code in (200, 201, 202):
                res = json.loads(body) if body else {}
                deploy_id = res.get("id", "accepted")
                print(
                    f"✅ Render Deploy triggered successfully for {service_id} (Deploy ID: {deploy_id}) [HTTP {status_code}]"
                )
                return True
            else:
                print(
                    f"⚠️ Unexpected status code {status_code} for {service_id}: {body}"
                )
                return False
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"❌ Render API HTTP Error ({e.code}) for {service_id}: {err_body}")
        if e.code == 404:
            # Human-readable diagnosis (self-evolving: observe → explain → heal).
            # A 404 on the deploy endpoint means the service ID does not exist
            # under this API key's account — almost always a deleted/renamed
            # Render service, NOT a transient failure. Same diagnosis style as
            # service_preflight_check.py (owner idiom).
            print(
                "   → Diagnosis   : service ID not found in this Render account. "
                "The service was likely DELETED or RENAMED on Render."
            )
            print(
                "   → Action      : update the service-ID secret this workflow passes "
                "(RENDER_STAGING_SERVICE_ID / PRIMARY_SVC_ID) to the new srv-… ID, "
                "or clear it so service auto-discovery can find the current backend."
            )
            print(
                "   → Next attempt: falling through to service auto-discovery "
                "(name contains 'supremeai' + 'backend')."
            )
        elif e.code == 401:
            print(
                "   → Diagnosis   : API key expired or revoked — rotate RENDER_API_KEY in GitHub Secrets."
            )
        elif e.code == 403:
            print(
                "   → Diagnosis   : key valid but permission denied — check Render account/team permissions."
            )
        return False
    except Exception as e:
        print(f"❌ Render API Connection/Network Error for {service_id}: {e}")
        return False


def trigger_via_api(
    api_key: str, default_svc_id: str, image_url: str | None = None
) -> bool:
    if not api_key:
        return False

    # Try explicit service ID first if available
    if default_svc_id:
        print(f"🚀 Attempting direct deploy trigger on service: {default_svc_id}")
        if trigger_deploy_for_service(api_key, default_svc_id, image_url):
            return True

    # Otherwise list services and search for backend
    print("🔍 Fetching service list from Render API...")
    url = "https://api.render.com/v1/services?limit=100"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            services = json.loads(response.read().decode("utf-8"))
            print(f"🔍 Render API listed {len(services)} service(s) for this key.")
            candidates = []
            for item in services:
                svc = item.get("service", item)
                name = svc.get("name", "")
                svc_id = svc.get("id", "")
                if "supremeai" in name.lower() and "backend" in name.lower():
                    candidates.append((name, svc_id))
            if not candidates:
                # Observable discovery outcome — a silent zero here used to leave
                # only generic fallback noise in the CI log.
                print(
                    "⚠️ Discovery found NO service whose name contains both "
                    "'supremeai' and 'backend'. Visible services: "
                    + (
                        ", ".join(
                            f"{it.get('service', it).get('name', '?')} ({it.get('service', it).get('id', '?')})"
                            for it in services[:10]
                        )
                        or "none"
                    )
                )
            for name, svc_id in candidates:
                print(f"🎯 Discovered backend service: {name} ({svc_id})")
                if trigger_deploy_for_service(api_key, svc_id, image_url):
                    return True
    except Exception as e:
        print(f"⚠️ Could not list Render services: {e}")
    return False


def trigger_via_webhook(webhook_url: str) -> bool:
    if not webhook_url:
        return False
    print("🪝 Attempting deploy trigger via Render Deploy Webhook...")
    req = urllib.request.Request(
        webhook_url, method="POST", headers={"User-Agent": "SupremeAI-CI"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"✅ Webhook trigger accepted with HTTP {resp.getcode()}")
            return True
    except Exception as e:
        print(f"❌ Deploy Webhook failed: {e}")
        return False


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError as exc:
        # REL-002 (error observability): report the real reason, not a placeholder.
        print(f"stream reconfigure unsupported in this runtime: {exc}")

    primary_key = os.environ.get("RENDER_API_KEY", "").strip()
    # FIX (env-var mismatch): the sole caller (staging-deploy.yml) passes the
    # service ID as RENDER_SVC_ID, but this script only read PRIMARY_SVC_ID —
    # so the configured ID was ALWAYS ignored and the stale hardcoded fallback
    # below won, producing 'HTTP 404 … service not found' on every run.
    # Both names are now honored (additive; PRIMARY_SVC_ID contract preserved).
    primary_svc = (
        os.environ.get("RENDER_SVC_ID", "").strip()
        or os.environ.get("PRIMARY_SVC_ID", "").strip()
        or "srv-da07ogmgekts739amqa0"
    )
    deploy_hook = os.environ.get("RENDER_DEPLOY_HOOK_URL", "").strip()
    image_url = os.environ.get("IMAGE_URL", "").strip() or None

    if not primary_key and not deploy_hook:
        print(
            "⚠️ No Render credentials found (RENDER_API_KEY / RENDER_DEPLOY_HOOK_URL). Skipping deploy."
        )
        sys.exit(1)

    print("🚀 Triggering Render Deployment...")
    # 1. Try Primary API Key first
    if primary_key:
        print(f"🔑 Trying Primary Render API Key (Service: {primary_svc})...")
        if trigger_via_api(primary_key, primary_svc, image_url):
            print("🎉 Primary deployment initiated successfully!")
            sys.exit(0)
        else:
            print(
                "⚠️ Primary deployment failed or key quota exhausted. Falling back to Webhook..."
            )

    # 2. Fallback to Deploy Hook
    if deploy_hook:
        print("🔗 Triggering via Deploy Hook Webhook...")
        if trigger_via_webhook(deploy_hook):
            print("🎉 Deployment initiated successfully via webhook!")
            sys.exit(0)
        else:
            print("❌ Webhook trigger failed.")
    else:
        # Explain WHY the webhook fallback did not run — an empty URL used to
        # skip silently and left 'All deployment triggers failed' unexplained.
        print(
            "ℹ️ Webhook fallback not configured (RENDER_DEPLOY_HOOK_URL empty "
            "for this job) — skipped."
        )

    print("❌ All deployment triggers failed.")
    sys.exit(1)


if __name__ == "__main__":
    main()
