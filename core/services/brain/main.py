"""SupremeAI Tiny AI Brain Backend — 512MB Micro-Service.

বাংলা: আল্ট্রা-লাইটওয়েট মাইক্রো-এআই ব্রেন সার্ভিস। 
512MB RAM সিলিংয়ে চলার উপযোগী অপ্টিমাইজড FastAPI মাইক্রোসার্ভিস।
- মেমোরি কনজিউম কম (<100MB)
- দ্রুত মেগাস্ট্রিম বা ইনফারেন্স ক্যাশ রাউটিং
- মডেল ইনফারেন্স ডেলিগেশন ও হেলথ মেট্রিক্স
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("supremeai.tiny_brain")

# Auth header definition
API_KEY_NAME = "x-brain-token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

BRAIN_AUTH_TOKEN = os.getenv("BRAIN_AUTH_TOKEN", "")

# In-memory LRU cache for ultra-fast responses without Redis overhead
DECISION_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_MAX_ENTRIES = 500


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(">>> Booting SupremeAI 512MB Micro-AI Brain Backend...")
    yield
    logger.info(">>> Shutting down SupremeAI Tiny AI Brain Backend...")


app = FastAPI(
    title="SupremeAI Tiny Brain Service",
    description="Ultra-lightweight 512MB Micro-AI Decision Engine and Router",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_brain_token(token: Optional[str] = Depends(api_key_header)) -> bool:
    """Validate internal microservice authorization if BRAIN_AUTH_TOKEN is configured."""
    if not BRAIN_AUTH_TOKEN:
        return True
    if token != BRAIN_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized brain access")
    return True


# Schemas
class RouteRequest(BaseModel):
    task: str = Field(..., description="Task description or prompt")
    complexity: Optional[str] = Field("low", description="low | medium | high")
    preferred_provider: Optional[str] = Field("auto", description="auto | openrouter | gemini | local")
    context_length: Optional[int] = Field(0, description="Estimated token length")


class RouteDecision(BaseModel):
    recommended_model: str
    tier: str
    estimated_latency_ms: int
    delegation_url: Optional[str] = None
    cached: bool = False


class CognitiveEvalRequest(BaseModel):
    prompt: str
    options: List[str]


class CognitiveEvalResponse(BaseModel):
    selected_option: str
    confidence: float
    reasoning: str


@app.get("/")
def root():
    return {
        "service": "supremeai-tiny-brain",
        "status": "online",
        "memory_profile": "512MB-optimized",
        "timestamp": time.time(),
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "cache_size": len(DECISION_CACHE),
        "uptime": time.time(),
    }


@app.post("/v1/brain/route", response_model=RouteDecision)
def route_task(req: RouteRequest, authorized: bool = Depends(verify_brain_token)):
    """Ultra-fast deterministic model routing based on memory footprint and complexity."""
    cache_key = f"{req.task[:100]}_{req.complexity}_{req.preferred_provider}"
    if cache_key in DECISION_CACHE:
        cached_result = DECISION_CACHE[cache_key]
        cached_result["cached"] = True
        return cached_result

    # Minimal deterministic routing logic
    if req.complexity == "high" or req.context_length > 8000:
        decision = {
            "recommended_model": "google/gemini-2.5-pro",
            "tier": "flagship",
            "estimated_latency_ms": 950,
            "delegation_url": "https://openrouter.ai/api/v1",
            "cached": False,
        }
    elif req.complexity == "medium":
        decision = {
            "recommended_model": "google/gemini-2.5-flash",
            "tier": "standard",
            "estimated_latency_ms": 350,
            "delegation_url": "https://openrouter.ai/api/v1",
            "cached": False,
        }
    else:
        # Low complexity / Micro-AI
        decision = {
            "recommended_model": "google/gemma-2-9b-it:free",
            "tier": "zero-cost-micro",
            "estimated_latency_ms": 120,
            "delegation_url": "https://openrouter.ai/api/v1",
            "cached": False,
        }

    # Evict if cache exceeds threshold
    if len(DECISION_CACHE) >= CACHE_MAX_ENTRIES:
        DECISION_CACHE.pop(next(iter(DECISION_CACHE)))
    DECISION_CACHE[cache_key] = decision

    return decision


@app.post("/v1/brain/evaluate", response_model=CognitiveEvalResponse)
def evaluate_options(req: CognitiveEvalRequest, authorized: bool = Depends(verify_brain_token)):
    """Fast heuristics-based decision arbitrator without full LLM roundtrip overhead."""
    if not req.options:
        raise HTTPException(status_code=400, detail="Options list cannot be empty")

    # Lightweight heuristics scoring
    best_opt = req.options[0]
    best_score = 0.0

    prompt_tokens = set(req.prompt.lower().split())
    for opt in req.options:
        opt_tokens = set(opt.lower().split())
        overlap = len(prompt_tokens.intersection(opt_tokens))
        score = overlap / max(len(opt_tokens), 1)
        if score > best_score:
            best_score = score
            best_opt = opt

    confidence = min(round(0.5 + (best_score * 0.5), 2), 0.99)
    return {
        "selected_option": best_opt,
        "confidence": confidence,
        "reasoning": f"Heuristic overlap confidence score: {confidence}",
    }
