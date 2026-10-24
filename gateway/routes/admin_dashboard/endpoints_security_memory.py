"""Admin security telemetry endpoints — REAL data (Wave 2.5, issue #1242).

FIXED 2026-09-25 (gap-analysis re-run): the frontend SecurityDashboard called
``GET /admin-api/security/tasks`` and ``GET /admin-api/security/memory`` but
these routes did not exist, so the dashboard either errored or fell back to
static fabricated "[OK]" messages (Class-G false assurance). Both endpoints
now exist and read ONLY from real sources:

* ``core.utils.background_tasks`` — the live strong-reference task registry
  (same process, direct read) for tracked/untracked task counts;
* ``tracemalloc`` — real Python heap usage when tracing is active, else an
  explicit ``unavailable`` marker (never a fabricated number).
"""

from api.routes.admin_dashboard import router
from core.logging_config import logger
from core.utils.background_tasks import safe_create_task, security_memory_snapshot, snapshot_tasks


@router.get("/security/tasks")
async def get_security_tasks() -> dict:
    """Live strong-reference background-task registry (REAL, in-process)."""
    try:
        tasks = snapshot_tasks()
        mem = security_memory_snapshot()
        return {
            "status": "ok",
            "tasks": tasks,
            "trackedTasks": mem["trackedTasks"],
            "untrackedTasks": mem["untrackedTasks"],
        }
    except Exception as exc:
        logger.warning(f"security/tasks snapshot failed: {exc}")
        # honest failure — no fabricated task list
        return {
            "status": "error",
            "tasks": [],
            "trackedTasks": 0,
            "untrackedTasks": 0,
            "error": str(exc),
        }


@router.get("/security/memory")
async def get_security_memory() -> dict:
    """Real memory telemetry; heap fields are None + source 'unavailable'
    when tracemalloc is not active — the UI renders those honestly as '—'."""
    try:
        snap = security_memory_snapshot()
        return {
            "status": "ok",
            "heapUsed": snap["heapUsed"],
            "heapTotal": snap["heapTotal"],
            "heapSource": snap["heapSource"],
            "zombieTasksDetected": snap["zombieTasksDetected"],
            "failuresBlocked": snap["failuresBlocked"],
            "trackedTasks": snap["trackedTasks"],
            "untrackedTasks": snap["untrackedTasks"],
        }
    except Exception as exc:
        logger.warning(f"security/memory snapshot failed: {exc}")
        return {
            "status": "error",
            "heapUsed": None,
            "heapTotal": None,
            "heapSource": "unavailable",
            "zombieTasksDetected": 0,
            "failuresBlocked": 0,
            "trackedTasks": 0,
            "untrackedTasks": 0,
            "error": str(exc),
        }


# keep import used (safe_create_task re-exported for convenience of callers)
_ = safe_create_task
