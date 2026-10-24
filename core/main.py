"""SupremeAI 2.0 — Entry point. Handles ENV bootstrap, signal handling, and Uvicorn launch.

বাংলা: রুট এন্ট্রি পয়েন্ট। ENV সেটআপ, সিগন্যাল হ্যান্ডলিং এবং সার্ভার লঞ্চ।
Trigger backend CI pipeline via push!
"""

import os
import signal
import sys
from typing import Any

if not os.getenv("ENV"):
    if os.getenv("RENDER"):
        os.environ["ENV"] = "production"
    else:
        os.environ["ENV"] = os.getenv("SUPREMEAI_DEFAULT_ENV", "local")

print(f">>> SUPREMEAI BOOTSTRAP STARTING (ENV={os.getenv('ENV')}) <<<", flush=True)

# Initialize global silent catcher before any other imports that might spawn threads
from core.intelligent_silent_catcher import setup_silent_catcher

setup_silent_catcher()

# ----------------- SUPERAI ENV VALIDATION -----------------
# বাংলা মন্তব্য: Pydantic Settings এখন Single Source of Truth এবং এটি
# Infisical থেকে ডায়নামিকালি ডেটা ফেচ করে validate করে (Fail-Fast)।
# আগের `EnvironmentValidator` শুধু `os.environ` চেক করতো, যা Infisical-এর সাথে
# কাজ করে না এবং প্রোডাকশনে সার্ভার ক্র্যাশ করায়। তাই এটি রিমুভ করা হলো।
# ----------------------------------------------------------


import uvicorn

from core.logging_config import logger

# বাংলা মন্তব্য: টেস্ট এনভায়রনমেন্টে সম্পূর্ণ অ্যাপ এবং প্রোডাকশনে রোল অনুযায়ী ইউজার/অ্যাডমিন এন্ট্রি পয়েন্ট লোড করা হচ্ছে
# বাংলা: _APP_IMPORT_STRING ট্র্যাক করা হয় যাতে uvicorn.run()-এ app object-এর বদলে
# import string পাস করা যায় — reload=True বা workers>1 উভয় ক্ষেত্রেই সঠিকভাবে কাজ করে।
if "pytest" in sys.modules:
    _APP_IMPORT_STRING = "core.app:app"
else:
    _APP_IMPORT_STRING = "core.app:app"

# বাংলা মন্তব্য (ROOT-CAUSE FIX): আগে এখানে `from core.app import app` করে মডিউল-লেভেলে
# সম্পূর্ণ (all-routers) অ্যাপ তৈরি হতো।
# এখন `app` লেজি `__getattr__`-এর মাধ্যমে দেওয়া হয়: শুধু যারা সত্যিই
# `from main import app` করে (schema_exporter, generate_openapi, legacy tests)
# তারাই full app তৈরি করবে; সার্ভার বুট পথে এটি আর তৈরি হবে না।
__all__ = ["app"]  # noqa: F822 — `app` মডিউল-লেভেল __getattr__ (নিচে) দিয়ে lazily দেওয়া হয়, ruff static analysis এটা বুঝতে পারে না


def __getattr__(name: str) -> Any:
    """Lazy re-export of `core.app:app` for backward compatibility.

    বাংলা: `from main import app` আগের মতোই কাজ করবে, কিন্তু সার্ভার বুটের সময়
    অপ্রয়োজনীয়ভাবে দ্বিতীয় অ্যাপ ইনস্ট্যান্স তৈরি হবে না।
    """
    if name == "app":
        from core.app import app as _app

        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


from core.config import settings
from core.logging_config import setup_logging

print(">>> CONFIG AND LOGGING LOADED <<<", flush=True)

setup_logging()

print(">>> LOGGING SETUP COMPLETE <<<", flush=True)


def _handle_sigterm(signum: int, frame: object) -> None:
    """SIGTERM/SIGINT handler.

    SupremeAI FastAPI shutdown is handled by Uvicorn + `lifespan.app_lifespan`.
    This handler must NOT force `sys.exit()` because that can bypass lifespan teardown.
    """
    logger.info(
        f"🚨 Signal received ({signum}). Initiating graceful shutdown via Uvicorn/FastAPI lifespan..."
    )
    # Best-effort observability: let operators know shutdown intent was triggered.
    os.environ["UVICORN_SHUTDOWN_REQUESTED"] = "1"
    # Do not block here; return control to Uvicorn so it can run shutdown hooks.
    return


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


def run_server() -> None:
    """Boot the Uvicorn server with config-driven settings.

    বাংলা: কনফিগ-ড্রিভেন সেটিংস দিয়ে Uvicorn সার্ভার বুট।
    """
    # বাংলা: আগে শুধু settings.env == "local" চেক করা হতো — "dev"/"development"
    # এনভ ব্যবহার করলে reload চালু হতো না। Settings.is_local() তিনটাই ধরে।
    is_local = settings.is_local()
    port = int(os.getenv("PORT", str(settings.port)))
    host = os.getenv("HOST") or (
        "0.0.0.0" if os.getenv("RENDER") or os.getenv("PORT") or not is_local else settings.host
    )
    uvicorn_kwargs: dict = {
        "host": host,
        "port": port,
        "log_level": os.getenv("UVICORN_LOG_LEVEL", "info"),
        "access_log": os.getenv("UVICORN_ACCESS_LOG", "true").lower() == "true",
        "timeout_keep_alive": int(os.getenv("UVICORN_KEEP_ALIVE_TIMEOUT") or "30"),
    }
    if is_local:
        uvicorn_kwargs["reload"] = True
    else:
        uvicorn_kwargs["reload"] = False
        # REVISION 2: Enforce 1 worker in production for 512MB RAM constraint
        workers = int(os.getenv("UVICORN_WORKERS") or "1")
        if workers > 1:
            logger.critical(
                f"Startup failed: UVICORN_WORKERS is set to {workers}, but exactly 1 worker is allowed in production to prevent OOM!"
            )
            sys.exit(1)
        uvicorn_kwargs["workers"] = 1

    try:
        # বাংলা: আগে app object সরাসরি পাস হতো — reload=True বা workers>1 হলে uvicorn
        # 'must pass import string' ওয়ার্নিং দিত এবং port bind না করেই exit হতো (status 3)।
        # import string ব্যবহারে reload ও multi-worker দুটো ক্ষেত্রেই নির্ভরযোগ্যভাবে কাজ করে।
        uvicorn.run(_APP_IMPORT_STRING, **uvicorn_kwargs)
    except RuntimeError as exc:
        logger.critical(f"Server failed to start (configuration error): {exc}")
        if settings.sentry_dsn:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
            except Exception as sentry_exc:
                logger.warning(f"Failed to report error to Sentry: {sentry_exc}")
        sys.exit(1)
    except OSError as exc:
        logger.critical(
            f"Server failed to start (port/bind error on {settings.host}:{port}): {exc}"
        )
        if settings.sentry_dsn:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
            except Exception as sentry_exc:
                logger.warning(f"Failed to report error to Sentry: {sentry_exc}")
        sys.exit(1)
    except BaseException as exc:
        logger.critical(f"Server exited unexpectedly: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_server()
# Testing GitHub Actions -> GHCR -> Render Deploy trigger timing
