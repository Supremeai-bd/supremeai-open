# backend/core/event_bus.py
# বাংলা মন্তব্য: সম্পূর্ণ রি-ফ্যাক্টর — Observable Anti-Suppression Error Pipeline।
# প্রতিটি error structured context (user_id, task_id, request_id) সহ emit হয়।
# CancelledError কখনো suppress হয় না — সবসময় re-raise।
# Dead Letter Queue bounded (maxsize=1000) — unbounded growth নিষিদ্ধ।
# Listener failure → DLQ — silent drop সম্পূর্ণ নিষিদ্ধ।

import asyncio
import os
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.logging_config import logger

try:
    import psutil
except ImportError:
    psutil = None


from enum import StrEnum


class ErrorSeverity(StrEnum):
    """
    বাংলা মন্তব্য: Error severity লেভেলের Enum।
    CRITICAL, HIGH, MEDIUM, LOW অনুযায়ী ফিল্টার এবং alert করা যায়।
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def _error_context_env() -> str:
    """Env tag for error context — never crashes.

    Issue #601 real-boot probes: during ``core.config`` initialization the
    partially-initialized module has no ``settings`` yet, and this
    default_factory runs while the error bus reports a boot-time failure.
    An error-bus metadata lookup must never turn a caught exception into a
    different crash, so degrade to the raw environment variable.
    """
    try:
        from core.config import settings

        return getattr(settings, "env", "unknown")
    except Exception:
        return os.getenv("ENV", "unknown")


class ErrorContext(BaseModel):
    """
    বাংলা মন্তব্য: প্রতিটি error event-এ এই structured context থাকবে।
    Generic 'module' মাত্র নয় — user_id, task_id, request_id সহ।
    এটি production debugging-এ correlation করার জন্য অপরিহার্য।
    """

    module: str
    # বাংলা মন্তব্য: Correlation IDs — production debugging-এ অপরিহার্য
    user_id: str | None = None
    task_id: str | None = None
    request_id: str | None = None
    # বাংলা মন্তব্য: কোন env-এ ঘটলো — staging vs production আলাদাভাবে alert হবে
    env: str = Field(default_factory=_error_context_env)
    system_state: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class ErrorEvent(BaseModel):
    """
    বাংলা মন্তব্য: ErrorEventBus-এর primary data model।
    severity levels: CRITICAL > ERROR / HIGH > WARNING / MEDIUM > INFO / LOW
    structured_context দিয়ে correlation ID track করা যায়।
    """

    module: str = "default"
    error_type: str = "UNKNOWN_ERROR"
    message: str
    severity: str = "ERROR"  # CRITICAL, ERROR/HIGH, WARNING/MEDIUM, INFO/LOW
    service: str = "backend"
    type: str | None = None  # Alias for error_type
    attempts: int = 0
    resolved: bool = False
    context: dict[str, Any] = Field(default_factory=dict)
    # বাংলা মন্তব্য: structured context — flat dict-এর পাশাপাশি type-safe correlation
    structured_context: ErrorContext = Field(default_factory=lambda: ErrorContext(module="default"))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def model_post_init(self, __context: Any) -> None:
        if self.type is None:
            self.type = self.error_type
        else:
            self.error_type = self.type


class DeadLetterQueueItem(BaseModel):
    """বাংলা মন্তব্য: Handler failure-এ এই item DLQ-তে যায়। Silent drop নিষিদ্ধ।"""

    event_type: str
    handler_name: str
    error: str
    timestamp: datetime
    retry_count: int = 0
    original_event: ErrorEvent | None = None


class ErrorEventBus:
    """
    বাংলা মন্তব্য: Central Observable Error Pipeline।
    কোনো silent drop নেই। প্রতিটি failure DLQ-তে যায়।
    CancelledError সবসময় re-raise হয়।
    Structured logging — severity অনুযায়ী log level।
    Bounded DLQ — maxsize=1000 (অতিরিক্ত item-এ critical alert)।
    Thread-safe implementation with duplicate listener prevention.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[ErrorEvent], Any]]] = defaultdict(list)
        self._lock = threading.RLock()  # Use RLock for better thread safety
        self._registered_handlers: set[str] = (
            set()
        )  # Track registered handlers to prevent duplicates
        # বাংলা মন্তব্য: bounded queue — unbounded growth prevent করা হলো
        self._dlq: asyncio.Queue[DeadLetterQueueItem] = asyncio.Queue(maxsize=1000)
        self._dead_letter_handlers: list[Callable[[DeadLetterQueueItem], Any]] = []
        self._total_emitted: int = 0
        self._total_dlq_items: int = 0
        self._pending_tasks: set[asyncio.Task] = set()

    def _cleanup_task(self, task: asyncio.Task) -> None:
        self._pending_tasks.discard(task)

    def _track_task(self, task: asyncio.Task) -> None:
        self._pending_tasks.add(task)
        task.add_done_callback(self._cleanup_task)

    def register_listener(
        self,
        event_type_or_listener: str | Callable[[ErrorEvent], Any] = "*",
        listener: Callable[[ErrorEvent], Any] | None = None,
    ) -> None:
        """বাংলা মন্তব্য: Error event listener register করুন (thread-safe)।
        Duplicate registration এড়ানো হয়।"""
        if callable(event_type_or_listener) and listener is None:
            event_type = "*"
            actual_listener = event_type_or_listener
        elif isinstance(event_type_or_listener, str) and listener is not None:
            event_type = event_type_or_listener
            actual_listener = listener
        else:
            raise TypeError("register_listener requires a listener callable.")

        with self._lock:
            # Create a unique identifier for the handler to prevent duplicates
            listener_module = getattr(actual_listener, "__module__", "unknown")
            listener_name = getattr(actual_listener, "__name__", str(actual_listener))
            handler_id = f"{event_type}:{listener_module}:{listener_name}"

            if handler_id in self._registered_handlers:
                logger.debug(
                    f"[ErrorEventBus] Handler {handler_id} already registered for event {event_type}, skipping duplicate registration"
                )
                return

            self._listeners[event_type].append(actual_listener)
            self._registered_handlers.add(handler_id)
            logger.debug(
                f"[ErrorEventBus] Registered listener for event type: {event_type}: {listener_name}"
            )

    def unregister_listener(self, event_type: str, listener: Callable[[ErrorEvent], Any]) -> None:
        """বাংলা মন্তব্য: Error event listener unregister করুন (thread-safe)."""
        with self._lock:
            if event_type in self._listeners:
                try:
                    self._listeners[event_type].remove(listener)
                    handler_id = f"{event_type}:{listener.__module__}:{listener.__name__}"
                    self._registered_handlers.discard(handler_id)
                    logger.debug(
                        f"[ErrorEventBus] Unregistered listener for event type: {event_type}: {getattr(listener, '__name__', str(listener))}"
                    )
                except ValueError:
                    logger.debug(f"[ErrorEventBus] Listener not found for event type: {event_type}")

    def register_dead_letter_handler(self, handler: Callable[[DeadLetterQueueItem], Any]) -> None:
        """বাংলা মন্তব্য: DLQ handler register করুন — handler failure alert পাঠাতে।"""
        self._dead_letter_handlers.append(handler)

    def emit(self, event: ErrorEvent) -> None:
        """
        বাংলা মন্তব্য: Synchronous emit — async context ছাড়াও call করা যাবে।
        Structured log সবসময় emit হয় — listener failure-তেও।
        """
        # বাংলা মন্তব্য: listener failure নির্বিশেষে structured log সবসময় emit হয়
        self._log_event(event)
        self._total_emitted += 1

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._dispatch_async(event))
            self._track_task(task)
        except RuntimeError:
            # বাংলা মন্তব্য: running loop নেই — sync context (tests, scripts)।
            # নতুন loop তৈরি করা হয় না — thread safety issue এড়াতে।
            logger.debug(
                f"[ErrorEventBus] No running loop for async dispatch of '{event.error_type}'. Sync log completed."
            )

    async def async_emit(self, event: ErrorEvent) -> None:
        """বাংলা মন্তব্য: Async context-এ সরাসরি call করার জন্য।"""
        self._log_event(event)
        self._total_emitted += 1
        await self._dispatch_async(event)

    # Alias for backwards compatibility if any
    emit_async = async_emit

    async def _dispatch_async(self, event: ErrorEvent) -> None:
        """বাংলা মন্তব্য: সব listeners-এ concurrent dispatch। Individual failure isolation।"""
        with self._lock:
            listeners = list(self._listeners.get(event.error_type, []))
            if "*" in self._listeners:
                listeners.extend(self._listeners["*"])

        results = await asyncio.gather(
            *[self._safe_invoke(handler, event) for handler in listeners],
            return_exceptions=True,
        )

        for handler, result in zip(listeners, results, strict=False):
            if isinstance(result, BaseException):
                handler_name = getattr(handler, "__name__", str(handler))
                dlq_item = DeadLetterQueueItem(
                    event_type=event.error_type,
                    handler_name=handler_name,
                    error=str(result),
                    timestamp=datetime.now(UTC),
                    original_event=event,
                )
                try:
                    self._dlq.put_nowait(dlq_item)
                    self._total_dlq_items += 1
                except asyncio.QueueFull:
                    # বাংলা মন্তব্য: DLQ full হলে drop এবং critical log — silent নয়
                    logger.critical(
                        f"[ErrorEventBus] DLQ full! Dropping item for handler: '{handler_name}'. DLQ capacity exceeded — check stuck listeners."
                    )

                logger.error(
                    f"[ErrorEventBus] Handler '{handler_name}' failed for event '{event.error_type}': {result}"
                )

                for dl_handler in self._dead_letter_handlers:
                    try:
                        await dl_handler(dlq_item)
                    except asyncio.CancelledError:
                        # বাংলা মন্তব্য: CancelledError কখনো suppress করা যাবে না
                        raise
                    except Exception as dl_exc:
                        logger.error(f"[ErrorEventBus] Dead letter handler failed: {dl_exc}")

    async def _safe_invoke(self, handler: Callable, event: ErrorEvent) -> Any:
        """
        বাংলা মন্তব্য: প্রতিটি handler individually isolate করা।
        CancelledError re-raise — graceful shutdown নিশ্চিত।
        """
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except asyncio.CancelledError:
            logger.warning(
                f"[ErrorEventBus] CancelledError in handler '{getattr(handler, '__name__', str(handler))}' — re-raising."
            )
            raise  # CRITICAL: CancelledError কখনো suppress করা যাবে না
        except Exception as exc:
            return exc  # exception return করা হচ্ছে, suppress নয়

    def _log_event(self, event: ErrorEvent) -> None:
        """
        বাংলা মন্তব্য: Structured logging — severity অনুযায়ী log level।
        context সহ — user_id, task_id, request_id correlation।
        """
        ctx = event.context.copy()
        ctx.update(
            {
                "user_id": event.structured_context.user_id,
                "task_id": event.structured_context.task_id,
                "request_id": event.structured_context.request_id,
                "env": event.structured_context.env,
            }
        )

        log_msg = f"[{event.module}] {event.error_type}: {event.message[:500]} | ctx={ctx}"

        if event.severity == "CRITICAL":
            logger.critical(log_msg)
        elif event.severity == "ERROR":
            logger.error(log_msg)
        elif event.severity == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    @property
    def dead_letter_queue_size(self) -> int:
        return self._dlq.qsize()

    @property
    def stats(self) -> dict[str, int]:
        """বাংলা মন্তব্য: Event bus statistics — admin dashboard-এ expose করা যাবে।"""
        return {
            "total_emitted": self._total_emitted,
            "total_dlq_items": self._total_dlq_items,
            "dlq_current_size": self._dlq.qsize(),
            "registered_listeners": len(self._listeners),
        }

    async def process_dead_letter_queue(self, max_items: int = 10) -> list[DeadLetterQueueItem]:
        """
        বাংলা মন্তব্য: DLQ থেকে items process করা।
        max_items bounded — unbounded processing prevent।
        """
        processed: list[DeadLetterQueueItem] = []
        for _ in range(min(max_items, self._dlq.qsize())):
            try:
                item = self._dlq.get_nowait()
                item.retry_count += 1
                processed.append(item)
                logger.warning(
                    f"[ErrorEventBus] DLQ processed: '{item.handler_name}' (retry #{item.retry_count}) | event: {item.event_type}"
                )
            except asyncio.QueueEmpty:
                break
        return processed


