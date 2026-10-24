# backend/api/routes/deep_research.py
"""Feature S12: Deep Research Mode.

Orchestrates a multi-step research pipeline that parses queries, generates
sub-queries, executes web searches, indexes findings, identifies gaps, and
synthesises a structured report with citations.

Provides both a synchronous endpoint and an SSE streaming variant.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import db as supabase_db

router = APIRouter(
    prefix="/api/research",
    tags=["Deep Research"],
    dependencies=[Depends(get_current_user_token)],
)

# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_RESEARCH_SQL = """
CREATE TABLE IF NOT EXISTS deep_research_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    report JSONB,
    steps_completed INTEGER DEFAULT 0,
    total_sources INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_research_bootstrapped = False

#: Columns returned by GET /history. চুক্তি (M08 P-A): ``report`` অবশ্যই
#: থাকবে — ফ্রন্টএন্ড ResearchHistoryItem.report এই ফিল্ড থেকেই ভরে;
#: এটি বাদ দিলে ইতিহাস-ভিউয়ার স্থায়ীভাবে "Report not available" দেখায়।
HISTORY_SELECT_COLUMNS = "id, query, status, steps_completed, total_sources, created_at, report"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DeepResearchRequest(BaseModel):
    """Body for initiating a deep research session."""

    query: str = Field(..., min_length=3, description="The research question.")
    max_steps: int = Field(default=10, ge=3, le=20, description="Maximum pipeline steps.")
    conversation_id: str | None = Field(None, description="Optional conversation to attach to.")


class ResearchStepEvent(BaseModel):
    """A single step event emitted during streaming."""

    type: str = "step"
    step: int = 0
    name: str = ""
    content: str = ""


class ReportSection(BaseModel):
    title: str
    content: str
    sources: list[str] = Field(default_factory=list)


class ResearchReport(BaseModel):
    title: str
    sections: list[ReportSection] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)
    summary: str = ""


class DeepResearchResponse(BaseModel):
    """Final response for a completed deep research session."""

    id: str
    report: ResearchReport
    steps_completed: int
    total_sources: int


class ResearchSessionSummary(BaseModel):
    """Lightweight summary for listing past sessions."""

    id: str
    query: str
    status: str
    steps_completed: int
    total_sources: int
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_schema() -> None:
    global _research_bootstrapped
    if _research_bootstrapped:
        return
    if not supabase_db.client:
        raise HTTPException(status_code=503, detail="Database is not available.")
    try:
        supabase_db.client.rpc("exec_sql", {"query_string": _RESEARCH_SQL}).execute()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")
    _research_bootstrapped = True


def _save_session(
    session_id: str,
    user_id: str,
    query: str,
    report: dict | None,
    steps_completed: int,
    total_sources: int,
    status: str,
) -> None:
    """Persist or update a research session row."""
    if not supabase_db.client:
        return
    now = datetime.now(UTC).isoformat()
    try:
        supabase_db.client.table("deep_research_sessions").upsert(
            {
                "id": session_id,
                "user_id": user_id,
                "query": query,
                "report": report,
                "steps_completed": steps_completed,
                "total_sources": total_sources,
                "status": status,
                "updated_at": now,
            }
        ).execute()
    except Exception as exc:
        logger.warning(f"Failed to save research session {session_id}: {exc}")


async def _llm_call(prompt: str, user_id: str, task_type: str = "deep_research") -> str:
    """Invoke the LLM gateway and extract the text response."""
    try:
        from core.llm.llm_gateway import llm_gateway
        from core.llm.llm_gateway.context import InferenceContext

        resp = await llm_gateway.acompletion(
            prompt=prompt,
            # M03 P0-পূর্ণাংশ: context বাধ্যতামূলক — deep-research খরচ
            # টেন্যান্ট user_id-তে অ্যাট্রিবিউটেড হয়।
            context=InferenceContext(
                tenant_id=str(user_id) if user_id else "anonymous",
                task_type=task_type,
                stream=False,
            ),
            timeout=30.0,
        )
        if isinstance(resp, dict):
            return resp.get("text", "") or str(resp)
        if hasattr(resp, "choices") and resp.choices:
            return resp.choices[0].message.content or ""
        return str(resp)
    except Exception as exc:
        logger.error(f"LLM call failed ({task_type}): {exc}")
        return ""


