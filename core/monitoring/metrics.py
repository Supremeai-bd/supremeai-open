"""SupremeAI 2.0 — Custom core metrics.

বাংলা মন্তব্য: প্রজেক্টের পারফরম্যান্স ও এপিআই কল ট্র্যাকিংয়ের জন্য
কোর মেট্রিক্স এবং ডেকোরেটরসমূহ (যেমন counter ও timed)।
"""

import functools
import inspect
from collections.abc import Callable
from typing import Any

from core.logging_config import logger


def counter(name: str) -> Callable[..., Any]:
    """Decorator to count method executions.

    বাংলা মন্তব্য: যেকোনো ফাংশন কলের কাউন্টার মেট্রিক্স ট্র্যাক করার ডেকোরেটর।
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                logger.debug(f"Metrics: Counter incremented for {name}")
                return await func(*args, **kwargs)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                logger.debug(f"Metrics: Counter incremented for {name}")
                return func(*args, **kwargs)

            return sync_wrapper

    return decorator


def timed(name: str) -> Callable[..., Any]:
    """Decorator to measure method latency.

    বাংলা মন্তব্য: যেকোনো ফাংশন কলের লেটেন্সি বা টাইম পরিমাপের ডেকোরেটর।
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                import time

                start = time.perf_counter()
                res = await func(*args, **kwargs)
                logger.debug(
                    f"Metrics: Timed {name} took {(time.perf_counter() - start) * 1000:.2f}ms"
                )
                return res

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                import time

                start = time.perf_counter()
                res = func(*args, **kwargs)
                logger.debug(
                    f"Metrics: Timed {name} took {(time.perf_counter() - start) * 1000:.2f}ms"
                )
                return res

            return sync_wrapper

    return decorator
