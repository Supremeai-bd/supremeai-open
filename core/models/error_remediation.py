import logging
from collections.abc import Callable
from typing import Any

from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from core.logging_config import logger
from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- সার্কিট ব্রেকার কনফিগারেশন ---
# কোনো ফাংশন ৩ বার ব্যর্থ হলে সার্কিট "open" হবে এবং পরবর্তী ৩০ সেকেন্ডের জন্য সেই ফাংশনে কোনো কল যেতে দেবে না।
# এটি ক্লাউড ফাংশনের মতো রিসোর্সের ಅನವශ්‍ය রানিং কস্ট কমায়।
db_breaker = CircuitBreaker("db_breaker", failure_threshold=3, recovery_timeout=30)


class ExternalService:
    """
    একটি কাল্পনিক এক্সটার্নাল সার্ভিস বা ডেটাবেজ কানেকশন যা মাঝে মাঝে ফেইল করতে পারে।
    """

    def __init__(self):
        self._fail_count = 0

    def unstable_operation(self, should_fail: bool = False):
        """
        এই অপারেশনটি ইচ্ছাকৃতভাবে ফেইল করানো যায়।
        """
        if should_fail:
            self._fail_count += 1
            logger.error(f"অপারেশন ফেইল! চেষ্টার সংখ্যা: {self._fail_count}")
            raise ConnectionError("ডেটাবেজ কানেকশন স্থাপন করা যায়নি")

        logger.info("অপারেশন সফলভাবে সম্পন্ন হয়েছে।")
        self._fail_count = 0  # সফল হলে কাউন্টার রিসেট
        return "অপারেশন সফল"


@db_breaker
@retry(
    # এক্সপোনেনশিয়াল ব্যাকঅফ: প্রথমবার ১ সেকেন্ড, এরপর ২, ৪ সেকেন্ড অপেক্ষা করবে।
    wait=wait_exponential(multiplier=1, min=1, max=5),
    # সর্বোচ্চ ৩ বার চেষ্টা করবে।
    stop=stop_after_attempt(3),
)
def resilient_call(service_operation: Callable[..., Any], *args, **kwargs) -> Any:
    """
    এক্সপোনেনশিয়াল ব্যাকঅফ এবং সার্কিট ব্রেকার দিয়ে একটি ফাংশনকে কল করার র‍্যাপার।

    - Retry Logic: এক্সপোনেনশিয়াল ব্যাকঅফসহ সর্বোচ্চ ৩ বার চেষ্টা করবে, যেখানে সর্বোচ্চ ডিলে ৫ সেকেন্ড।
    - Circuit Breaker: যদি ৩ বার চেষ্টার পরও ব্যর্থ হয়, সার্কিট ব্রেকার 'open' হয়ে যাবে।
    """
    logger.info("অপারেশন চালানোর চেষ্টা করা হচ্ছে...")
    return service_operation(*args, **kwargs)


if __name__ == "__main__":
    service = ExternalService()

    logger.info("\n--- পরিস্থিতি ১: সার্ভিস সফলভাবে কাজ করছে ---")
    try:
        result = resilient_call(service.unstable_operation, should_fail=False)
        logger.info(f"ফলাফল: {result}")
    except (RetryError, CircuitBreakerOpenError) as e:
        logger.error(f"ত্রুটি: {e}")

    logger.info("\n--- পরিস্থিতি ২: সার্ভিস অস্থায়ীভাবে ফেইল করছে (কিন্তু রিট্রাই করে সফল হবে) ---")
    # এখানে আমরা এমন একটি পরিস্থিতি তৈরি করছি যেখানে প্রথমবার ফেইল করলেও দ্বিতীয়বার সফল হবে।
    # এই উদাহরণটি দেখানোর জন্য সরাসরি resilient_call ব্যবহার না করে ম্যানুয়ালি দেখানো হলো।

    logger.info("\n--- পরিস্থিতি ৩: সার্ভিস স্থায়ীভাবে ফেইল করছে (সার্কিট ব্রেকার ওপেন হবে) ---")
    try:
        # এই কলটি ৩ বার রিট্রাই করার পর চূড়ান্তভাবে ফেইল করবে
        resilient_call(service.unstable_operation, should_fail=True)
    except (RetryError, CircuitBreakerOpenError) as e:
        logger.error(f"চূড়ান্ত ত্রুটি: {e}. সার্কিট ব্রেকার এখন '{db_breaker.state.name}' অবস্থায় আছে।")

    logger.info("\n--- পরিস্থিতি ৪: সার্কিট ব্রেকার 'open' থাকা অবস্থায় পুনরায় কল করার চেষ্টা ---")
    try:
        resilient_call(service.unstable_operation, should_fail=True)
    except CircuitBreakerOpenError as e:
        logger.warning(f"সার্কিট ওপেন থাকায় কলটি ব্লক করা হয়েছে: {e}")
        logger.info(f"ব্রেকার রিসেট হতে আর {db_breaker.recovery_timeout} সেকেন্ড অপেক্ষা করতে হবে।")
