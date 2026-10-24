from fastapi import APIRouter

router = APIRouter(prefix="/ws/command-center", tags=["Command Center WS"])


@router.get("/health")
async def ws_health():
    return {"status": "ok"}
