"""SupremeAI worker HTTP wrapper — makes the Celery worker viable on Render's free tier.

Render free web services MUST bind $PORT and answer HTTP or they are spun down
forever (and never receive Celery tasks). This module serves a minimal FastAPI
control/health surface and (best-effort) supervises a Celery worker subprocess
so a single free web service can act as both the HTTP endpoint and the queue
consumer. All Celery/Redis wiring is wrapped in try/except: the HTTP service
ALWAYS starts, even if Celery or Redis is unavailable (status becomes degraded).

Run with:  python worker_service.py   (backend/ as working dir)
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import hashlib
import importlib.util
import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.automation.models import ExecutionEnvelope
from database.session import get_db_session_context

SUPPORTED_CAPABILITIES = frozenset({"acknowledge", "scrape"})
MAX_METADATA_BYTES = 32_768

logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "8080"))
ROLE = os.getenv("SUPREMEAI_SERVICE_ROLE", "worker")
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="SupremeAI Worker", docs_url=None, redoc_url=None, openapi_url=None)
_state: dict[str, Any] = {"celery_proc": None, "degraded": False, "detail": ""}
_idempotency_lock = asyncio.Lock()
_idempotency_records: dict[str, tuple[str, str]] = {}
MAX_IDEMPOTENCY_RECORDS = 10_000


class TaskContract(BaseModel):
    """The single tenant-scoped contract accepted by the worker boundary."""

    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=10_000)
    capability: Literal["acknowledge", "scrape"] = "acknowledge"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=256)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_retries: int = Field(default=3, ge=0, le=3)
    timeout_seconds: int = Field(default=300, ge=1, le=900)
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution: ExecutionEnvelope | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> TaskContract:
        if len(str(self.metadata).encode("utf-8")) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata exceeds {MAX_METADATA_BYTES} bytes")
        if self.execution is not None:
            if self.execution.tenant_id != self.tenant_id:
                raise ValueError("execution tenant does not match task tenant")
            if self.user_id and self.execution.actor_id != self.user_id:
                raise ValueError("execution actor does not match task user")
        else:
            self.execution = ExecutionEnvelope(
                actor_id=self.user_id or "worker",
                tenant_id=self.tenant_id,
                intent=self.goal,
                trace_id=self.correlation_id,
            )
        if self.capability == "scrape" and not isinstance(self.metadata.get("url"), str):
            raise ValueError("metadata.url is required for scrape tasks")
        return self


class HealthStatus(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    role: str
    queue_configured: bool
    queue_available: bool
    celery_alive: bool
    detail: str | None = None


def _celery_alive() -> bool:
    proc: subprocess.Popen[bytes] | None = _state.get("celery_proc")
    return bool(proc and proc.poll() is None)


async def _queue_available() -> tuple[bool, str | None]:
    if not _redis_url():
        return False, "Redis URL is not configured"
    try:
        await asyncio.wait_for(asyncio.to_thread(_queue_call, "get_queue_stats"), timeout=5.0)
        return True, None
    except Exception as exc:
        _state.update(degraded=True, detail=f"queue unavailable: {exc}")
        return False, "Queue is unavailable"


def _verify_worker_auth(request: Request) -> None:
    """Validate internal worker authentication token (Audit Critical-4 Fix).

    SECURITY FIX (P1, review 2026-09-12): the JWT *signing secrets*
    (SUPREMEAI_JWT_SECRET / JWT_SECRET) were accepted as bearer passwords here.
    Any leak of those env values granted full worker-service access, and signing
    secrets must never double as credentials. Only dedicated worker tokens
    (WORKER_AUTH_TOKEN / INTERNAL_API_KEY / SUPREMEAI_API_KEY) are accepted now.
    """
    # Allow testing bypass only if explicitly enabled AND ENV is EXPLICITLY a
    # non-production value (Issue #512 / BE-06). Fail-closed: unset/empty ENV
    # is treated as production. The old check `os.getenv("ENV") != "production"`
    # let the bypass through when ENV was unset ("" != "production") or set to
    # "prod", so a leaked ALLOW_TEST_AUTH_BYPASS=true from a CI base image
    # fully bypassed worker auth in production.
    bypass_env_allowlist = ("dev", "development", "test", "local")
    env_value = (os.getenv("ENV") or "").strip().lower()
    if (
        os.getenv("ALLOW_TEST_AUTH_BYPASS", "").lower() in ("true", "1")
        and env_value in bypass_env_allowlist
    ):
        return

    expected_tokens: list[str] = [
        t
        for t in [
            os.getenv("WORKER_AUTH_TOKEN"),
            os.getenv("INTERNAL_API_KEY"),
            os.getenv("SUPREMEAI_API_KEY"),
        ]
        if t
    ]

    if not expected_tokens:
        # Fallback to loading from core.config if available
        try:
            from core.config import settings

            sec = getattr(settings, "supremeai_api_key", None)
            if sec and hasattr(sec, "get_secret_value"):
                expected_tokens.append(sec.get_secret_value())
        except Exception as e:
            logger.debug(f"Failed to load expected auth tokens from settings: {e}")

    if not expected_tokens:
        raise HTTPException(status_code=500, detail="Worker service security tokens not configured")

    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif request.headers.get("X-Worker-Token"):
        token = request.headers["X-Worker-Token"].strip()
    elif request.headers.get("X-API-Key"):
        token = request.headers["X-API-Key"].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Worker token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not any(secrets.compare_digest(token, expected) for expected in expected_tokens):
        raise HTTPException(status_code=403, detail="Forbidden: Invalid worker token")


def _celery_importable() -> bool:
    return importlib.util.find_spec("celery") is not None


def _redis_url() -> str | None:
    """Redis URL from env, falling back to core.config (lazy — that import can raise)."""
    if os.getenv("REDIS_URL"):
        return os.environ["REDIS_URL"]
    try:
        from core.config import settings

        return getattr(settings, "redis_url", None)
    except Exception:
        return None


def _spawn_celery() -> None:
    """Best-effort Celery subprocess spawn. Never raises."""
    try:
        if ROLE != "worker" or not _celery_importable() or not _redis_url():
            return
        _state["celery_proc"] = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "workers.celery_app",
                "worker",
                "--loglevel=INFO",
                "-c",
                "2",
            ],
            cwd=BACKEND_DIR,
            env=os.environ.copy(),
        )
        logger.info("[worker_service] celery spawned pid=%s", _state["celery_proc"].pid)
    except Exception as exc:  # HTTP service must survive celery/redis failures
        _state.update(degraded=True, detail=f"celery spawn failed: {exc}")


def _terminate_celery() -> None:
    proc: subprocess.Popen[bytes] | None = _state.get("celery_proc")
    if proc is None:
        return
    with contextlib.suppress(Exception):
        proc.terminate()
        proc.wait(timeout=10)


def _queue_call(op: str, *args: Any, **kwargs: Any) -> Any:
    """Run an async core.queue.task_queue_enhanced API in a fresh event loop.

    Runs inside a worker thread (via asyncio.to_thread) so asyncio.run is legal.
    Import is lazy: that module raises at import time when redis_url is missing
    (task_queue_enhanced.py ~line 583) — module top level here must never raise.
    """
    from core.queue import task_queue_enhanced as tq

    async def _inner() -> Any:
        result: Coroutine[Any, Any, Any] = getattr(tq, op)(*args, **kwargs)
        return await result

    return asyncio.run(_inner())


def _drain_once() -> dict[str, Any]:
    """Submit a no-op heartbeat through TaskQueue and await its result (e2e proof)."""
    from core.queue.task_queue_enhanced import get_task_queue

    async def _inner() -> dict[str, Any]:
        async def heartbeat() -> str:
            return "heartbeat-ok"

        queue = get_task_queue()
        task_id = await queue.submit_task(heartbeat, task_name="worker_heartbeat", timeout=30)
        result = await queue.get_result(task_id, timeout=30)
        return {"task_id": task_id, "status": result.status, "result": result.result}

    return asyncio.run(_inner())


@app.get("/")
async def root() -> dict[str, Any]:
    return {"service": "supremeai-worker", "status": "ok", "role": ROLE}


@app.get("/health")
async def health() -> dict[str, str]:
    """Process-level health — the HTTP wrapper is up (Render free-tier keepalive)."""
    return {"status": "ok", "service": "supremeai-worker"}


@app.get("/health/live")
@app.get("/api/v1/health/live")
async def liveness() -> JSONResponse:
    """Liveness reflects the critical queue dependency (Issue #508 / BE-02).

    Previously this returned a static 200, so Docker/Render HEALTHCHECK kept a
    worker whose Redis/queue was down "alive" and never restarted it. It now
    mirrors /health/ready semantics: 503 with the HealthStatus payload when
    the queue is unreachable, so the orchestrator can restart/route away from
    a broken instance.
    """
    queue_ok, detail = await _queue_available()
    payload = HealthStatus(
        status="ready" if queue_ok else "not_ready",
        role=ROLE,
        queue_configured=bool(_redis_url()),
        queue_available=queue_ok,
        celery_alive=_celery_alive(),
        detail=detail,
    )
    return JSONResponse(payload.model_dump(), status_code=200 if queue_ok else 503)


@app.get("/health/ready", response_model=HealthStatus)
async def readiness() -> JSONResponse:
    queue_ok, detail = await _queue_available()
    status = "ready" if queue_ok else "not_ready"
    payload = HealthStatus(
        status=status,
        role=ROLE,
        queue_configured=bool(_redis_url()),
        queue_available=queue_ok,
        celery_alive=_celery_alive(),
        detail=detail,
    )
    return JSONResponse(payload.model_dump(), status_code=200 if queue_ok else 503)


@app.get("/health/degraded", response_model=HealthStatus)
async def degraded_health() -> HealthStatus:
    queue_ok, detail = await _queue_available()
    return HealthStatus(
        status="degraded" if _state["degraded"] or not queue_ok else "ready",
        role=ROLE,
        queue_configured=bool(_redis_url()),
        queue_available=queue_ok,
        celery_alive=_celery_alive(),
        detail=detail or _state["detail"] or None,
    )


def _request_fingerprint(request: TaskContract) -> str:
    payload = request.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _use_durable_idempotency() -> bool:
    # Use memory in test runs where automation_executions table is not migrated
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING") == "true":
        return False
    try:
        from core.config import settings

        return bool(
            getattr(settings, "supabase_database_url", None)
            or getattr(settings, "database_url", None)
        )
    except Exception:
        return False


async def _claim_durable_idempotency(request: TaskContract, fingerprint: str) -> str | None:
    if not request.idempotency_key:
        return None
    workflow_key = f"worker:{request.tenant_id}"
    try:
        async with get_db_session_context() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO automation_executions
                        (id, event_id, workflow_key, provider, status, external_execution_id,
                         idempotency_key, trace_id)
                    VALUES (:id, :event_id, :workflow_key, 'supremeai-worker', 'PENDING',
                            '__pending__', :idempotency_key, :trace_id)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "event_id": str(uuid.uuid4()),
                    "workflow_key": workflow_key,
                    "idempotency_key": request.idempotency_key,
                    "trace_id": fingerprint,
                },
            )
            await session.commit()
            return None
    except IntegrityError:
        async with get_db_session_context() as session:
            result = await session.execute(
                text(
                    """
                    SELECT external_execution_id, trace_id
                    FROM automation_executions
                    WHERE workflow_key = :workflow_key AND idempotency_key = :idempotency_key
                    ORDER BY created_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {
                    "workflow_key": workflow_key,
                    "idempotency_key": request.idempotency_key,
                },
            )
            row = result.mappings().first()
            if not row or row["trace_id"] != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used with a different task payload",
                )
            if row["external_execution_id"] == "__pending__":
                raise HTTPException(
                    status_code=409,
                    detail="A task with this idempotency key is currently being submitted",
                )
            return row["external_execution_id"]


