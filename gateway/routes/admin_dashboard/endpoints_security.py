"""Security-scan endpoints
(GET/POST /admin-api/security-scan, GET /admin-api/security-scan/findings)."""

import os

from api.routes.admin_dashboard import router
from core.config import settings
from core.logging_config import logger
from core.utils.time_utils import utc_now


# CI FIX: frontend hooks.ts:376 calls POST /admin-api/security-scan.
# Added POST alias (same handler as GET).
@router.get("/security-scan")
@router.post("/security-scan")
def run_security_scan():
    findings = []
    try:
        # Configuration Drift Filter: never compare against a literal secret
        # value in source (that value itself becomes a leaked credential the
        # moment it's committed). Use structural checks instead — the same
        # ones already enforced by Settings.validate_jwt_secret_strength.
        _jwt_secret = settings.jwt_secret or ""
        _weak_secrets = {
            "secret",
            "password",
            "123456",
            "changeme",
            "admin",
            "jwt_secret",
        }
        if not _jwt_secret or len(_jwt_secret) < 64 or _jwt_secret.lower() in _weak_secrets:
            findings.append(
                {
                    "item": "jwt_secret",
                    "severity": "critical",
                    "message": "JWT secret is missing, too short (<64 bytes entropy), or a known-weak value",
                }
            )
        if settings.debug:
            findings.append(
                {
                    "item": "debug_mode",
                    "severity": "medium",
                    "message": "Application is running in debug mode",
                }
            )
        if not os.path.exists(".env"):
            findings.append(
                {
                    "item": "env_file",
                    "severity": "low",
                    "message": ".env file not found",
                }
            )
    except Exception as e:
        logger.error(f"Security scan failed: {e}")
        return {"status": "error", "detail": str(e)}
    return {
        "status": "success",
        "scan_time": utc_now().isoformat(),
        "findings": findings,
        "total_findings": len(findings),
    }


@router.get("/security-scan/findings")
def get_security_findings():
    """Return array of security findings for CommandCenter Threats module."""
    scan = run_security_scan()
    raw_findings = scan.get("findings", [])
    # Format to match frontend SecurityFinding { id, severity, title, description }
    formatted = []
    for idx, f in enumerate(raw_findings):
        formatted.append(
            {
                "id": f"finding-{idx + 1}",
                "severity": f.get("severity", "low"),
                "title": f.get("item", "Security Finding"),
                "description": f.get("message", "Security scan warning"),
            }
        )
    return formatted
