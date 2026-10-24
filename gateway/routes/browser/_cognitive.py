"""SupremeBrowser advanced cognitive suite endpoints (L4 semantic click,
L4 cascade, L5 autonomous goal, L5+ swarm exploration).

Split out of the former single-module api/routes/browser.py verbatim.
Heavy browser/ dependencies are imported lazily inside the handlers,
exactly as before.
"""

import asyncio

from pydantic import BaseModel

from api.routes.browser import router
from api.routes.browser._tasks import GoalRequest


class SemanticClickRequest(BaseModel):
    target: str
    context: str = ""


class SwarmExploreRequest(BaseModel):
    site: str
    sub_goals: list[str]


@router.post("/semantic-click")
async def semantic_click(req: SemanticClickRequest):
    """L4: Click by meaning — matches natural language intent to dynamic DOM embeddings."""
    from browser.semantic_dom import SemanticDOM

    sdom = SemanticDOM(page=None)
    await sdom.build_index()
    el = await sdom.query(req.target)
    return {
        "status": "clicked",
        "matched_text": el.get("text"),
        "xpath": el.get("xpath"),
        "confidence": el.get("semantic_confidence"),
    }


@router.post("/smart-click")
async def smart_click(req: SemanticClickRequest):
    """L4 Cascade: Semantic DOM → Vision Grounding Fallback → HITL Takeover."""
    from browser.semantic_dom import ElementNotFoundSemantically, SemanticDOM
    from browser.vision_grounding import LowConfidenceGrounding, VisionGrounding

    # 1. Semantic DOM
    try:
        sdom = SemanticDOM(page=None)
        await sdom.build_index()
        el = await sdom.query(req.target)
        return {"status": "clicked", "method": "semantic_dom", "element": el}
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")

    # 2. Vision Grounding
    try:
        vg = VisionGrounding(page=None)
        click_res = await vg.click(req.target)
        return {"status": "clicked", "method": "vision_grounding", "coordinates": click_res}
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")

    # 3. HITL Takeover Escalation
    return {"status": "escalated_to_hitl", "method": "hitl", "target": req.target}


@router.post("/autonomous/run")
async def run_autonomous_goal(req: GoalRequest):
    """L5: Execute natural language browsing goal with reasoning, replanning, and memory."""
    from browser.autonomous_browser import AutonomousBrowserAgent

    agent = AutonomousBrowserAgent(session=None)
    result = await agent.achieve(req.goal)
    return result


@router.post("/swarm/explore")
async def explore_swarm(req: SwarmExploreRequest):
    """L5+: Deploy parallel agent swarm across web sub-goals and synthesize multi-agent findings."""
    from browser.swarm_browser import SwarmBrowser

    swarm = SwarmBrowser()
    result = await swarm.explore(req.site, req.sub_goals)
    return result
