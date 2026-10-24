import asyncio
import json
from typing import Any

from core.errors.error_bus import with_error_bus

try:
    import networkx as nx
except ImportError:

    class _MockDiGraph:
        def __init__(self, *args, **kwargs):
            self._nodes = {}
            self._edges = []

        def add_node(self, node_id, **kwargs):
            self._nodes[node_id] = kwargs

        def add_edge(self, u, v):
            self._edges.append((u, v))

        def has_edge(self, u, v):
            return (u, v) in self._edges

        def number_of_nodes(self):
            return len(self._nodes)

        def nodes(self, data=False):
            if data:
                return [(k, v) for k, v in self._nodes.items()]
            return list(self._nodes.keys())

        def in_degree(self):
            deg = {k: 0 for k in self._nodes}
            for _u, v in self._edges:
                if v in deg:
                    deg[v] += 1
            return deg

        def successors(self, node):
            return [v for u, v in self._edges if u == node]

    class _MockNetworkX:
        DiGraph = _MockDiGraph

        @staticmethod
        @with_error_bus("is_directed_acyclic_graph")
        def is_directed_acyclic_graph(graph):
            return True

    nx = _MockNetworkX()
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.logging_config import logger

try:
    from brain.model_router import ModelRouter
except Exception:

    class ModelRouter:
        pass


router = APIRouter(prefix="/agent", tags=["agent-planner"])


class PlanRequest(BaseModel):
    objective: str


