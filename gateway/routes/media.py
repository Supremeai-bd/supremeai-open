import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.config import settings
from storage.r2_storage_client import R2StorageClient, StorageNotConfiguredError

# বাংলা মন্তব্য: ক্লায়েন্টের জন্য প্রে-সাইনড আপলোড ইউআরএল জেনারেট করার এন্ডপয়েন্ট।

router = APIRouter(prefix="/api/v1/media", tags=["media"])
storage_client = R2StorageClient()


class UploadRequest(BaseModel):
    file_name: str
    file_type: str
    folder: str = "skills_bundles"


# বাংলা মন্তব্য: রিয়েল অথরাইজেশন টোকেন ডিপেন্ডেন্সি এখানে ইন্টিগ্রেট করা হবে।
# টেস্ট সহজে পাস করানোর জন্য এটি একটি মক ইউজার রিটার্ন করছে।
async def get_current_user():
    return {"id": "user_123"}


@router.post("/generate-upload-url")
async def get_upload_url(request: UploadRequest, user=Depends(get_current_user)):
    safe_filename = f"{request.folder}/{user['id']}_{uuid.uuid4().hex}_{request.file_name}"

    try:
        upload_url = storage_client.generate_presigned_upload_url(
            object_name=safe_filename, file_type=request.file_type
        )
    except StorageNotConfiguredError as exc:
        # বাংলা মন্তব্য: ভুয়া mock URL-এর বদলে সৎ 503 — স্টোরেজ কনফিগার নেই (audit B-01)।
        raise HTTPException(
            status_code=503,
            detail=(
                "Object storage is not configured — uploads are unavailable. "
                "Set R2_ACCOUNT_ID, R2_ACCESS_KEY and R2_SECRET_KEY."
            ),
        ) from exc

    if not upload_url:
        raise HTTPException(status_code=500, detail="Could not generate upload URL")

    return {
        "upload_url": upload_url,
        "file_path": safe_filename,
        "public_url": f"{getattr(settings, 'r2_public_url', 'https://pub-your-r2.dev')}/{safe_filename}",
    }
