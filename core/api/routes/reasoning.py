"""Feature S2: Reasoning/Thinking Display.

Exposes tree-of-thought and debate engine reasoning capabilities via REST
and SSE streaming endpoints.
"""

from __future__ import annotations

import json
import uuid
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.llm.llm_gateway.context import InferenceContext
from core.logging_config import logger
from engine.debate_engine import ConsensusOrchestrator, Proposal
from engine.tree_of_thought import TreeOfThoughtReasoner

router = APIRouter(
    prefix="/api/reasoning",
    tags=["Reasoning"],
    dependencies=[Depends(get_current_user_token)],
)


class ReasoningMode(StrEnum):
    TREE_OF_THOUGHT = "tree_of_thought"
    DEBATE = "debate"
    QUICK = "quick"


class ReasoningRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The prompt to reason about")
    mode: ReasoningMode = Field(
        default=ReasoningMode.QUICK,
        description="Reasoning strategy to use",
    )
    model_name: str | None = Field(
        default=None,
        description="Optional model override for the reasoning engine",
    )


class ReasoningStep(BaseModel):
    content: str
    score: float | None = None
    agent_id: str | None = None


class ReasoningResponse(BaseModel):
    reasoning_steps: list[ReasoningStep]
    final_answer: str
    confidence: float
    mode: str


async def _quick_reason(prompt: str, tenant_id: str = "anonymous") -> ReasoningResponse:
    """Perform a single LLM call asking for step-by-step reasoning."""
    from core.llm.llm_gateway import llm_gateway

    system_msg = (
        "You are a careful reasoning assistant. Break down the user's question "
        "into clear, numbered reasoning steps, then provide your final answer. "
        "Format your response exactly as follows:\n\n"
        "STEP 1: <reasoning>\n"
        "STEP 2: <reasoning>\n"
        "...\n"
        "ANSWER: <final answer>\n"
        "CONFIDENCE: <a float between 0.0 and 1.0>"
    )

    try:
        response = await llm_gateway.acompletion(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            # M03 P0-পূর্ণাংশ: context বাধ্যতামূলক — reasoning-খরচ টেন্যান্টে
            # অ্যাট্রিবিউটেড (আগে অদৃশ্য ছিল)।
            context=InferenceContext(tenant_id=tenant_id, task_type="reasoning", stream=False),
        )

        text = response.get("text", "") if isinstance(response, dict) else str(response)
    except Exception as e:
        logger.warning(f"Quick reasoning LLM call failed: {e}. Using fallback.")
        text = f"STEP 1: Analyzing the prompt: {prompt}\nANSWER: Unable to generate reasoning at this time.\nCONFIDENCE: 0.3"

    # Parse the structured response
    steps: list[ReasoningStep] = []
    final_answer = ""
    confidence = 0.5

    current_section = None
    section_buffer = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("STEP "):
            if current_section == "step" and section_buffer:
                steps.append(ReasoningStep(content=section_buffer.strip()))
            current_section = "step"
            section_buffer = line
        elif line.upper().startswith("ANSWER:"):
            if current_section == "step" and section_buffer:
                steps.append(ReasoningStep(content=section_buffer.strip()))
            current_section = "answer"
            section_buffer = line[len("ANSWER:") :].strip()
        elif line.upper().startswith("CONFIDENCE:"):
            current_section = "confidence"
            try:
                confidence = float(line.split(":", 1)[1].strip())
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, IndexError):
                confidence = 0.5
        elif current_section:
            section_buffer += "\n" + line

    # Flush remaining buffer
    if current_section == "step" and section_buffer:
        steps.append(ReasoningStep(content=section_buffer.strip()))
    elif current_section == "answer":
        final_answer = section_buffer.strip()

    # If parsing failed, put everything as a single step
    if not steps and not final_answer:
        steps.append(ReasoningStep(content=text))
        final_answer = text

    return ReasoningResponse(
        reasoning_steps=steps,
        final_answer=final_answer,
        confidence=confidence,
        mode="quick",
    )


async def _tree_of_thought_reason(prompt: str) -> ReasoningResponse:
    """Run the Tree-of-Thought reasoner."""
    reasoner = TreeOfThoughtReasoner(max_depth=3, num_branches=3)
    result = await reasoner.reason(prompt)

    steps = [
        ReasoningStep(
            content=path,
            score=None,
            agent_id=None,
        )
        for path in result.get("reasoning_path", [])
    ]

    # Add the best thought as the final high-scored step
    best_thought = result.get("best_thought", "")
    confidence_score = result.get("confidence_score", 0.5)
    if best_thought:
        steps.append(
            ReasoningStep(
                content=f"Best selected strategy: {best_thought}",
                score=confidence_score,
                agent_id="tot_selector",
            )
        )

    return ReasoningResponse(
        reasoning_steps=steps,
        final_answer=best_thought,
        confidence=confidence_score,
        mode="tree_of_thought",
    )


