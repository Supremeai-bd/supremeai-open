from __future__ import annotations

import asyncio
import functools
import random
import time
from collections.abc import Callable
from typing import Any

from core.logging_config import logger


def retry_handler(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    use_jitter: bool = True,
    on_retry_callback: Callable[[int, Exception], None] | None = None,
    on_max_retries_callback: Callable[[Exception], None] | None = None,
):
    """
    বাংলা মন্তব্য: এক্সপোনেনশিয়াল ব্যাকঅফ এবং জিটার সহ রিট্রাই হ্যান্ডলার ডেকোরেটর।

    Args:
        max_retries: সর্বাধিক রিট্রাই চেষ্টার সংখ্যা
        delay: প্রাথমিক বিলম্বের সময় (সেকেন্ড)
        backoff: ব্যাকঅফ গুণক (প্রতিটি রিট্রাইতে বিলম্ব বৃদ্ধি হবে)
        exceptions: রিট্রাইয়ের জন্য ধরন (শুধুমাত্র এই ধরনের এক্সেপশনগুলির জন্য রিট্রাই হবে)
        use_jitter: জিটার ব্যবহার করবে কিনা (থান্ডারিং হার্ড প্রতিরোধে সাহায্য করে)
        on_retry_callback: প্রতিটি রিট্রাই পরে কল হবে এমন ফাংশন
        on_max_retries_callback: সর্বাধিক রিট্রাই শেষে কল হবে এমন ফাংশন
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"রিট্রাই সম্পূর্ণ ব্যর্থ ({max_retries + 1} টি চেষ্টা): "
                            f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}"
                        )
                        if on_max_retries_callback:
                            on_max_retries_callback(e)
                        break

                    # Calculate delay with exponential backoff
                    current_delay = delay * (backoff**attempt)

                    # Add jitter if enabled
                    if use_jitter:
                        jitter = random.uniform(0.1, 0.3) * current_delay
                        current_delay += jitter

                    logger.warning(
                        f"রিট্রাই চলছে ({attempt + 1}/{max_retries + 1}): "
                        f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}. "
                        f"বিলম্ব করা হবে {current_delay:.2f} সেকেন্ড"
                    )

                    if on_retry_callback:
                        on_retry_callback(attempt + 1, e)

                    await asyncio.sleep(current_delay)

            if last_exception:
                raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"রিট্রাই সম্পূর্ণ ব্যর্থ ({max_retries + 1} টি চেষ্টা): "
                            f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}"
                        )
                        if on_max_retries_callback:
                            on_max_retries_callback(e)
                        break

                    # Calculate delay with exponential backoff
                    current_delay = delay * (backoff**attempt)

                    # Add jitter if enabled
                    if use_jitter:
                        jitter = random.uniform(0.1, 0.3) * current_delay
                        current_delay += jitter

                    logger.warning(
                        f"রিট্রাই চলছে ({attempt + 1}/{max_retries + 1}): "
                        f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}. "
                        f"বিলম্ব করা হবে {current_delay:.2f} সেকেন্ড"
                    )

                    if on_retry_callback:
                        on_retry_callback(attempt + 1, e)

                    # DEEP-003 NOTE: This is the *sync* wrapper. When called from
                    # inside a running event loop, any blocking sleep stalls the
                    # loop — the old ThreadPoolExecutor workaround still blocked
                    # the calling thread via .result(). Callers inside async
                    # contexts must use the async wrapper instead (async paths
                    # correctly use await asyncio.sleep above).
                    time.sleep(current_delay)

            if last_exception:
                raise last_exception

        # Return appropriate wrapper based on whether the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def retry_with_budget(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    use_jitter: bool = True,
):
    """
    বাংলা মন্তব্য: রিট্রাই বাজেট সিস্টেম সহ রিট্রাই হ্যান্ডলার ডেকোরেটর।

    Args:
        max_retries: সর্বাধিক রিট্রাই চেষ্টার সংখ্যা
        delay: প্রাথমিক বিলম্বের সময় (সেকেন্ড)
        backoff: ব্যাকঅফ গুণক (প্রতিটি রিট্রাইতে বিলম্ব বৃদ্ধি হবে)
        exceptions: রিট্রাইয়ের জন্য ধরন (শুধুমাত্র এই ধরনের এক্সেপশনগুলির জন্য রিট্রাই হবে)
        use_jitter: জিটার ব্যবহার করবে কিনা (থান্ডারিং হার্ড প্রতিরোধে সাহায্য করে)
    """
    from .retry_budget import global_retry_budget

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                # Check if we have budget for a retry
                if attempt > 0:  # First attempt doesn't require budget
                    has_budget = await global_retry_budget.consume()
                    if not has_budget:
                        logger.warning(
                            f"রিট্রাই বাজেট শেষ: ফাংশন '{func.__name__}' এর জন্য আর রিট্রাই করা যাবে না"
                        )
                        break

                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"রিট্রাই সম্পূর্ণ ব্যর্থ ({max_retries + 1} টি চেষ্টা): "
                            f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}"
                        )
                        break

                    # Calculate delay with exponential backoff
                    current_delay = delay * (backoff**attempt)

                    # Add jitter if enabled
                    if use_jitter:
                        jitter = random.uniform(0.1, 0.3) * current_delay
                        current_delay += jitter

                    logger.warning(
                        f"রিট্রাই চলছে ({attempt + 1}/{max_retries + 1}): "
                        f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}. "
                        f"বিলম্ব করা হবে {current_delay:.2f} সেকেন্ড"
                    )

                    await asyncio.sleep(current_delay)

            if last_exception:
                raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                # For sync functions, we'll call the async budget checker
                has_budget = asyncio.run(global_retry_budget.consume()) if attempt > 0 else True
                if attempt > 0 and not has_budget:
                    logger.warning(
                        f"রিট্রাই বাজেট শেষ: ফাংশন '{func.__name__}' এর জন্য আর রিট্রাই করা যাবে না"
                    )
                    break

                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"রিট্রাই সম্পূর্ণ ব্যর্থ ({max_retries + 1} টি চেষ্টা): "
                            f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}"
                        )
                        break

                    # Calculate delay with exponential backoff
                    current_delay = delay * (backoff**attempt)

                    # Add jitter if enabled
                    if use_jitter:
                        jitter = random.uniform(0.1, 0.3) * current_delay
                        current_delay += jitter

                    logger.warning(
                        f"রিট্রাই চলছে ({attempt + 1}/{max_retries + 1}): "
                        f"ফাংশন '{func.__name__}' এক্সেপশন দিয়েছে: {type(e).__name__}: {e}. "
                        f"বিলম্ব করা হবে {current_delay:.2f} সেকেন্ড"
                    )

                    # DEEP-003 NOTE: see sync_wrapper above — blocking sleep is
                    # inherent to the sync wrapper; async callers must use the
                    # async wrapper (await asyncio.sleep) instead.
                    time.sleep(current_delay)

            if last_exception:
                raise last_exception

        # Return appropriate wrapper based on whether the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Example usage:
#
# @retry_handler(max_retries=3, delay=1.0, backoff=2.0)
# async def example_async_function():
#     # Your async code here
#     pass
#
# @retry_handler(max_retries=3, delay=1.0, backoff=2.0)
# def example_sync_function():
#     # Your sync code here
#     pass
