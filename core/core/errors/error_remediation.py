"""This module provides robust error remediation strategies for the
SupremeAI project, combining a vector database (Qdrant) for dynamic fix
lookups with a resilient local fallback mechanism. It ensures system stability
by incorporating circuit breaking and exponential backoff for external service
interactions, offering automated suggestions for known error patterns to
enhance the overall reliability of the AI ecosystem.

Key Components:
- `ErrorRemediation`: Central class for managing error remediation
  strategies, including Qdrant integration, circuit breaking, and local
  fallback logic.
- `_ensure_fallback_file()`: Initializes and ensures the presence of the
  local JSON file used for fallback error fixes.
- `_load_local_fallback()`: Retrieves a default error fix from the module's
  local fallback JSON file.
- `_backoff_retry()`: Async utility that retries a given operation with
  exponential backoff, respecting the circuit breaker's state.
- `lookup_fix()`: Primary method to find a remediation fix for a given error
  signature, leveraging Qdrant or falling back to a local solution.
- `_compute_embedding()`: Generates a vector embedding from an error signature
  string using sentence-transformers (preferred) or a deterministic hash-based
  fallback.

Fixes Applied (Autonomous Architecture Audit):
- 🛑 [CRITICAL] Removed zero-vector placeholder `[0.0] * 384` — replaced with proper embedding function
- 🔴 [HIGH] Added collection auto-creation with correct vector size (384 dimensions)
- 🟡 [MEDIUM] Qdrant URL now uses `settings` instead of raw `os.getenv()`
- 🟡 [MEDIUM] Lazy Qdrant client initialization to avoid unnecessary memory allocation
- 🟢 [LOW] Added `insert_error_pattern()` for self-healing capability
"""

import asyncio
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus
from core.resilience.circuit_breaker import CircuitBreaker

# ── Embedding Provider ─────────────────────────────────────────────────────────
# sentence_transformers is imported lazily inside _compute_embedding() to prevent
# heavy model loading at module import time (avoids 30s+ timeout in CI/tests).
_SENTENCE_TRANSFORMER_AVAILABLE: bool | None = None  # None = unchecked
_SENTENCE_TRANSFORMER_MODEL = None


def _compute_embedding(text: str, vector_size: int = 384) -> list[float]:
    """Generate a dense vector embedding from an error signature string.

    Priority:
    1. sentence-transformers (if available) — produces meaningful semantic embeddings
    2. Deterministic hash-based fallback — produces reproducible pseudo-embeddings

    Args:
        text: Input error signature string.
        vector_size: Target embedding dimensionality (default: 384 for Qdrant compatibility).

    Returns:
        A list of floats of length `vector_size` representing the embedding.
    """
    global _SENTENCE_TRANSFORMER_AVAILABLE, _SENTENCE_TRANSFORMER_MODEL

    # Lazy-check availability on first call only
    if _SENTENCE_TRANSFORMER_AVAILABLE is None:
        try:
            if os.getenv("LOW_MEMORY_MODE", "false").lower() == "true":
                raise ImportError("Low memory mode enabled.")
            import importlib

            importlib.import_module("sentence_transformers")
            _SENTENCE_TRANSFORMER_AVAILABLE = True
        except (ImportError, OSError, Exception):
            _SENTENCE_TRANSFORMER_AVAILABLE = False

    if _SENTENCE_TRANSFORMER_AVAILABLE:
        try:
            if _SENTENCE_TRANSFORMER_MODEL is None:
                from sentence_transformers import SentenceTransformer

                # বাংলা মন্তব্য: Lazy load — all-MiniLM-L6-v2 (384-dim) Qdrant-এর সাথে compatible
                _SENTENCE_TRANSFORMER_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            embedding = _SENTENCE_TRANSFORMER_MODEL.encode(text, normalize_embeddings=True)
            return embedding.tolist()  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug(
                f"sentence-transformers encode failed, falling back to hash embedding: {exc}"
            )

    # ── Deterministic hash-based fallback ──────────────────────────────────────
    # বাংলা মন্তব্য: SHA-256-এর প্রতিটি বাইটকে [0,1] রেঞ্জে normalize করে
    # reproducible pseudo-embedding তৈরি করা হয়। এটি semantic নয় কিন্তু
    # identical error strings-এর জন্য consistent result দেয়.
    raw = hashlib.sha256(text.encode("utf-8")).digest()  # 32 bytes
    result: list[float] = []
    for i in range(vector_size):
        idx = i % len(raw)
        # Map byte [0,255] → float [-1.0, 1.0]
        normalized = (raw[idx] / 127.5) - 1.0
        result.append(round(normalized, 6))
    return result


