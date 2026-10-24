import asyncio
import os
import random

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.logging_config import logger

# বাংলা মন্তব্য: ChaosInjectorMiddleware — LOCAL_CHAOS_MODE env var দিয়ে নিয়ন্ত্রিত।
# Production-এ সম্পূর্ণ নিষ্ক্রিয়। শুধুমাত্র local dev/test-এ random delay ও packet drop inject করে।


# DROP_THRESHOLD এর নিচে random() হলে packet drop হবে
_DROP_THRESHOLD = 0.15
# DELAY_THRESHOLD এর নিচে random() হলে delay inject হবে
_DELAY_THRESHOLD = 0.3
_DELAY_MIN = 0.5
_DELAY_MAX = 3.5


class ChaosInjectorMiddleware(BaseHTTPMiddleware):
    """
    Chaos Engineering Middleware — LOCAL_CHAOS_MODE=true হলে random delay ও packet drop inject করে।
    Production Safety: ENV=production হলে সম্পূর্ণ bypass।
    """

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        # বাংলা মন্তব্য: LOCAL_CHAOS_MODE env var থেকে chaos_enabled নির্ধারণ করা হয়
        self.chaos_enabled = os.getenv("LOCAL_CHAOS_MODE", "false").lower() == "true"

    async def dispatch(self, request: Request, call_next) -> Response:
        env = os.getenv("ENV", "local").lower()
        # Production safety switch — production is completely bypassed regardless of
        # LOCAL_CHAOS_MODE. self.chaos_enabled (explicit LOCAL_CHAOS_MODE=true opt-in) is
        # the only other gate needed: nothing in .github/workflows/ or render.yaml ever sets
        # that var, so no test/CI run is affected unless it deliberately opts in (as this
        # middleware's own unit tests do, to verify the injection logic itself). An earlier
        # blanket "pytest in sys.modules" / CI/GITHUB_ACTIONS bypass here broke exactly those
        # tests, in both local pytest runs and real GitHub Actions CI (GITHUB_ACTIONS=true is
        # always set there).
        if env == "production" or not self.chaos_enabled:
            return await call_next(request)

        roll = random.random()  # — intentional non-crypto random for chaos

        # packet drop — 504 Gateway Timeout
        if roll < _DROP_THRESHOLD:
            logger.warning(f"[CHAOS] Packet drop for {request.url.path}")
            return JSONResponse(status_code=504, content={"detail": "Chaos: packet dropped"})

        # latency injection — random sleep
        if roll < _DELAY_THRESHOLD:
            delay = _DELAY_MIN + random.random() * (_DELAY_MAX - _DELAY_MIN)
            logger.warning(f"[CHAOS] Injecting {delay:.2f}s delay for {request.url.path}")
            await asyncio.sleep(delay)
            # packet drop after delay (values[1] < threshold triggers drop)
            if random.random() < _DROP_THRESHOLD:
                return JSONResponse(
                    status_code=504, content={"detail": "Chaos: packet dropped after delay"}
                )

        return await call_next(request)