class SelfPlanner:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        # বাংলা মন্তব্য: রানিং ব্যাকগ্রাউন্ড টাস্কগুলোর স্ট্রং রেফারেন্স ধরে রাখার জন্য সেট ইনিশিয়ালাইজেশন
        self.active_tasks: set[asyncio.Task] = set()
        logger.info("Initialized SelfPlanner")

    async def generate_plan(self, objective: str) -> nx.DiGraph:
        logger.info(f"Generating plan for objective: {objective}")

        model_router = ModelRouter()
        prompt = (
            "You are an autonomous project planner. Break down the following objective into a JSON array of tasks. "
            "Each task must have: id (string), description (string), depends_on (array of string task IDs). "
            "Return ONLY a valid JSON array without markdown wrapping or explanations.\n\n"
            f"Objective: {objective}"
        )
        try:
            result = await model_router.async_route_and_generate(
                prompt, task_type="reasoning", max_cost=0.05
            )
        except Exception as e:
            # ✅ FIXED: LLM planning failures now propagate as real errors instead of
            # being masked by a hardcoded fallback plan. A caller must know planning failed.
            logger.error(f"LLM planner call failed: {e}")
            raise RuntimeError(f"Agent planning failed: LLM call error ({e})") from e

        text = result.get("text", "") if isinstance(result, dict) else ""

        # Clean up JSON if it contains markdown blocks
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            plan = json.loads(text)
            if not isinstance(plan, list):
                err_msg = "LLM plan response was not a JSON array"
                raise TypeError(err_msg)
        except Exception as e:
            # ✅ FIXED: no more silent fallback to a hardcoded plan — an unparsable
            # response means planning genuinely failed and must be surfaced as an error.
            logger.error(f"LLM returned non-JSON/invalid plan: {e}")
            err_msg_rt = f"Agent planning failed: LLM returned an invalid plan ({e})"
            raise RuntimeError(err_msg_rt) from e

        dag = nx.DiGraph()
        for task in plan:
            dag.add_node(
                task.get("id", ""),
                description=task.get("description", ""),
                status="pending",
            )
            for dep in task.get("depends_on", []):
                dag.add_edge(dep, task.get("id", ""))

        if not nx.is_directed_acyclic_graph(dag):
            raise ValueError("Generated plan contains circular dependencies!")

        logger.info(f"Generated DAG with {dag.number_of_nodes()} tasks.")
        return dag

    def get_execution_order(self, dag: nx.DiGraph) -> list[list[str]]:
        batches = []
        in_degrees = dict(dag.in_degree())

        while in_degrees:
            current_batch = [node for node, degree in in_degrees.items() if degree == 0]
            if not current_batch:
                raise RuntimeError("Circular dependency detected during execution ordering")

            batches.append(current_batch)
            for node in current_batch:
                for successor in dag.successors(node):
                    in_degrees[successor] -= 1
                del in_degrees[node]

        return batches

    async def parallel_agent_executor(self, dag: nx.DiGraph) -> dict[str, Any]:
        """
        Executes the DAG using a breadth-first batch approach.
        Tasks in the same batch run concurrently.
        """
        batches = self.get_execution_order(dag)
        execution_results = {}

        for batch_index, batch in enumerate(batches):
            logger.info(f"Executing Batch {batch_index + 1}/{len(batches)}: {batch}")

            # Run batch concurrently
            async def run_task(task_id: str):
                desc = dag.nodes[task_id].get("description", "")
                logger.info(f"Task Started: [{task_id}] {desc}")
                # Simulate agent execution
                await asyncio.sleep(0.5)
                result = f"Completed: {desc}"
                logger.info(f"Task Completed: [{task_id}]")
                return task_id, {"status": "success", "result": result}

            tasks = [run_task(task_id) for task_id in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in batch_results:
                if isinstance(res, tuple):
                    task_id, task_res = res
                    execution_results[task_id] = task_res
                    dag.nodes[task_id]["status"] = "completed"
                else:
                    logger.error(f"Task failed with exception: {res}")

        # After all batches are complete, log the summary and return.
        # 🛑 ZERO-GAP: Removed recursive self-generating planning logic to avoid OOM loop leaks.
        final_summary = "Completed all tasks. " + json.dumps(execution_results)
        logger.info(f"Plan execution finished for objective. Summary: {final_summary[:200]}")

        return {
            "status": "completed",
            "batches_executed": len(batches),
            "results": execution_results,
            "next_plan_started": False,
        }

    # বাংলা মন্তব্য: কন্টেইনার শাটডাউনে জম্বি প্রসেস কিল করার জন্য গ্রেসফুল টিয়ারডাউন মেথড
    async def shutdown(self):
        """Cancels all currently active running planner tasks."""
        if not self.active_tasks:
            return
        logger.warning(
            f"Shutting down SelfPlanner. Cancelling {len(self.active_tasks)} active tasks..."
        )
        for task in list(self.active_tasks):
            if not task.done():
                task.cancel()

        # Wait for all tasks to finalize cancellations safely
        await asyncio.gather(*self.active_tasks, return_exceptions=True)
        self.active_tasks.clear()
        logger.info("SelfPlanner cleanup finalized.")

    @with_error_bus("validate_plan")
    def validate_plan(self, graph: Any) -> bool:
        """Backward-compatible alias for basic validation."""
        try:
            return bool(nx.is_directed_acyclic_graph(graph))
        except Exception:
            return False

    async def execute_plan(self, graph: Any) -> list[dict[str, Any]]:
        """Backward-compatible alias for parallel_agent_executor."""
        return await self.parallel_agent_executor(graph)  # type: ignore


planner = SelfPlanner()


@router.post("/plan")
async def create_plan(request: PlanRequest):
    try:
        dag = await planner.generate_plan(request.objective)
        batches = planner.get_execution_order(dag)

        # 🛑 ZERO-GAP: active_tasks সেট-এ টাস্কটি এড করে স্ট্রং রেফারেন্স ট্র্যাকিং নিশ্চিত করা হলো
        task = asyncio.create_task(planner.parallel_agent_executor(dag))
        planner.active_tasks.add(task)
        # টাস্ক সম্পন্ন হলে সেট থেকে অটো-ডিসকার্ডের কলব্যাক রেজিস্টার
        task.add_done_callback(planner.active_tasks.discard)

        nodes = []
        for n in dag.nodes(data=True):
            nodes.append(
                {
                    "id": n[0],
                    "description": n[1].get("description"),
                    "status": n[1].get("status"),
                }
            )

        return {
            "status": "success",
            "message": "Plan generated and execution started.",
            "execution_batches": batches,
            "tasks": nodes,
        }
    except Exception as e:
        # বাংলা: str(e) সরাসরি ইউজারকে দেওয়া সম্পূর্ণ নিষিদ্ধ — API key বা DB string লিক হতে পারে।
        # Internal error log-এ যাবে, ইউজার শুধু generic message দেখবে।
        logger.error(f"Planner failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Planning failed due to an internal error. Please try again later.",
        ) from e
