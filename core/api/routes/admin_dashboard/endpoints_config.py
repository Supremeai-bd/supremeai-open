"""Environment/config endpoints + env-etag / env-lock helpers
(GET/POST /admin-api/config).

``get_env_etag`` / ``_acquire_env_lock`` / ``_release_env_lock`` register no
routes; they are kept (and re-exported from the package) because the
test-suite imports them from ``api.routes.admin_dashboard``."""

import hashlib
import os

from api.routes.admin_dashboard import router
from api.routes.admin_dashboard.endpoints_crud import _load_json_data, _save_json_data
from core.errors.error_bus import with_error_bus
from core.logging_config import logger


def get_env_etag(redis_key: str = "config:env_etag") -> str:
    import core.services as app_mod

    redis_queue = getattr(app_mod, "redis_queue", None)
    if redis_queue and getattr(redis_queue, "configured", False):
        cached = redis_queue.get(redis_key)
        if cached:
            return cached
    if os.path.exists(".env"):
        try:
            with open(".env", "rb") as f:
                etag = hashlib.md5(f.read(), usedforsecurity=False).hexdigest()  # nosec B324
            if redis_queue and getattr(redis_queue, "configured", False):
                redis_queue.set(redis_key, etag, ex=300)
            return etag
        except Exception as exc:
            # বল মনতবয: .env এর etag গণনা বযর্থ হল "empty-env" ফলবযাক হয়;
            # নরব সযলপ ন কর ডবগ লগ কর হল
            logger.debug(f"Failed to compute .env etag: {exc}")
    return "empty-env"


# বাংলা মন্তব্য: মাল্টি-ইনস্ট্যা�����্স রেস কন্ডিশন এড়ানোর জন্য রেডিস-ব্যাকড লক ও ফাইল-লকের ফিজিবল কম্বিনেশন
@with_error_bus("_acquire_env_lock")
def _acquire_env_lock(lock_path: str = ".env.lock") -> bool:
    import core.services as app_mod

    redis_queue = getattr(app_mod, "redis_queue", None)
    if redis_queue and getattr(redis_queue, "configured", False):
        try:
            return redis_queue.set_nx("lock:env_write", "locked", ex=10)
        except Exception as exc:
            # বল মনতবয: রডস লক বযর্থ হল ফাইল-লক ফলবযাক বযবহত হয়;
            # নরব সযলপ ন কর ডবগ লগ কর হল
            logger.debug(f"Redis env lock acquisition failed, falling back to file lock: {exc}")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:
        logger.exception("Unhandled exception")
        return False


def _release_env_lock(lock_path: str = ".env.lock"):
    import core.services as app_mod

    redis_queue = getattr(app_mod, "redis_queue", None)
    if redis_queue and getattr(redis_queue, "configured", False):
        try:
            redis_queue._request("DEL", "lock:env_write")
        except Exception as exc:
            logger.exception(f"Lock release via redis failed: {exc}")
    try:
        os.remove(lock_path)
    except Exception as exc:
        logger.exception(f"Lock file removal failed for {lock_path}: {exc}")


# বাংলা মন্তব্ত: AUDIT-018 ফিক্স — Studio Client-এর useAdminApi.ts এবং
# AdminShell.tsx-এর /admin-api/config কল এখন ব্যাকএন্ডে আছে (আগে 404 পেত)।
@router.get("/config")
def get_config():
    """Get environment configuration for the admin dashboard."""
    import os

    config = {}
    for key in ["ENV", "DEBUG", "LOG_LEVEL", "REDIS_URL", "DATABASE_URL"]:
        val = os.environ.get(key, "")
        if val:
            config[key] = val
    return config


@router.post("/config")
def update_config(payload: dict):
    """Update environment configuration (writes to settings.json)."""
    import os

    # বাংলা মন্তব্য: প্যাকেজ স্প্লিটের পর __file__ এক লেভেল গভীরে (admin_dashboard/ ডিরেক্টরিতে),
    # তাই traversal-এ একটি বাড়তি ".." যোগ করা হয়েছে — resolved path আগের মতোই
    # <backend>/data/settings.json (আগের single-file মডিউলের সাথে আচরণে সমতুল্য)।

    config = _load_json_data(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "settings.json"), {}
    )
    config.update(payload)
    _save_json_data(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "settings.json"), config
    )
    return {"status": "success", "message": "Configuration updated"}