async def _debate_reason(prompt: str) -> ReasoningResponse:
    """Run the debate/consensus engine."""
    session_id = f"debate_{uuid.uuid4().hex[:12]}"
    orchestrator = ConsensusOrchestrator(session_id=session_id)

    winner: Proposal | None = await orchestrator.run_debate_cycle(prompt)

    if winner is None:
        return ReasoningResponse(
            reasoning_steps=[],
            final_answer="Debate failed to reach any conclusion.",
            confidence=0.0,
            mode="debate",
        )

    # Collect all proposals as reasoning steps
    steps = [
        ReasoningStep(
            content=p.content,
            score=p.score if p.score > 0 else None,
            agent_id=p.agent_id,
        )
        for p in orchestrator.proposals
        if p.content != "[PROPOSAL_GENERATION_FAILED]"
    ]

    return ReasoningResponse(
        reasoning_steps=steps,
        final_answer=winner.content,
        confidence=winner.score if winner.score > 0 else 0.5,
        mode="debate",
    )


@router.post("/think", response_model=ReasoningResponse)
async def think(
    payload: ReasoningRequest,
    token_payload: dict = Depends(get_current_user_token),
):
    """Run a reasoning process on the given prompt.

    Supports three modes:
    - ``tree_of_thought``: Explores multiple reasoning branches and selects the best.
    - ``debate``: Runs a multi-agent debate with Architect, Coder, and QA agents.
    - ``quick``: Single LLM call with step-by-step reasoning (default).
    """
    logger.info(f"Reasoning request: mode={payload.mode}, prompt='{payload.prompt[:80]}...'")

    try:
        # M03 P0-পূর্ণাংশ: token-থেকে টেন্যান্ট সত্য — context-এ যায়।
        tenant_id = str(
            token_payload.get("tenant_id")
            or token_payload.get("org_id")
            or token_payload.get("sub")
            or "anonymous"
        )
        if payload.mode == ReasoningMode.TREE_OF_THOUGHT:
            return await _tree_of_thought_reason(payload.prompt)
        elif payload.mode == ReasoningMode.DEBATE:
            return await _debate_reason(payload.prompt)
        else:
            return await _quick_reason(payload.prompt, tenant_id=tenant_id)
    except Exception as e:
        logger.error(f"Reasoning failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reasoning engine error: {e}") from e


@router.post("/think/stream")
async def think_stream(
    payload: ReasoningRequest,
    token_payload: dict = Depends(get_current_user_token),
):
    """Stream reasoning steps as Server-Sent Events.

    Each reasoning step is emitted as:
        ``data: {"type": "thinking", "step": N, "content": "..."}``

    The final answer is emitted as:
        ``data: {"type": "answer", "content": "..."}``

    The stream terminates with:
        ``data: [DONE]``
    """
    logger.info(f"Streaming reasoning request: mode={payload.mode}")

    async def event_generator():
        try:
            if payload.mode == ReasoningMode.TREE_OF_THOUGHT:
                # Stream tree-of-thought steps
                reasoner = TreeOfThoughtReasoner(max_depth=3, num_branches=3)
                result = await reasoner.reason(payload.prompt)

                paths = result.get("reasoning_path", [])
                for idx, path in enumerate(paths, start=1):
                    event_data = {
                        "type": "thinking",
                        "step": idx,
                        "content": path,
                        "agent_id": None,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

                # Emit the best thought as the answer
                best = result.get("best_thought", "")
                confidence = result.get("confidence_score", 0.5)
                answer_data = {
                    "type": "answer",
                    "content": best,
                    "confidence": confidence,
                }
                yield f"data: {json.dumps(answer_data)}\n\n"

            elif payload.mode == ReasoningMode.DEBATE:
                # Stream debate proposals
                session_id = f"debate_{uuid.uuid4().hex[:12]}"
                orchestrator = ConsensusOrchestrator(session_id=session_id)
                winner = await orchestrator.run_debate_cycle(payload.prompt)

                step_num = 0
                for proposal in orchestrator.proposals:
                    if proposal.content == "[PROPOSAL_GENERATION_FAILED]":
                        continue
                    step_num += 1
                    event_data = {
                        "type": "thinking",
                        "step": step_num,
                        "content": proposal.content,
                        "agent_id": proposal.agent_id,
                        "score": proposal.score if proposal.score > 0 else None,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

                if winner:
                    answer_data = {
                        "type": "answer",
                        "content": winner.content,
                        "confidence": winner.score if winner.score > 0 else 0.5,
                        "agent_id": winner.agent_id,
                    }
                    yield f"data: {json.dumps(answer_data)}\n\n"

            else:
                # Quick mode: stream step-by-step
                # M03 P0-পূর্ণাংশ: টেন্যান্ট context streaming পথেও যায়।
                result = await _quick_reason(
                    payload.prompt,
                    tenant_id=str(
                        token_payload.get("tenant_id")
                        or token_payload.get("org_id")
                        or token_payload.get("sub")
                        or "anonymous"
                    ),
                )

                for idx, step in enumerate(result.reasoning_steps, start=1):
                    event_data = {
                        "type": "thinking",
                        "step": idx,
                        "content": step.content,
                        "score": step.score,
                        "agent_id": step.agent_id,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

                answer_data = {
                    "type": "answer",
                    "content": result.final_answer,
                    "confidence": result.confidence,
                }
                yield f"data: {json.dumps(answer_data)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Streaming reasoning error: {e}")
            error_data = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )
