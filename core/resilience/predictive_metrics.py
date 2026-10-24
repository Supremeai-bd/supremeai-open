# Standard imports
import math
import time
from collections import deque

from core.logging_config import logger


class PredictiveMetricsTracker:
    """
    ট্রাফিক প্যাটার্ন, লেটেন্সি (p95/p99) এবং এরর রেট (5xx status codes) ট্র্যাক করার জন্য স্লাইডিং উইন্ডো মেট্রিক ট্র্যাকার।
    EWMA (Exponentially Weighted Moving Average) এবং Consecutive Error Count ব্যবহার করা হয়েছে যাতে False Positive এড়ানো যায়।
    """

    def __init__(self, window_size_seconds: int = 300, alpha: float = 0.2):
        """
        :param window_size_seconds: উইন্ডোর সময়সীমা (ডিফল্ট: ৩০০ সেকেন্ড বা ৫ মিনিট)
        :param alpha: EWMA স্মুথিং ফ্যাক্টর (০ থেকে ১-এর মাঝে)
        """
        self.window_size_seconds = window_size_seconds
        self.alpha = alpha
        self.latencies: deque = deque()
        self.status_codes: deque = deque()

        # Moving Averages & Error Counters
        self.ewma_latency: float | None = None
        self.consecutive_errors: int = 0
        self.error_threshold_consecutive: int = 5

    def record_request(self, latency_ms: float, status_code: int) -> None:
        """
        একটি রিকোয়েস্টের লেটেন্সি এবং স্ট্যাটাস কোড স্লাইডিং উইন্ডোতে রেকর্ড করা।
        """
        current_time = time.time()
        self.latencies.append((current_time, latency_ms))
        self.status_codes.append((current_time, status_code))

        # EWMA Latency আপডেট করা
        if self.ewma_latency is None:
            self.ewma_latency = latency_ms
        else:
            self.ewma_latency = (self.alpha * latency_ms) + ((1 - self.alpha) * self.ewma_latency)

        # Consecutive errors পর্যবেক্ষণ করা
        if 500 <= status_code < 600:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = 0

        self._clean_old_metrics(current_time)

    def _clean_old_metrics(self, current_time: float) -> None:
        """
        উইন্ডোর বাইরের পুরাতন ডেটা রিমুভ করা।
        """
        cutoff = current_time - self.window_size_seconds
        while self.latencies and self.latencies[0][0] < cutoff:
            self.latencies.popleft()
        while self.status_codes and self.status_codes[0][0] < cutoff:
            self.status_codes.popleft()

    def calculate_percentile(self, percentile: float) -> float:
        """
        উইন্ডোর ভেতরের লেটেন্সির পার্সেন্টাইল (p95/p99) হিসাব করা।
        """
        if not self.latencies:
            return 0.0
        values = sorted([val for _, val in self.latencies])
        k = (len(values) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return values[int(k)]
        d0 = values[int(f)] * (c - k)
        d1 = values[int(c)] * (k - f)
        return d0 + d1

    def get_error_rate(self) -> float:
        """
        বর্তমানে উইন্ডোর ভেতরের 5xx এরর রেট (পার্সেন্টেজে) হিসাব করা।
        """
        if not self.status_codes:
            return 0.0
        error_count = sum(1 for _, code in self.status_codes if 500 <= code < 600)
        return (error_count / len(self.status_codes)) * 100.0

    def is_anomaly_detected(self) -> bool:
        """
        EWMA লেটেন্সি স্পাইক এবং টানা ৫টি কনসিকিউটিভ এরর চেক করে অ্যানমেলি অ্যানালাইসিস করা।
        False Positive এড়াতে Double Threshold ব্যবহার করা হয়েছে।
        """
        if not self.latencies:
            return False

        p95 = self.calculate_percentile(95)
        error_rate = self.get_error_rate()

        # রুল ১: টানা ৫টি বা তার বেশি 5xx এরর হওয়া
        if self.consecutive_errors >= self.error_threshold_consecutive:
            logger.warning(
                f"Predictive Anomaly: High consecutive errors ({self.consecutive_errors})"
            )
            return True

        # রুল ২: EWMA লেটেন্সি সাধারণ পার্সেন্টাইলের ৩ গুণের চেয়ে বেশি হওয়া এবং মিনিমাম ১০টি স্যাম্পল থাকা
        if len(self.latencies) >= 10 and self.ewma_latency and self.ewma_latency > (p95 * 3.0):
            logger.warning(
                f"Predictive Anomaly: Latency spike detected (EWMA: {self.ewma_latency:.2f}ms, p95: {p95:.2f}ms)"
            )
            return True

        # রুল ৩: এরর রেট ১০%-এর বেশি হওয়া
        if len(self.status_codes) >= 10 and error_rate > 10.0:
            logger.warning(f"Predictive Anomaly: High error rate ({error_rate:.2f}%)")
            return True

        return False