async def _scout_search(query: str, tenant_id: str) -> list[dict[str, str]]:
    """Governed scout crawl search (MASTER_PLAN Phase 1: "Scout goes live").

    বাংলা: আগে scout crawler ছিল API-র চোখে dead code — এখন deep research-এর
    web search প্রথমে টেন্যান্টের *সক্রিয়* CrawlPolicy মেনে governed crawl চালায়
    (robots.txt, rate pacing, SSRF gate, dedup, zero-token summary)। Policy না
    থাকলে বা crawl খালি হলে কলার browser fallback-এ ফিরে যায় (Graceful
    Degradation)। প্রতিটি crawl-এর ফলাফল durable history-তে রেকর্ড হয় —
    research উত্তর এখন governed সোর্স cite করে (B2 battlefield fuel)।
    """
    results: list[dict[str, str]] = []
    try:
        from urllib.parse import quote_plus

        from scout.crawler import CrawlerService
        from scout.models import CrawlRequest
        from scout.persistence import get_active_policy, record_crawl_response

        tenant_id = str(tenant_id).strip()
        if not tenant_id:
            return []
        policy = await get_active_policy(tenant_id)
        if policy is None:
            # বাংলা: Policy Before Power — সক্রিয় policy না থাকলে scout কিছুই crawl করে না।
            return []

        service = CrawlerService(policy=policy)
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        resp = await service.execute_crawl(
            CrawlRequest(
                query_or_url=search_url,
                tenant_id=tenant_id,
                max_depth=1,
                max_results=min(policy.max_results, 8),
            )
        )
        await record_crawl_response(resp)

        for page in resp.pages:
            if page.is_duplicate or not page.url:
                continue
            snippet = " ".join((page.content or "").split())[:280]
            results.append(
                {
                    "title": page.title or page.url,
                    "url": page.url,
                    "snippet": snippet,
                    "source": "scout",
                }
            )
    except Exception as exc:
        logger.warning(f"Scout search failed for '{query[:60]}': {exc}")
    return results


async def _web_search(query: str, user_id: str = "") -> list[dict[str, str]]:
    """Scout-first web search with browser-agent fallback.

    বাংলা: Phase 1 — governed scout crawl (tenant policy মেনে) প্রথম প্রচেষ্টা;
    সেটি ফাঁকা হলে পুরোনো autonomous-browser path (LLM-চালিত) fallback হিসেবে
    চলে। ফলাফল: [{title, url, snippet}]।
    """
    results: list[dict[str, str]] = []
    try:
        from scout.persistence import get_active_policy

        tenant_id = str(user_id).strip()
        if not tenant_id:
            return []
        if await get_active_policy(tenant_id) is not None:
            results = await _scout_search(query, tenant_id)
    except Exception as exc:
        logger.warning(f"Scout search gate check failed for '{query[:60]}': {exc}")
    if results:
        return results

    # Issue #447 fix: the old fallback here launched AutonomousBrowserAgent,
    # whose _decide_action ignores the goal entirely (hardcoded 3-step tour of
    # supremeai.dev) and whose navigate action never touches a browser — it
    # could only ever return a fabricated summary that failed JSON parsing
    # anyway.  Zero real sources is an honest outcome; a fake-looking report
    # is not.  Scout stays strictly CrawlPolicy-gated.
    if not results:
        logger.warning(
            "Web search yielded no results for '%s' (scout policy-gated or "
            "unavailable) — returning no sources honestly (issue #447; the "
            "scripted fake-browser fallback was removed).",
            query[:60],
        )
    return results


