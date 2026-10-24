# বাংলা কমেন্ট: ফাইল আপলোড ভ্যালিডেশন লজিক — সাইজ + কনটেন্ট টাইপ + অ্যLLOWলিস্টিং

from fastapi import HTTPException, status

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {
    ".py": ["text/x-python", "application/octet-stream"],
    ".ts": ["text/typescript", "application/typescript", "application/octet-stream"],
    ".tsx": ["text/typescript", "application/octet-stream"],
    ".js": ["text/javascript", "application/javascript", "application/octet-stream"],
    ".jsx": ["text/javascript", "application/octet-stream"],
    ".dart": ["text/dart", "application/octet-stream"],
    ".java": ["text/x-java", "application/octet-stream"],
    ".go": ["text/x-go", "application/octet-stream"],
    ".rs": ["text/x-rust", "application/octet-stream"],
    ".png": ["image/png"],
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".gif": ["image/gif"],
    ".webp": ["image/webp"],
    ".mp3": ["audio/mpeg"],
    ".wav": ["audio/wav"],
    ".mp4": ["video/mp4"],
    ".pdf": ["application/pdf"],
    ".txt": ["text/plain"],
    ".json": ["application/json"],
}


class UploadValidationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)


async def validate_upload(file: object) -> None:
    file_obj = file
    filename = getattr(file_obj, "filename", "") or ""
    content_type = getattr(file_obj, "content_type", "") or ""
    ext = filename.lower().split(".")[-1]
    if not ext or "." not in filename:
        raise UploadValidationError("Unsupported file type.")
    ext = "." + ext
    allowed = ALLOWED_EXTENSIONS.get(ext)
    if not allowed:
        raise UploadValidationError(f"Extension '{ext}' is not allowed.")
    if content_type and content_type not in allowed:
        raise UploadValidationError(
            f"Content type '{content_type}' does not match allowed types for '{ext}'."
        )
    body = await file_obj.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload exceeds maximum allowed size of {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
        )
    await file_obj.seek(0)
