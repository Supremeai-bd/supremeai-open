# বাংলা মন্তব্য: core.idempotency_middleware কে middleware প্যাকেজে সরানো হয়েছে;
# এখান থেকে সরাসরি re-export করে unified idempotency module তৈরি করা হলো।
from .idempotency_middleware import IdempotencyMiddleware

__all__ = ["IdempotencyMiddleware"]
