import os

from core.logging_config import logger

auth = None


def get_firebase_auth():
    global auth
    if auth is not None:
        return auth

    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth
        from firebase_admin import credentials as fb_credentials

        if not firebase_admin._apps:
            from core.config import settings

            _gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
            _sa_json = getattr(settings, "firebase_service_account_json", "")
            _sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or "service-account.json"

            if _sa_json:
                import json as _json

                _cred = fb_credentials.Certificate(_json.loads(_sa_json))
                firebase_admin.initialize_app(_cred)
                logger.info("Firebase Admin initialized from FIREBASE_SERVICE_ACCOUNT_JSON")
            elif _sa_path:
                _resolved_path = None
                for p in [
                    _sa_path,
                    os.path.join("backend", _sa_path),
                    os.path.join("..", _sa_path),
                ]:
                    clean_p = p.replace("backend/backend/", "backend/")
                    if not os.path.exists(clean_p) and clean_p.startswith("backend/"):
                        clean_p = clean_p[8:]
                    if os.path.exists(clean_p):
                        _resolved_path = clean_p
                        break

                if _resolved_path:
                    _cred = fb_credentials.Certificate(_resolved_path)
                    firebase_admin.initialize_app(_cred)
                    logger.info(f"Firebase Admin initialized from file: {_resolved_path}")
                elif _sa_path != "service-account.json":
                    logger.warning(f"Firebase service account file not found at {_sa_path}")
                    raise RuntimeError(f"Service account file not found: {_sa_path}")
                elif _gac and os.path.exists(_gac):
                    firebase_admin.initialize_app()
                    logger.info("Firebase Admin initialized via GOOGLE_APPLICATION_CREDENTIALS")
                else:
                    logger.warning("Firebase Admin SDK: No credentials found.")
                    raise RuntimeError("No Firebase credentials configured")
            elif _gac and os.path.exists(_gac):
                firebase_admin.initialize_app()
                logger.info("Firebase Admin initialized via GOOGLE_APPLICATION_CREDENTIALS")
            else:
                logger.warning(
                    "Firebase Admin SDK: No credentials found. Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH in .env"
                )
                raise RuntimeError("No Firebase credentials configured")
        auth = firebase_auth
        logger.info("Firebase Admin SDK ready ✅")
        return auth
    except Exception as e:
        logger.warning(f"Firebase Admin SDK not available: {e}")
        return None
