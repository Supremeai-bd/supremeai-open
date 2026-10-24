from __future__ import annotations

# বাংলা মন্তব্য: নন-ব্লকিং অপারেশনের জন্য asyncio এবং redis.asyncio ইম্পোর্ট করা হলো
import base64
import json

from fastapi.responses import JSONResponse

from core.config import settings
from core.logging_config import logger

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

# শেয়ার্ড ইউটিলিটি — টেস্ট এনভায়রনমেন্ট চেক কেন্দ্রীভূত
from utils.environment import is_test_environment


class IdempotencyMiddleware:
    def __init__(self, app) -> None:
        self.app = app
        self._redis_client = None

    async def _get_redis(self):
        """
        বাংলা মন্তব্য: শেয়ার্ড অ্যাসিঙ্ক্রোনাস Redis ক্লায়েন্ট (redis_manager) ব্যবহার করা হচ্ছে।
        """
        from core.cache.redis_manager import redis_manager

        return getattr(redis_manager, "client", None)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # রিফ্যাক্টর: লোকাল is_test চেকের বদলে শেয়ার্ড ইউটিলিটি ব্যবহার
        if is_test_environment():
            await self.app(scope, receive, send)
            return

        # Only check idempotency for modifying operations
        method = scope.get("method")
        if method not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        idempotency_key = None
        for k, v in headers:
            if k.lower() == b"idempotency-key":
                idempotency_key = v.decode("utf-8")
                break

        path = scope.get("path", "")
        # For critical mutating endpoints, enforce the presence of the key.
        if not idempotency_key:
            # P1 Security Fix: Enforce idempotency key for critical mutating endpoints
            # This prevents accidental duplicate task executions or billing events.
            if any(p in path for p in settings.idempotency_critical_paths):
                logger.warning(
                    f"Rejected request to '{path}' due to missing Idempotency-Key header."
                )
                response = JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Idempotency-Key header is required for this endpoint to prevent duplicate operations."
                    },
                )
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        redis = await self._get_redis()
        if not redis:
            await self.app(scope, receive, send)
            return

        # AUD-3.7 (P1): the idempotency namespace is now scoped per caller
        # credential. Previously the key space was global — user B replaying
        # user A's Idempotency-Key would receive A's cached response. This
        # middleware sits OUTSIDE AuthMiddleware in the ASGI stack, so the
        # identity is derived from the raw credential (hashed — never stored
        # in plaintext) instead of request.state.user.
        import hashlib

        credential = b""
        for k, v in headers:
            if k.lower() in (b"authorization", b"x-api-key"):
                credential = v
                break
        caller_scope = hashlib.sha256(credential).hexdigest()[:16] if credential else "anon"
        redis_key = f"idempotency:{caller_scope}:{idempotency_key}"

        # 1. Check if the request key exists in Redis
        existing = await redis.get(redis_key)
        if existing:
            try:
                data = json.loads(existing)
                if data.get("status") == "processing":
                    response = JSONResponse(
                        status_code=409,
                        content={
                            "detail": "Conflict: Request is already being processed. Please wait."
                        },
                    )
                    await response(scope, receive, send)
                    return
                elif data.get("status") == "completed":
                    # Replay the cached response
                    from starlette.responses import Response

                    body = data.get("body")
                    if isinstance(body, dict):
                        response = JSONResponse(content=body, status_code=data.get("status_code"))
                    else:
                        response = Response(
                            # বাংলা মন্তব্য: বাইনারি ডেটা হ্যান্ডেল করার জন্য Base64 ডিকোড করা হচ্ছে
                            content=base64.b64decode(body),
                            status_code=data.get("status_code"),
                            media_type=data.get("media_type"),
                        )
                    await response(scope, receive, send)
                    return
            except (json.JSONDecodeError, TypeError) as exc:
                # বল মনতবয: কযশকরত idempotency রকরড পরস করত বযরথ হল রকয়সট পনরায় পরসস হব;
                # নরবভ ডট করাপশন লকয় রখত warning লগ যকত কর হল
                logger.warning(
                    f"Could not parse cached idempotency record for key '{idempotency_key}': {exc}. Reprocessing request."
                )

        # 2. অ্যাটমিকভাবে idempotency key লক করা (Race Condition প্রতিরোধ)
        # `nx=True` নিশ্চিত করে যে শুধুমাত্র যদি key-টি আগে থেকে না থাকে, তবেই এটি সেট হবে।
        # এটি `get` এবং `set` এর মধ্যে অন্য রিকোয়েস্ট আসার সুযোগ বন্ধ করে দেয়।
        is_locked = await redis.set(
            redis_key, json.dumps({"status": "processing"}), ex=600, nx=True
        )
        if not is_locked:
            # যদি অন্য কোনো থ্রেড এইমাত্র কী-টি লক করে ফেলে, তবে কনফ্লিক্ট রেসপন্স পাঠানো হবে
            response = JSONResponse(
                status_code=409,
                content={"detail": "Conflict: Request is already being processed."},
            )
            await response(scope, receive, send)
            return

        # 3. Call the next request handler and capture response
        response_body_bytes = b""
        response_headers = []
        response_status = 200

        async def custom_send(message):
            nonlocal response_body_bytes, response_headers, response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response_body_bytes += message.get("body", b"")
            await send(message)

        try:
            await self.app(scope, receive, custom_send)

            # Get media_type from response headers if possible
            media_type = "application/json"
            for k, v in response_headers:
                if k.lower() == b"content-type":
                    media_type = v.decode("utf-8")
                    break

            # বাংলা মন্তব্য: রেসপন্স বডি JSON নাকি বাইনারি তা নির্ধারণ করা
            try:
                # যদি JSON হয়, তাহলে সরাসরি সেইভ করা হবে
                body_to_cache = json.loads(response_body_bytes)
            except json.JSONDecodeError:
                # যদি JSON না হয় (যেমন ছবি বা ফাইল), তাহলে Base64 এনকোড করে সেইভ করা হবে
                body_to_cache = base64.b64encode(response_body_bytes).decode("utf-8")

            # সম্পন্ন হওয়া রেসপন্সটি Redis-এ ২৪ ঘণ্টার জন্য ক্যাশ করা হচ্ছে
            await redis.set(
                redis_key,
                json.dumps(
                    {
                        "status": "completed",
                        "status_code": response_status,
                        "media_type": media_type,
                        "body": body_to_cache,
                    }
                ),
                ex=86400,
            )
        except (
            Exception
        ):  # বাংলা মন্তব্য: কোনো কারণে রিকোয়েস্ট ফেইল হলে কী-টি মুছে ফেলা হবে, যাতে ক্লায়েন্ট আবার চেষ্টা করতে পারে
            try:
                await redis.delete(redis_key)
            except Exception as exc:
                logger.exception(f"Failed to delete idempotency key {redis_key}: {exc}")
            raise