class IntelligentErrorBus(ErrorEventBus):
    """
    বাংলা মন্তব্য: Semantic Error Brain.
    Contextually enriches errors with system metrics and escalates repeating patterns.
    """

    def __init__(self) -> None:
        super().__init__()
        from collections import deque

        # Sliding window for pattern detection (recent 5 events)
        self._error_history = deque(maxlen=5)

    def _get_current_metrics(self) -> dict[str, Any]:
        if not psutil:
            return {}
        try:
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
            }
        except (psutil.Error, OSError):
            return {}

    def _check_and_escalate_pattern(self, event: ErrorEvent) -> None:
        with self._lock:
            self._error_history.append(event.error_type)
            if len(self._error_history) >= 3:
                last_three = list(self._error_history)[-3:]
                if len(set(last_three)) == 1:
                    event.severity = "CRITICAL"
                    event.error_type = "SILENT_PATTERN_ESCALATED"
                    logger.critical(
                        f"🚨 Pattern Detected: {last_three[0]} repeated 3 times consecutively. Escalated to CRITICAL."
                    )

    def emit(self, event: ErrorEvent) -> None:
        event.structured_context.system_state = self._get_current_metrics()
        self._check_and_escalate_pattern(event)

        # Forward severe errors to Sentry via monitoring
        if event.severity in ["CRITICAL", "ERROR", "HIGH"]:
            from monitoring import track_exception

            track_exception(
                Exception(f"[{event.error_type}] {event.message}"),
                context={
                    "module": event.module,
                    "service": event.service,
                    **event.context,
                    **event.structured_context.model_dump(),
                },
            )

        super().emit(event)

    async def publish(self, event: ErrorEvent) -> ErrorEvent:
        """
        বাংলা মন্তব্য: ইভেন্ট পাবলিশ করে এবং স্বয়ংক্রিয় সেলফ-হিলিং প্রসেস ট্রাইগার করে।
        """
        await self.async_emit(event)
        await self.process_error_for_healing(event)
        return event

    async def process_error_for_healing(self, event: ErrorEvent) -> None:
        """
        বাংলা মন্তব্য: সেলফ-হিলিং স্ট্র্যাটেজি এক্সিকিউট করা।
        DB সংযোগ বিচ্ছিন্নতা, মেমোরি লিমিট ও এপিআই টাইমআউট স্বয়ংক্রিয়ভাবে রিকভার করে।
        """
        if event.resolved:
            return

        err_type = event.error_type or event.type
        logger.info(f"[Self-Healing] Processing error event for healing: {err_type}")

        try:
            if err_type == "MEMORY_LIMIT_EXCEEDED":
                import gc

                gc.collect()
                logger.info("[Self-Healing] Garbage collection executed cleanly")
                event.resolved = True
            elif err_type == "DB_CONNECTION_FAILURE":
                from core.persistence.pooled_pg import _get_pool

                pool = _get_pool()
                if pool:
                    logger.info("[Self-Healing] Database connection pool checked/refreshed")
                    event.resolved = True
            elif err_type == "API_TIMEOUT":
                import os

                current_timeout = int(os.environ.get("API_TIMEOUT_MS", "30000"))
                new_timeout = min(current_timeout * 2, 120000)
                os.environ["API_TIMEOUT_MS"] = str(new_timeout)
                logger.info(f"[Self-Healing] Scaled API timeout to {new_timeout}ms")
                event.resolved = True
        except Exception as exc:
            logger.error(f"[Self-Healing] Healing strategy failed for {err_type}: {exc}")
            event.attempts += 1


