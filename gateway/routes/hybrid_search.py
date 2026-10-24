# SupremeAI 2.0 — Hybrid RAG Search API Router
# বাংলা মন্তব্য: এটি ডেন্স এবং স্পার্স হাইব্রিড সার্চের জন্য FastAPI এন্ডপয়েন্ট সরবরাহ করে।

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.rag.hybrid_retriever import HybridRetriever

router = APIRouter(prefix="/api/v1/rag", tags=["RAG Hybrid Search"])

global_retriever = HybridRetriever(rrf_k=60)


class IndexRequest(BaseModel):
    documents: list[dict[str, Any]]


class HybridSearchRequest(BaseModel):
    query: str
    top_k: int | None = 10
    dense_results: list[dict[str, Any]] | None = None


@router.post("/index")
async def index_documents(req: IndexRequest):
    """
    Index documents for hybrid retrieval.
    """
    if not req.documents:
        raise HTTPException(status_code=400, detail="Documents list cannot be empty")
    global_retriever.index_documents(req.documents)
    return {"status": "success", "indexed_count": len(req.documents)}


@router.post("/hybrid-search")
async def hybrid_search(req: HybridSearchRequest):
    """
    Perform Hybrid Search combining Dense vector search and BM25 sparse keyword search via RRF.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    results = global_retriever.hybrid_search(
        query=req.query, dense_vector_results=req.dense_results, top_k=req.top_k or 10
    )
    return {
        "status": "success",
        "query": req.query,
        "results_count": len(results),
        "results": results,
    }
