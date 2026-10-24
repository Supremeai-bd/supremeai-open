from fastapi import APIRouter, Depends

from api.dependencies import get_current_admin

router = APIRouter(
    prefix="",
    tags=["Command Center"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/build/router")
async def get_router():
    return {"provider_order": [], "cost_quality_preference": 0.5}


@router.get("/build/providers")
async def list_providers():
    return []


@router.get("/build/skills")
async def list_skills():
    return []


@router.get("/build/memory")
async def get_memory():
    return {"banks": [], "semantic_cache_hit_rate": 0, "tokens_saved": 0}


@router.get("/build/knowledge")
async def get_knowledge():
    return {"docs_count": 0, "rag_index_status": "indexed"}
