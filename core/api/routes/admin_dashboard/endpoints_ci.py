"""CI/CD report ingestion + log endpoints (GET /admin-api/ci-logs, POST /admin-api/ci-report)."""

from fastapi import HTTPException, Request

from api.routes.admin_dashboard import router
from core.logging_config import logger
from models.ci_report import CIReportPayload, create_ci_report


@router.get("/ci-logs")
async def get_ci_logs(limit: int = 20):
    # বাংলা মন্তব্য: ড্যাশবোর্ডে CI/CD পাইপলাইনের সাম্প্রতিক রিপোর্টগুলো দেখানোর জন্য এন্ডপয়েন্ট
    from models.ci_report import get_recent_ci_reports

    try:
        reports = await get_recent_ci_reports(limit)
        return reports
    except Exception as e:
        logger.error(f"❌ Failed to fetch CI logs: {e!s}")
        raise HTTPException(status_code=500, detail=f"Database query failure: {e!s}") from e


@router.post("/ci-report")
async def receive_ci_report(report: CIReportPayload, request: Request):
    """
    Receives and stores a structured CI/CD report from a GitHub Actions workflow.
    This endpoint is protected by a constitutional rule.
    """
    # Constitutional Gatekeeper for this endpoint
    from core import services

    if not services.god.get_rule("autofix_reporting_authorized", "false") == "true":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: CI/CD reporting is disabled by constitutional rule.",
        )

    # Optional: Verify the request is coming from GitHub Actions
    # This could be improved with a shared secret or webhook signature validation
    if "github.com" not in request.headers.get(
        "host", ""
    ) and "localhost" not in request.headers.get("host", ""):
        logger.warning(f"CI Report received from non-GitHub host: {request.headers.get('host')}")

    try:
        # বাংলা মন্তব্য: নতুন CI রিপোর্ট ডাটাবেসে ইনসার্ট বা আপডেট করা হচ্ছে
        res = await create_ci_report(report)
        report_id = res.get("id") if res else None
        logger.info(f"Successfully saved CI report with ID: {report_id}")
        return {"status": "success", "report_id": report_id}
    except Exception as e:
        logger.error(f"❌ Failed to save CI report: {e!s}")
        raise HTTPException(status_code=500, detail=f"Failed to save CI report: {e!s}") from e