async def _finalize_durable_idempotency(request: TaskContract, task_id: str) -> None:
    if not request.idempotency_key:
        return
    async with get_db_session_context() as session:
        await session.execute(
            text(
                """
                UPDATE automation_executions
                SET external_execution_id = :task_id, status = 'QUEUED'
                WHERE workflow_key = :workflow_key AND idempotency_key = :idempotency_key
                """
            ),
            {
                "task_id": task_id,
                "workflow_key": f"worker:{request.tenant_id}",
                "idempotency_key": request.idempotency_key,
            },
        )
        await session.commit()


async def _claim_idempotency(request: TaskContract) -> tuple[str, str | None]:
    """Claim idempotency durably when SQL storage is configured; use memory only in tests/dev."""
    fingerprint = _request_fingerprint(request)
    if _use_durable_idempotency():
        return fingerprint, await _claim_durable_idempotency(request, fingerprint)
    if not request.idempotency_key:
        return fingerprint, None
    record_key = f"{request.tenant_id}:{request.idempotency_key}"
    async with _idempotency_lock:
        existing = _idempotency_records.get(record_key)
        if existing:
            if existing[0] != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used with a different task payload",
                )
            if not existing[1]:
                raise HTTPException(
                    status_code=409,
                    detail="A task with this idempotency key is currently being submitted",
                )
            return fingerprint, existing[1]
        if len(_idempotency_records) >= MAX_IDEMPOTENCY_RECORDS:
            _idempotency_records.pop(next(iter(_idempotency_records)))
        _idempotency_records[record_key] = (fingerprint, "")
    return fingerprint, None


