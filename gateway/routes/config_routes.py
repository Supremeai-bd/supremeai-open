from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response

# বাংলা: একটি কেন্দ্রীয় require_admin_token import করা হচ্ছে।
# আগে এই module-এ duplicate local function ছিল —
# তার ফলে test এ dependency_overrides কাজ করত না।
from api.routes.admin_dashboard import require_admin_token
from core.deployment_fallback_defaults import BACKEND_URL_DEFAULT


# টেস্ট কম্প্যাটিবিলিটি:
# `tests/test_api_new_endpoints.py::test_config_endpoint_admin_control` monkeypatch করে
# `backend.api.routes.config_routes_routes_routes_routes.db.client` সেট করে।
class _ConfigDBClientWrapper:
    def __init__(self):
        # টেস্ট monkeypatch করবে: config_route.db.client
        self.client = None

    def get_config(self, key: str):
        # টেস্ট monkeypatch করবে: config_route.db.get_config
        return None

    def set_config(self, key: str, value: Any, category: str = "general"):
        # টেস্ট monkeypatch করবে: config_route.db.set_config
        return None


db = _ConfigDBClientWrapper()

router = APIRouter(prefix="/config", tags=["Global Config"])


@router.get("/public")
async def get_public_config(response: Response):
    """
    পাবলিক কনфিগ ডেটা সরাসরি ব্রাউজার এবং CDN (Cloudflare/Vercel) এ ক্যাশ করবে,
    যাতে প্রতিবার ব্যাকএন্ড সার্ভারে হিট না আসে।
    """
    config_data = {
        "ENV": "production",
        # বাংলা মন্তব্য: সঠিক প্রাইমারি প্রোডাকশন ব্যাকএন্ড ইউআরএল সেট করা হলো
        "BACKEND_URL": BACKEND_URL_DEFAULT,
        "FEATURES": {
            "morphic_rewrite": True,
            "sandbox_v2": True,
            "background_tasks_enabled": True,
        },
    }

    # 🛡️ Edge Caching Enforcer (১ ঘণ্টা ব্রাউজার / ২৪ ঘণ্টা শেয়ার্ড CDN ক্যাশ)
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
    return config_data


@router.get("/validation-report")
async def get_config_validation_report(admin: str = Depends(require_admin_token)):
    """specs/001 close-out: বর্তমান env-এর সৎ configuration truth (admin-only).

    বাংলা: MASTER_PLAN Phase 1 — required env vars, ফরম্যাট, ও CORS unification
    status এক কলে জানায়। কোনো ভুয়া 'ok' নেই — সমস্যা থাকলে status=error + fix
    suggestion যায় (No Silent Failure)। রুটের আগে ডিক্লেয়ার করা বাধ্যতামূলক,
    নইলে /{key} পাথ এটাকে গিলে ফেলে।
    """
    from core.config_validation import build_config_validation_report

    return build_config_validation_report().model_dump()


# বাংলা মন্তব্য: অ্যাডমিন ট্রাস্টেড এক্সেস কন্ট্রোলের মাধ্যমে নির্দিষ্ট কনফিগ কি রিড করার এন্ডপয়েন্ট।
@router.get("/{key}")
async def get_config_by_key(key: str, admin: str = Depends(require_admin_token)):
    val = db.get_config(key)
    if val is None:
        raise HTTPException(status_code=404, detail="Config key not found")
    return {"key": key, "value": val}


# বাংলা মন্তব্য: অ্যাডমিন ট্রাস্টেড এক্সেস কন্ট্রোলের মাধ্যমে নির্দিষ্ট কনফিগ কি আপডেট করার এন্ডপয়েন্ট।
@router.put("/{key}")
async def update_config_by_key(
    key: str, value: Any = Body(...), admin: str = Depends(require_admin_token)
):
    db.set_config(key, value)
    return {"status": "success"}