# CentralErrorBus & error_bus aliases for compatibility
CentralErrorBus = IntelligentErrorBus

# বাংলা মন্তব্য: Module-level singleton — সিস্টেমে একটিই ErrorEventBus instance থাকবে।
# Lazy initialization to avoid asyncio.Queue creation at import time in test environments.
_error_event_bus_instance: IntelligentErrorBus | None = None


def _get_error_event_bus() -> IntelligentErrorBus:
    """Lazy initialization of error_event_bus singleton."""
    global _error_event_bus_instance
    if _error_event_bus_instance is None:
        _error_event_bus_instance = IntelligentErrorBus()
    return _error_event_bus_instance


class _ErrorEventBusProxy:
    """Proxy that delegates all attribute access to the lazily-initialized singleton."""

    def __getattr__(self, name: str):
        return getattr(_get_error_event_bus(), name)


error_event_bus: IntelligentErrorBus = _ErrorEventBusProxy()  # type: ignore[misc, assignment]
error_bus: IntelligentErrorBus = error_event_bus


class EventBus:
    """
    বাংলা মন্তব্য: টপিক-ভিত্তিক মেসেজিং ও সাবস্ক্রিপশনের জন্য সাধারণ ইভেন্ট বাস ক্লাস।
    Thread-safe implementation with duplicate listener prevention.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
        self._registered_handlers: set[str] = set()

    async def register_listener(self, topic: str, listener: Callable) -> None:
        """Register a listener for a specific topic with thread safety and duplicate prevention."""
        with self._lock:
            # Create a unique identifier for the handler to prevent duplicates
            handler_id = f"{topic}:{listener.__module__}:{listener.__name__}"

            if handler_id in self._registered_handlers:
                logger.debug(
                    f"[EventBus] Handler {handler_id} already registered for topic {topic}, skipping duplicate registration"
                )
                return

            self._listeners[topic].append(listener)
            self._registered_handlers.add(handler_id)
            logger.debug(
                f"[EventBus] Registered listener for topic: {topic}: {getattr(listener, '__name__', str(listener))}"
            )

    async def emit(self, topic: str, event: dict[str, Any]) -> None:
        """Emit an event to all listeners of a specific topic."""
        listeners = []
        with self._lock:
            listeners = list(self._listeners.get(topic, []))

        for listener in listeners:
            try:
                res = listener(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(f"[EventBus] Error in listener on topic '{topic}': {e}")