async def _store_idempotency_task(request: TaskContract, task_id: str) -> None:
    if _use_durable_idempotency():
        await _finalize_durable_idempotency(request, task_id)
        return
    if not request.idempotency_key:
        return
    record_key = f"{request.tenant_id}:{request.idempotency_key}"
    async with _idempotency_lock:
        _idempotency_records[record_key] = (_request_fingerprint(request), task_id)


def _log_task_event(event: str, request: TaskContract, **fields: Any) -> None:
    logger.info(
        "worker_task_event",
        extra={
            "event": event,
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "correlation_id": request.correlation_id,
            "idempotency_key_present": bool(request.idempotency_key),
            **fields,
        },
    )


async def _process_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a validated, tenant-scoped task contract."""
    contract = TaskContract.model_validate(payload)
    metadata = contract.metadata
    capability = contract.capability
    if capability == "scrape":
        from utils.http_client import create_async_client

        scraper_url = (
            os.getenv("SCRAPER_URL")
            or os.getenv("SCRAPER_SERVICE_URL")
            or os.getenv("RENDER_SCRAPER_URL")
        )
        if not scraper_url:
            raise RuntimeError("A scraper service URL is required for scrape tasks")
        scraper_url = scraper_url.rstrip("/")
        url = metadata["url"]
        async with create_async_client(timeout=45.0) as client:
            response = await client.post(f"{scraper_url}/scrape", json={"url": url})
            response.raise_for_status()
            return {
                "capability": capability,
                "tenant_id": contract.tenant_id,
                "user_id": contract.user_id,
                "execution_id": contract.execution.execution_id if contract.execution else None,
                "trace_id": contract.execution.trace_id
                if contract.execution
                else contract.correlation_id,
                "data": response.json(),
            }
    if capability != "acknowledge":
        raise ValueError(f"Unsupported worker capability: {capability}")
    return {
        "capability": capability,
        "tenant_id": contract.tenant_id,
        "user_id": contract.user_id,
        "execution_id": contract.execution.execution_id if contract.execution else None,
        "trace_id": contract.execution.trace_id if contract.execution else contract.correlation_id,
        "goal": contract.goal,
        "metadata": metadata,
    }


@app.post("/tasks", dependencies=[Depends(_verify_worker_auth)])
async def submit_task(request: TaskContract) -> JSONResponse:
    try:
        _fingerprint, existing_task_id = await _claim_idempotency(request)
        if existing_task_id:
            _log_task_event("deduplicated", request, task_id=existing_task_id)
            return JSONResponse(
                {
                    "task_id": existing_task_id,
                    "status": "pending",
                    "deduplicated": True,
                    "correlation_id": request.correlation_id,
                },
                status_code=200,
            )

        from core.queue.task_queue_enhanced import get_task_queue

        queue = get_task_queue()
        task_id = await queue.submit_task(
            _process_task,
            request.model_dump(),
            task_name=f"supremeai_task:{request.capability}",
            max_retries=request.max_retries,
            timeout=request.timeout_seconds,
        )
        await _store_idempotency_task(request, task_id)
        _log_task_event("submitted", request, task_id=task_id, capability=request.capability)
        return JSONResponse(
            {"task_id": task_id, "status": "pending", "correlation_id": request.correlation_id},
            status_code=202,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _log_task_event("submission_failed", request, error_type=type(exc).__name__)
        _state.update(degraded=True, detail=f"task submit failed: {exc}")
        return JSONResponse({"status": "degraded", "detail": str(exc)[:200]}, status_code=503)


@app.get("/tasks/{task_id}", dependencies=[Depends(_verify_worker_auth)])
async def task_status(task_id: str) -> JSONResponse:
    try:
        from core.queue.task_queue_enhanced import get_task_queue

        status = await get_task_queue().get_status(task_id)
        if status == "unknown":
            raise HTTPException(status_code=404, detail="Task not found")
        return JSONResponse({"task_id": task_id, "status": status})
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post("/tasks/{task_id}/cancel", dependencies=[Depends(_verify_worker_auth)])
async def cancel_task(task_id: str) -> JSONResponse:
    try:
        from core.queue.task_queue_enhanced import get_task_queue

        cancelled = await get_task_queue().cancel_task(task_id)
        if not cancelled:
            raise HTTPException(status_code=409, detail="Task cannot be cancelled")
        return JSONResponse({"task_id": task_id, "status": "cancelled"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.get("/tasks/stats", dependencies=[Depends(_verify_worker_auth)])
async def tasks_stats() -> JSONResponse:
    try:
        stats = await asyncio.wait_for(
            asyncio.to_thread(_queue_call, "get_queue_stats"), timeout=10.0
        )
        return JSONResponse({"status": "ok", "stats": stats})
    except Exception as exc:
        _state.update(degraded=True, detail=f"queue stats failed: {exc}")
        return JSONResponse({"status": "degraded", "detail": str(exc)[:200]}, status_code=503)


@app.post("/tasks/drain", dependencies=[Depends(_verify_worker_auth)])
async def tasks_drain() -> JSONResponse:
    try:
        proof = await asyncio.wait_for(asyncio.to_thread(_drain_once), timeout=45.0)
        return JSONResponse({"status": "ok", "queue": "asyncio", **proof})
    except Exception as exc:
        _state.update(degraded=True, detail=f"drain failed: {exc}")
        return JSONResponse({"status": "degraded", "detail": str(exc)[:200]}, status_code=503)


@app.get("/worker/status", dependencies=[Depends(_verify_worker_auth)])
async def worker_status() -> dict[str, Any]:
    proc: subprocess.Popen[bytes] | None = _state.get("celery_proc")
    return {
        "service": "supremeai-worker",
        "role": ROLE,
        "celery_spawned": proc is not None,
        "celery_pid": proc.pid if proc else None,
        "celery_alive": bool(proc and proc.poll() is None),
        "redis_configured": _redis_url() is not None,
        "degraded": bool(_state["degraded"]),
        "detail": _state["detail"],
    }


def _start_kaggle_dispatcher() -> None:
    """Issue #439: run the Kaggle job dispatcher loop on the worker node.

    Previously get_next_job()/dispatch_job_to_kaggle() had ZERO callers — jobs
    submitted through the API sat in Redis forever.  This daemon thread owns an
    asyncio loop that pops queued jobs, selects a quota-available account, and
    pushes REAL kernels to Kaggle; results arrive via the token-authenticated
    callback.  Env-gated so primary/scraper nodes never dispatch.
    """
    if os.getenv("ENABLE_KAGGLE_DISPATCHER", "true").lower() != "true":
        logger.info("[kaggle-dispatcher] disabled via ENABLE_KAGGLE_DISPATCHER")
        return
    if ROLE != "worker":
        return

    def _loop() -> None:
        try:
            from core.kaggle_orchestrator import KaggleOrchestrator

            orchestrator = KaggleOrchestrator.get_instance()
        except Exception as exc:
            logger.warning(f"[kaggle-dispatcher] orchestrator unavailable, not starting: {exc}")
            return
        if not orchestrator.accounts or not orchestrator.redis_client:
            logger.info("[kaggle-dispatcher] no kaggle accounts or redis — dispatcher idle")
            return

        async def _run() -> None:
            logger.info(f"[kaggle-dispatcher] started with {len(orchestrator.accounts)} account(s)")
            while True:
                try:
                    job = await orchestrator.get_next_job()
                    if job is None:
                        await asyncio.sleep(10)
                        continue
                    account = await orchestrator.select_account_for_job(job)
                    if account is None:
                        await asyncio.sleep(30)
                        continue
                    await orchestrator.dispatch_job_to_kaggle(job, account)
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    logger.error(f"[kaggle-dispatcher] loop error: {exc}")
                    await asyncio.sleep(15)

        try:
            asyncio.run(_run())
        except Exception as exc:
            logger.warning(f"[kaggle-dispatcher] stopped: {exc}")

    import threading

    threading.Thread(target=_loop, name="kaggle-dispatcher", daemon=True).start()


# ── Process lifecycle (Issue #568 / BE-17) ───────────────────────────────────
# The atexit/signal cleanup, the Celery subprocess spawn and the Kaggle
# dispatcher thread used to run at IMPORT time, so any process that merely
# imported worker_service (openapi gen, schema_exporter, tests, lazy
# __getattr__) unconditionally forked a Celery subprocess and started
# dispatching Kaggle jobs. They are side effects of RUNNING the service, so
# they now happen only under `python worker_service.py` (the production
# entrypoint — docker-compose.yml command), never on import.
if __name__ == "__main__":
    # atexit is the reliable path; uvicorn replaces our signal handlers when
    # it installs its own, but both are registered.
    atexit.register(_terminate_celery)
    for _sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(ValueError, OSError):  # non-main thread / unsupported
            signal.signal(_sig, lambda *_: (_terminate_celery(), sys.exit(0)))

    _spawn_celery()
    _start_kaggle_dispatcher()

    uvicorn.run(app, host="0.0.0.0", port=PORT)
