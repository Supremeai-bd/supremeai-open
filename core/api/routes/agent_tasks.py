import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import get_current_user_token
from brain.agent_departments import AgentDepartment
from brain.model_router import ModelRouter
from core.generation_monitor import GenerationMonitor
from core.logging_config import logger
from core.zero_cost_architecture.swarm_orchestrator_integration import ZeroCostSwarmOrchestrator

agent_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(get_current_user_token)],
)

# FIX (AUDIT-WIRE-1): রেজিস্ট্রির register_router() সবসময় module-এর 'router'
# attribute খোঁজে — এই ফাইল শুধু 'agent_router' এক্সপোর্ট করত বলে ALL_ROUTERS-এ
# যোগ করলেও এটি silently no-op হত। ক্যানোনিকাল alias যোগ করা হলো।
router = agent_router

model_router = ModelRouter()
agent_department = AgentDepartment(model_router)
monitor = GenerationMonitor()


class SwarmExecuteRequest(BaseModel):
    task: str
    session_id: str | None = None
    user_id: str = "default_user"


def _correlation_id(request: Request) -> str:
    """Issue #685: the id assigned by SupremeContext/RequestContext middleware."""
    return getattr(request.state, "correlation_id", "") or ""


@agent_router.get("/roles")
async def list_agent_roles():
    return {"roles": agent_department.list_roles()}


@agent_router.get("/monitor/latency")
async def agent_latency_summary():
    summary = monitor.latency_summary()
    return JSONResponse(content=summary)


@agent_router.post("/swarm/execute")
async def execute_swarm(request: Request, body: SwarmExecuteRequest):
    """
    Executes the multi-agent swarm logic (Architecture -> Code -> QA)
    and returns the final workspace state.
    """
    session_id = body.session_id or str(uuid.uuid4())
    # Issue #685 (Domain 15): high-traffic router correlation logging.
    logger.info(
        "[agents.swarm_execute] session_id=%s correlation_id=%s",
        session_id,
        _correlation_id(request),
    )
    # Issue #1816 fix: the adapter's real signature is
    # ZeroCostSwarmOrchestrator(config: ZeroCostConfig | None = None) — the old
    # user_id/session_id/task_prompt kwargs raised TypeError before anything
    # ran, and it exposes execute_task()/execute_batch() (no execute()). The
    # ExecutionResult carries .workspace (SharedWorkspace) whose payload lives
    # in .work_product — there are no generated_code/architecture_design
    # attributes on the model.
    orchestrator = ZeroCostSwarmOrchestrator()
    result = await orchestrator.execute_task(body.task, body.user_id)
    workspace = result.workspace

    return {
        "status": result.status or "completed",
        "session_id": session_id,
        "task_id": result.task_id,
        "results": {
            "task_id": result.task_id,
            "passed_qa": workspace.test_results.get("passed", False),
            "feedback": workspace.test_results.get("feedback", ""),
            "generated_code": workspace.work_product.get(
                "generated_code", workspace.work_product.get("code")
            ),
            "architecture": workspace.work_product.get(
                "architecture", workspace.work_product.get("architecture_design")
            ),
            "work_product": workspace.work_product,
            "errors": result.errors or workspace.errors,
        },
    }
