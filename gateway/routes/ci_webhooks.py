import hmac

from fastapi import APIRouter, Header, HTTPException

from core.config import settings
from models.ci_report import CIReportPayload, create_ci_report

router = APIRouter(prefix="/api/ci", tags=["ci"])


@router.post("/webhook")
async def ci_webhook(
    payload: CIReportPayload,
    x_ci_webhook_secret: str = Header(..., alias="X-CI-Webhook-Secret"),
):
    # বাংলা মন্তব্য: সিক্রেট কি ভ্যালিডেশন করে সিআই রিপোর্ট ডাটাবেসে স্টোর করার জন্য ওয়েবহুক এন্ডপয়েন্ট
    # বাংলা মন্তব্য: কনফিগারেশন সেটিংস থেকে ci_webhook_secret নিয়ে হেডার ভ্যালুর সাথে তুলনা করা হচ্ছে
    if not settings.ci_webhook_secret:
        raise HTTPException(status_code=500, detail="CI Webhook Secret not configured on server")

    if not hmac.compare_digest(x_ci_webhook_secret, settings.ci_webhook_secret):
        raise HTTPException(status_code=401, detail="Unauthorized webhook request")

    report = await create_ci_report(payload)
    if not report:
        raise HTTPException(status_code=500, detail="Failed to store CI report")
    return {"status": "success", "report_id": report["id"]}
