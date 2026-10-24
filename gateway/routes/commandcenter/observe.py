from fastapi import APIRouter, Depends

from api.dependencies import get_current_admin

router = APIRouter(
    prefix="",
    tags=["Command Center"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/observe/metrics")
# Issue #1665: these handlers return static/aggregated data with no
# await — plain `def` routes (FastAPI runs them in the threadpool)
# instead of `async def` coroutines that never await. HTTP contract
# unchanged; only the event-loop scheduling semantics are corrected.

def get_metrics():
    return {}


@router.get("/observe/logs")
def get_logs():
    return []


@router.get("/observe/events")
def get_events():
    return []


@router.get("/observe/ci")
def get_ci():
    return []


@router.get("/observe/health")
def get_health():
    return {
        "gcp": {"status": "unknown"},
        "railway": {"status": "unknown"},
        "render": {"status": "unknown"},
        "overall_health_percent": 0,
    }


@router.get("/observe/traffic")
def get_traffic():
    return {"current_rps": 0, "window_30min": [], "distribution": {}}