def _index_findings(findings: list[dict[str, str]], user_id: str) -> int:
    """Index scraped data via the KnowledgeBaseIndexer. Returns count indexed."""
    try:
        from tools.knowledge.knowledge_base_indexer import KnowledgeBaseIndexer

        indexer = KnowledgeBaseIndexer()
        data_to_index = [
            {
                "content": f.get("snippet", ""),
                "source": f.get("url", ""),
                "title": f.get("title", ""),
            }
            for f in findings
        ]
        result = indexer.index_scraped_data(data_to_index)
        return result.get("indexed", len(data_to_index))
    except Exception as exc:
        logger.warning(f"Knowledge indexing failed: {exc}")
        return 0


# ---------------------------------------------------------------------------
# Research pipeline
# ---------------------------------------------------------------------------


async def _run_research_pipeline(
    query: str,
    user_id: str,
    max_steps: int,
    on_step: Any | None = None,
    session_id: str | None = None,
) -> tuple[dict[str, Any], int, int]:
    """Execute the full research pipeline.

    Returns (report_dict, steps_completed, total_sources).
    If *on_step* is a callable it receives (step_number, step_name, content).
    When *session_id* is provided every step is also streamed to the session
    SSE channel as a reasoning step (Phase 1: visible intelligence).
    """
    steps_completed = 0
    all_sources: list[dict[str, str]] = []

    async def emit(step: int, name: str, content: str) -> None:
        nonlocal steps_completed
        steps_completed = step
        if session_id:
            try:
                from core.observability.reasoning_stream import emit_reasoning_step

                emit_reasoning_step(session_id, step=step, content=f"{name}: {content}")
            except Exception as emit_err:  # reasoning never breaks research
                # বাংলা মন্তব্য: fail-open ইচ্ছাকৃত — টেলিমেট্রি ব্যর্থ হলেও গবেষণা
                # চলবে, কিন্তু নীরব নয়: debug লগে কারণ রেখে দিচ্ছি যাতে ভাঙা
                # reasoning-stream কেউ খেয়াল না করে বলে লুকিয়ে না যায়।
                # (loguru: %-args/exc_info কাজ করে না — f-string বাধ্যতামূলক)
                logger.debug(f"reasoning_stream emit failed (research continues): {emit_err}")
        if on_step:
            if callable(on_step):
                on_step(step, name, content)
            else:
                await on_step(step, name, content)

    # --- Step 1: Parse and refine the research query ---
    refined = query
    try:
        refine_prompt = (
            "You are a research query optimiser. Rewrite the following research query "
            "to be more specific, actionable, and comprehensive. Output ONLY the refined query, "
            "nothing else.\n\n"
            f"Original query: {query}"
        )
        refined = await _llm_call(refine_prompt, user_id)
        refined = refined.strip().strip('"').strip("'") or query
    except Exception:
        refined = query
    await emit(1, "Parsing query", f"Refined query: {refined}")

    # --- Step 2: Generate sub-queries (3-5) ---
    sub_queries: list[str] = [refined]
    try:
        sub_prompt = (
            f'Given the research question: "{refined}"\n\n'
            "Generate 4 specific sub-queries that together would comprehensively answer this question. "
            "Return a JSON array of strings, nothing else."
        )
        raw = await _llm_call(sub_prompt, user_id)
        import re

        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                sub_queries = [q for q in parsed if isinstance(q, str) and len(q) > 3][:5]
    except Exception as exc:
        logger.warning(f"Sub-query generation failed: {exc}")
    await emit(
        2,
        "Generating sub-queries",
        f"Generated {len(sub_queries)} sub-queries: " + "; ".join(sub_queries[:3]),
    )

    # --- Step 3: Execute web searches ---
    search_results: list[dict[str, str]] = []
    for sq in sub_queries:
        results = await _web_search(sq, user_id)
        search_results.extend(results)
    all_sources = search_results
    await emit(
        3,
        "Executing web searches",
        f"Found {len(search_results)} results across {len(sub_queries)} queries.",
    )

    # --- Step 4: Index findings via knowledge_base_indexer ---
    indexed_count = _index_findings(search_results, user_id)
    await emit(
        4,
        "Indexing findings",
        f"Indexed {indexed_count} results into the knowledge base.",
    )

    # --- Step 5: Extract key information ---
    key_info_parts: list[str] = []
    for i, src in enumerate(search_results[:15]):
        snippet = src.get("snippet", "")
        if snippet:
            key_info_parts.append(f"[{src.get('title', 'Source')}]: {snippet}")

    key_info_text = (
        "\n".join(key_info_parts) if key_info_parts else "No detailed snippets available."
    )
    await emit(
        5,
        "Extracting key information",
        f"Extracted information from {len(key_info_parts)} sources.",
    )

    # --- Step 6: Identify gaps and generate follow-up queries ---
    follow_up_queries: list[str] = []
    try:
        gap_prompt = (
            f"Research question: {refined}\n\n"
            f"Information found so far:\n{key_info_text[:3000]}\n\n"
            "Identify 2-3 important gaps or missing perspectives in this research. "
            "Return a JSON array of follow-up search queries (strings only)."
        )
        raw = await _llm_call(gap_prompt, user_id)
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                follow_up_queries = [q for q in parsed if isinstance(q, str) and len(q) > 3][:3]
    except Exception as exc:
        logger.warning(f"Gap analysis failed: {exc}")
    await emit(
        6,
        "Identifying research gaps",
        f"Found {len(follow_up_queries)} follow-up queries to fill gaps.",
    )

    # --- Step 7: Execute follow-up searches ---
    follow_results: list[dict[str, str]] = []
    for fq in follow_up_queries:
        results = await _web_search(fq, user_id)
        follow_results.extend(results)
    all_sources.extend(follow_results)
    await emit(
        7,
        "Executing follow-up searches",
        f"Found {len(follow_results)} additional results from follow-up searches.",
    )

    # --- Step 8: Synthesize all findings ---
    all_findings_text = "\n".join(
        f"- [{s.get('title', 'Untitled')}] {s.get('snippet', '')}" for s in all_sources[:20]
    )
    synthesis = ""
    if not all_sources:
        # Issue #447 fix: zero real sources = nothing to synthesize. The old
        # path still prompted the LLM, which happily authored a coherent-looking
        # analysis (and downstream, "citations") from empty findings.
        synthesis = (
            "No web sources could be retrieved for this research request: the "
            "scout crawler is CrawlPolicy-gated and no active policy exists for "
            "this tenant (issue #447 honest-mode)."
        )
        await emit(
            8,
            "No sources available",
            "Zero real sources retrieved — synthesis skipped (honest mode).",
        )
    else:
        try:
            synth_prompt = (
                f"Research question: {refined}\n\n"
                f"All findings:\n{all_findings_text[:5000]}\n\n"
                "Synthesize all findings into a coherent, well-structured analysis. "
                "Include key insights, patterns, and important details. "
                "Reference sources by their title in brackets when relevant. "
                "Only cite sources that appear in the findings list; if the "
                "findings do not cover some aspect, say so explicitly instead "
                "of inventing information."
            )
            synthesis = await _llm_call(synth_prompt, user_id, task_type="deep_research_synthesis")
        except Exception as exc:
            logger.warning(f"Synthesis failed: {exc}")
            synthesis = "Synthesis generation failed. See sources for raw findings."
        await emit(
            8,
            "Synthesizing findings",
            f"Synthesized {len(all_sources)} sources into a coherent analysis.",
        )

    # --- Step 9: Generate structured report with citations ---
    report_dict: dict[str, Any] = {
        "title": refined,
        "sections": [],
        "sources": [
            {"title": s.get("title", ""), "url": s.get("url", ""), "snippet": s.get("snippet", "")}
            for s in all_sources
        ],
        "summary": "",
    }
    if not all_sources:
        # Issue #447 fix: honest no-source report — never a cited-looking fake.
        report_dict["sections"] = [
            {"title": "No Sources Retrieved", "content": synthesis, "sources": []}
        ]
        report_dict["summary"] = (
            "No live web sources could be gathered for this query. Configure a "
            "tenant CrawlPolicy (scout) to enable live research."
        )
        report_dict["no_web_sources"] = True
        await emit(9, "Generating structured report", "No-source honest report generated.")
    else:
        try:
            report_prompt = (
                f"Create a structured research report on: {refined}\n\n"
                f"Synthesized analysis:\n{synthesis[:4000]}\n\n"
                f"Available sources (use titles for citations):\n{all_findings_text[:4000]}\n\n"
                "Return a JSON object with this exact structure:\n"
                '{"title": "...", "summary": "2-3 sentence summary", '
                '"sections": [{"title": "Section Title", "content": "Section content with [Source Title] citations", '
                '"sources": ["Source Title 1", "Source Title 2"]}], '
                '"sources": [{"title": "...", "url": "...", "snippet": "..."}]}\n\n'
                "Return ONLY the JSON object, no other text."
            )
            raw_report = await _llm_call(report_prompt, user_id, task_type="deep_research_report")
            json_match = re.search(r"\{.*\}", raw_report, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict):
                    report_dict = {
                        "title": parsed.get("title", refined),
                        "sections": parsed.get("sections", []),
                        "sources": parsed.get("sources", report_dict["sources"]),
                        "summary": parsed.get("summary", ""),
                    }
        except Exception as exc:
            logger.warning(f"Structured report generation failed: {exc}")
            report_dict["summary"] = (
                synthesis[:1000] if synthesis else "Report generation encountered an error."
            )
            report_dict["sections"] = [{"title": "Findings", "content": synthesis, "sources": []}]
        await emit(9, "Generating structured report", f"Report titled: {report_dict['title']}")

    # --- Step 10: Store results in memory ---
    try:
        from services.memory_service import save_memory

        await save_memory(
            session_id=f"research:{uuid.uuid4()}",
            summary=f"Research: {refined} — {report_dict.get('summary', '')[:300]}",
            task_type="deep_research",
            agent_type="researcher",
            metadata={"query": refined, "report_title": report_dict["title"]},
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning(f"Failed to store research in memory: {exc}")
    await emit(10, "Storing in memory", "Research results stored for future reference.")

    return report_dict, steps_completed, len(all_sources)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/deep",
    response_model=DeepResearchResponse,
    summary="Execute a deep research pipeline (synchronous)",
)
async def deep_research_sync(
    payload: DeepResearchRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Run the full research pipeline and return the complete report."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    session_id = str(uuid.uuid4())
    _save_session(session_id, user_id, payload.query, None, 0, 0, "running")

    try:
        report, steps, sources = await _run_research_pipeline(
            query=payload.query,
            user_id=user_id,
            max_steps=payload.max_steps,
        )
        _save_session(session_id, user_id, payload.query, report, steps, sources, "completed")

        # Optionally link to a conversation
        if payload.conversation_id and supabase_db.client:
            try:
                summary = report.get("summary", "")[:2000]
                await (
                    supabase_db.client.table("messages")
                    .insert(
                        {
                            "conversation_id": payload.conversation_id,
                            "role": "assistant",
                            "content": f"[Deep Research: {report.get('title', '')}]\n\n{summary}",
                        }
                    )
                    .execute()
                )
            except Exception as exc:
                logger.warning(f"Failed to attach research to conversation: {exc}")

        return {
            "id": session_id,
            "report": report,
            "steps_completed": steps,
            "total_sources": sources,
        }
    except Exception as exc:
        logger.error(f"deep_research_sync failed for session {session_id}: {exc}")
        _save_session(session_id, user_id, payload.query, None, 0, 0, "failed")
        raise HTTPException(status_code=500, detail="Deep research pipeline failed.") from exc


@router.post(
    "/deep/stream",
    summary="Execute deep research with SSE streaming",
)
async def deep_research_stream(
    payload: DeepResearchRequest,
    request: Request,
    user: dict = Depends(get_current_user_token),
) -> StreamingResponse:
    """Run the research pipeline and stream each step as an SSE event."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()
    session_id = str(uuid.uuid4())
    _save_session(session_id, user_id, payload.query, None, 0, 0, "running")

    async def event_generator():
        try:
            step_queue: list[tuple[int, str, str]] = []
            done_event = False

            def on_step(step: int, name: str, content: str) -> None:
                step_queue.append((step, name, content))

            # We need to run the pipeline in a way that we can yield intermediate results.
            # Since the pipeline is async, we use an approach where we run steps and yield.
            import asyncio

            async def run_and_yield():
                nonlocal done_event
                report, steps, sources = await _run_research_pipeline(
                    query=payload.query,
                    user_id=user_id,
                    max_steps=payload.max_steps,
                    on_step=on_step,
                    session_id=session_id,
                )
                done_event = True
                return report, steps, sources

            # Start pipeline as a task
            pipeline_task = asyncio.create_task(run_and_yield())

            # Process step queue as results come in
            while not done_event or step_queue:
                if await request.is_disconnected():
                    pipeline_task.cancel()
                    return

                if step_queue:
                    step_num, step_name, content = step_queue.pop(0)
                    event = {
                        "type": "step",
                        "step": step_num,
                        "name": step_name,
                        "content": content,
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                elif done_event:
                    break
                else:
                    await asyncio.sleep(0.1)

            # Retrieve results
            try:
                report, steps, sources = await pipeline_task
            except Exception as exc:
                logger.error(f"Pipeline task failed: {exc}")
                error_event = {"type": "error", "content": str(exc)}
                yield f"data: {json.dumps(error_event)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Emit final report
            report_event = {
                "type": "report",
                "content": report,
                "steps_completed": steps,
                "total_sources": sources,
                "id": session_id,
            }
            yield f"data: {json.dumps(report_event)}\n\n"

            # Save to DB
            _save_session(session_id, user_id, payload.query, report, steps, sources, "completed")

            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error(f"deep_research_stream error: {exc}")
            error_event = {"type": "error", "content": "Internal research stream error."}
            yield f"data: {json.dumps(error_event)}\n\n"
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


@router.get(
    "/history",
    response_model=list[dict[str, Any]],
    summary="List past research sessions",
)
async def list_research_history(
    limit: int = 20,
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Return recent research sessions for the authenticated user.

    বাংলা: ``report`` কলামটি বাধ্যতামূলক — ফ্রন্টএন্ড ``DeepResearchPanel``
    ইতিহাস-ভিউয়ার সরাসরি এই ফিল্ড নিয়ে রিপোর্ট দেখায় (M08 P-A চুক্তি)।
    কলাম-তালিকা একটি কনস্ট্যান্টে পিন করা যাতে চুক্তি-টেস্ট ধরে রাখতে পারে।
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        resp = (
            await supabase_db.client.table("deep_research_sessions")
            .select(HISTORY_SELECT_COLUMNS)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.error(f"list_research_history failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch research history.") from exc


@router.get(
    "/{research_id}",
    response_model=dict[str, Any],
    summary="Get a full research report",
)
async def get_research_report(
    research_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Retrieve the complete report for a past research session."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        resp = (
            await supabase_db.client.table("deep_research_sessions")
            .select("*")
            .eq("id", research_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Research session not found.")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_research_report failed for {research_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch research report.") from exc
