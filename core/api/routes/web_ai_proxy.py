"""OpenAI-Compatible Web AI Session Reverse Proxy Router (askalf + auth2api + g4f inspired).

বাংলা সারসংক্ষেপ:
------------------
SupremeAI-এর জিরো-কস্ট সেশন পুলকে স্ট্যান্ডার্ড OpenAI API (/v1/chat/completions)-এ
এক্সপোজ করার FastAPI রাউটার।
এর ফলে যে কোনো বাইরের টুল (Cursor, Cline, Aider, Claude Code, বা আমাদের নিজস্ব এজেন্ট)
একে স্ট্যান্ডার্ড OpenAI এন্ডপয়েন্ট হিসেবে ব্যবহার করতে পারে।
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.deps import get_current_admin  # ROOT-CAUSE FIX (#2730): admin gate
from core.monitoring.logging_config import logger
from core.web_ai_session_bridge import (
    WebAISessionError,
    global_session_pool,
)

# ROOT-CAUSE FIX (#2730): entire /v1/* surface now requires admin auth.
# Previously: zero auth deps — any free-tier JWT holder could inject upstream
# tokens via /pool/accounts, poisoning the cascade for other tenants +
# bypassing CostGuard/tenant ledger. Constitution fail-closed-costguard violated.
router = APIRouter(
    prefix="/v1",
    tags=["web-ai-proxy"],
    dependencies=[Depends(get_current_admin)],  # admin-only — pool management is privileged
)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="auto-zero-cost", description="কাঙ্ক্ষিত মডেল বা সার্ভিস")
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: float | None = 0.7
    stream: bool = False


class AccountRegisterRequest(BaseModel):
    service: str = Field(
        ...,
        description="সার্ভিস বা নিউট্রাল নাম (core-architect, core-logic, core-design, core-speed, claude, chatgpt, v0)",
    )
    # ROOT-CAUSE FIX (#2828-পরিবার audit): #2730-এর সিকিউরিটি ফিক্স হ্যান্ডলারে
    # body-টোকেন প্রত্যাখ্যান করে, কিন্তু মডেলে `token: str` required থেকে গিয়েছিল —
    # ফলে token-সহ পাঠালে সিকিউরিটি-422, না পাঠালে validation-422: এন্ডপয়েন্ট
    # সম্পূর্ণ অব্যবহারযোগ্য (dead endpoint)। চুক্তি: token ঐচ্ছিক — দিলে প্রত্যাখ্যাত,
    # না দিলে vault/env থেকে resolve।
    token: str | None = None
    account_id: str | None = None


def _resolve_service_from_model(model_name: str) -> tuple[str, tuple[str, ...]]:
    """
    বাংলা মন্তব্য:
    মডেলের নাম থেকে প্রায়োরিটি সার্ভিস ও ফলব্যাক চেইন নির্ধারণ করা।
    নিউট্রাল/ক্যামোফ্লেজ আইডি (core-architect, core-logic, core-design, core-speed, auto-zero-cost)
    ও লিটারাল নাম উভয়কেই সাপোর্ট করে।
    """
    m = model_name.lower().strip()
    if "architect" in m or "claude" in m:
        return "claude", ("claude", "chatgpt", "v0")
    if "logic" in m or "gpt" in m or "chatgpt" in m or "openai" in m:
        return "chatgpt", ("chatgpt", "claude", "v0")
    if "design" in m or "v0" in m:
        return "v0", ("v0", "claude", "chatgpt")
    if "speed" in m or "gemini" in m:
        return "claude", ("claude", "chatgpt", "v0")
    # ডিফল্ট অটো চেইন
    return "claude", ("claude", "chatgpt", "v0")


@router.post("/chat/completions")
async def chat_completions(payload: ChatCompletionRequest):
    """
    বাংলা সারসংক্ষেপ:
    ------------------
    স্ট্যান্ডার্ড OpenAI /v1/chat/completions এন্ডপয়েন্ট।
    মাল্টি-অ্যাকাউন্ট রোটেশন এবং ক্রস-প্রোভাইডার ক্যাস্কেড সহ ইনফারেন্স চালায়।
    """
    preferred_service, fallback_chain = _resolve_service_from_model(payload.model)

    # সিস্টেম প্রম্পট ও ইউজার প্রম্পট আলাদা করা
    system_prompts: list[str] = []
    user_prompts: list[str] = []

    for msg in payload.messages:
        if msg.role == "system":
            system_prompts.append(msg.content)
        elif msg.role in ("user", "assistant"):
            user_prompts.append(f"{msg.role.upper()}: {msg.content}")

    system_text = "\n".join(system_prompts) if system_prompts else None
    prompt_text = "\n".join(user_prompts)

    if not prompt_text:
        raise HTTPException(status_code=400, detail="No prompt or user messages provided.")

    try:
        # বাংলা মন্তব্য: গ্লোবাল পুল দিয়ে ক্যাস্কেড এক্সিকিউশন
        response = await global_session_pool.complete_with_cascade(
            prompt=prompt_text,
            system_prompt=system_text,
            preferred_service=preferred_service,
            fallback_chain=fallback_chain,
            model=payload.model,
        )
        return response
    except WebAISessionError as exc:
        logger.error(f"[WebAIProxy] All cascade providers failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Web AI Session Proxy failure: {exc}")
    except Exception as exc:
        # ROOT-CAUSE FIX (#2730): don't leak internal exception text to client.
        # Contrast with the correlation-id-only pattern in api/routes/admin.py:72-77.
        logger.error(f"[WebAIProxy] Unexpected error in chat completion: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error — check server logs")


@router.get("/models")
async def list_models():
    """বাংলা মন্তব্য: উপলব্ধ মডেলগুলোর তালিকা (নিউট্রাল ও অডিট-সেফ নাম)।"""
    available_models = [
        {
            "id": "core-architect",
            "object": "model",
            "owned_by": "supremeai-session-pool",
            "description": "Deep architectural reasoning, complex system design, and zero-cost synthesis",
        },
        {
            "id": "core-logic",
            "object": "model",
            "owned_by": "supremeai-session-pool",
            "description": "High-speed backend logic, algorithm refinement, and refactoring",
        },
        {
            "id": "core-design",
            "object": "model",
            "owned_by": "supremeai-session-pool",
            "description": "Frontend UI component synthesis, layout styling, and design system crafting",
        },
        {
            "id": "core-speed",
            "object": "model",
            "owned_by": "supremeai-session-pool",
            "description": "Low-latency summary, rapid sweep analysis, and quick completions",
        },
        {
            "id": "auto-zero-cost",
            "object": "model",
            "owned_by": "supremeai-session-pool",
            "description": "Adaptive zero-cost cascade routing across active compute nodes",
        },
    ]
    return {"object": "list", "data": available_models}


@router.get("/pool/status")
async def pool_status():
    """বাংলা মন্তব্য: মাল্টি-অ্যাকাউন্ট পুলের বর্তমান স্বাস্থ্য ও সক্রিয় অ্যাকাউন্ট সংখ্যা।"""
    return global_session_pool.get_pool_status()


@router.post("/pool/accounts")
async def register_pool_account(body: AccountRegisterRequest):
    """বাংলা মন্তব্য: পুলে ডায়নামিকালি নতুন অ্যাকাউন্ট/টোকেন ইনজেক্ট করা।

    ROOT-CAUSE FIX (#2730): previously accepted `token` from request body —
    any admin could inject arbitrary upstream tokens, poisoning the cascade
    for other tenants. Now: token must be None (pool derives from vault/env)
    or match a vault-keyed reference. Request-body tokens are rejected.
    """
    # ROOT-CAUSE FIX (#2730): reject request-body tokens — pool accounts must
    # be derived from vault/env, not client-supplied strings. This prevents
    # pool poisoning + CostGuard bypass.
    if body.token:
        raise HTTPException(
            status_code=422,
            detail="Pool account tokens must be provisioned via vault/env, not request body. "
            "POST /pool/accounts with service+account_id only — the pool will resolve "
            "the token from the secret vault.",
        )
    # Token-less registration: pool will resolve from vault at first use
    acc = global_session_pool.register_account(
        service=body.service,
        token=None,  # ROOT-CAUSE FIX (#2730): never accept body token
        account_id=body.account_id,
    )
    return {
        "status": "success",
        "service": acc.service,
        "account_id": acc.account_id,
        "is_active": acc.is_active,
    }


class ParallelTaskItem(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    prompt: str
    service: str = Field(
        default="auto",
        description="সার্ভিস বা নিউট্রাল নাম (core-architect, core-logic, core-design, core-speed, auto)",
    )
    model: str | None = None
    system_prompt: str | None = None


class ParallelTasksRequest(BaseModel):
    tasks: list[ParallelTaskItem] = Field(..., min_length=1, max_length=20)
    concurrency_limit: int = Field(default=5, ge=1, le=20)


@router.post("/tasks/parallel")
async def parallel_chat_completions(payload: ParallelTasksRequest):
    """
    বাংলা সারসংক্ষেপ:
    ------------------
    একই সাথে একাধিক সেশনে ভিন্ন ভিন্ন AI-কে ভিন্ন ভিন্ন কাজের দায়িত্ব সমান্তরালে (Parallel) সম্পাদন।
    যেমন:
      - Task 1: Claude (Frontend Design)
      - Task 2: ChatGPT (Backend API & Database)
      - Task 3: v0 (React UI Components)
    """
    task_dicts = [t.model_dump() for t in payload.tasks]
    try:
        results = await global_session_pool.execute_parallel_tasks(
            tasks=task_dicts,
            concurrency_limit=payload.concurrency_limit,
        )
        return results
    except Exception as exc:
        logger.error(f"[WebAIProxy] Parallel execution error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


class PromptEnhanceRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="মূল প্রম্পট")
    mode: str = Field(
        default="dual_ai_conductor",
        description="মোড: dual_ai_conductor ('Copy this to your AI:' অটোনোমাস ব্লুপ্রিন্ট), stealth_chat, ui_sparkle, dev_api",
    )
    current_file_path: str | None = None
    selected_code: str | None = None
    language: str | None = None
    user_intent: str | None = None


@router.post("/prompt/enhance")
async def enhance_prompt_endpoint(payload: PromptEnhanceRequest):
    """
    বাংলা সারসংক্ষেপ:
    ------------------
    প্রম্পট অপ্টিমাইজেশন ও অ্যান্টি-বট কেমোফ্লেজ এন্ডপয়েন্ট।
    Mode 'stealth_chat' নির্বাচন করলে এটি অন্য চ্যাট থেকে কপি করে পেস্ট করার স্বাভাবিক আচরণ ধারণ করে।
    """
    from core.prompt_enhancement_engine import (
        EnhancementContext,
        EnhancementMode,
        default_enhancer,
    )

    try:
        mode_enum = EnhancementMode(payload.mode)
    except ValueError:
        mode_enum = EnhancementMode.STEALTH_CHAT

    context = EnhancementContext(
        current_file_path=payload.current_file_path,
        selected_code=payload.selected_code,
        language=payload.language,
        user_intent=payload.user_intent,
    )

    result = default_enhancer.enhance(
        prompt=payload.prompt,
        mode=mode_enum,
        context=context,
    )

    return {
        "original_prompt": result.original_prompt,
        "enhanced_prompt": result.enhanced_prompt,
        "mode": result.mode.value,
        "applied_tricks": result.applied_tricks,
        "confidence_score": result.confidence_score,
    }


class OrchestratePlanRequest(BaseModel):
    raw_ai_output: str
    repo_name: str = "SaifulHaqueNiloy/supremeai"
    branch: str = "main"
    source_platform: str = "generic_ai"


class OrchestrateApplyRequest(BaseModel):
    file_actions: list[dict[str, Any]]
    verification_commands: list[str] = Field(default_factory=list)
    workspace_root: str | None = None


@router.post("/orchestrator/parse-and-plan")
async def parse_orchestration_plan(payload: OrchestratePlanRequest):
    """
    বাংলা সারসংক্ষেপ:
    ------------------
    Genkit, ChatGPT, Claude বা Gemini-এর কাঁচা টেক্সট আউটপুট থেকে
    স্বয়ংক্রিয়ভাবে ফাইল এডিট এবং ১-ক্লিক Codespaces/Gitpod ডিপ-লিঙ্ক তৈরি করে।
    """
    from core.multi_platform_orchestrator import default_orchestrator

    plan = default_orchestrator.parse_ai_output(
        raw_output=payload.raw_ai_output,
        repo_name=payload.repo_name,
        branch=payload.branch,
        source_platform=payload.source_platform,
    )

    return {
        "engine_brand": plan.engine_brand,
        "platform_agnostic_summary": plan.platform_agnostic_summary,
        "supreme_workspace_url": plan.supreme_workspace_url,
        "source_platform": plan.source_platform,
        "file_actions": [
            {
                "file_path": a.file_path,
                "action_type": a.action_type.value,
                "content_preview": a.content[:200] + "..." if len(a.content) > 200 else a.content,
                "language": a.language,
            }
            for a in plan.file_actions
        ],
        "verification_commands": plan.verification_commands,
        "codespaces_url": plan.codespaces_url,
        "gitpod_url": plan.gitpod_url,
        "jules_url": plan.jules_url,
        "explanation": plan.explanation,
    }


__all__ = ["router"]