# ── Qdrant Integration ────────────────────────────────────────────────────────

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qdrant_models
    from qdrant_client.http.exceptions import UnexpectedResponse

    HAS_QDRANT = True
except (ImportError, TypeError, Exception):
    QdrantClient = None  # type: ignore
    qdrant_models = None  # type: ignore
    UnexpectedResponse = Exception  # type: ignore
    HAS_QDRANT = False

# Qdrant default collection configuration
QDRANT_COLLECTION_NAME = "error_patterns"
QDRANT_VECTOR_SIZE = 384
QDRANT_DISTANCE = qdrant_models.Distance.COSINE if (HAS_QDRANT and qdrant_models) else None


class ErrorRemediation:
    """Self-healing error remediation engine with Qdrant vector search + local fallback.

    Usage::
        remediator = ErrorRemediation()
        fix = await remediator.lookup_fix("ValueError: invalid literal for int()")
    """

    def __init__(self) -> None:
        self._qdrant: QdrantClient | None = None
        self._qdrant_initialized: bool = False
        self.fallback_path = Path(tempfile.gettempdir()) / "error_remediation_fallback.json"
        self.circuit_breaker = CircuitBreaker(
            name="qdrant", failure_threshold=3, recovery_timeout=60.0
        )
        self._ensure_fallback_file()

        # Listen for escalating errors to trigger RefactorWiz
        error_event_bus.register_listener("SILENT_PATTERN_ESCALATED", self._trigger_refactor_wiz)

    def _trigger_refactor_wiz(self, event: ErrorEvent):
        """বাংলা মন্তব্য: Automatically triggers RefactorWiz to generate a patch for escalated silent patterns."""
        # TEST-ENV BOUNDARY GUARD (hardening-2 round 3, root cause of the CI
        # services-group teardown hang in run 34817278198): a mission test
        # tripping SILENT_PATTERN_ESCALATED spawned a real
        # `scripts/devops/refactor_wiz.py` SUBPROCESS from inside pytest; its
        # task then survived asyncio's cancel-all-tasks during teardown and
        # hung the whole CI job until pytest-timeout killed it. Auto-patching
        # source files from a test run is never desirable — same guard idiom
        # as core/rate_limit.py and core/middleware/security.py.
        if os.getenv("ENV") == "test" or os.getenv("PYTEST_CURRENT_TEST"):
            logger.info(
                f"RefactorWiz auto-patch skipped in test environment (module={event.module})."
            )
            return

        module_name = event.module
        if not module_name or module_name == "unknown":
            return

        logger.info(
            f"🚀 SILENT_PATTERN_ESCALATED for {module_name}. Triggering Auto-Patch via RefactorWiz..."
        )

        # We run this in the background
        async def _run_wiz():
            try:
                # Resolve module to file path if possible
                file_path = module_name.replace(".", "/") + ".py"
                if not os.path.exists(file_path):
                    file_path = "backend/" + file_path
                if not os.path.exists(file_path):
                    logger.warning(f"Could not resolve {module_name} to a file for RefactorWiz.")
                    return

                cmd = [
                    "python",
                    "scripts/devops/refactor_wiz.py",
                    "--files",
                    file_path,
                    "--no-prompt",
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    logger.info(f"✅ RefactorWiz auto-patch completed for {file_path}")
                else:
                    logger.error(
                        f"❌ RefactorWiz auto-patch failed for {file_path}:\n{stderr.decode()}"
                    )
            except Exception as e:
                logger.error(f"Error triggering RefactorWiz: {e}")

        from core.utils.background_tasks import track_task

        track_task(asyncio.create_task(_run_wiz()))

    # ── Lazy Qdrant initializer ────────────────────────────────────────────────

    def _init_qdrant(self) -> None:
        """Initialize Qdrant client with proper collection auto-creation.

        This is intentionally a separate method (not in __init__) so that
        the Qdrant client is only instantiated when `lookup_fix()` is actually
        called. This avoids memory waste when `HAS_QDRANT=False` or when
        the application only uses the local fallback.
        """
        if self._qdrant_initialized:
            return
        if not HAS_QDRANT:
            self._qdrant_initialized = True
            return

        try:
            # Use settings if available, fallback to env var
            qdrant_url: str = ""
            try:
                from core.config import settings as app_settings

                qdrant_url = getattr(app_settings, "qdrant_url", "")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")
            if not qdrant_url:
                qdrant_url = os.getenv("QDRANT_URL", "")
                if not qdrant_url:
                    current_env = (
                        getattr(app_settings, "env", os.getenv("ENV", "local")).lower()
                        if "app_settings" in locals()
                        else "local"
                    )
                    if current_env in ("local", "development", "dev", "test"):
                        qdrant_url = "http://localhost:6333"  # is_local()
                    else:
                        raise ValueError("QDRANT_URL is required in production environment")

            self._qdrant = QdrantClient(url=qdrant_url, prefer_grpc=False)
            self._ensure_qdrant_collection()
            self._qdrant_initialized = True
            logger.info(f"✅ Qdrant error remediation client connected ({qdrant_url})")
        except Exception as exc:
            logger.warning(f"⚠️ Qdrant initialization failed: {exc}. Using local fallback only.")
            self._qdrant = None
            self._qdrant_initialized = True

    def _ensure_qdrant_collection(self) -> None:
        """Auto-create the error_patterns Qdrant collection if it doesn't exist."""
        if not self._qdrant:
            return
        try:
            collections = self._qdrant.get_collections().collections
            existing_names = {c.name for c in collections}
            if QDRANT_COLLECTION_NAME not in existing_names:
                self._qdrant.recreate_collection(
                    collection_name=QDRANT_COLLECTION_NAME,
                    vectors_config=qdrant_models.VectorParams(
                        size=QDRANT_VECTOR_SIZE,
                        distance=QDRANT_DISTANCE or qdrant_models.Distance.COSINE,
                    ),
                )
                logger.info(
                    f"✅ Created Qdrant collection '{QDRANT_COLLECTION_NAME}' (size={QDRANT_VECTOR_SIZE})"
                )

            # DLQ Collection
            if "failed_fixes" not in existing_names:
                self._qdrant.recreate_collection(
                    collection_name="failed_fixes",
                    vectors_config=qdrant_models.VectorParams(
                        size=QDRANT_VECTOR_SIZE,
                        distance=QDRANT_DISTANCE or qdrant_models.Distance.COSINE,
                    ),
                )
                logger.info("✅ Created Qdrant collection 'failed_fixes' (DLQ)")
        except UnexpectedResponse as exc:
            logger.warning(
                f"Qdrant collection check failed (may already exist or service unavailable): {exc}"
            )

    # ── Fallback file management ───────────────────────────────────────────────

    @with_error_bus("_ensure_fallback_file")
    def _ensure_fallback_file(self) -> None:
        """Ensure the fallback file exists with proper structure."""
        try:
            # Validate paths and create directories if needed
            self.fallback_path.parent.mkdir(parents=True, exist_ok=True)

            # Create default fallback file if it doesn't exist
            if not self.fallback_path.exists():
                try:
                    with open(self.fallback_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "default_fix": "Retry with exponential backoff",
                                "fallbacks": {
                                    "default": "Retry with exponential backoff",
                                    "timeout": "Increase timeout or reduce payload size",
                                    "rate_limit": "Implement exponential backoff with jitter",
                                    "auth_error": "Verify API key and permissions",
                                    "connection_refused": "Check service availability and firewall rules",
                                },
                            },
                            f,
                            indent=2,
                        )
                    logger.info(f"Created fallback file at {self.fallback_path}")
                except Exception as file_write_exc:
                    logger.error(f"Failed to write fallback file: {file_write_exc}")
                    error_event_bus.emit(
                        ErrorEvent(
                            module="error_remediation",
                            error_type="FALLBACK_FILE_WRITE_FAILED",
                            message=f"Failed to write fallback file: {file_write_exc}",
                            severity="ERROR",
                            structured_context=ErrorContext(
                                module="error_remediation",
                                extra={
                                    "file_path": str(self.fallback_path),
                                    "exception": str(file_write_exc)[:200],
                                },
                            ),
                        )
                    )
                    return False  # type: ignore
            return True  # type: ignore

        except Exception as exc:
            logger.error(f"Error ensuring fallback file: {exc}")
            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="FALLBACK_FILE_SETUP_FAILED",
                    message=f"Error ensuring fallback file: {exc}",
                    severity="ERROR",
                    structured_context=ErrorContext(
                        module="error_remediation",
                        extra={"file_path": str(self.fallback_path), "exception": str(exc)[:200]},
                    ),
                )
            )
            return False  # type: ignore

    @with_error_bus("_load_local_fallback")
    def _load_local_fallback(self, error_sig: str | None = None) -> str | None:
        """Load a fallback fix from the local JSON file.

        If `error_sig` is provided, it attempts a keyword-based match against
        the ``fallbacks`` dictionary keys; otherwise returns the default.

        Returns:
            A remediation suggestion string, or ``None`` if no fix is found.
        """
        try:
            # Ensure fallback file exists and is properly structured
            if not self._ensure_fallback_file():
                logger.warning("Fallback file not available")
                return None

            # Load fallback data
            try:
                with open(self.fallback_path, encoding="utf-8") as f:
                    data: dict = json.load(f)
            except json.JSONDecodeError as je:
                logger.error(f"Invalid JSON in fallback file: {je}")
                error_event_bus.emit(
                    ErrorEvent(
                        module="error_remediation",
                        error_type="INVALID_JSON_FALLBACK",
                        message=f"Invalid JSON in fallback file: {je}",
                        severity="ERROR",
                        structured_context=ErrorContext(
                            module="error_remediation",
                            extra={
                                "file_path": str(self.fallback_path),
                                "exception": str(je)[:200],
                            },
                        ),
                    )
                )
                return data.get("fallbacks", {}).get("default")  # Use default if JSON is invalid

            # Try keyword-specific fallback first
            if error_sig:
                sig_lower = error_sig.lower()
                for keyword, fix in data.get("fallbacks", {}).items():
                    if keyword in sig_lower:
                        logger.debug(f"Found keyword match for '{keyword}' in error signature")
                        return fix

            # Return default fallback
            default_fix = data.get("default_fix") or data.get("fallbacks", {}).get("default")
            if not default_fix:
                logger.warning("No default fix found in fallback file")
                error_event_bus.emit(
                    ErrorEvent(
                        module="error_remediation",
                        error_type="NO_DEFAULT_FIX",
                        message="No default fix found in fallback file",
                        severity="WARNING",
                        structured_context=ErrorContext(
                            module="error_remediation", extra={"file_path": str(self.fallback_path)}
                        ),
                    )
                )
            return default_fix

        except Exception as exc:  # Catch any unexpected errors
            logger.error(f"Unexpected error loading local fallback: {exc}", exc_info=True)
            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="LOCAL_FALLBACK_LOAD_ERROR",
                    message=f"Unexpected error loading local fallback: {exc}",
                    severity="ERROR",
                    structured_context=ErrorContext(
                        module="error_remediation",
                        extra={"file_path": str(self.fallback_path), "exception": str(exc)[:200]},
                    ),
                )
            )
            return None

    @with_error_bus("_load_redis_fallback")
    async def _load_redis_fallback(self, error_sig: str) -> str | None:
        """Attempt to fetch a known fix from Redis if Qdrant is unavailable."""
        if not error_sig:
            return None

        try:
            from core.cache.redis_manager import redis_manager

            if redis_manager and redis_manager.client:
                cache_key = f"remediation:fix:{hashlib.sha256(error_sig.encode()).hexdigest()}"
                fix = await redis_manager.client.get(cache_key)
                if fix:
                    logger.info("✅ Found remediation in Redis fallback cache.")
                    return fix.decode("utf-8")
        except Exception as exc:
            logger.warning(f"Redis fallback failed: {exc}", exc_info=True)
            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="REDIS_FALLBACK_FAILED",
                    message=f"Redis fallback failed: {exc}",
                    severity="WARNING",
                    structured_context=ErrorContext(
                        module="error_remediation",
                        extra={"error_sig": error_sig[:200], "exception": str(exc)[:200]},
                    ),
                )
            )
        return None

    # ── Circuit-breaking retry ─────────────────────────────────────────────────

    async def _backoff_retry(
        self, operation: Callable, max_attempts: int = 3, base_delay: float = 0.5
    ):
        """Execute an async operation with exponential backoff and circuit breaking.

        Args:
            operation: An async callable to execute.
            max_attempts: Maximum retry attempts.
            base_delay: Initial delay in seconds; doubles each attempt.

        Returns:
            The operation result, or ``None`` if all attempts failed.
        """
        last_exception: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            if not self.circuit_breaker.allow_request():
                logger.warning("Circuit breaker open; skipping Qdrant lookup.")
                return None
            try:
                result = await operation()
                self.circuit_breaker.mark_success()
                return result
            except Exception as exc:
                last_exception = exc
                self.circuit_breaker.mark_failure()
                logger.debug(f"Qdrant lookup attempt {attempt}/{max_attempts} failed: {exc}")
                if attempt < max_attempts:
                    await asyncio.sleep(min(base_delay * (2 ** (attempt - 1)), 5.0))

        if last_exception is not None:
            logger.warning(
                f"Qdrant lookup exhausted {max_attempts} attempts; falling back. Last error: {last_exception}"
            )
        return None

    # ── Public API ─────────────────────────────────────────────────────────────

    @with_error_bus("lookup_fix")
    async def lookup_fix(self, error_sig: str) -> str | None:
        """Find a remediation fix for a given error signature.

        Args:
            error_sig: The error signature string (e.g., exception message).

        Returns:
            A suggested fix string, or ``None`` if no remediation is found.
        """
        if not error_sig:
            logger.warning("Empty error signature provided to lookup_fix")
            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="EMPTY_ERROR_SIGNATURE",
                    message="Empty error signature provided",
                    severity="WARNING",
                    structured_context=ErrorContext(
                        module="error_remediation", extra={"error_sig": ""}
                    ),
                )
            )
            return None

        # Emit event for monitoring
        error_event_bus.emit(
            ErrorEvent(
                module="error_remediation",
                error_type="QDRANT_LOOKUP_INITIATED",
                message="Starting Qdrant remediation lookup",
                severity="DEBUG",
                structured_context=ErrorContext(
                    module="error_remediation", extra={"error_sig": error_sig[:200]}
                ),
            )
        )

        try:
            # Lazy-init Qdrant on first call
            self._init_qdrant()

            if not HAS_QDRANT:
                logger.warning("Qdrant not available — skipping vector search, using fallback only")
                error_event_bus.emit(
                    ErrorEvent(
                        module="error_remediation",
                        error_type="QDRANT_NOT_AVAILABLE",
                        message="Qdrant not available, using fallback",
                        severity="WARNING",
                        structured_context=ErrorContext(
                            module="error_remediation", extra={"error_sig": error_sig[:200]}
                        ),
                    )
                )
                redis_fix = await self._load_redis_fallback(error_sig)
                if redis_fix:
                    return redis_fix
                return self._load_local_fallback(error_sig)

            embedding = _compute_embedding(error_sig, QDRANT_VECTOR_SIZE)

            @with_error_bus("_search")
            async def _search():
                # বাংলা মন্তব্য: Proper embedding-based search — no more zero vectors!
                return self._qdrant.search(
                    collection_name=QDRANT_COLLECTION_NAME,
                    query_vector=embedding,
                    limit=1,
                    score_threshold=0.6,  # Only return high-confidence matches
                )

            results = await self._backoff_retry(_search)

            if results and results[0].payload:
                fix: str | None = results[0].payload.get("fix")
                if fix:
                    logger.info(f"✅ Found Qdrant remediation (score={results[0].score:.3f})")
                    return fix

            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="QDRANT_NO_FIX_FOUND",
                    message="No remediation found in Qdrant for error signature",
                    severity="INFO",
                    structured_context=ErrorContext(
                        module="error_remediation", extra={"error_sig": error_sig[:200]}
                    ),
                )
            )

            # ── DLQ Insertion ──
            try:
                self._qdrant.upsert(
                    collection_name="failed_fixes",
                    points=[
                        qdrant_models.PointStruct(
                            id=abs(hash(error_sig)) % (10**12),
                            vector=embedding,
                            payload={"error_sig": error_sig[:500]},
                        )
                    ],
                )
                logger.debug(
                    "Inserted unresolved error signature into DLQ (failed_fixes collection)."
                )
            except Exception as dlq_exc:
                logger.warning(f"Failed to insert into DLQ: {dlq_exc}")
                error_event_bus.emit(
                    ErrorEvent(
                        module="error_remediation",
                        error_type="DLQ_INSERTION_FAILED",
                        message=f"Failed to insert into DLQ: {dlq_exc}",
                        severity="WARNING",
                        structured_context=ErrorContext(
                            module="error_remediation",
                            extra={"error_sig": error_sig[:200], "exception": str(dlq_exc)[:200]},
                        ),
                    )
                )

            redis_fix = await self._load_redis_fallback(error_sig)
            if redis_fix:
                return redis_fix
            return self._load_local_fallback(error_sig)

        except Exception as exc:  # Catch any unexpected errors
            logger.error(f"Unexpected error in lookup_fix: {exc}", exc_info=True)
            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="LOOKUP_FIX_UNEXPECTED_ERROR",
                    message=f"Unexpected error in lookup_fix: {exc}",
                    severity="ERROR",
                    structured_context=ErrorContext(
                        module="error_remediation",
                        extra={"error_sig": error_sig[:200], "exception": str(exc)[:200]},
                    ),
                )
            )
            # Fallback to local fallback in case of any unexpected errors
            return self._load_local_fallback(error_sig)

    @with_error_bus("insert_error_pattern")
    async def insert_error_pattern(
        self,
        error_sig: str,
        fix: str,
        metadata: dict | None = None,
    ) -> bool:
        """Insert a new error-remediation pattern into Qdrant for future self-healing.

        Args:
            error_sig: The error signature string (e.g., exception message).
            fix: The remediation suggestion.
            metadata: Optional metadata (e.g., ``{"severity": "HIGH", "module": "billing"}``).

        Returns:
            ``True`` if the pattern was inserted successfully, ``False`` otherwise.
        """
        self._init_qdrant()
        if not self._qdrant:
            logger.warning("Qdrant not available — cannot insert error pattern.")
            return False

        embedding = _compute_embedding(error_sig, QDRANT_VECTOR_SIZE)
        payload: dict = {"error_sig": error_sig[:500], "fix": fix}
        if metadata:
            payload.update(metadata)

        try:
            self._qdrant.upsert(
                collection_name=QDRANT_COLLECTION_NAME,
                points=[
                    qdrant_models.PointStruct(
                        id=abs(hash(error_sig)) % (10**12),
                        vector=embedding,
                        payload=payload,
                    )
                ],
            )
            logger.info(f"✅ Inserted error pattern ({len(embedding)}-dim): {error_sig[:80]}")
            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="ERROR_PATTERN_INSERTED",
                    message="Error pattern inserted into Qdrant",
                    severity="INFO",
                    structured_context=ErrorContext(
                        module="error_remediation",
                        extra={"error_sig": error_sig[:200], "fix_len": len(fix)},
                    ),
                )
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to insert error pattern into Qdrant: {exc}")
            error_event_bus.emit(
                ErrorEvent(
                    module="error_remediation",
                    error_type="ERROR_PATTERN_INSERT_FAILED",
                    message=f"Failed to insert error pattern into Qdrant: {exc}",
                    severity="ERROR",
                    structured_context=ErrorContext(
                        module="error_remediation",
                        extra={
                            "error_sig": error_sig[:200],
                            "exception": str(exc)[:200],
                        },
                    ),
                )
            )
            return False


# ── Singleton (shared instance) ───────────────────────────────────────────────
error_remediator = ErrorRemediation()
lookup_fix = error_remediator.lookup_fix
insert_error_pattern = error_remediator.insert_error_pattern
